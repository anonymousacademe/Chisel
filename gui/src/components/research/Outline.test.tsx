// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../backend/api", () => ({
  api: {
    outlineGetScope: vi.fn(), outlineSetScope: vi.fn(), outlineCurrent: vi.fn(), outlineStandard: vi.fn(), outlineApply: vi.fn(),
    guidelinesList: vi.fn(), aiStart: vi.fn(), aiPoll: vi.fn(), aiCancel: vi.fn(),
  },
}));
import { api } from "../../backend/api";
import { OutlineAssistantDialog } from "./OutlineAssistantDialog";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const sec = (id: string, title: string) => ({ id, title, part: "", partTitle: "", frontMatter: false, position: 1, words: 5, purpose: "" });
const CURRENT = { ok: true, kind: "manuscript", journal: "ems", journalName: "EMS", sections: [sec("i", "Introduction"), sec("m", "Methods")] };
const ITEMS = [
  { id: "1", action: "add", title: "Study area", part: "", after: "i", purpose: "Describe the site.", why: "Needed." },
  { id: "2", action: "rename", title: "Methods", section: "m", newTitle: "Materials and methods", why: "Journal heading." },
  { id: "3", action: "advice", title: "Add limitations", why: "Reviewers ask." },
  { id: "4", action: "keep", title: "Introduction", section: "i" },
];
const SENT = { feature: "outline", estTokens: 100, window: 32000, reserve: 4000, overBudget: false, trimmed: false, sections: [], attached: [] };

const handlers = () => ({
  notify: vi.fn(), onClose: vi.fn(), requireAi: vi.fn(() => true), flushSave: vi.fn(async () => true),
  onApplied: vi.fn(async () => {}), refresh: vi.fn(async () => {}),
});

async function mount() {
  const h = handlers();
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => { root.render(<OutlineAssistantDialog {...h} />); });
  return { host, root, h };
}
const button = (label: string) => [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;
const boxes = () => [...document.body.querySelectorAll<HTMLInputElement>("input[type=checkbox]")];
async function click(el: HTMLElement) { await act(async () => { el.click(); }); }
async function until(fn: () => boolean) {
  for (let n = 0; n < 60 && !fn(); n++) await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
}
function setValue(el: HTMLTextAreaElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  vi.clearAllMocks(); document.body.innerHTML = "";
  m.outlineGetScope.mockResolvedValue({ ok: true, text: "We study runoff." });
  m.outlineSetScope.mockResolvedValue({ ok: true });
  m.outlineCurrent.mockResolvedValue(CURRENT);
  m.guidelinesList.mockResolvedValue({ ok: true, files: [{ name: "guide.pdf", type: "pdf", size: 1, chars: 10, extracted: true, message: "" }] });
  m.aiStart.mockResolvedValue({ ok: true, job: "j1" });
  m.aiPoll.mockResolvedValue({ ok: true, state: "done", text: "", length: 0, elapsed: 1, cost: 0.01, result: { items: ITEMS, sent: SENT, cost: 0.01, model: "x", dropped: [{ title: "Bad", reason: "Unknown section." }] } });
  m.aiCancel.mockResolvedValue({ ok: true, state: "cancelled" });
  m.outlineApply.mockResolvedValue({ ok: true, changed: ["m"], remap: { m: "m2" }, skipped: [{ id: "1", reason: "Gone." }], created: ["n"] });
});

