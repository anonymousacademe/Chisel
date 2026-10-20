// Research projects: figures, tables and equations drawn in the editor (plan-research-mode section 7.3).
// The file keeps the raw `![[fig:label]]` line / `[[fig:label]]` reference; everything here is display only.
// Python decides what exists and its number (core.objects, object_render); this file draws what it is told.
import { Facet, StateEffect, StateField, type EditorState, type Extension } from "@codemirror/state";
import { EditorView, ViewPlugin, WidgetType, type ViewUpdate } from "@codemirror/view";
import katex from "katex";
import "katex/dist/katex.min.css";
import type { ObjectKind, Span } from "./spans";

/** One entry of the bridge's object_render answer (see gui/research_objects_api.py). */
export interface ObjectInfo {
  id: string;
  kind?: ObjectKind;
  label?: string;
  caption?: string;
  number?: string | null;
  status?: string;
  width?: number | null;
  alt?: string;
  /** undefined = not loaded yet (object_render with images=false), null = the file is missing or unreadable. */
  imageUrl?: string | null;
  /** the file's version (ns, as a string) and the image's [width, height] in pixels, null when unreadable. */
  mtime?: string;
  pixels?: [number, number] | null;
  cells?: string[][] | null;
  align?: string[] | null;
  latex?: string;
  error?: string;
}

// -- KaTeX ---------------------------------------------------------------------------------------------

/**
 * The author's LaTeX as KaTeX HTML, or an error. trust stays false (so \href, \url, \includegraphics and
 * \htmlClass are refused), strict is off, expansion is capped. The HTML comes ONLY from katex.renderToString
 * of the given LaTeX; an error is returned as text, never as markup.
 */
export function renderMath(latex: string, display = true): { html: string } | { error: string } {
  try {
    const html = katex.renderToString(latex, {
      displayMode: display, throwOnError: false, trust: false, strict: "ignore", maxExpand: 500, maxSize: 20, output: "html",
    });
    // throwOnError false draws a parse error as a coloured span: show the plain source instead
    if (html.includes("katex-error")) return { error: latex };
    return { html };
  } catch {
    return { error: latex };
  }
}

// -- data cache ----------------------------------------------------------------------------------------

export interface ObjectEntry { info: ObjectInfo; stale: boolean }
export interface ObjectData { gen: number; map: ReadonlyMap<string, ObjectEntry> }

/** Fresh metadata from the bridge: {gen} the generation the request was made in. */
export const setObjectData = StateEffect.define<{ gen: number; infos: ObjectInfo[] }>();
/** One figure's image arrived (url) or is known to be unreadable (null), for the file version `mtime`. */
export const setObjectImage = StateEffect.define<{ key: string; mtime: string; url: string | null }>();
/** The workspace's objects changed (caption, image, numbering ...): every cached entry is stale until refetched. */
export const invalidateObjects = StateEffect.define<null>();

/** Everything shown except the image itself (cheap: no data URL in it). */
function metaSig(i: ObjectInfo): string {
  return JSON.stringify({ ...i, imageUrl: undefined });
}

export const objectDataField = StateField.define<ObjectData>({
  create: () => ({ gen: 0, map: new Map() }),
  update(data, tr) {
    let out = data;
    for (const e of tr.effects) {
      if (e.is(invalidateObjects)) {
        const map = new Map<string, ObjectEntry>();
        for (const [k, v] of out.map) map.set(k, { info: v.info, stale: true });
        out = { gen: out.gen + 1, map };
      } else if (e.is(setObjectData)) {
        if (e.value.gen !== out.gen) continue;        // an answer to a question asked before the last invalidation
        const map = new Map(out.map);
        for (const fresh of e.value.infos) {
          const old = map.get(fresh.id)?.info;
          let info = fresh;
          if (old && !old.error && !fresh.error) {
            // the same file version keeps its image (no refetch); unchanged content keeps the same object (no redraw)
            const sameFile = (old.mtime ?? "") === (fresh.mtime ?? "") && fresh.imageUrl === undefined;
            if (sameFile && typeof old.imageUrl === "string") info = { ...fresh, imageUrl: old.imageUrl };
            if (metaSig(old) === metaSig(info) && old.imageUrl === info.imageUrl) info = old;
          }
          map.set(fresh.id, { info, stale: false });
        }
        out = { gen: out.gen, map };
      } else if (e.is(setObjectImage)) {
        const hit = out.map.get(e.value.key);
        if (!hit || hit.info.error || (hit.info.mtime ?? "") !== e.value.mtime) continue;
        const map = new Map(out.map);
        map.set(e.value.key, { info: { ...hit.info, imageUrl: e.value.url }, stale: hit.stale });
        out = { gen: out.gen, map };
      }
    }
    return out;
  },
});

