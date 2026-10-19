// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../backend/api", () => ({
  api: {
    recentProjects: vi.fn(), suggestProjectPath: vi.fn(), newProject: vi.fn(), openProject: vi.fn(), chooseFolder: vi.fn(),
    researchProfiles: vi.fn(), researchGetSettings: vi.fn(), researchSetSettings: vi.fn(), researchRequirements: vi.fn(),
    guidelinesList: vi.fn(), guidelinesAdd: vi.fn(), guidelinesAddText: vi.fn(), guidelinesRead: vi.fn(), guidelinesRemove: vi.fn(),
    openExternal: vi.fn(),
  },
}));
import { api } from "../../backend/api";
import { Launch } from "../Launch";
import { GuidelinesDialog } from "./GuidelinesDialog";
import { ProjectSettingsDialog } from "./ProjectSettingsDialog";
import { RequirementsDialog } from "./RequirementsDialog";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const PROFILES = [
  { id: "ems", name: "Environmental Modelling & Software", publisher: "Elsevier", kind: "manuscript", source: "https://example.org/guide", readOn: "2026-10-01" },
  { id: "generic-manuscript", name: "Generic manuscript", publisher: "", kind: "manuscript", source: "", readOn: "" },
  { id: "generic-proposal", name: "Generic proposal", publisher: "", kind: "proposal", source: "", readOn: "" },
];

async function mount(el: React.ReactElement) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => { root.render(el); });
  return { host, root };
}
const button = (_host: HTMLElement, label: string) => {
  const all = [...document.body.querySelectorAll("button")];
  return (all.find((b) => b.textContent === label) ?? all.find((b) => b.textContent?.includes(label))) as HTMLButtonElement;
};
function setValue(el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
}

beforeEach(() => {
  vi.clearAllMocks(); document.body.innerHTML = "";
  m.recentProjects.mockResolvedValue({ ok: true, recents: [] });
  m.suggestProjectPath.mockResolvedValue({ ok: true, path: "/tmp/p" });
  m.newProject.mockResolvedValue({ ok: true });
  m.researchProfiles.mockResolvedValue({ ok: true, profiles: PROFILES });
});

describe("Launch", () => {
  it("shows kind and journal only for Research and passes them to newProject", async () => {
    const { host } = await mount(<Launch onOpened={() => {}} />);
    expect(host.textContent).not.toContain("What are you writing?");
    await act(async () => { button(host, "Research").click(); });
    expect(host.textContent).toContain("What are you writing?");
    expect(host.textContent).toContain("Starts with the journal's section layout");
    const select = host.querySelector<HTMLSelectElement>('select[aria-label="Target journal"]')!;
    expect([...select.options].map((o) => o.textContent)).toEqual(["Environmental Modelling & Software", "Generic manuscript", "No target journal (standard structure)"]);
    expect(select.value).toBe("ems");
    await act(async () => { setValue(host.querySelector<HTMLInputElement>('input[aria-label="New project title"]')!, "Paper"); });
    await act(async () => { button(host, "Create").click(); });
    expect(m.newProject).toHaveBeenCalledWith("Paper", "/tmp/p", "research", "manuscript", "ems");
  });

  it("switches to a proposal and its own profiles", async () => {
    const { host } = await mount(<Launch onOpened={() => {}} />);
    await act(async () => { button(host, "Research").click(); });
    await act(async () => { button(host, "Proposal").click(); });
    await act(async () => { setValue(host.querySelector<HTMLInputElement>('input[aria-label="New project title"]')!, "Grant"); });
    await act(async () => { button(host, "Create").click(); });
    expect(m.newProject).toHaveBeenCalledWith("Grant", "/tmp/p", "research", "proposal", "generic-proposal");
  });

  it("passes nothing new for a story", async () => {
    const { host } = await mount(<Launch onOpened={() => {}} />);
    await act(async () => { setValue(host.querySelector<HTMLInputElement>('input[aria-label="New project title"]')!, "Novel"); });
    await act(async () => { button(host, "Create").click(); });
    expect(m.newProject).toHaveBeenCalledWith("Novel", "/tmp/p", "story");
  });
});

describe("ProjectSettingsDialog", () => {
  it("saves the kind and journal", async () => {
    const saved = { ok: true, kind: "manuscript", journal: "generic-manuscript", journalName: "Generic manuscript", citationStyle: "apa", source: "", readOn: "" };
    m.researchGetSettings.mockResolvedValue({ ...saved, journal: "ems", journalName: "Environmental Modelling & Software", source: "https://example.org/guide", readOn: "2026-10-01" });
    m.researchSetSettings.mockResolvedValue(saved);
    const onClose = vi.fn(); const notify = vi.fn();
    const { host } = await mount(<ProjectSettingsDialog notify={notify} onClose={onClose} />);
    expect(host.textContent).toContain("Rules read on 2026-10-01");
    expect(host.textContent).toContain("never moves or deletes your sections");
    await act(async () => { setValue(document.body.querySelector<HTMLSelectElement>("select")!, "generic-manuscript"); });
    await act(async () => { button(host, "Save").click(); });
    expect(m.researchSetSettings).toHaveBeenCalledWith("manuscript", "generic-manuscript");
    expect(onClose).toHaveBeenCalled();
  });
});

