// Drives headless Chromium against build/gui_server.py and saves the GUI figures
// to build/guishots/. Usage: node gui_capture.mjs URL CDP_PORT PROJECT_DIR [stage]
import fs from "node:fs";
import path from "node:path";
import { connect } from "./cdp.mjs";

const [url, port, project, only] = process.argv.slice(2);
const OUT = path.join(path.dirname(new URL(import.meta.url).pathname), "guishots");
fs.mkdirSync(OUT, { recursive: true });
const c = await connect(Number(port));
const W = 1280, H = 800;
await c.size(W, H, 2);

const out = (n) => path.join(OUT, n + ".png");
const sleep = c.sleep;
const shot = async (name, clip) => { await c.shot(out(name), clip); console.log("shot", name); };
/** Screenshot of one element (plus padding), css pixels. */
const shotEl = async (name, sel, text, pad = 0, extra = {}) => {
  const r = await c.rect(sel, text);
  if (!r) throw new Error("no element for " + name + ": " + sel);
  const x = Math.max(0, r.x - pad), y = Math.max(0, r.y - pad);
  await shot(name, { x, y, width: Math.min(W - x, r.w + 2 * pad), height: Math.min(H - y, r.h + 2 * pad), ...extra });
};
const load = async (waitFor = ".lw-binder") => {
  await c.goto(url);
  for (let i = 0; i < 40; i++) { if (await c.rect(waitFor)) break; await sleep(250); }
  await sleep(900);
};
const stage = (n) => !only || only === n;
const text = (sel) => c.eval(`document.querySelector(${JSON.stringify(sel)})?.innerText ?? null`);
const openScene = async (title) => { await c.click(".lw-binder__item", title); await sleep(900); };
const cmEnd = () => c.eval(`(() => { const v = document.querySelector('.cm-content'); v.focus(); return true; })()`);

// ---------------------------------------------------------------- A: launch (no project)
if (stage("launch")) {
  // the server was started without a project: the launch screen is what shows
  await load(".lw-launch");
  // the paths of the temporary copies are replaced by a tidy home directory, as in the TUI figures
  await c.eval(`document.querySelectorAll('.lw-launch__recent .lw-mono').forEach((e) => { e.textContent = e.textContent.replace(/^.*\\/(residual|the-salt-road)$/, '/home/writer/novels/$1'); })`);
  await shotEl("launch", ".lw-launch__card", undefined, 16);
  await c.click(".lw-launch__input[aria-label='New project title']");
  await c.type("The Salt Road");
  await sleep(700);
  await c.eval(`document.querySelectorAll('input[aria-label="New project folder"]').forEach((e) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, '/home/writer/novels/the-salt-road'); e.dispatchEvent(new Event('input', { bubbles: true })); })`);
  await sleep(300);
  await shotEl("launch_new", ".lw-launch__card", undefined, 16);
}

// ---------------------------------------------------------------- B: window
if (stage("window")) {
  await load();
  await openScene("Rain on the Spur");
  await shot("main");
  await shotEl("binder", ".lw-binder", undefined, 0);
  await shotEl("rail", ".lw-rail", undefined, 0);
  await shotEl("titlebar", ".lw-titlebar", undefined, 0);
  await shotEl("statusbar", ".lw-status", undefined, 0);
  await shotEl("toolbar", ".lw-editor__toolbar", undefined, 0);
  await shotEl("editor", ".lw-editor", undefined, 0);
  // views
  await c.click(".lw-viewmode", "Corkboard"); await sleep(500);
  await shotEl("corkboard", ".lw-editor", undefined, 0);
  await c.click(".lw-viewmode", "Outline"); await sleep(500);
  await shotEl("outline", ".lw-editor", undefined, 0);
  await c.click(".lw-viewmode", "Manuscript"); await sleep(500);
  // assistant tabs
  await c.click(".lw-tab", "Context"); await sleep(400);
  await shotEl("assistant_context", ".lw-assistant");
  await c.click(".lw-tab", "Notes"); await sleep(400);
  await shotEl("assistant_notes_empty", ".lw-assistant");
  await c.click(".lw-tab", "Assistant"); await sleep(400);
  await shotEl("assistant", ".lw-assistant");
  // library view
  await c.click(".lw-rail__item[aria-label='Library']"); await sleep(600);
  await shotEl("library", ".lw-binder");
  await c.click(".lw-rail__item[aria-label='Binder']"); await sleep(600);
  // quick switcher
  await c.key("k", { ctrl: true }); await sleep(500);
  await c.type("sal"); await sleep(500);
  await shotEl("switcher", ".lw-switcher", undefined, 0);
  await c.key("Escape"); await sleep(300);
  // focus mode
  await c.key("F11"); await sleep(600);
  await shot("focus");
  await c.key("F11"); await sleep(400);
  // placeholder tooltip target
  await shotEl("placeholders", ".lw-collections", undefined, 0);
  // scene menu
  await c.click("button[aria-label*='options']"); await sleep(400);
  await shotEl("scenemenu", ".lw-menu", undefined, 10);
  await c.key("Escape"); await sleep(300);
  await c.click("button[aria-label='More']"); await sleep(400);
  await shotEl("projectmenu", ".lw-menu", undefined, 10);
  await c.key("Escape"); await sleep(300);
  await c.click("button[aria-label='More AI actions']"); await sleep(400);
  await shotEl("aimenu", ".lw-menu", undefined, 10);
  await c.key("Escape"); await sleep(300);
}