/** Called by the Edit affordance and by Ctrl-click on a reference: open the object's dialog (key "fig:label"). */
export const openObjectFacet = Facet.define<(key: string) => void, ((key: string) => void) | undefined>({
  combine: (v) => v[v.length - 1],
});

/** The keys of every placement and reference in the document's spans (the objects the widgets need). */
export function objectKeys(spans: readonly Span[]): string[] {
  const out = new Set<string>();
  for (const s of spans) if ((s.kind === "placement" || s.kind === "objref") && s.key) out.add(s.key);
  return [...out];
}

const BATCH = 200;          // the bridge refuses more ids than this per call
const MAX_IMAGES = 4;       // concurrent object_image calls
const BACKOFF_MS = 1000;

/**
 * Fetches object metadata (no images) for keys that are not cached or are stale, batched per tick, and then the
 * images of the figures that are placed in the document, one call each, at most four at a time, once per
 * (key, mtime). A key that got no answer is not asked again until an invalidation, or until the set of keys
 * changed and a backoff has passed. An answer is applied only for keys still in the document and only if no
 * invalidation happened since the request.
 */
export function objectFetcher(
  renderObjects: (keys: string[]) => Promise<ObjectInfo[]>,
  spansOf: (state: EditorState) => readonly Span[],
  fetchImage?: (label: string) => Promise<string | null>,
): Extension {
  return ViewPlugin.fromClass(class {
    inflight = new Map<string, number>();   // key -> generation it was requested in
    failed = new Map<string, { gen: number; sig: string; at: number; n: number }>();
    imgInflight = new Set<string>();        // "key|mtime"
    scheduled = false;
    destroyed = false;
    readonly view: EditorView;
    constructor(view: EditorView) { this.view = view; this.schedule(); }
    update(u: ViewUpdate) {
      const spansChanged = u.state !== u.startState && spansOf(u.state) !== spansOf(u.startState);
      const answered = u.transactions.some((t) => t.effects.some((e) => e.is(setObjectData)));
      if (spansChanged || answered || u.transactions.some((t) => t.effects.some((e) => e.is(invalidateObjects)))) this.schedule();
    }
    schedule() {
      if (this.scheduled || this.destroyed) return;
      this.scheduled = true;
      void Promise.resolve().then(() => { this.scheduled = false; this.fetch(); this.pump(); });
    }
    fetch() {
      if (this.destroyed) return;
      const state = this.view.state;
      const data = state.field(objectDataField);
      const keys = objectKeys(spansOf(state));
      const sig = [...keys].sort().join("\n");
      const now = Date.now();
      const want = keys.filter((k) => {
        const hit = data.map.get(k);
        if (hit && !hit.stale) return false;
        if (this.inflight.get(k) === data.gen) return false;
        const f = this.failed.get(k);
        if (f && f.gen === data.gen && (f.sig === sig || now - f.at < BACKOFF_MS * 2 ** Math.min(f.n, 5))) return false;
        return true;
      });
      if (!want.length) return;
      const gen = data.gen;
      for (const k of want) this.inflight.set(k, gen);
      for (let i = 0; i < want.length; i += BATCH) this.request(want.slice(i, i + BATCH), gen, sig);
    }
    request(chunk: string[], gen: number, sig: string) {
      const done = (answered: Set<string>) => {
        for (const k of chunk) {
          if (this.inflight.get(k) === gen) this.inflight.delete(k);
          if (answered.has(k)) { this.failed.delete(k); continue; }
          const n = (this.failed.get(k)?.n ?? 0) + 1;
          this.failed.set(k, { gen, sig, at: Date.now(), n });
        }
      };
      let p: Promise<ObjectInfo[]>;
      try { p = renderObjects(chunk); } catch { done(new Set()); return; }
      p.then((infos) => {
        done(new Set(infos.map((i) => i.id)));
        if (this.destroyed) return;
        const live = new Set(objectKeys(spansOf(this.view.state)));
        const keep = infos.filter((i) => live.has(i.id));
        if (keep.length) this.view.dispatch({ effects: setObjectData.of({ gen, infos: keep }) });
      }, () => done(new Set()));
    }
    /** Starts image requests for placed figures that have metadata but no image yet (never more than MAX_IMAGES). */
    pump() {
      if (this.destroyed || !fetchImage) return;
      const state = this.view.state;
      const map = state.field(objectDataField).map;
      for (const s of spansOf(state)) {
        if (this.imgInflight.size >= MAX_IMAGES) return;
        if (s.kind !== "placement" || s.objectKind !== "fig" || !s.key) continue;
        const info = map.get(s.key)?.info;
        if (!info || info.error || info.imageUrl !== undefined) continue;
        const key = s.key;
        const mtime = info.mtime ?? "";
        const id = `${key}|${mtime}`;
        if (this.imgInflight.has(id)) continue;
        this.imgInflight.add(id);
        const finish = (url: string | null) => {
          this.imgInflight.delete(id);
          if (!this.destroyed) {
            this.view.dispatch({ effects: setObjectImage.of({ key, mtime, url }) });
            this.pump();
          }
        };
        let p: Promise<string | null>;
        try { p = fetchImage(key.replace(/^fig:/, "")); } catch { finish(null); continue; }
        p.then((url) => finish(typeof url === "string" && url ? url : null), () => finish(null));
      }
    }
    destroy() { this.destroyed = true; }
  });
}

