// Dev-only fake of the figure / table / equation bridge (wave F): the contract of research_objects_api.py with a small
// in-memory set of objects. Never reachable in the real app (transport.ts only loads mock.ts without a core).
import type { ObjectKind, ObjectRow, TableAlign, TrustState } from "../data/research";
import type { BinderNode } from "../data/types";

const PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const NAMES: Record<ObjectKind, string> = { fig: "Figure", tbl: "Table", eq: "Equation" };
const GROUPS: [string, string, ObjectKind][] = [["group:figures", "Figures", "fig"], ["group:tables", "Tables", "tbl"], ["group:equations", "Equations", "eq"]];

interface MockObject extends ObjectRow {
  cells?: string[][]; tAlign?: TableAlign[]; latex?: string; mtime?: string; script?: string; trust?: TrustState;
}
const base = (kind: ObjectKind, label: string, caption: string, over: Partial<MockObject> = {}): MockObject =>
  ({ kind, label, id: `${kind}:${label}`, path: `${{ fig: "figures", tbl: "tables", eq: "equations" }[kind]}/${kind}-${label}.md`, caption,
    source: "static", file: null, width: null, alt: "", status: "current", ...over });

const seed = (): MockObject[] => [
  base("fig", "flow-model", "Flow through the treatment train", { file: "figures/fig-flow-model.png", alt: "A flow diagram" }),
  base("fig", "effluent-trend", "Effluent ammonia over the study period", { source: "script", file: "figures/fig-effluent-trend.png", script: "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.savefig('out.png')\n", trust: "untrusted", status: "stale" }),
  base("tbl", "site-summary", "Summary of the three sites", { cells: [["Site", "Flow (m3/d)"], ["A", "1200"], ["B", "860"]], tAlign: ["left", "right"], mtime: "1" }),
  base("tbl", "kpi-table", "Indicators built from the data", { source: "data", cells: [["Indicator", "Value"], ["NH4", "1.2"]], tAlign: ["default", "default"], mtime: "1" }),
  base("eq", "monod", "Monod growth rate", { latex: "\\mu = \\mu_{max}\\frac{S}{K_s + S}" }),
];
let items: MockObject[] = seed();
let jobs = new Map<string, { id: string; polls: number; cancelled: boolean }>();
let jobSeq = 0;
/** Which documents place / mention which objects (the mock has no sections). */
const USES: Record<string, { placements: { doc: string; title: string; row: number }[]; refs: { doc: string; title: string; row: number }[] }> = {
  "fig:flow-model": { placements: [{ doc: "manuscript/01-introduction.md", title: "Introduction", row: 6 }], refs: [{ doc: "manuscript/02-methods.md", title: "Methods", row: 3 }] },
  "eq:monod": { placements: [{ doc: "manuscript/02-methods.md", title: "Methods", row: 9 }, { doc: "manuscript/03-results.md", title: "Results", row: 2 }], refs: [] },
};

export function resetMockObjects() { items = seed(); jobs = new Map(); jobSeq = 0; }