describe("RequirementsDialog", () => {
  const report = {
    ok: true, journal: "ems", name: "Environmental Modelling & Software", source: "https://example.org/guide", readOn: "2026-10-01",
    summary: { ok: 12, warn: 3, info: 1, advice: 14 },
    groups: [
      { title: "Structure", items: [
        { id: "a", title: "Abstract length", status: "ok", message: "218 words." },
        { id: "b", title: "Highlights", status: "warn", message: "None found." },
      ] },
      { title: "Submission", items: [{ id: "c", title: "Software availability", status: "advice", message: "State where to get it." }] },
    ],
  };
  it("shows groups, status words, the summary and the reminder style", async () => {
    m.researchRequirements.mockResolvedValue(report);
    const { host } = await mount(<RequirementsDialog notify={() => {}} onClose={() => {}} />);
    expect(host.textContent).toContain("12 ok, 3 need attention, 14 reminders");
    expect(host.textContent).toContain("Structure");
    expect(host.textContent).toContain("Submission");
    const items = [...document.body.querySelectorAll<HTMLElement>("li[data-status]")];
    expect(items.map((i) => i.dataset.status)).toEqual(["ok", "warn", "advice"]);
    expect(items[1].textContent).toContain("Needs attention");
    expect(items[2].textContent).toContain("Reminder");
    expect(items[2].className).toContain("lw-faint");
    expect(items[0].className).not.toContain("lw-faint");
    expect(host.textContent).toContain("Rules read on 2026-10-01; check the journal's live guide before you submit.");
    await act(async () => { button(host, "Check again").click(); });
    expect(m.researchRequirements).toHaveBeenCalledTimes(2);
  });
  it("opens the source link through the app", async () => {
    m.researchRequirements.mockResolvedValue(report);
    m.openExternal.mockResolvedValue({ ok: true });
    const { host } = await mount(<RequirementsDialog notify={() => {}} onClose={() => {}} />);
    await act(async () => { host.querySelector<HTMLAnchorElement>("a")!.click(); });
    expect(m.openExternal).toHaveBeenCalledWith("https://example.org/guide");
  });
});

describe("GuidelinesDialog", () => {
  const files = [
    { name: "guide.pdf", type: "pdf", size: 2048, chars: 900, extracted: true, message: "" },
    { name: "scan.pdf", type: "pdf", size: 4096, chars: 0, extracted: false, message: "No text could be read from this PDF." },
  ];
  beforeEach(() => { m.guidelinesList.mockResolvedValue({ ok: true, files }); });

  it("lists files and shows a failed extraction message", async () => {
    const { host } = await mount(<GuidelinesDialog notify={() => {}} onClose={() => {}} />);
    expect(host.textContent).toContain("Guidelines stay on this computer.");
    expect(host.textContent).toContain("guide.pdf");
    expect(host.textContent).toContain("No text could be read from this PDF.");
  });

  it("adds pasted text", async () => {
    m.guidelinesAddText.mockResolvedValue({ ok: true, name: "call.md" });
    const { host } = await mount(<GuidelinesDialog notify={() => {}} onClose={() => {}} />);
    await act(async () => { button(host, "Paste text").click(); });
    await act(async () => { setValue(host.querySelector<HTMLInputElement>('input[aria-label="Guideline title"]')!, "Call"); });
    await act(async () => { setValue(host.querySelector<HTMLTextAreaElement>('textarea[aria-label="Guideline text"]')!, "Page limit 10."); });
    await act(async () => { button(host, "Add text").click(); });
    expect(m.guidelinesAddText).toHaveBeenCalledWith("Call", "Page limit 10.");
    expect(m.guidelinesList).toHaveBeenCalledTimes(2);
  });

  it("asks before removing", async () => {
    m.guidelinesRemove.mockResolvedValue({ ok: true });
    const { host } = await mount(<GuidelinesDialog notify={() => {}} onClose={() => {}} />);
    await act(async () => { button(host, "Remove").click(); });
    expect(m.guidelinesRemove).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("Remove guideline file");
    const confirm = [...document.body.querySelectorAll("button")].filter((b) => b.textContent === "Remove").pop()!;
    await act(async () => { confirm.click(); });
    expect(m.guidelinesRemove).toHaveBeenCalledWith("guide.pdf");
  });

  it("views text with a truncation note", async () => {
    m.guidelinesRead.mockResolvedValue({ ok: true, name: "guide.pdf", text: "abc", truncated: true, chars: 900 });
    const { host } = await mount(<GuidelinesDialog notify={() => {}} onClose={() => {}} />);
    await act(async () => { button(host, "View text").click(); });
    expect(m.guidelinesRead).toHaveBeenCalledWith("guide.pdf");
    expect(host.textContent).toContain("first part only");
    expect(host.querySelector<HTMLTextAreaElement>("textarea[readonly]")!.value).toBe("abc");
  });
});