// ---------------------------------------------------------------- helpers for text
/** Viewport rect of the first occurrence of `needle` in the editor text (start..end of the match). */
const textRect = (needle, nth = 0) => c.eval(`(() => {
  const root = document.querySelector('.cm-content');
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n, seen = 0;
  while ((n = w.nextNode())) {
    let i = -1, from = 0;
    while ((i = n.data.indexOf(${JSON.stringify(needle)}, from)) !== -1) {
      if (seen++ === ${nth}) {
        const a = document.createRange(); a.setStart(n, i); a.setEnd(n, i + 1);
        const z = document.createRange(); z.setStart(n, i + ${needle.length} - 1); z.setEnd(n, i + ${needle.length});
        const ra = a.getBoundingClientRect(), rz = z.getBoundingClientRect();
        const all = document.createRange(); all.setStart(n, i); all.setEnd(n, i + ${needle.length});
        const r = all.getClientRects()[0];
        return { x0: ra.left, y0: ra.top + ra.height / 2, x1: rz.right, y1: rz.top + rz.height / 2, cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
      }
      from = i + 1;
    }
  }
  return null;
})()`);
const reveal = async (needle) => {
  for (const top of [0, 250, 500, 750, 1000, 1500]) {
    await scrollEditor(top); await sleep(250);
    const r = await textRect(needle);
    if (r && r.y0 > 180 && r.y0 < 600) return r;
  }
  throw new Error("cannot reveal " + needle);
};
const clickText = async (needle, opts = {}) => {
  const r = await textRect(needle, opts.nth ?? 0);
  if (!r) throw new Error("text not found: " + needle);
  await c.clickAt(opts.atEnd ? r.x1 - 1 : r.cx, r.cy, opts);
  return r;
};
const selectText = async (needle, len = needle.length) => {
  const r = await textRect(needle);
  if (!r) throw new Error("text not found: " + needle);
  await c.clickAt(r.x0 + 1, r.y0, { wait: 150 });
  await c.key("Home", { wait: 50 }); // not used for the caret; clicking set it
  await c.clickAt(r.x0 + 1, r.y0, { wait: 150 });
  for (let i = 0; i < len; i++) await c.key("ArrowRight", { shift: true, wait: 15 });
  await c.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 1000, y: 790 });
  await sleep(450);
};
const scrollEditor = (where) => c.eval(`(() => { const s = document.querySelector('.lw-editor__scroll'); s.scrollTop = ${where === "end" ? "s.scrollHeight" : where}; })()`);
const pending = () => c.eval(`document.querySelectorAll('.lw-draft').length`);
const clickBtn = (label) => c.click("button", label);
const aiMenu = async (item) => { await c.click("button[aria-label='More AI actions']"); await sleep(300); await c.click(".lw-menu__item", item); };
const eyes = () => fs.readFileSync(path.join(project, "manuscript", "01-the-recall", "02-capsule-7-19.md"), "utf8");

