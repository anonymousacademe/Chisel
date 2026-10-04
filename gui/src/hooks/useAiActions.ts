import type { Dispatch, RefObject, SetStateAction } from "react";
import { api } from "../backend/api";
import type { AliasSuggestion, CanonProposal, DocumentPayload, GenerateResult, Issue, SceneMention, SentReport as SentInfo, Workspace } from "../data/types";
import type { Dialog } from "../data/dialog";
import type { AiKind } from "../backend/api";
import { anchorDraft } from "../editor/drafts";
import { cost } from "../data/appLogic";
import { isTrimmed, sentSummary } from "../data/sent";
import type { SaveController } from "../editor/saveController";
import type { EditorHandle } from "../components/EditorPane";
import type { AssistantTab } from "../components/Assistant";
import type { Notice } from "../components/Toast";

interface Deps {
  saver: SaveController;
  ws: Workspace | null | undefined;
  docRef: RefObject<DocumentPayload | null>;
  editorRef: RefObject<EditorHandle | null>;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  refresh: () => Promise<unknown>;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
  aiCall: <X>(label: string, verb: string, kind: AiKind, args: Record<string, unknown>) => Promise<(X & { ok: true }) | null>;
  requireAi: () => boolean;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  setIssues: Dispatch<SetStateAction<Issue[]>>;
  setIssuesSent: (s: SentInfo | null) => void;
  setTab: (t: AssistantTab) => void;
  setAssistantOpen: (open: boolean) => void;
  setSpansVersion: Dispatch<SetStateAction<number>>;
  setNoteVersion: Dispatch<SetStateAction<number>>;
  setMentions: (m: SceneMention[]) => void;
}

/**
 * The AI actions on the open scene: continuity, aliases, canon, style, drafting, and accepting or rejecting drafts.
 * Everything the model returns is a suggestion: a review list, or a pending <!--ai--> draft with Accept / Reject.
 * Nothing here edits prose on its own.
 */
