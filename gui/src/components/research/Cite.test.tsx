// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../backend/api", () => ({
  api: {
    searchSources: vi.fn(), sourceCard: vi.fn(), zoteroItemCollections: vi.fn(), openInZotero: vi.fn(), openExternal: vi.fn(),
  },
}));
import { api } from "../../backend/api";
import { CiteDialog } from "./CiteDialog";
import { SourceCard } from "./SourceCard";
import { citationCard, citeCompletion, citeText } from "../../data/research";
import { contextActions } from "../../data/editorMenu";
import { specsFor, type Span } from "../../editor/spans";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

async function mount(el: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => { root.render(el); });
  return { host, root };
}
const button = (host: HTMLElement, label: string) => [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;
function type(input: HTMLInputElement, value: string) {
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

const hit = { key: "daneshgar2024", display: "Daneshgar et al. 2024", title: "ML for wastewater", authors: "Daneshgar", year: 2024, venue: "Water Research" };
const card = {
  ok: true, key: "daneshgar2024", citeAs: "[[@daneshgar2024]]", display: "Daneshgar et al. 2024", title: "ML for wastewater",
  authors: "Daneshgar, S.", year: 2024, venue: "Water Research", doi: "10.1/x", url: "", zoteroKey: "AB12CD34", noteCount: 2, highlightCount: 5,
};

beforeEach(() => { vi.clearAllMocks(); document.body.innerHTML = ""; });

describe("citation spans and text", () => {
  const span = (over: Partial<Span>): Span => ({ kind: "citation", start: 0, end: 20, status: "resolved", keys: ["a"], ...over });
  it("maps status to the right class", () => {
    expect(specsFor([span({})], 100, 50)[0].cls).toBe("lw-cite lw-cite--resolved");
    expect(specsFor([span({ status: "unresolved" })], 100, 50)[0].cls).toBe("lw-cite lw-cite--unresolved");
  });
  it("builds the inserted text", () => {
    expect(citeText("k")).toBe("[[@k]]");
    expect(citeText("k", "12")).toBe("[[@k, p. 12]]");
    expect(citeText("k", " ch. 3 ")).toBe("[[@k, ch. 3]]");
    expect(citeCompletion("", "k")).toEqual({ insert: "k]]", cursor: 3 });
    expect(citeCompletion("]] more", "k")).toEqual({ insert: "k", cursor: 3 });
  });
  it("hover text: resolved shows label and title, unresolved says what to do", () => {
    expect(citationCard({ status: "resolved", keys: ["k"], label: "Smith 2023", title: "A paper" })).toMatchObject({ title: "Smith 2023", body: "A paper" });
    const u = citationCard({ status: "unresolved", keys: ["zzz"] });
    expect(u.missing).toBe(true);
    expect(u.body).toBe("No source with this key. Sync from Zotero, or check the key.");
  });
  it("the context menu offers Cite only in research projects, and no create-note on a citation", () => {
    expect(contextActions({ research: true }, []).some((a) => a.id === "cite")).toBe(true);
    expect(contextActions({}, []).some((a) => a.id === "cite")).toBe(false);
    const acts = contextActions({ span: span({}), word: "daneshgar", research: true }, []);
    expect(acts.some((a) => a.id === "create-note")).toBe(false);
  });
});

describe("CiteDialog", () => {
  it("inserts [[@key]] without a page and [[@key, p. 12]] with one", async () => {
    m.searchSources.mockResolvedValue({ ok: true, sources: [hit] });
    const onInsert = vi.fn(), onClose = vi.fn();
    const { host } = await mount(<CiteDialog notify={() => {}} onInsert={onInsert} onSync={() => {}} onClose={onClose} />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(host.textContent).toContain("Daneshgar et al. 2024");
    expect(host.textContent).toContain("Ctrl+Shift+L");
    await act(async () => { button(host, "Insert").click(); });
    expect(onInsert).toHaveBeenLastCalledWith("[[@daneshgar2024]]");
    await act(async () => { type(host.querySelector<HTMLInputElement>('input[aria-label="Page"]')!, "12"); });
    await act(async () => { button(host, "Insert").click(); });
    expect(onInsert).toHaveBeenLastCalledWith("[[@daneshgar2024, p. 12]]");
  });

  it("with no sources, says to sync first and offers the sync dialog", async () => {
    m.searchSources.mockResolvedValue({ ok: true, sources: [] });
    const onSync = vi.fn();
    const { host } = await mount(<CiteDialog notify={() => {}} onInsert={() => {}} onSync={onSync} onClose={() => {}} />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(host.textContent).toContain("Sync from Zotero first");
    await act(async () => { button(host, "Sync sources from Zotero").click(); });
    expect(onSync).toHaveBeenCalled();
  });
});

describe("SourceCard", () => {
  it("shows Cite as and Open in Zotero, and the collections", async () => {
    m.sourceCard.mockResolvedValue(card);
    m.zoteroItemCollections.mockResolvedValue({ ok: true, collections: ["AI / WRRI"] });
    m.openInZotero.mockResolvedValue({ ok: true });
    const { host } = await mount(<SourceCard id="entities/sources/daneshgar2024.md" notify={() => {}} />);
    expect(host.textContent).toContain("[[@daneshgar2024]]");
    expect(host.textContent).toContain("AI / WRRI");
    expect(host.textContent).toContain("5 highlights");
    await act(async () => { button(host, "Open in Zotero").click(); });
    expect(m.openInZotero).toHaveBeenCalledWith("entities/sources/daneshgar2024.md");
  });

  it("explains in plain words when the collections cannot be read", async () => {
    m.sourceCard.mockResolvedValue(card);
    m.zoteroItemCollections.mockResolvedValue({ ok: false, error: "Zotero is not running." });
    const { host } = await mount(<SourceCard id="x" notify={() => {}} />);
    expect(host.textContent).toContain("Zotero is not running.");
    expect(host.textContent).toContain("[[@daneshgar2024]]");
  });
});