// ---------------------------------------------------------------- C: spelling, notes, hover
if (stage("spell")) {
  await load();
  await openScene("Rain on the Spur");
  await shotEl("statusbar_spell", ".lw-status");
  await clickText("maglev");
  await sleep(500);
  await shot("spell_popover_full");
  const pop = await c.rect(".lw-spellmenu");
  await shot("spell_popover", { x: Math.max(330, pop.x - 120), y: Math.max(0, pop.y - 70), width: 420, height: pop.h + 120 });
  await c.key("Escape"); await sleep(300);
  await selectText("sweet rot");
  await sleep(300);
  console.log("selection:", JSON.stringify(await c.eval("window.getSelection().toString()")));
  await c.key(".", { ctrl: true }); await sleep(500);
  const pop2 = await c.rect(".lw-spellmenu");
  if (pop2) await shot("spell_phrase", { x: Math.max(330, pop2.x - 120), y: Math.max(0, pop2.y - 120), width: 420, height: pop2.h + 180 });
  await c.key("Escape"); await sleep(300);
  // dictionary file
  await c.click(".lw-binder__item", "Dictionary"); await sleep(900);
  await shotEl("dictionary", ".lw-editor");
  await openScene("Rain on the Spur");
}
if (stage("notes")) {
  await load();
  await openScene("Rain on the Spur");
  const m = await c.rect(".lw-mention", "Kessler");
  await c.hover(m.cx, m.cy);
  const hc = await c.rect(".lw-hovercard");
  if (hc) { const x0 = Math.max(330, hc.x - 30); await shot("hovercard", { x: x0, y: Math.max(0, hc.y - 110), width: Math.min(500, 905 - x0), height: hc.h + 250 }); }
  const rt = await c.rect(".lw-mention", "Rook Tanaka");
  await c.clickAt(rt.cx, rt.cy, { ctrl: true, wait: 900 });
  await sleep(800);
  await c.click(".lw-tab", "Notes"); await sleep(500);
  await shotEl("assistant_notes", ".lw-assistant");
  await c.click(".lw-tab", "Assistant");
}
const focusEditor = async () => { const r = await c.rect('.cm-line:not(.lw-blank)'); await c.clickAt(r.x + 20, r.y + r.h / 2, { wait: 200 }); };
const dialogShot = (name, pad = 0) => shotEl(name, ".lw-dialog", undefined, pad);
const waitFor = async (sel, ms = 8000) => { for (let t = 0; t < ms; t += 200) { if (await c.rect(sel)) return true; await sleep(200); } throw new Error("timeout waiting for " + sel); };

// ---------------------------------------------------------------- D: consistency features
if (stage("consistency")) {
  await load();
  // alias finder (scene 3)
  await openScene("The Stairwell");
  const before = fs.readFileSync(path.join(project, "manuscript", "02-ghost-frequency", "01-the-stairwell.md"), "utf8");
  await aiMenu("Find aliases");
  await waitFor(".lw-dialog");
  await sleep(500);
  await c.click("button", "Select all"); await sleep(300);
  await dialogShot("aliasreview");
  await c.click("button.lw-btn--primary"); await sleep(1200);
  if (fs.readFileSync(path.join(project, "manuscript", "02-ghost-frequency", "01-the-stairwell.md"), "utf8") !== before) throw new Error("alias finder edited the scene");
  // continuity (scene 2)
  await openScene("Capsule 7-19");
  await c.click(".lw-tool", "Continuity");
  await waitFor(".lw-insight--card, .lw-insight__kind");
  await sleep(600);
  await shotEl("assistant_continuity", ".lw-assistant");
  const card = await c.rect(".lw-insight", "Continuity check");
  await shot("continuity_card", { x: card.x - 8, y: card.y - 8, width: card.w + 16, height: card.h + 16 });
  await c.click("button", "Review passage"); await sleep(700);
  await shot("continuity_review");
  // story bible (scene 2)
  await aiMenu("Update story bible");
  await waitFor(".lw-dialog"); await sleep(500);
  await c.click("button", "Select all"); await sleep(300);
  await dialogShot("canonreview");
  await c.key("Escape"); await sleep(400);
  // dismiss = waive, then restore
  await c.click("button", "Dismiss"); await sleep(600);
  await shotEl("assistant_dismissed", ".lw-assistant");
  await aiMenu("Restore waived issues"); await sleep(800);
  await shot("toast_restore");
}

