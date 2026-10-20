// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../backend/api", () => ({
  api: {
    requirementsCustom: vi.fn(), requirementsSave: vi.fn(), requirementsRemove: vi.fn(), researchRequirements: vi.fn(),
    guidelinesList: vi.fn(), aiStart: vi.fn(), aiPoll: vi.fn(), aiCancel: vi.fn(), openExternal: vi.fn(),
  },
}));
import { api } from "../../backend/api";
import { RequirementsDialog } from "./RequirementsDialog";
import { RequirementsSuggestDialog } from "./RequirementsSuggestDialog";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const base = { group: "Your requirements", kind: "check", severity: "warn", source: "guide.pdf" };
const ITEMS = [
  { ...base, id: "abs", title: "Abstract length", check: "section-words-max", section: ["abstract"], max: 150, quote: "At most 150 words.", why: "Hard limit.", verified: true },
  { ...base, id: "hl", title: "Highlights", check: "list-count", section: ["highlights"], min: 3, max: 5, quote: "Three to five highlights.", why: "Often asked.", verified: false },
];
const SENT = { feature: "requirements", estTokens: 100, window: 32000, reserve: 4000, overBudget: false, trimmed: false, sections: [], attached: [] };
const EXISTING = [{ id: "old", group: "Your requirements", title: "Old rule", kind: "check", check: "sources-doi", severity: "info" }];

