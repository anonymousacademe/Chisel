// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../backend/api";
import { makeMockResearchProject, mockCall } from "../../../backend/mock";
import { resetMockObjects } from "../../../backend/mockObjects";
import { Binder } from "../../Binder";
import { placementText, type PlaceTarget } from "../../../data/objects";
import { findNode } from "../../../data/tree";
import type { BinderNode, Workspace } from "../../../data/types";
import { InsertEquationDialog, InsertFigureDialog, InsertTableDialog } from "./InsertDialogs";
import { KatexView, renderLatex } from "./KatexView";
import { ObjectDialog } from "./ObjectDialog";
import { TableGridEditor } from "./TableGridEditor";
import { blankGrid, placeObject, type Grid } from "../../../data/objects";
import { useState } from "react";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let roots: Root[] = [];
async function mount(el: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  roots.push(root);
  await act(async () => { root.render(el); });
  return host;
}
const flush = async (ms = 0) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)); }); };
async function until(fn: () => unknown, tries = 60) {
  for (let i = 0; i < tries; i++) { if (fn()) return; await flush(5); }
  throw new Error("timed out waiting");
}
const q = (s: string) => document.body.querySelector(s) as HTMLElement | null;
const btn = (label: string) => [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement | undefined;
const click = async (el: Element | undefined | null) => { if (!el) throw new Error("missing element"); await act(async () => { (el as HTMLElement).click(); }); };
async function type(el: HTMLInputElement | HTMLTextAreaElement | null, value: string) {
  if (!el) throw new Error("missing field");
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); });
}
const field = (label: string) => q(`[aria-label="${label}"]`) as HTMLInputElement & HTMLTextAreaElement | null;
const notify = vi.fn();

beforeEach(() => { resetMockObjects(); vi.restoreAllMocks(); notify.mockClear(); document.body.innerHTML = ""; });
afterEach(async () => { await act(async () => { roots.forEach((r) => r.unmount()); }); roots = []; });

describe("binder groups", () => {
  it("the mock puts Figures, Tables and Equations after the Notebook group, only in research projects", async () => {
    const story = (mockCall("get_workspace", []) as { workspace: Workspace }).workspace;
    expect(findNode(story.binder, "group:figures")).toBeUndefined();
    makeMockResearchProject();
    const ws = (mockCall("get_workspace", []) as { workspace: Workspace }).workspace;
    const ids = ws.binder.map((n) => n.id);
    expect(ids.indexOf("group:figures")).toBe(ids.indexOf("ph:research") + 1);
    expect(ids.indexOf("ph:research")).toBeGreaterThan(-1);
    expect(ids.slice(ids.indexOf("group:figures"), ids.indexOf("group:figures") + 3)).toEqual(["group:figures", "group:tables", "group:equations"]);
    const fig = findNode(ws.binder, "fig:flow-model")!;
    expect(fig).toMatchObject({ kind: "object", title: "Figure 1: Flow through the treatment train" });
    expect(findNode(ws.binder, "eq:monod")!.title).toBe("Equation (1): Monod growth rate");
  });

  const nodes = (): BinderNode[] => {
    const ws = (mockCall("get_workspace", []) as { workspace: Workspace }).workspace;
    return ws.binder.filter((n) => n.kind === "objects");
  };
  const renderBinder = (onSelect: (n: BinderNode) => void, onInsertObject?: (k: string) => void) => mount(
    <Binder nodes={nodes()} count={5} activeId={null} focusId={null} unit="section" expanded={new Set(["group:figures", "group:tables", "group:equations"])}
      onToggle={() => {}} onSelect={onSelect} onNew={() => {}} onMenu={() => {}} searching={false} library={false} canNew canMenu
      collections={[]} activeCollection={null} onCollection={() => {}} onEditCollections={() => {}} onDropUrl={() => {}} onNewNote={() => {}} onInsertObject={onInsertObject} />,
  );

  it("renders the groups and their rows; clicking a row selects it (App opens the card)", async () => {
    makeMockResearchProject();
    const picked: BinderNode[] = [];
    await renderBinder((n) => picked.push(n));
    expect(q('[aria-label="Manuscript binder"]')!.textContent).toContain("Figures");
    expect(q('[aria-label="Manuscript binder"]')!.textContent).toContain("Equation (1): Monod growth rate");
    const row = [...document.body.querySelectorAll('[role="treeitem"]')].find((r) => r.textContent?.includes("Summary of the three sites"));
    await click(row);
    expect(picked.map((n) => n.id)).toEqual(["tbl:site-summary"]);
  });

  it("the group header has an Insert button for its kind", async () => {
    makeMockResearchProject();
    const kinds: string[] = [];
    await renderBinder(() => {}, (k) => kinds.push(k));
    await click(q('[aria-label="Insert tables"]'));
    await click(q('[aria-label="Insert equations"]'));
    expect(kinds).toEqual(["tbl", "eq"]);
  });
});

