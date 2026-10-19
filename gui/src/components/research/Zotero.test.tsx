// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../backend/api", () => ({
  api: {
    zoteroGetSettings: vi.fn(), zoteroSetSettings: vi.fn(), zoteroSetKey: vi.fn(), zoteroClearKey: vi.fn(), zoteroStatus: vi.fn(),
    zoteroCollections: vi.fn(), zoteroSavedCollections: vi.fn(), zoteroSyncPlan: vi.fn(), zoteroSyncApply: vi.fn(),
  },
}));
import { api } from "../../backend/api";
import { SyncReviewDialog } from "./SyncReviewDialog";
import { ZoteroSettingsDialog } from "./ZoteroSettingsDialog";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

async function mount(el: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => { root.render(el); });
  return { host, root };
}
const button = (host: HTMLElement, label: string) => { const all = [...host.querySelectorAll("button")]; return (all.find((b) => b.textContent === label) ?? all.find((b) => b.textContent?.includes(label))) as HTMLButtonElement; };
function type(input: HTMLInputElement, value: string) {
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => { vi.clearAllMocks(); document.body.innerHTML = ""; });

describe("ZoteroSettingsDialog", () => {
  it("never renders the key, saves it, then clears the field", async () => {
    m.zoteroGetSettings.mockResolvedValue({ ok: true, userId: "", webBase: "https://api.zotero.org", local: true, localBase: "http://127.0.0.1:23119", file: "", keySet: true });
    m.zoteroSetKey.mockResolvedValue({ ok: true, keySet: true });
    const { host } = await mount(<ZoteroSettingsDialog notify={() => {}} onClose={() => {}} />);
    const key = host.querySelector<HTMLInputElement>('input[type="password"]')!;
    expect(key.value).toBe("");
    expect(host.textContent).toContain("A key is saved");
    await act(async () => { type(key, "s3cret-key"); });
    expect(key.value).toBe("s3cret-key");
    await act(async () => { button(host, "Save key").click(); });
    expect(m.zoteroSetKey).toHaveBeenCalledWith("s3cret-key");
    expect(key.value).toBe("");
    expect(host.innerHTML).not.toContain("s3cret-key");
  });
});

const rows = [
  { id: "a", key: "K1", action: "new", summary: "Add A", blocked: "" },
  { id: "b", key: "K2", action: "changed", summary: "Change B", blocked: "" },
  { id: "c", key: "K3", action: "key-mismatch", summary: "Clash C", blocked: "Fix the key first" },
];