// -- widgets -------------------------------------------------------------------------------------------

const KIND_WORD: Record<ObjectKind, string> = { fig: "figure", tbl: "table", eq: "equation" };
const PX_PER_INCH = 96;

/** "Equation (3)" -> "(3)": the number sits on the right of the equation. */
function equationNumber(display: string): string {
  const m = /\([^)]*\)\s*$/.exec(display);
  return m ? m[0].trim() : display;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function caption(display: string, text: string | undefined, cls: string): HTMLElement {
  const c = el("div", cls);
  c.textContent = text ? `${display}. ${text}` : display;
  return c;
}

const infoIds = new WeakMap<ObjectInfo, number>();
let nextInfoId = 1;
/** A small identity for a cache entry (0 = none). */
function infoId(info: ObjectInfo | undefined): number {
  if (!info) return 0;
  let id = infoIds.get(info);
  if (!id) { id = nextInfoId++; infoIds.set(info, id); }
  return id;
}

/** [w, h] when the entry carries usable pixel dimensions. */
function pixelsOf(info: ObjectInfo): [number, number] | null {
  const p = info.pixels;
  return p && p.length === 2 && p[0] > 0 && p[1] > 0 && Number.isFinite(p[0]) && Number.isFinite(p[1]) ? [p[0], p[1]] : null;
}

/** The rendered figure / table / equation of a placement (a block), or the notice for a missing one. */
export class ObjectBlockWidget extends WidgetType {
  readonly sig: string;
  readonly key: string;
  readonly kind: ObjectKind;
  readonly display: string;
  readonly resolved: boolean;
  readonly info: ObjectInfo | undefined;
  readonly above: boolean;
  constructor(key: string, kind: ObjectKind, display: string, resolved: boolean, info: ObjectInfo | undefined, above: boolean) {
    super();
    this.key = key; this.kind = kind; this.display = display; this.resolved = resolved; this.info = info; this.above = above;
    // what the DOM shows, by identity: the cache hands out the same info object until something shown changes,
    // so eq() never looks at (or serialises) image data
    this.sig = `${key}|${kind}|${display}|${resolved}|${above}|${infoId(info)}`;
  }
  eq(o: ObjectBlockWidget) { return o.sig === this.sig; }
  get estimatedHeight() { return this.kind === "fig" ? 270 : this.kind === "tbl" ? 60 : 50; }