// ---------------------------------------------------------------- E: style card
if (stage("style")) {
  await load();
  await openScene("Rain on the Spur");
  const card0 = await c.rect("section[aria-label='Your style']");
  await shot("stylecard_before", { x: card0.x - 8, y: card0.y - 8, width: card0.w + 16, height: card0.h + 16 });
  await c.click("button", "Learn my style");
  await waitFor(".lw-dialog"); await sleep(600);
  await dialogShot("stylereview");
  await c.click("button", "Save style guide"); await sleep(1500);
  await openScene("Rain on the Spur");
  const card1 = await c.rect("section[aria-label='Your style']");
  await shot("stylecard_after", { x: card1.x - 8, y: card1.y - 8, width: card1.w + 16, height: card1.h + 16 });
  await c.click("button", "Open guide"); await sleep(1000);
  await shotEl("styleguide", ".lw-editor");
}

// ---------------------------------------------------------------- F: writing (draft, expand, rewrite)
if (stage("writing")) {
  await load();
  await openScene("Ghost in the Ice");
  // put the caret at the very end
  await focusEditor(); await c.key("End", { ctrl: true });
  await c.key("g", { ctrl: true }); await waitFor(".lw-dialog"); await sleep(400);
  await c.type("One paragraph: the company flyer's searchlight finds the window. Rook goes still. Dread, not panic.");
  await dialogShot("generate_dialog");
  await c.key("Enter", { wait: 1500 });
  await waitFor(".lw-draft"); await sleep(600);
  await scrollEditor("end"); await sleep(400);
  await shotEl("draft", ".lw-editor__surface");
  const bar = await c.rect(".lw-draftbar");
  if (bar) await shot("draftbar", { x: Math.max(330, bar.x - 90), y: Math.max(0, bar.y - 150), width: 520, height: 190 });
  await shotEl("statusbar_cost", ".lw-status");
  await c.click(".lw-draftbar__btn.is-accept"); await sleep(700);
  await shotEl("draft_accepted", ".lw-editor__surface");
  // expand placeholder (scene 2)
  await openScene("Capsule 7-19");
  await focusEditor();
  const rl = await reveal(" lay on her back");
  await c.clickAt(rl.x0 + 1, rl.y0, { wait: 150 });
  await c.key("Home", { wait: 100 });
  await c.type("{{expand: the lobby of the Meridian at 3 a.m., wet and humming}}");
  await c.key("Enter", { wait: 80 }); await c.key("Enter", { wait: 80 });
  await sleep(400);
  const pill = await c.rect(".lw-expand");
  await c.clickAt(pill.x + pill.w / 2, pill.y + pill.h / 2, { wait: 300 });
  await shotEl("expand_marker", ".lw-editor__surface");
  await c.key("g", { ctrl: true, wait: 1800 });
  await waitFor(".lw-draft"); await sleep(500);
  await shotEl("expand_draft", ".lw-editor__surface");
  const sidecar = fs.readdirSync(path.join(project, ".drafts"));
  console.log("sidecars:", sidecar);
  await c.key("F8", { wait: 700 });
  if (await pending()) throw new Error("reject did not clear the draft");
  await shotEl("expand_rejected", ".lw-editor__surface");
  // rewrite a selection (scene 3)
  await openScene("The Stairwell");
  await focusEditor();
  await reveal(" sat in ");
  await selectText("The shard", "The shard sat in Rook's pocket like a coin from another country.".length);
  await shotEl("rewrite_selected", ".lw-editor__surface");
  await c.key("g", { ctrl: true }); await waitFor(".lw-dialog"); await sleep(400);
  await dialogShot("rewrite_dialog");
  await c.key("Enter", { wait: 1800 });
  await waitFor(".lw-draft"); await sleep(500);
  await shotEl("rewrite_draft", ".lw-editor__surface");
  console.log("sidecars:", fs.readdirSync(path.join(project, ".drafts")));
  await c.key("F8", { wait: 700 });
  await shotEl("rewrite_rejected", ".lw-editor__surface");
}

// ---------------------------------------------------------------- G: chat
if (stage("chat")) {
  await load();
  await openScene("Rain on the Spur");
  await c.click("textarea"); await c.type("How can I make this scene more tense without adding an event?");
  await c.key("Enter", { wait: 2000 });
  await sleep(800);
  await shotEl("chat", ".lw-assistant");
}