const number = (o: MockObject) => `${o.kind === "eq" ? "Equation (" : NAMES[o.kind] + " "}${items.filter((x) => x.kind === o.kind).indexOf(o) + 1}${o.kind === "eq" ? ")" : ""}`;
const row = (o: MockObject): ObjectRow => ({
  kind: o.kind, label: o.label, id: o.id, path: o.path, caption: o.caption, source: o.source, file: o.file, width: o.width, alt: o.alt, status: o.status,
  number: { seq: items.filter((x) => x.kind === o.kind).indexOf(o) + 1, display: number(o) },
});
const find = (id: unknown) => items.find((o) => o.id === String(id));
const err = (error: string) => ({ ok: false, error });
const LABEL = /^[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*$/;

/** The Figures / Tables / Equations groups of the binder (only the ones that have objects). */
export function mockObjectGroups(): BinderNode[] {
  return GROUPS.flatMap(([id, title, kind]) => {
    const own = items.filter((o) => o.kind === kind);
    return own.length ? [{ id, title, kind: "objects" as const, children: own.map((o) => ({ id: o.id, title: `${number(o)}: ${o.caption || o.label}`, kind: "object" as const, meta: o.status })) }] : [];
  });
}

function create(kind: ObjectKind, label: unknown, caption: unknown, over: Partial<MockObject>) {
  const l = String(label ?? "");
  if (!LABEL.test(l)) return err("A label may use letters, digits, - . and _ only.");
  if (find(`${kind}:${l}`)) return err(`There is already a ${NAMES[kind].toLowerCase()} labelled ${l}.`);
  const o = base(kind, l, String(caption ?? ""), over);
  items.push(o);
  return { ok: true, id: o.id, object: row(o) };
}

export function mockObjectsCall(method: string, args: unknown[]): object | undefined {
  switch (method) {
    case "list_objects": return { ok: true, objects: items.map(row) };
    case "object_numbers": return { ok: true, numbers: Object.fromEntries(items.map((o) => [o.id, row(o).number])) };
    case "object_render": {
      const out = (args[0] as string[]).map((id) => {
        const o = find(id);
        if (!o) return { id, error: `no such object: ${id}` };
        const r = row(o);
        return {
          id: o.id, kind: o.kind, label: o.label, caption: o.caption, number: r.number?.display ?? null, seq: r.number?.seq ?? null, status: o.status, source: o.source, path: o.path,
          ...(o.kind === "fig" ? { imageUrl: o.status === "missing" ? null : PIXEL, width: o.width, alt: o.alt } : {}),
          ...(o.kind === "tbl" ? { cells: o.cells, align: o.tAlign, mtime: o.mtime, generated: o.source === "data" } : {}),
          ...(o.kind === "eq" ? { latex: o.latex } : {}),
        };
      });
      return { ok: true, objects: out };
    }
    case "object_suggest_label": {
      const slug = String(args[1] ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").split("-").slice(0, 4).join("-") || NAMES[args[0] as ObjectKind].toLowerCase();
      let label = slug, n = 2;
      while (find(`${String(args[0])}:${label}`)) label = `${slug}-${n++}`;
      return { ok: true, label };
    }
    case "object_references": {
      const o = find(args[0]);
      return o ? { ok: true, ...(USES[o.id] ?? { placements: [], refs: [] }) } : err(`no such object: ${String(args[0])}`);
    }
    case "update_object": {
      const o = find(args[0]);
      if (!o) return err(`no such object: ${String(args[0])}`);
      const [, caption, alt, width, latex] = args as [unknown, string | null, string | null, number | null, string | null];
      if (width !== null && width !== undefined && (o.kind !== "fig" || !(width >= 1 && width <= 20))) return err("The width must be 1 to 20 inches.");
      if (caption !== null && caption !== undefined) o.caption = caption;
      if (alt !== null && alt !== undefined && o.kind === "fig") o.alt = alt;
      if (width !== null && width !== undefined) o.width = width;
      if (latex !== null && latex !== undefined && o.kind === "eq") o.latex = latex;
      return { ok: true, object: row(o) };
    }
    case "trash_object": {
      const o = find(args[0]);
      if (!o) return err(`no such object: ${String(args[0])}`);
      items = items.filter((x) => x !== o);
      return { ok: true, trashed: true, name: o.path.split("/").pop() };
    }
    case "insert_figure": {
      if (!String(args[0] ?? "").startsWith("data:image/")) return err("the image must be sent as a base64 data URL");
      return create("fig", args[1], args[2], { file: `figures/fig-${String(args[1])}.png` });
    }
    case "create_table": {
      const cells = args[2] as string[][];
      if (!Array.isArray(cells) || !cells.length) return err("a table needs a header row and at least one column");
      return create("tbl", args[0], args[1], { cells, tAlign: args[3] as TableAlign[], mtime: "1" });
    }
    case "create_equation": {
      if (!String(args[1] ?? "").trim()) return err("the equation is empty");
      return create("eq", args[0], args[2], { latex: String(args[1]) });
    }
    case "read_table": {
      const o = find(args[0]);
      if (!o || o.kind !== "tbl") return err(`no such table: ${String(args[0])}`);
      return { ok: true, id: o.id, caption: o.caption, cells: o.cells, align: o.tAlign, mtime: o.mtime, generated: o.source === "data" };
    }
    case "save_table": {
      const o = find(args[0]);
      if (!o || o.kind !== "tbl") return err(`no such table: ${String(args[0])}`);
      if (o.source === "data") return err("this table is built from data; edit the data or its format instead");
      if (String(args[3]) !== o.mtime) return { ok: false, conflict: true, mtime: o.mtime, error: "This table changed on disk since you opened it. Reload it before saving." };
      o.cells = args[1] as string[][]; o.tAlign = args[2] as TableAlign[]; o.mtime = String(Number(o.mtime) + 1);
      return { ok: true, id: o.id, mtime: o.mtime };
    }
    case "build_table": {
      const o = find(args[0]);
      if (!o || o.kind !== "tbl") return err(`no such table: ${String(args[0])}`);
      return { ok: true, id: o.id, markdown: "", grid: [...(o.cells ?? []), ["TN", "9.8"]], latex: "", warnings: ["1 row had no value."], caption: o.caption, footnotes: [] };
    }
    case "apply_table": {
      const o = find(args[0]);
      if (!o || o.kind !== "tbl") return err(`no such table: ${String(args[0])}`);
      o.cells = [...(o.cells ?? []), ["TN", "9.8"]]; o.mtime = String(Number(o.mtime) + 1);
      return { ok: true, id: o.id, mtime: o.mtime, markdown: "", grid: o.cells, latex: "", warnings: [], caption: o.caption, footnotes: [] };
    }
    case "figure_trust_info": {
      const o = find(args[0]);
      if (!o || o.kind !== "fig" || o.source !== "script") return err(`no such figure: ${String(args[0])}`);
      return { ok: true, id: o.id, script: o.script, sha: `mocksha-${(o.script ?? "").length}`, path: "figures/scripts/effluent_trend.py", interpreter: "/usr/bin/python3", data: ["data/effluent.csv"], trust: o.trust };
    }
    case "trust_figure": {
      const o = find(args[0]);
      if (!o || o.kind !== "fig") return err(`no such figure: ${String(args[0])}`);
      if (String(args[1]) !== `mocksha-${(o.script ?? "").length}`) return err("the script changed after you read it; read it again");
      o.trust = "trusted";
      return { ok: true, id: o.id, trust: o.trust };
    }
    case "figure_run_start": {
      const o = find(args[0]);
      if (!o || o.kind !== "fig") return err(`no such figure: ${String(args[0])}`);
      if (o.trust !== "trusted") return err("this script has not been confirmed; review and confirm it first");
      const job = `f${++jobSeq}`;
      jobs.set(job, { id: o.id, polls: 0, cancelled: false });
      return { ok: true, job, id: o.id };
    }
    case "figure_run_status": {
      const j = jobs.get(String(args[0]));
      if (!j) return err("unknown figure run (it may have expired)");
      if (j.cancelled) return { ok: true, job: String(args[0]), figure: j.id, state: "cancelled", error: "", stderr: "" };
      if (++j.polls < 3) return { ok: true, job: String(args[0]), figure: j.id, state: "running" };
      const o = find(j.id); if (o) o.status = "current";
      return { ok: true, job: String(args[0]), figure: j.id, state: "done", error: "", stderr: "" };
    }
    case "figure_run_cancel": {
      const j = jobs.get(String(args[0]));
      if (!j) return err("unknown figure run (it may have expired)");
      j.cancelled = true;
      return { ok: true, job: String(args[0]), state: "cancelled" };
    }
    case "suggest_latex":
      return { ok: true, text: "\\mu = \\mu_{max}\\frac{S}{K_s + S + S^2/K_i}", model: "mock", cost: 0.0004 };
    default: return undefined;
  }
}