  toDOM(view?: EditorView) {
    const box = el("div", `lw-object lw-object--${this.kind}${this.above ? " lw-object--above" : ""}`);
    box.setAttribute("data-object", this.key);
    box.contentEditable = "false";
    const info = this.info;
    if (!this.resolved || (info && info.error)) {
      const word = KIND_WORD[this.kind];
      box.classList.add("lw-object--missing");
      box.append(el("div", "lw-object__notice", info?.error && this.resolved ? `Cannot show ${word} ${this.key}: ${info.error}` : `Missing ${word}: ${this.key}`));
    } else if (!info) {
      box.classList.add("lw-object--pending");
      box.append(this.placeholder());
    } else if (this.kind === "fig") {
      this.figure(box, info, view);
    } else if (this.kind === "tbl") {
      this.table(box, info);
    } else {
      this.equation(box, info);
    }
    if (this.resolved) {
      const edit = el("button", "lw-object__edit", "Edit");
      edit.type = "button";
      edit.title = `Open ${this.display}`;
      edit.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); });
      edit.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        view?.state.facet(openObjectFacet)?.(this.key);
      });
      box.append(edit);
    }
    return box;
  }

  /** A box of the final size class, so the layout does not jump when the data arrives. */
  private placeholder(): HTMLElement {
    const p = el("div", `lw-object__placeholder lw-object__placeholder--${this.kind}`);
    p.textContent = this.display;
    return p;
  }

  private figure(box: HTMLElement, info: ObjectInfo, view?: EditorView) {
    const fig = el("figure", "lw-object__figure");
    const px = pixelsOf(info);
    const sized = info.width && info.width > 0 ? `${Math.min(info.width, 20) * PX_PER_INCH}px` : null;
    if (info.imageUrl === undefined) {
      // the image is on its way: hold its final box (same ratio and width) so nothing jumps on arrival
      const ph = el("div", "lw-object__placeholder lw-object__placeholder--fig", this.display);
      if (px) {
        ph.style.aspectRatio = `${px[0]} / ${px[1]}`;
        ph.style.width = sized ?? `min(100%, ${px[0]}px)`;
      }
      fig.append(ph);
    } else if (info.imageUrl) {
      const img = el("img", "lw-object__img");
      img.alt = info.alt || info.caption || info.label || "";
      img.draggable = false;
      if (px) {
        img.setAttribute("width", String(px[0]));
        img.setAttribute("height", String(px[1]));
        img.style.aspectRatio = `${px[0]} / ${px[1]}`;
      }
      if (sized) img.style.width = sized;
      img.addEventListener("load", () => view?.requestMeasure());
      img.src = info.imageUrl;
      fig.append(img);
    } else {
      fig.append(el("div", "lw-object__placeholder lw-object__placeholder--fig", "Image file not found"));
    }
    fig.append(caption(this.display, info.caption, "lw-object__caption"));
    box.append(fig);
  }

  private table(box: HTMLElement, info: ObjectInfo) {
    const wrap = el("div", "lw-object__tablewrap");
    wrap.append(caption(this.display, info.caption, "lw-object__caption lw-object__caption--top"));
    const cells = info.cells;
    if (!cells || !cells.length) {
      wrap.append(el("div", "lw-object__placeholder lw-object__placeholder--tbl", "Table has no readable cells"));
    } else {
      const t = el("table", "lw-object__table");
      cells.forEach((row, r) => {
        const tr = el("tr", "");
        row.forEach((c, i) => {
          const td = el(r === 0 ? "th" : "td", "", c);
          const a = info.align?.[i];
          if (a === "left" || a === "right" || a === "center") td.style.textAlign = a;
          tr.append(td);
        });
        (r === 0 ? t.createTHead() : (t.tBodies[0] ?? t.createTBody())).append(tr);
      });
      wrap.append(t);
    }
    box.append(wrap);
  }

  private equation(box: HTMLElement, info: ObjectInfo) {
    const row = el("div", "lw-object__eqrow");
    const body = el("div", "lw-object__eq");
    const out = renderMath(info.latex ?? "", true);
    if ("html" in out) body.innerHTML = out.html;      // KaTeX output of the author's LaTeX only (see renderMath)
    else { body.classList.add("lw-object__eq--error"); body.textContent = out.error; }
    row.append(body, el("div", "lw-object__eqno", equationNumber(this.display)));
    box.append(row);
    if (info.caption) box.append(caption(this.display, info.caption, "lw-object__caption"));
  }

  ignoreEvent(e: Event) {
    const t = e.target as HTMLElement | null;
    return !!t?.closest?.(".lw-object__edit");
  }
}

/** A reference inside prose: "Figure 2" as a link-like word; the raw `[[fig:label]]` stays in the document. */
export class ObjectRefWidget extends WidgetType {
  readonly key: string;
  readonly display: string;
  readonly status: string;
  constructor(key: string, display: string, status: string) { super(); this.key = key; this.display = display; this.status = status; }
  eq(o: ObjectRefWidget) { return o.key === this.key && o.display === this.display && o.status === this.status; }
  toDOM() {
    const e = el("span", `lw-objref lw-objref--shown ${this.status === "resolved" ? "lw-objref--resolved" : "lw-objref--unresolved"}`, this.display);
    e.setAttribute("data-object", this.key);
    return e;
  }
  // false: a click still moves the cursor in (revealing the raw text); Ctrl-click is handled by the editor
  ignoreEvent() { return false; }
}