// ---------------------------------------------------------------- H: settings, conflict
if (stage("settings")) {
  await load();
  await openScene("Rain on the Spur");
  await c.size(W, 1300, 2);
  await sleep(500);
  await c.click(".lw-rail__item[aria-label='Settings']"); await waitFor(".lw-dialog"); await sleep(600);
  const dlg = await c.rect(".lw-dialog");
  await shot("settings", { x: dlg.x, y: dlg.y, width: dlg.w, height: dlg.h });
  await c.eval(`[...document.querySelectorAll('button')].filter((b) => b.textContent.includes('Choose')).at(2).click()`);
  await sleep(1500);
  await c.type("llama"); await sleep(500);
  const dlg2 = await c.rect(".lw-dialog");
  await shot("settings_picker", { x: dlg2.x, y: dlg2.y, width: dlg2.w, height: dlg2.h });
  await c.key("Escape"); await sleep(300);
  await c.size(W, H, 2);
}
if (stage("conflict")) {
  await load();
  await openScene("Rain on the Spur");
  await focusEditor();
  await c.key("End", { ctrl: true });
  await c.type(" (typing in the app)");
  const f = path.join(project, "manuscript", "01-the-recall", "01-rain-on-the-spur.md");
  fs.appendFileSync(f, "\nA line added by the terminal app.\n");
  const t = new Date(Date.now() + 5000); fs.utimesSync(f, t, t);
  await sleep(3500);
  await waitFor(".lw-conflict", 6000);
  await shotEl("conflict", ".lw-conflict", undefined, 0);
  await shot("conflict_full");
  await c.click("button", "Keep my version"); await sleep(1500);
}

// ================================================================ Fourth Edition stages
const menuItem = async (label) => { await c.click(".lw-menu__item", label); await sleep(500); };
const binderMenu = async () => { await c.click("button[aria-label*='options']"); await sleep(350); };
const closeDialog = async () => { await c.key("Escape"); await sleep(350); };
/** HTML5 drag and drop, synthesized: React listens for these events at the document root. */
const dnd = (fromSel, fromText, toSel, toText, drop = true) => c.eval(`(async () => {
  const find = (sel, text) => [...document.querySelectorAll(sel)].find((e) => !text || e.textContent.includes(text));
  const a = find(${JSON.stringify(fromSel)}, ${JSON.stringify(fromText)}), b = find(${JSON.stringify(toSel)}, ${JSON.stringify(toText)});
  if (!a || !b) return "missing " + (a ? "target" : "source");
  const dt = new DataTransfer();
  const fire = (el, type) => el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
  fire(a, "dragstart"); await new Promise((r) => setTimeout(r, 80));
  fire(b, "dragenter"); fire(b, "dragover"); await new Promise((r) => setTimeout(r, 120));
  ${drop ? 'fire(b, "drop"); fire(a, "dragend");' : ""}
  return "ok";
})()`);

if (stage("structure")) {
  await load();
  await openScene("Capsule 7-19");
  await c.click(".lw-binder__item", "Front Matter"); await sleep(400);
  await shotEl("g_binder", ".lw-binder");
  await shotEl("g_strip", ".lw-inspector");
  await shotEl("g_context", ".lw-editor__context");
  // scene details dialog from the status tag
  await c.click(".lw-editor__context button, .lw-editor__context .lw-tag", "evising"); await sleep(600);
  if (await c.rect(".lw-dialog")) { await dialogShot("g_details_dialog"); await closeDialog(); }
  await binderMenu();
  await shotEl("g_binder_menu", ".lw-menu", undefined, 10);
  await menuItem("Move scene to part");
  await dialogShot("g_move_to_part"); await closeDialog();
  // corkboard in parts, then a drag with its confirm
  await c.click(".lw-viewmode", "Corkboard"); await sleep(700);
  await shotEl("g_corkboard", ".lw-editor");
  console.log("dnd:", await dnd(".lw-card", "Capsule", ".lw-card", "Ghost in the Ice"));
  await sleep(600);
  if (await c.rect(".lw-dialog")) { await dialogShot("g_drag_confirm"); await closeDialog(); }
  await c.click(".lw-viewmode", "Outline"); await sleep(700);
  await shotEl("g_outline", ".lw-editor");
  await c.click(".lw-viewmode", "Manuscript"); await sleep(500);
  // Trash
  await c.click(".lw-binder__item", "Trash"); await sleep(800);
  if (await c.rect(".lw-dialog")) { await dialogShot("g_trash"); await closeDialog(); }
  // collections: manager, filter, per-scene picker
  await c.click("button", "Edit"); await sleep(600);
  if (await c.rect(".lw-dialog")) { await dialogShot("g_collections_manager"); await closeDialog(); }
  await c.click(".lw-collections__row", "Needs continuity"); await sleep(600);
  await c.click(".lw-viewmode", "Corkboard"); await sleep(600);
  await shot("g_collection_filter_full");
  await shotEl("g_collection_filter", ".lw-editor");
  await c.click(".lw-viewmode", "Manuscript"); await sleep(400);
  await c.click(".lw-collections__row", "Needs continuity"); await sleep(300);
  await c.click(".lw-metric--button", "Collections"); await sleep(600);
  if (await c.rect(".lw-dialog")) { await dialogShot("g_scene_collections"); await closeDialog(); }
}