async function mount(el: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => { root.render(el); });
  return host;
}
const suggestProps = () => ({ notify: vi.fn(), onClose: vi.fn(), requireAi: vi.fn(() => true), refresh: vi.fn(async () => {}), onSaved: vi.fn() });
const button = (label: string) => [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;
const boxes = () => [...document.body.querySelectorAll<HTMLInputElement>("input[type=checkbox]")];
async function click(el: HTMLElement) { await act(async () => { el.click(); }); }
async function until(fn: () => boolean) {
  for (let n = 0; n < 60 && !fn(); n++) await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
}
function setValue(el: HTMLInputElement | HTMLSelectElement, value: string) {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
}
const field = (label: string) => document.body.querySelector<HTMLInputElement>(`[aria-label="${label}"]`)!;

beforeEach(() => {
  vi.clearAllMocks(); document.body.innerHTML = "";
  m.guidelinesList.mockResolvedValue({ ok: true, files: [{ name: "guide.pdf", type: "pdf", size: 1, chars: 10, extracted: true, message: "" }] });
  m.aiStart.mockResolvedValue({ ok: true, job: "j1" });
  m.aiPoll.mockResolvedValue({ ok: true, state: "done", text: "", length: 0, elapsed: 1, cost: 0.01, result: { items: ITEMS, sent: SENT, cost: 0.01, model: "x", dropped: [{ id: "tone", title: "Writing style", reason: "Not a check the app has." }] } });
  m.aiCancel.mockResolvedValue({ ok: true, state: "cancelled" });
  m.requirementsCustom.mockResolvedValue({ ok: true, rows: EXISTING });
  m.requirementsSave.mockImplementation(async (rows: unknown) => ({ ok: true, rows }));
  m.requirementsRemove.mockResolvedValue({ ok: true, rows: [] });
  m.researchRequirements.mockResolvedValue({ ok: true, journal: "", name: "", source: "", readOn: "", summary: { ok: 0, warn: 0, info: 0, advice: 0 }, groups: [] });
});

async function toReview() {
  const props = suggestProps();
  const host = await mount(<RequirementsSuggestDialog {...props} />);
  await click(boxes()[0]);
  await click(button("Suggest requirements"));
  await until(() => host.textContent!.includes("Ignored from the reply"));
  return { host, props };
}

describe("RequirementsSuggestDialog", () => {
  it("ticks no guideline, says what is shared, and cannot start without one", async () => {
    const host = await mount(<RequirementsSuggestDialog {...suggestProps()} />);
    expect(boxes().every((b) => !b.checked)).toBe(true);
    expect(host.textContent).toContain("Ticked guidelines are sent to the AI. Nothing else is shared.");
    expect(button("Suggest requirements").disabled).toBe(true);
  });

  it("starts the job with the ticked guidelines; unverified items are unticked and marked", async () => {
    const { host } = await toReview();
    expect(m.aiStart).toHaveBeenCalledWith("requirements", { instruction: "", guidelines: ["guide.pdf"] });
    const [abs, hl] = boxes();
    expect(abs.checked).toBe(true);
    expect(hl.checked).toBe(false);
    expect(host.textContent).toContain("Abstract: at most 150 words");
    expect(host.textContent).toContain("Could not find this quote in the guideline: check it before adding");
    expect(host.textContent!.match(/Could not find this quote/g)).toHaveLength(1);
    expect(host.textContent).toContain("Writing style: Not a check the app has.");
    expect(button("Add 1 requirement")).toBeTruthy();
    expect(m.requirementsSave).not.toHaveBeenCalled();
  });

  it("sends only the ticked, edited rows together with the rows already saved", async () => {
    const { props } = await toReview();
    await click(boxes()[1]);   // tick the unverified one
    await act(async () => { setValue(field("At most for abs"), "120"); setValue(field("Title of hl"), "Highlights list"); });
    await click(button("Add 2 requirements"));
    expect(m.requirementsCustom).toHaveBeenCalled();
    const sent = m.requirementsSave.mock.calls[0][0] as { id: string; title: string; max?: number; why?: string; verified?: boolean }[];
    expect(sent.map((r) => r.id)).toEqual(["old", "abs", "hl"]);
    expect(sent[1].max).toBe(120);
    expect(sent[2].title).toBe("Highlights list");
    expect(sent[1]).not.toHaveProperty("why");
    expect(sent[1]).not.toHaveProperty("verified");
    expect(props.onSaved).toHaveBeenCalled();
    expect(document.body.textContent).toContain("Added 2 requirements");
  });

  it("an untick sends nothing for that row and Add needs a ticked row", async () => {
    await toReview();
    await click(boxes()[0]);
    expect(button("Add 0 requirements").disabled).toBe(true);
    await click(button("Add 0 requirements"));
    expect(m.requirementsSave).not.toHaveBeenCalled();
  });

  it("shows Python's refusal and stays on the review", async () => {
    m.requirementsSave.mockResolvedValue({ ok: false, error: "\"Abstract length\": max must be a whole number." });
    const { props } = await toReview();
    await click(button("Add 1 requirement"));
    expect(document.body.textContent).toContain("max must be a whole number");
    expect(props.notify).toHaveBeenCalledWith(expect.stringContaining("whole number"), "error");
    expect(button("Add 1 requirement")).toBeTruthy();
  });

  it("Stop cancels the job and saves nothing", async () => {
    m.aiPoll.mockResolvedValue({ ok: true, state: "running", text: "", length: 0, elapsed: 2, cost: null });
    const props = suggestProps();
    const host = await mount(<RequirementsSuggestDialog {...props} />);
    await click(boxes()[0]);
    await click(button("Suggest requirements"));
    await until(() => !!button("Stop"));
    expect(host.textContent).toContain("2 s");
    await click(button("Stop"));
    await until(() => !!button("Suggest requirements"));
    expect(m.aiCancel).toHaveBeenCalledWith("j1");
    expect(m.requirementsSave).not.toHaveBeenCalled();
    expect(props.notify).toHaveBeenCalledWith("Stopped. Nothing was changed.");
    expect(button("Add ")).toBeUndefined();
  });

  it("does not start when no AI key is set", async () => {
    const props = suggestProps(); props.requireAi.mockReturnValue(false);
    await mount(<RequirementsSuggestDialog {...props} />);
    await click(boxes()[0]);
    await click(button("Suggest requirements"));
    expect(m.aiStart).not.toHaveBeenCalled();
  });
});

describe("Manage my requirements", () => {
  const open = async () => mount(<RequirementsDialog notify={vi.fn()} onClose={() => {}} />);

  it("lists the saved rows and removes one only after a confirm", async () => {
    const host = await open();
    expect(host.textContent).toContain("Old rule");
    expect(host.textContent).toContain("Every cited source has a DOI");
    await click(button("Remove"));
    expect(m.requirementsRemove).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("Remove “Old rule” from your requirements?");
    await click([...document.body.querySelectorAll("button")].filter((b) => b.textContent === "Cancel").pop()!);
    expect(m.requirementsRemove).not.toHaveBeenCalled();
    await click(button("Remove"));
    await click([...document.body.querySelectorAll("button")].filter((b) => b.textContent === "Remove").pop()!);
    expect(m.requirementsRemove).toHaveBeenCalledWith("old");
    await until(() => host.textContent!.includes("You have not added any requirements"));
  });

  it("the add form sends a valid row appended to the saved ones", async () => {
    await open();
    await click(button("Add a requirement"));
    expect(button("Add requirement").disabled).toBe(true);
    await act(async () => { setValue(field("Requirement title"), "Abstract length"); });
    await act(async () => { setValue(field("Section title"), "abstract, summary"); });
    await act(async () => { setValue(field("At most"), "150"); });
    await click(button("Add requirement"));
    const sent = m.requirementsSave.mock.calls[0][0] as Record<string, unknown>[];
    expect(sent).toHaveLength(2);
    expect(sent[0].id).toBe("old");
    expect(sent[1]).toEqual({ id: "abstract-length", group: "Your requirements", title: "Abstract length", kind: "check", check: "section-words-max", section: ["abstract", "summary"], max: 150, severity: "warn" });
  });

  it("asks only for the parameters the kind needs", async () => {
    await open();
    await click(button("Add a requirement"));
    await act(async () => { setValue(field("What to check") as unknown as HTMLSelectElement, "sources-doi"); });
    expect(document.body.querySelector('[aria-label="Section title"]')).toBeNull();
    await act(async () => { setValue(field("What to check") as unknown as HTMLSelectElement, "objects-captioned"); });
    expect(document.body.querySelector('[aria-label="Which kind"]')).not.toBeNull();
  });

  it("shows Python's message when it refuses a row", async () => {
    m.requirementsSave.mockResolvedValue({ ok: false, error: "\"Abstract length\": a word limit is needed." });
    await open();
    await click(button("Add a requirement"));
    await act(async () => { setValue(field("Requirement title"), "Abstract length"); setValue(field("Section title"), "abstract"); setValue(field("At most"), "5"); });
    await click(button("Add requirement"));
    expect(document.body.querySelector('[role="alert"]')!.textContent).toContain("a word limit is needed");
  });
});