describe("OutlineAssistantDialog", () => {
  it("loads the scope, ticks no guidelines and saves the scope when asked", async () => {
    const { host, h } = await mount();
    const area = host.ownerDocument.querySelector("textarea")!;
    expect(area.value).toBe("We study runoff.");
    expect(boxes().every((b) => !b.checked)).toBe(true);
    expect(button("Save").disabled).toBe(true);
    await act(async () => { setValue(area, "A new scope."); });
    await click(button("Save"));
    expect(m.outlineSetScope).toHaveBeenCalledWith("A new scope.");
    expect(h.notify).toHaveBeenCalledWith("Saved.");
  });

  it("suggests with the ticked guidelines, shows the review and sends only ticked actionable items", async () => {
    const { host, h } = await mount();
    await click(boxes()[0]);   // guide.pdf
    await click(button("Suggest an outline"));
    await until(() => host.textContent!.includes("Ignored from the reply"));
    expect(m.aiStart).toHaveBeenCalledWith("outline", { instruction: "", guidelines: ["guide.pdf"] });
    expect(host.textContent).toContain("Unknown section.");
    expect(host.textContent).toContain("Add limitations");
    // two checkboxes: add and rename. Advice has none, keep is hidden.
    expect(boxes()).toHaveLength(2);
    expect(host.textContent).not.toContain("Keep");
    expect(button("Apply 2 changes")).toBeTruthy();
    await click(boxes()[1]);   // untick the rename
    await click(button("Apply 1 change"));
    expect(m.outlineApply).toHaveBeenCalledWith([ITEMS[0]]);
    expect(h.flushSave).toHaveBeenCalled();
  });

  it("reopens through the remap and summarises the result", async () => {
    const { host, h } = await mount();
    await click(button("Suggest an outline"));
    await until(() => !!button("Apply 2 changes"));
    await click(button("Apply 2 changes"));
    expect(h.onApplied).toHaveBeenCalledWith({ m: "m2" });
    expect(host.textContent).toContain("1 changed, 1 created, 1 skipped");
    expect(host.textContent).toContain("Gone.");
    expect(host.textContent).toContain("saved as a snapshot first");
  });

  it("Stop cancels the job and applies nothing", async () => {
    m.aiPoll.mockResolvedValue({ ok: true, state: "running", text: "", length: 0, elapsed: 2, cost: null });
    const { host, h } = await mount();
    await click(button("Suggest an outline"));
    await until(() => !!button("Stop"));
    expect(host.textContent).toContain("2 s");
    await click(button("Stop"));
    await until(() => !!button("Suggest an outline"));
    expect(m.aiCancel).toHaveBeenCalledWith("j1");
    expect(m.outlineApply).not.toHaveBeenCalled();
    expect(h.notify).toHaveBeenCalledWith("Stopped. Nothing was changed.");
    expect(button("Apply")).toBeUndefined();
  });

  it("the standard structure needs no AI", async () => {
    m.outlineStandard.mockResolvedValue({ ok: true, name: "EMS", items: [{ id: "s1", action: "add", title: "Conclusions", part: "", after: "m", purpose: "End." }] });
    const { host } = await mount();
    await click(button("Use the standard structure"));
    await until(() => !!button("Apply 1 change"));
    expect(m.aiStart).not.toHaveBeenCalled();
    expect(host.textContent).toContain("Standard structure: EMS");
    expect(host.textContent).toContain("Conclusions");
  });

  it("does not start when no AI key is set", async () => {
    const h = handlers(); h.requireAi.mockReturnValue(false);
    const host = document.createElement("div"); document.body.appendChild(host);
    await act(async () => { createRoot(host).render(<OutlineAssistantDialog {...h} />); });
    await click(button("Suggest an outline"));
    expect(m.aiStart).not.toHaveBeenCalled();
  });

  it("Use the standard structure does not save the scope; Save and Suggest do", async () => {
    m.outlineStandard.mockResolvedValue({ ok: true, name: "EMS", items: [{ id: "s1", action: "add", title: "Conclusions", part: "", after: "m", purpose: "End." }] });
    const { host } = await mount();
    await act(async () => { setValue(host.ownerDocument.querySelector("textarea")!, "Edited."); });
    expect(host.textContent).toContain("Saved with the project when you press Suggest or Save");
    await click(button("Use the standard structure"));
    await until(() => !!button("Apply 1 change"));
    expect(m.outlineSetScope).not.toHaveBeenCalled();
    await click(button("Back"));
    await click(button("Suggest an outline"));
    await until(() => !!button("Apply 2 changes"));
    expect(m.outlineSetScope).toHaveBeenCalledWith("Edited.");
  });

  it("asks before closing with unsaved scope edits", async () => {
    const { host, h } = await mount();
    await click(button("Cancel"));
    expect(h.onClose).toHaveBeenCalledTimes(1);   // nothing edited: closes at once
    await act(async () => { setValue(host.ownerDocument.querySelector("textarea")!, "Edited."); });
    await click(button("Cancel"));
    expect(h.onClose).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).toContain("Close without saving them?");
    await click([...document.body.querySelectorAll("button")].filter((b) => b.textContent === "Cancel").pop()!);   // keep editing
    expect(h.onClose).toHaveBeenCalledTimes(1);
    await click(button("Cancel"));
    await click(button("Discard"));
    expect(h.onClose).toHaveBeenCalledTimes(2);
  });

  it("says what each change does, with real titles and destinations", async () => {
    const { host } = await mount();
    await click(button("Suggest an outline"));
    await until(() => !!button("Apply 2 changes"));
    expect(host.textContent).toContain("Add “Study area” to the top level, after “Introduction”.");
  });

  it("mentions snapshots only when something was renamed or moved", async () => {
    m.outlineApply.mockResolvedValue({ ok: true, changed: [], remap: {}, skipped: [], created: ["n"] });
    const { host } = await mount();
    await click(button("Suggest an outline"));
    await until(() => !!button("Apply 2 changes"));
    await click(boxes()[1]);   // untick the rename: only the add is applied
    await click(button("Apply 1 change"));
    expect(host.textContent).toContain("0 changed, 1 created");
    expect(host.textContent).not.toContain("snapshot");
  });
});