const sectionShot = async (name, headingText) => {
  const r = await c.eval(`(() => {
    const h = [...document.querySelectorAll('.lw-settings__section h3')].find((e) => e.textContent.includes(${JSON.stringify(headingText)}));
    if (!h) return null; h.scrollIntoView({ block: "center" });
    const b = h.parentElement.getBoundingClientRect();
    return { x: b.x, y: b.y, width: b.width, height: b.height };
  })()`);
  if (!r) throw new Error("no settings section " + headingText);
  await sleep(300);
  const r2 = await c.eval(`(() => { const h = [...document.querySelectorAll('.lw-settings__section h3')].find((e) => e.textContent.includes(${JSON.stringify(headingText)})); const b = h.parentElement.getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height }; })()`);
  await shot(name, { x: r2.x - 6, y: r2.y - 6, width: r2.width + 12, height: r2.height + 12 });
};
/** Replace the temporary paths shown in dialogs by tidy stand-ins (as in the terminal figures). */
const maskPaths = (pairs) => c.eval(`(() => {
  const pairs = ${JSON.stringify(pairs)};
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = w.nextNode())) for (const [a, b] of pairs) if (n.data.includes(a)) n.data = n.data.split(a).join(b);
})()`);
const PATHS = () => [[path.join(path.dirname(project), "remote.git"), "git@example.com:writer/residual.git"], [project, "/home/writer/novels/residual"]];

if (stage("history")) {
  await load();
  await openScene("Capsule 7-19");
  await shotEl("g_status_left", ".lw-status .lw-row");
  await c.click("button[aria-label='History']"); await waitFor(".lw-dialog"); await sleep(700);
  await c.click("input[placeholder^='Label']");
  await c.type("before cutting the lobby"); await sleep(200);
  await dialogShot("g_history");
  await c.click("button", "Compare"); await sleep(900);
  await dialogShot("g_compare");
  await c.click("button", "Back to the list"); await sleep(500);
  await c.click("button", "Restore"); await sleep(600);
  await dialogShot("g_restore_confirm");
  await closeDialog(); await closeDialog();
  // the Draft badge
  await c.click(".lw-titlebar .lw-tag, .lw-titlebar button", "Draft 2"); await sleep(500);
  await shotEl("g_draft_menu", ".lw-menu", undefined, 10);
  await c.click(".lw-menu__item", "Start draft"); await waitFor(".lw-dialog"); await sleep(400);
  await dialogShot("g_draft_confirm"); await closeDialog();
  // sync: menu, commit, push
  await c.click(".lw-status button", "change"); await sleep(500);
  await shotEl("g_sync_menu", ".lw-menu", undefined, 10);
  await c.click(".lw-menu__item", "Commit"); await waitFor(".lw-dialog"); await sleep(500);
  await maskPaths(PATHS());
  await dialogShot("g_commit");
  await c.click("button.lw-btn--primary"); await sleep(1800);
  await c.click(".lw-status button", "Ahead"); await sleep(500);
  await shotEl("g_sync_menu_ahead", ".lw-menu", undefined, 10);
  await c.click(".lw-menu__item", "Push"); await waitFor(".lw-dialog"); await sleep(400);
  await maskPaths(PATHS());
  await dialogShot("g_push"); await closeDialog();
  // settings: the History section
  await c.size(W, 1300, 2); await sleep(400);
  await c.click(".lw-rail__item[aria-label='Settings']"); await waitFor(".lw-dialog"); await sleep(600);
  await sectionShot("g_settings_history", "History");
  await sectionShot("g_goals", "Writing goals");
  await closeDialog();
  await c.size(W, H, 2);
}