describe("SyncReviewDialog", () => {
  beforeEach(() => {
    m.zoteroSavedCollections.mockResolvedValue({ ok: true, keys: [] });
    m.zoteroCollections.mockResolvedValue({ ok: true, collections: [
      { key: "C1", path: "AI and Computing / WRRI", items: 4 }, { key: "C2", path: "Hydrology / Runoff", items: null },
    ] });
    m.zoteroSyncPlan.mockResolvedValue({ ok: true, rows, report: ["Read 3 items."], backend: "local", token: "t1" });
    m.zoteroSyncApply.mockResolvedValue({ ok: true, changed: ["a"], skipped: [{ id: "b", reason: "edited" }], recorded: true });
  });

  it("previews without applying, leaves blocked rows unticked, and applies only ticked ids", async () => {
    const onApplied = vi.fn();
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={onApplied} onClose={() => {}} />);
    await act(async () => { button(host, "Preview changes").click(); });
    expect(m.zoteroSyncPlan).toHaveBeenCalledWith({});
    expect(m.zoteroSyncApply).not.toHaveBeenCalled();
    expect(host.textContent).toContain("Read 3 items.");
    expect(host.textContent).toContain("Fix the key first");
    const boxes = host.querySelectorAll<HTMLInputElement>(".lw-review:not([aria-label=\"Collections\"]) input[type=\"checkbox\"]");
    expect([...boxes].map((b) => b.checked)).toEqual([true, true, false]);
    expect(boxes[2].disabled).toBe(true);
    await act(async () => { boxes[1].click(); });
    await act(async () => { button(host, "Apply 1 change").click(); });
    expect(m.zoteroSyncApply).toHaveBeenCalledWith(["a"], "t1");
    expect(onApplied).toHaveBeenCalled();
    expect(host.textContent).toContain("b: edited");
  });

  const collBoxes = (host: HTMLElement) => [...host.querySelectorAll<HTMLInputElement>('[aria-label="Collections"] input[type="checkbox"]')];

  it("filters the collection list and scopes the preview to the ticked collections", async () => {
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={() => {}} onClose={() => {}} />);
    expect(host.textContent).toContain("Whole library");
    expect(host.textContent).toContain("Runoff");
    await act(async () => { type(host.querySelector<HTMLInputElement>('input[aria-label="Filter collections"]')!, "wrri"); });
    expect(host.textContent).not.toContain("Runoff");
    await act(async () => { collBoxes(host)[0].click(); });
    expect(host.textContent).toContain("1 collection selected");
    await act(async () => { button(host, "Preview changes").click(); });
    expect(m.zoteroSyncPlan).toHaveBeenCalledWith({ collections: ["C1"], includeSubcollections: true });
  });

  it("multi-select sends every ticked collection and the subcollection choice", async () => {
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={() => {}} onClose={() => {}} />);
    await act(async () => { collBoxes(host).forEach((b) => b.click()); });
    expect(host.textContent).toContain("2 collections selected");
    await act(async () => { [...host.querySelectorAll<HTMLInputElement>("input")].find((i) => i.parentElement?.textContent?.includes("Include subcollections"))!.click(); });
    await act(async () => { button(host, "Preview changes").click(); });
    expect(m.zoteroSyncPlan).toHaveBeenCalledWith({ collections: ["C1", "C2"], includeSubcollections: false });
  });

  it("preselects the saved collections and offers Sync again", async () => {
    m.zoteroSavedCollections.mockResolvedValue({ ok: true, keys: ["C2"] });
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={() => {}} onClose={() => {}} />);
    expect(collBoxes(host).map((b) => b.checked)).toEqual([false, true]);
    expect(button(host, "Sync again")).toBeTruthy();
    await act(async () => { collBoxes(host)[0].click(); });
    expect(button(host, "Preview changes")).toBeTruthy();
  });

  it("shows a spinner while the plan is pending, and Cancel discards a late result", async () => {
    let finish: (v: unknown) => void = () => {};
    m.zoteroSyncPlan.mockReturnValue(new Promise((res) => { finish = res; }));
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={() => {}} onClose={() => {}} />);
    await act(async () => { button(host, "Preview changes").click(); });
    expect(host.querySelector(".lw-spinner")).toBeTruthy();
    expect(host.textContent).toContain("Reading Zotero");
    expect(button(host, "Preview changes").disabled).toBe(true);
    await act(async () => { button(host, "Cancel preview").click(); });
    expect(host.querySelector(".lw-spinner")).toBeNull();
    expect(host.textContent).toContain("Nothing was written");
    await act(async () => { finish({ ok: true, rows, report: ["Late."], backend: "local" }); });
    expect(host.textContent).not.toContain("Late.");
    expect(host.textContent).not.toContain("Add A");
  });

  it("starting a new preview drops the old one, so it cannot be applied against the new plan", async () => {
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={() => {}} onClose={() => {}} />);
    await act(async () => { button(host, "Preview changes").click(); });
    expect(host.textContent).toContain("Add A");
    m.zoteroSyncPlan.mockReturnValue(new Promise(() => {}));
    await act(async () => { button(host, "Preview changes").click(); });
    expect(host.textContent).not.toContain("Add A");
    expect(host.textContent).not.toMatch(/Apply \d+ change/);
  });

  it("select all / none, search and the selected count", async () => {
    const { host } = await mount(<SyncReviewDialog notify={() => {}} onApplied={() => {}} onClose={() => {}} />);
    await act(async () => { button(host, "Preview changes").click(); });
    expect(host.textContent).toContain("2 of 3 selected");
    await act(async () => { button(host, "Select none").click(); });
    expect(host.textContent).toContain("0 of 3 selected");
    await act(async () => { button(host, "Select all").click(); });
    expect(host.textContent).toContain("2 of 3 selected");     // the blocked row stays unticked
    await act(async () => { button(host, "Select none").click(); });
    await act(async () => { type(host.querySelector<HTMLInputElement>('input[aria-label="Search papers"]')!, "change b"); });
    expect(host.textContent).not.toContain("Add A");
    await act(async () => { button(host, "Select all").click(); });
    expect(host.textContent).toContain("1 of 3 selected");
    await act(async () => { button(host, "Apply 1 change").click(); });
    expect(m.zoteroSyncApply).toHaveBeenCalledWith(["b"], "t1");
  });
});