export function useAiActions(d: Deps) {
  const { saver, ws, docRef, editorRef, notify, refresh, openDoc, aiCall, requireAi, setDialog, setIssues, setIssuesSent, setTab, setAssistantOpen,
    setSpansVersion, setNoteVersion, setMentions } = d;
  const liveText = () => editorRef.current?.getText() ?? "";
  const quickContinuity = async () => {
    const d = docRef.current;
    if (!d || d.kind !== "scene") return notify("Open a scene first.");
    const r = await aiCall<{ issues: Issue[]; waived: number; cost: number | null; sent: SentInfo }>("Checking continuity…", "checking continuity", "continuity", { doc_id: d.id, text: liveText() });
    if (!r || docRef.current?.id !== d.id) return;
    setIssues(r.issues); setIssuesSent(r.sent); setTab("assistant"); setAssistantOpen(true);
    const waived = r.waived ? ` (${r.waived} waived)` : "";
    notify((r.issues.length ? `${r.issues.length} possible conflict${r.issues.length === 1 ? "" : "s"}` : "No continuity issues found") + waived + cost(r.cost)
      + (isTrimmed(r.sent) ? `; ${sentSummary(r.sent)}` : ""), "info", { label: "What was sent", run: () => setDialog({ kind: "sent", report: r.sent }) });
  };
  const reviewIssue = (it: Issue) => {
    if (it.row === null) notify("Could not locate that passage; the quote on the card is what the assistant flagged.");
    else editorRef.current?.gotoLine(it.row);
  };
  const dismissIssue = async (it: Issue) => {
    const d = docRef.current;
    if (!d) return;
    const r = await api.waive(it.key, d.id);
    if (!r.ok) return notify(r.error, "error");
    setIssues((list) => list.filter((x) => x.key !== it.key));
    notify("Dismissed. It will not be reported again (Restore waived issues brings it back).");
  };
  const restoreWaived = async () => {
    const d = docRef.current;
    if (!d || d.kind !== "scene") return notify("Open a scene first.");
    const r = await api.restoreWaivers(d.id);
    if (!r.ok) return notify(r.error, "error");
    notify(r.restored ? `Restored ${r.restored} waived issue${r.restored === 1 ? "" : "s"}; the next check reports them again.` : "No waived issues are recorded for this scene.");
  };

  const findAliases = async () => {
    const d = docRef.current;
    if (!d || d.kind !== "scene") return notify("Open a scene first.");
    const r = await aiCall<{ suggestions: AliasSuggestion[]; cost: number | null; sent: SentInfo }>("Looking for aliases…", "looking for aliases", "aliases", { doc_id: d.id, text: liveText() });
    if (!r) return;
    if (!r.suggestions.length) return notify("No new aliases found" + cost(r.cost) + (isTrimmed(r.sent) ? `; ${sentSummary(r.sent)}` : ""), "info", { label: "What was sent", run: () => setDialog({ kind: "sent", report: r.sent }) });
    setDialog({ kind: "aliases", items: r.suggestions, sent: r.sent });
  };
  const applyAliases = async (picked: AliasSuggestion[]) => {
    setDialog(null);
    const r = await api.applyAliases(picked.map((p) => ({ entity: p.entity, surface: p.surface })));
    if (!r.ok) return notify(r.error, "error");
    notify(`Added ${r.added} alias${r.added === 1 ? "" : "es"} to your notes.`);
    await refresh(); setSpansVersion((v) => v + 1); setNoteVersion((v) => v + 1);
    const d = docRef.current;
    if (d?.kind === "scene") { const c = await api.sceneContext(d.id, liveText()); if (c.ok) setMentions(c.mentions); }
  };

  const updateBible = async () => {
    const d = docRef.current;
    if (!d || d.kind !== "scene") return notify("Open a scene first.");
    const r = await aiCall<{ updates: CanonProposal[]; cost: number | null; sent: SentInfo }>("Reading the scene for new canon…", "reading for canon", "canon", { doc_id: d.id, text: liveText() });
    if (!r) return;
    if (!r.updates.length) return notify("No new canon found in this scene" + cost(r.cost) + (isTrimmed(r.sent) ? `; ${sentSummary(r.sent)}` : ""), "info", { label: "What was sent", run: () => setDialog({ kind: "sent", report: r.sent }) });
    setDialog({ kind: "canon", items: r.updates, sent: r.sent });
  };
  const applyCanon = async (picked: { entity: string; facts: string[] }[]) => {
    setDialog(null);
    const r = await api.applyCanon(picked);
    if (!r.ok) return notify(r.error, "error");
    notify(`Added canon to ${r.applied} note${r.applied === 1 ? "" : "s"}.`);
    setNoteVersion((v) => v + 1); void refresh();
  };

  const openStyle = async () => {
    if (!ws?.status.hasStyle) { // first open creates the stub, as the terminal app does
      const r = await api.ensureStyle();
      if (!r.ok) return notify(r.error, "error");
      await refresh();
    }
    void openDoc("style.md");
  };
  const learnStyle = async () => {
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await aiCall<{ markdown: string; replacing: boolean; samples: number; cost: number | null }>("Learning your style…", "learning your style", "style", {});
    if (r) setDialog({ kind: "style", markdown: r.markdown, replacing: r.replacing });
  };
  const saveStyle = async (text: string) => {
    setDialog(null);
    const r = await api.saveStyle(text);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    if (docRef.current?.id === "style.md") await openDoc("style.md", { force: true });
    notify("Saved style.md");
  };

  /** Draft at the cursor, expand a {{expand: }} marker, or rewrite the selection. */
  const runGenerate = async (mode: "draft" | "expand" | "rewrite", instruction: string, from: number, to: number) => {
    const d = docRef.current, ed = editorRef.current;
    if (!d || !ed) return;
    const snapshot = ed.getText();
    const r = await aiCall<GenerateResult & { cost: number | null; noStyle?: boolean }>("Drafting…", "drafting", "generate", { mode, instruction, doc_id: d.id, text: snapshot, start: from, end: to });
    if (!r) return;
    if (docRef.current?.id !== d.id || !editorRef.current) return notify("Scene changed while drafting; draft discarded.", "error");
    const at = anchorDraft(editorRef.current.getText(), snapshot, r, editorRef.current.head());
    if (!at) return notify("The text changed while drafting; draft discarded.", "error");
    if (r.draftId && r.original !== null) { // the marker must never exist without its original
      const reg = await api.registerDraft(d.id, r.draftId, r.original);
      if (!reg.ok) return notify(reg.error, "error");
    }
    editorRef.current.insertDraft(at.from, at.to, r.insert);
    notify(`AI draft ready: F7 accept, F8 reject${cost(r.cost)}${isTrimmed(r.sent) ? `; ${sentSummary(r.sent)}` : ""}`, "info",
      { label: "What was sent", run: () => setDialog({ kind: "sent", report: r.sent }) });
    if (r.noStyle) notify("Tip: learn a style guide first (AI menu, Learn style guide).");
  };
  const startGenerate = (): boolean => {
    const ed = editorRef.current;
    if (!ed || docRef.current?.kind !== "scene") { notify("Open a scene first."); return true; }
    if (!requireAi()) return true;
    const sel = ed.selection();
    if (sel.text.trim()) {
      setDialog({ kind: "generate", mode: "rewrite", from: sel.from, to: sel.to, title: "Rewrite the selection",
        label: "Edit the instruction", initial: "Rewrite this in my style." });
      return true;
    }
    const head = ed.head();
    const marker = ed.spans().find((sp) => sp.kind === "expand" && head >= sp.start && head <= sp.end);
    if (marker) {
      if (!marker.instruction?.trim()) notify("Empty {{expand: }} marker: say what to write.", "error");
      else void runGenerate("expand", marker.instruction, marker.start, marker.end);
      return true;
    }
    setDialog({ kind: "generate", mode: "draft", from: head, to: head, title: "Draft new prose here",
      label: "What should the AI write?", initial: "" });
    return true;
  };
  const rewriteSelection = () => {
    const ed = editorRef.current;
    if (!ed || !ed.selection().text.trim()) return notify("Select a passage in the text first, then choose Rewrite.");
    startGenerate();
  };

  const resolveDraft = async (index: number | null, accept: boolean) => {
    const d = docRef.current, ed = editorRef.current;
    if (!d || !ed) return;
    const text = ed.getText();
    const r = await api.resolveDrafts(d.id, text, accept, index);
    if (!r.ok) return notify(r.error, "error");
    if (r.found === 0) return notify("No AI drafts in this scene.");
    if (ed.getText() !== text) return notify("The text changed; try again.", "error");
    ed.applyEdits(r.edits);
    if (r.skipped) notify(`${r.skipped} draft${r.skipped === 1 ? "" : "s"} left: the original text is missing. Accept ${r.skipped === 1 ? "it" : "them"} or edit by hand.`, "error");
    else notify(r.found > 1 ? `${r.found} AI drafts ${accept ? "accepted" : "rejected"}.` : `AI draft ${accept ? "accepted" : "rejected"}.`);
  };
  const resolveAtCursor = (accept: boolean): boolean => {
    const i = editorRef.current?.pendingIndexAtCursor() ?? -1;
    if (i < 0) notify("No AI draft under the cursor.");
    else void resolveDraft(i, accept);
    return true;
  };

  return { liveText, quickContinuity, reviewIssue, dismissIssue, restoreWaived, findAliases, applyAliases, updateBible, applyCanon,
    openStyle, learnStyle, saveStyle, runGenerate, startGenerate, rewriteSelection, resolveDraft, resolveAtCursor };
}