describe("TableGridEditor", () => {
  function Host({ start, onGrid }: { start: Grid; onGrid: (g: Grid) => void }) {
    const [g, setG] = useState(start);
    return <TableGridEditor grid={g} onChange={(n) => { setG(n); onGrid(n); }} />;
  }
  it("adds and removes rows and columns, sets alignment", async () => {
    let last = blankGrid(2, 2);
    await mount(<Host start={last} onGrid={(g) => { last = g; }} />);
    await click(btn("Add row"));
    await click(btn("Add column"));
    expect(last.cells).toHaveLength(3);
    expect(last.align).toHaveLength(3);
    await act(async () => {
      const sel = q('[aria-label="Alignment of column 2"]') as HTMLSelectElement;
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(sel, "right");
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(last.align[1]).toBe("right");
    await click(q('[aria-label="Remove row 2"]'));
    await click(q('[aria-label="Remove column 3"]'));
    expect(last.cells).toHaveLength(2);
    expect(last.align).toHaveLength(2);
    expect(q('[aria-label="Remove row 0"]')).toBeNull();      // the header row has no remove button
  });

  it("pasting tab-separated text fills the grid from that cell", async () => {
    let last = blankGrid(2, 2);
    await mount(<Host start={last} onGrid={(g) => { last = g; }} />);
    const cell = q('[aria-label="Row 1, column 1"]')!;
    const ev = new Event("paste", { bubbles: true, cancelable: true }) as Event & { clipboardData?: unknown };
    ev.clipboardData = { getData: () => "a\tb\tc\n1\t2\t3" };
    await act(async () => { cell.dispatchEvent(ev); });
    expect(ev.defaultPrevented).toBe(true);
    expect(last.cells[1]).toEqual(["a", "b", "c"]);
    expect(last.cells[2]).toEqual(["1", "2", "3"]);
    expect(last.align).toHaveLength(3);
  });

  it("a plain paste is left to the cell", async () => {
    const seen: Grid[] = [];
    await mount(<Host start={blankGrid(2, 2)} onGrid={(g) => seen.push(g)} />);
    const ev = new Event("paste", { bubbles: true, cancelable: true }) as Event & { clipboardData?: unknown };
    ev.clipboardData = { getData: () => "just words" };
    await act(async () => { q('[aria-label="Row 1, column 1"]')!.dispatchEvent(ev); });
    expect(ev.defaultPrevented).toBe(false);
    expect(seen).toHaveLength(0);
  });
});

describe("equation preview", () => {
  it("renders good LaTeX and never throws on bad LaTeX", async () => {
    expect(renderLatex("\\frac{a}{b}")).toMatchObject({ ok: true });
    for (const bad of ["\\frac{a", "\\notacommand{x}", "{", "\\href{javascript:alert(1)}{x}", "\\includegraphics{x}", "$$"]) {
      const r = renderLatex(bad);
      if (!r.ok) expect(r.error).not.toBe("");
      else expect(r.html).not.toMatch(/<a |href=/);
    }
    const host = await mount(<KatexView latex={"\\frac{a"} />);
    expect(host.querySelector('[role="alert"]')!.textContent).toMatch(/does not parse/);
    const ok = await mount(<KatexView latex={"x^2"} />);
    expect(ok.querySelector(".katex")).not.toBeNull();
  });
  it("an empty box shows a placeholder, not an error", async () => {
    const host = await mount(<KatexView latex="" />);
    expect(host.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("insert flows: the bridge first, then the placement on its own line", () => {
  const editor = (text: string, at: number) => {
    const log = { text };
    const ed: PlaceTarget = {
      getText: () => log.text, selection: () => ({ from: at, to: at }), focus: () => {},
      replace: (f, t, s) => { log.text = log.text.slice(0, f) + s + log.text.slice(t); },
    };
    return { ed, log };
  };
  // what App does on onCreated
  const created = (ed: PlaceTarget, open = true) => vi.fn((id: string) => placeObject(ed, open, id));

  it("table: creates it through create_table, then places tbl:label", async () => {
    const spy = vi.spyOn(api, "createTable");
    const { ed, log } = editor("Results follow.", 15);
    const onCreated = created(ed);
    await mount(<InsertTableDialog notify={notify} onClose={() => {}} onCreated={onCreated} />);
    await type(field("Caption"), "Loads per site");
    await until(() => (field("Label") as HTMLInputElement).value === "loads-per-site");
    await type(q('[aria-label="Header, column 1"]') as HTMLInputElement, "Site");
    await click(btn("Insert table"));
    await until(() => onCreated.mock.calls.length > 0);
    expect(spy).toHaveBeenCalledWith("loads-per-site", "Loads per site", expect.any(Array), expect.any(Array));
    expect(onCreated).toHaveBeenCalledWith("tbl:loads-per-site");
    expect(log.text).toBe("Results follow.\n\n![[tbl:loads-per-site]]");
    expect(findInMock("tbl:loads-per-site")).toBe(true);
  });

  it("a blank table cannot be inserted", async () => {
    await mount(<InsertTableDialog notify={notify} onClose={() => {}} onCreated={() => {}} />);
    await type(field("Caption"), "x");
    expect(btn("Insert table")!.disabled).toBe(true);
  });

  it("equation: the label can be edited and the placement is on its own line after the cursor line", async () => {
    const spy = vi.spyOn(api, "createEquation");
    const { ed, log } = editor("Growth is modelled by  as shown.", 22);
    const onCreated = created(ed);
    await mount(<InsertEquationDialog notify={notify} onClose={() => {}} onCreated={onCreated} />);
    await type(field("LaTeX"), "y = ax + b");
    await type(field("Label"), "line");
    await click(btn("Insert equation"));
    await until(() => onCreated.mock.calls.length > 0);
    expect(spy).toHaveBeenCalledWith("line", "y = ax + b", "");
    expect(log.text).toBe("Growth is modelled by  as shown.\n\n![[eq:line]]");
  });

  it("an error from the bridge is shown and nothing is placed", async () => {
    const { ed, log } = editor("x", 1);
    const onCreated = created(ed);
    await mount(<InsertEquationDialog notify={notify} onClose={() => {}} onCreated={onCreated} />);
    await type(field("LaTeX"), "a");
    await type(field("Label"), "monod");        // already exists in the mock
    await click(btn("Insert equation"));
    await until(() => notify.mock.calls.length > 0);
    expect(notify.mock.calls[0][1]).toBe("error");
    expect(onCreated).not.toHaveBeenCalled();
    expect(log.text).toBe("x");
  });

  it("with no section open the object is created and nothing is inserted", async () => {
    const { ed, log } = editor("", 0);
    const onCreated = created(ed, false);
    await mount(<InsertEquationDialog notify={notify} onClose={() => {}} onCreated={onCreated} />);
    await type(field("LaTeX"), "a");
    await type(field("Label"), "solo");
    await click(btn("Insert equation"));
    await until(() => onCreated.mock.calls.length > 0);
    expect(onCreated.mock.results[0].value).toBe(false);
    expect(log.text).toBe("");
    expect(findInMock("eq:solo")).toBe(true);
  });

  it("AI suggestion: an AI job, shown apart with the sent report and cost, enters the equation only on Use this", async () => {
    const spy = vi.spyOn(api, "aiStart");
    await mount(<InsertEquationDialog notify={notify} onClose={() => {}} onCreated={() => {}} />);
    await type(field("Describe the equation"), "Monod with inhibition");
    await click(btn("Suggest LaTeX with AI"));
    expect(btn("Stop")).toBeTruthy();
    expect(q('[role="status"]')!.textContent).toMatch(/Suggesting LaTeX/);
    await until(() => q('[aria-label="Suggested LaTeX"]'), 600);
    expect(spy).toHaveBeenCalledWith("latex", { description: "Monod with inhibition" });
    expect(q('[aria-label="Suggested LaTeX"]')!.textContent).toContain("What was sent");
    expect(q('[aria-label="Suggested LaTeX"]')!.textContent).toMatch(/Cost: \$0\.0004/);
    expect(field("LaTeX")!.value).toBe("");
    await click(btn("Use this"));
    expect(field("LaTeX")!.value).toContain("K_i");
    expect(q('[aria-label="Suggested LaTeX"]')).toBeNull();
  });

  it("AI suggestion: Stop cancels the job and nothing is proposed", async () => {
    const cancel = vi.spyOn(api, "aiCancel");
    await mount(<InsertEquationDialog notify={notify} onClose={() => {}} onCreated={() => {}} />);
    await type(field("Describe the equation"), "anything");
    await click(btn("Suggest LaTeX with AI"));
    await until(() => btn("Stop"));
    await click(btn("Stop"));
    await until(() => cancel.mock.calls.length > 0);
    await until(() => btn("Suggest LaTeX with AI"), 200);
    expect(q('[aria-label="Suggested LaTeX"]')).toBeNull();
    expect(notify).toHaveBeenCalledWith("Stopped. Nothing was changed.");
  });

  it("AI suggestion honours the AI key check", async () => {
    const spy = vi.spyOn(api, "aiStart");
    await mount(<InsertEquationDialog notify={notify} onClose={() => {}} onCreated={() => {}} requireAi={() => false} />);
    await type(field("Describe the equation"), "anything");
    await click(btn("Suggest LaTeX with AI"));
    expect(spy).not.toHaveBeenCalled();
  });

  it("figure: a PNG is read, previewed and sent as a data URL; other types are refused", async () => {
    const spy = vi.spyOn(api, "insertFigure");
    const { ed, log } = editor("", 0);
    const onCreated = created(ed);
    await mount(<InsertFigureDialog notify={notify} onClose={() => {}} onCreated={onCreated} />);
    const input = q('input[type="file"]') as HTMLInputElement;
    const choose = async (f: File) => {
      Object.defineProperty(input, "files", { value: [f], configurable: true });
      await act(async () => { input.dispatchEvent(new Event("change", { bubbles: true })); });
    };
    await choose(new File(["x"], "scan.gif", { type: "image/gif" }));
    expect(q('[role="alert"]')!.textContent).toMatch(/PNG or JPG/);
    expect(btn("Insert figure")!.disabled).toBe(true);
    await choose(new File([new Uint8Array([137, 80, 78, 71])], "Flow Chart.png", { type: "image/png" }));
    await until(() => q("img.lw-drop__preview"));
    await until(() => (field("Label") as HTMLInputElement).value === "flow-chart");
    await type(field("Caption"), "The flow chart");
    await click(btn("Insert figure"));
    await until(() => onCreated.mock.calls.length > 0);
    expect(spy.mock.calls[0][0]).toMatch(/^data:image\/png;base64,/);
    expect(spy.mock.calls[0].slice(2)).toEqual(["The flow chart"]);
    expect(log.text).toBe(placementText(onCreated.mock.calls[0][0]));
  });
});

const findInMock = (id: string) => (mockCall("list_objects", []) as { objects: { id: string }[] }).objects.some((o) => o.id === id);

describe("ObjectDialog", () => {
  const open = (id: string, extra: Partial<React.ComponentProps<typeof ObjectDialog>> = {}) =>
    mount(<ObjectDialog id={id} notify={notify} onClose={() => {}} onChanged={() => {}} pollMs={5} {...extra} />);

  it("shows an equation with its LaTeX, where it is used, and saves edits through update_object", async () => {
    const spy = vi.spyOn(api, "updateObject");
    const changed = vi.fn();
    await open("eq:monod", { onChanged: changed });
    await until(() => q('[aria-label="Where it is used"]')!.textContent!.includes("Placed in 2 sections"));
    expect(q('[aria-label="Where it is used"]')!.textContent).toContain("Methods");
    expect(btn("Save details")!.disabled).toBe(true);
    await type(field("Caption"), "Monod rate");
    await click(btn("Save details"));
    await until(() => spy.mock.calls.length > 0);
    expect(spy).toHaveBeenCalledWith("eq:monod", { caption: "Monod rate", latex: "\\mu = \\mu_{max}\\frac{S}{K_s + S}" });
    await until(() => changed.mock.calls.length > 0);
  });

  it("figure: caption, alt text and a checked width", async () => {
    const spy = vi.spyOn(api, "updateObject");
    await open("fig:flow-model");
    await until(() => field("Alt text"));
    await type(field("Alt text"), "Boxes and arrows");
    await type(field("Width in inches"), "40");
    expect(q('[role="alert"]')!.textContent).toMatch(/1 to 20/);
    expect(btn("Save details")!.disabled).toBe(true);
    await type(field("Width in inches"), "6.5");
    await click(btn("Save details"));
    await until(() => spy.mock.calls.length > 0);
    expect(spy).toHaveBeenCalledWith("fig:flow-model", { caption: "Flow through the treatment train", alt: "Boxes and arrows", width: 6.5 });
  });

  it("table: edit the grid and save with the base mtime; a conflict asks to reload", async () => {
    const spy = vi.spyOn(api, "saveTable");
    await open("tbl:site-summary");
    await until(() => q('[aria-label="Row 1, column 2"]'));
    await type(q('[aria-label="Row 1, column 2"]') as HTMLInputElement, "1300");
    await click(btn("Save table"));
    await until(() => spy.mock.calls.length > 0);
    expect(spy.mock.calls[0][3]).toBe("1");
    await until(() => notify.mock.calls.some((c) => /saved/i.test(String(c[0]))));
    // someone else changed the file: the mock's mtime moved on, ours is stale
    mockCall("save_table", ["tbl:site-summary", [["Site", "Flow"], ["A", "1"]], ["left", "right"], "2"]);
    await type(q('[aria-label="Row 1, column 2"]') as HTMLInputElement, "1400");
    await click(btn("Save table"));
    await until(() => q('[role="alert"]'));
    expect(q('[role="alert"]')!.textContent).toMatch(/changed on disk/);
    await click(btn("Reload it"));
    await until(() => !q('[role="alert"]'));
  });

  it("Save details keeps unsaved grid edits and does not cause a false conflict on the next Save table", async () => {
    const save = vi.spyOn(api, "saveTable");
    await open("tbl:site-summary");
    await until(() => q('[aria-label="Row 1, column 2"]'));
    await type(q('[aria-label="Row 1, column 2"]') as HTMLInputElement, "1300");
    await type(field("Caption"), "A new caption");
    await click(btn("Save details"));
    await until(() => notify.mock.calls.some((c) => c[0] === "Saved."));
    await flush(20);
    expect((q('[aria-label="Row 1, column 2"]') as HTMLInputElement).value).toBe("1300");
    expect(btn("Save table")!.disabled).toBe(false);
    await click(btn("Save table"));
    await until(() => save.mock.calls.length > 0);
    await until(() => notify.mock.calls.some((c) => /table saved/i.test(String(c[0]))));
    expect(q('[role="alert"]')).toBeNull();
  });

  it("a generated table is read-only and is rebuilt only through preview then apply", async () => {
    const applySpy = vi.spyOn(api, "applyTable");
    await open("tbl:kpi-table");
    await until(() => btn("Rebuild from the data"));
    expect((q('[aria-label="Row 1, column 1"]') as HTMLInputElement).readOnly).toBe(true);
    expect(btn("Save table")).toBeUndefined();
    await click(btn("Rebuild from the data"));
    await until(() => q('[aria-label="Rebuilt table preview"]'));
    expect(applySpy).not.toHaveBeenCalled();
    await click(btn("Use the rebuilt table"));
    await until(() => applySpy.mock.calls.length > 0);
  });

  describe("generated figure: the script flow", () => {
    const id = "fig:effluent-trend";
    it("shows the script, its sha, path and interpreter, and does not run or trust by itself", async () => {
      const trust = vi.spyOn(api, "trustFigure"), start = vi.spyOn(api, "figureRunStart");
      await open(id);
      await until(() => q('[aria-label="Figure script"]'));
      expect(q('[aria-label="Script text"]')!.textContent).toContain("plt.savefig");
      expect(q('[data-testid="script-sha"]')!.textContent).toMatch(/^mocksha-/);
      expect(q('[aria-label="Figure script"]')!.textContent).toContain("figures/scripts/effluent_trend.py");
      expect(q('[aria-label="Figure script"]')!.textContent).toContain("/usr/bin/python3");
      expect(btn("Run the script")!.disabled).toBe(true);
      expect(trust).not.toHaveBeenCalled();
      expect(start).not.toHaveBeenCalled();
    });

    it("trust sends exactly the sha shown, then Run is possible and polls to done", async () => {
      const trust = vi.spyOn(api, "trustFigure"), start = vi.spyOn(api, "figureRunStart"), changed = vi.fn();
      await open(id, { onChanged: changed });
      await until(() => btn("Trust this script version"));
      const sha = q('[data-testid="script-sha"]')!.textContent;
      await click(btn("Trust this script version"));
      await until(() => !btn("Trust this script version"));
      expect(trust).toHaveBeenCalledWith(id, sha);
      expect(start).not.toHaveBeenCalled();
      expect(btn("Run the script")!.disabled).toBe(false);
      await click(btn("Run the script"));
      expect(start).toHaveBeenCalledWith(id);
      await until(() => q('[aria-label="Figure script"]')!.textContent!.includes("Done."));
      expect(changed).toHaveBeenCalled();
    });

    it("Stop cancels a running script", async () => {
      const cancel = vi.spyOn(api, "figureRunCancel");
      await open(id, { pollMs: 40 });
      await until(() => btn("Trust this script version"));
      await click(btn("Trust this script version"));
      await until(() => !btn("Trust this script version"));
      await click(btn("Run the script"));
      await until(() => btn("Stop"));
      await click(btn("Stop"));
      expect(cancel).toHaveBeenCalledTimes(1);
      await until(() => q('[aria-label="Figure script"]')!.textContent!.includes("Stopped."), 100);
    });

    it("closing while a script runs asks first: no keeps the card, yes stops the run", async () => {
      const cancel = vi.spyOn(api, "figureRunCancel"), closed = vi.fn();
      await open(id, { pollMs: 400, onClose: closed });
      await until(() => btn("Trust this script version"));
      await click(btn("Trust this script version"));
      await until(() => !btn("Trust this script version"));
      await click(btn("Run the script"));
      await until(() => btn("Stop"));
      await click([...document.body.querySelectorAll("button")].find((b) => b.textContent === "Close"));
      expect(q('[aria-label="Stop the run?"]')).toBeTruthy();
      expect(closed).not.toHaveBeenCalled();
      await click([...q('[aria-label="Stop the run?"]')!.querySelectorAll("button")].find((b) => b.textContent === "Cancel"));
      expect(closed).not.toHaveBeenCalled();
      expect(cancel).not.toHaveBeenCalled();
      await click([...document.body.querySelectorAll("button")].find((b) => b.textContent === "Close"));
      await click(btn("Stop the run"));
      expect(closed).toHaveBeenCalledTimes(1);
      // the parent unmounts the card on close: the run is cancelled through figure_run_cancel
      await act(async () => { roots.forEach((r) => r.unmount()); }); roots = [];
      expect(cancel).toHaveBeenCalledTimes(1);
    });

    it("the card re-reads the trust state on focus and after a refused run", async () => {
      const info = vi.spyOn(api, "figureTrustInfo");
      await open(id);
      await until(() => btn("Trust this script version"));
      await click(btn("Trust this script version"));
      await until(() => !btn("Trust this script version"));
      expect(btn("Run the script")!.disabled).toBe(false);
      // the script changes on disk
      info.mockResolvedValue({ ok: true, id, script: "print(2)", sha: "new", path: "figures/scripts/x.py", interpreter: "/usr/bin/python3", data: [], trust: "changed" });
      await act(async () => { window.dispatchEvent(new Event("focus")); });
      await until(() => btn("Trust this script version"));
      expect(btn("Run the script")!.disabled).toBe(true);
    });

    it("a refused Run reloads the script's trust", async () => {
      const info = vi.spyOn(api, "figureTrustInfo");
      await open(id);
      await until(() => btn("Trust this script version"));
      await click(btn("Trust this script version"));
      await until(() => !btn("Trust this script version"));
      const calls = info.mock.calls.length;
      vi.spyOn(api, "figureRunStart").mockResolvedValue({ ok: false, error: "the script changed" });
      info.mockResolvedValue({ ok: true, id, script: "print(2)", sha: "new", path: "figures/scripts/x.py", interpreter: "/usr/bin/python3", data: [], trust: "changed" });
      await click(btn("Run the script"));
      await until(() => info.mock.calls.length > calls && btn("Trust this script version"));
      expect(btn("Run the script")!.disabled).toBe(true);
    });

    it("a failed run shows the plain message and the stderr tail", async () => {
      vi.spyOn(api, "figureRunStatus").mockResolvedValue({ ok: true, job: "f1", figure: id, state: "failed", error: "The script exited with an error.", stderr: "Traceback...\nValueError: x" });
      await open(id);
      await until(() => btn("Trust this script version"));
      await click(btn("Trust this script version"));
      await until(() => !btn("Trust this script version"));
      await click(btn("Run the script"));
      await until(() => q('[aria-label="Error output"]'));
      expect(q('[aria-label="Figure script"]')!.textContent).toContain("The script exited with an error.");
      expect(q('[aria-label="Error output"]')!.textContent).toContain("ValueError");
      expect(btn("Run the script")!.disabled).toBe(false);
    });

    it("a script that changed after trust asks again", async () => {
      vi.spyOn(api, "figureTrustInfo").mockResolvedValue({
        ok: true, id, script: "print(1)", sha: "abc", path: "figures/scripts/x.py", interpreter: "/usr/bin/python3", data: [], trust: "changed",
      });
      await open(id);
      await until(() => btn("Trust this script version"));
      expect(q('[aria-label="Figure script"]')!.textContent).toMatch(/changed since you trusted it/);
      expect(btn("Run the script")!.disabled).toBe(true);
    });
  });

  describe("delete", () => {
    it("asks first, names the Trash and how many sections place it, and trashes only on confirm", async () => {
      const trash = vi.spyOn(api, "trashObject");
      const closed = vi.fn(), changed = vi.fn();
      await open("eq:monod", { onClose: closed, onChanged: changed });
      await until(() => q('[aria-label="Where it is used"]')!.textContent!.includes("Placed in 2"));
      await click(btn("Delete…"));
      const dlg = q('[aria-label="Delete Equation (1)"]')!;
      expect(dlg.textContent).toContain("goes to the Trash");
      expect(dlg.textContent).toContain("2 sections place it");
      expect(trash).not.toHaveBeenCalled();
      await click([...dlg.querySelectorAll("button")].find((b) => b.textContent === "Cancel"));
      expect(trash).not.toHaveBeenCalled();
      expect(findInMock("eq:monod")).toBe(true);
      await click(btn("Delete…"));
      await click(btn("Move to Trash"));
      await until(() => closed.mock.calls.length > 0);
      expect(trash).toHaveBeenCalledWith("eq:monod");
      expect(changed).toHaveBeenCalled();
      expect(findInMock("eq:monod")).toBe(false);
    });
  });
});