if (stage("notes4")) {
  await load();
  // comments: Capsule 7-19 has a detached one, the Stairwell an anchored one
  await openScene("Capsule 7-19");
  await c.click(".lw-tab", "Notes"); await sleep(700);
  await shotEl("g_comments_tab", ".lw-assistant");
  await openScene("The Stairwell"); await sleep(900);
  await c.click(".lw-tab", "Notes"); await sleep(600);
  const row = await c.rect(".lw-comments button", "shard");
  if (row) { await c.clickAt(row.cx, row.cy); await sleep(700); }
  const pop = await c.rect(".lw-comment-pop");
  if (pop) await shot("g_comment_popover", { x: Math.max(330, pop.x - 140), y: Math.max(0, pop.y - 130), width: Math.min(560, 905 - Math.max(330, pop.x - 140)), height: pop.h + 200 });
  await c.key("Escape"); await sleep(300);
  // add a comment on a selected passage
  await focusEditor();
  await reveal("Tell him no, and");
  await selectText("Tell him no, and", "Tell him no, and mean it, and walk.".length);
  await c.click("button[aria-label*='comment on']"); await waitFor(".lw-dialog"); await sleep(500);
  await c.click(".lw-dialog textarea"); await c.type("Does Wren say this twice? Check scene 4."); await sleep(300);
  await dialogShot("g_comment_add"); await closeDialog();
  // research: the binder group, a note, a link
  await c.click(".lw-binder__item", "Research"); await sleep(500);
  await shotEl("g_research_binder", ".lw-binder");
  await binderMenu(); await menuItem("from a link");
  await waitFor(".lw-dialog"); await c.click(".lw-dialog input"); await c.type("https://www.example.com/articles/capsule-hotel-etiquette.html"); await sleep(300);
  await dialogShot("g_research_link"); await closeDialog();
  // the research question, with its cited notes
  await openScene("Rain on the Spur");
  await c.click(".lw-tab", "Assistant"); await sleep(400);
  await c.click(".lw-tool", "Research"); await sleep(500);
  await c.click("textarea"); await c.type("What do real capsule hotels look like?");
  await c.key("Enter", { wait: 2200 }); await sleep(600);
  await shotEl("g_research_answer", ".lw-assistant");
  // save to notes
  await c.click("button[aria-label^='Save to notes']"); await sleep(700);
  const toast = await c.rect(".lw-toast");
  if (toast) await shot("g_save_toast", { x: toast.x - 10, y: toast.y - 10, width: toast.w + 20, height: toast.h + 20 });
  // conversations and attach
  await c.click("button[aria-label='Conversation history']"); await waitFor(".lw-dialog"); await sleep(700);
  await dialogShot("g_chats"); await closeDialog();
  await c.click("button[aria-label^='Attach']"); await waitFor(".lw-dialog"); await sleep(700);
  await c.click(".lw-picklist label, .lw-picklist__row", "Capsule 7-19"); await sleep(200);
  await c.click(".lw-picklist label, .lw-picklist__row", "Capsule hotels"); await sleep(300);
  await dialogShot("g_attach"); await closeDialog();
}

if (stage("aids")) {
  await load();
  await openScene("Rain on the Spur");
  await c.click(".lw-status button", "words today"); await waitFor(".lw-dialog"); await sleep(900);
  await dialogShot("g_stats"); await closeDialog();
  await c.size(W, 1300, 2); await sleep(300);
  await c.click(".lw-status button", "Sprint"); await waitFor(".lw-dialog"); await sleep(500);
  await dialogShot("g_sprint");
  await c.size(W, H, 2); await sleep(300);
  await c.click("button.lw-btn--primary"); await sleep(1500);
  const bar = await c.rect(".lw-status");
  await shot("g_sprint_bar", { x: bar.x + 520, y: bar.y, width: bar.w - 520, height: bar.h });
  // stop it: the end notice with its Session stats action
  await c.click(".lw-status button", "·"); await sleep(500);
  if (await c.rect(".lw-dialog")) { await c.click("button.lw-btn--danger, button.lw-btn--primary", "Stop sprint"); await sleep(900); }
  const toast = await c.rect(".lw-toast");
  if (toast) await shot("g_sprint_toast", { x: toast.x - 10, y: toast.y - 10, width: toast.w + 20, height: toast.h + 20 });
  // brainstorm
  await c.click(".lw-tool", "Brainstorm"); await sleep(2200);
  await shotEl("g_brainstorm", ".lw-assistant");
  await c.size(W, 1300, 2); await sleep(400);
  await c.click(".lw-rail__item[aria-label='Settings']"); await waitFor(".lw-dialog"); await sleep(600);
  await sectionShot("g_goals", "Writing goals");
  await closeDialog();
  await c.size(W, H, 2);
}

c.close();
