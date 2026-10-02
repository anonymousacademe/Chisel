import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, STREAMING_KINDS, type AiKind } from "./backend/api";
import { runAiJob, AiCancelled, type AiJob } from "./backend/aijobs";
import { DraftPanel, ProgressStrip } from "./components/AiProgress";
import type { AiRunView } from "./components/aiRun";
import type {
  AliasSuggestion, AttachItem, AttachReport, BinderNode, CanonProposal, ChatMessage, ChatSummary, CollectionColor, CommentRow, DetailsPatch, DocumentPayload, EntityInfo, EntityType, GenerateResult, Issue, Remap, RenameDone, RenamePreview, RenameScope, RenameUndone, SceneMention, SettingsInfo, StyleStatus, SyncInfo, Workspace,
} from "./data/types";
import type { BridgeResult } from "./backend/transport";
import { anchorDraft } from "./editor/drafts";
import { collectExpanded, isOpenable } from "./data/tree";
import { follow, type MovePlan } from "./data/reorder";
import { SaveController, type SaveState } from "./editor/saveController";
import type { Card, CursorInfo, SpellTarget } from "./editor/cm";
import type { Span } from "./editor/spans";
import { TitleBar } from "./components/TitleBar";
import { ActivityRail, type RailView } from "./components/ActivityRail";
import { Binder } from "./components/Binder";
import { Editor, type ViewMode } from "./components/Editor";
import type { EditorHandle } from "./components/EditorPane";
import { Assistant, type AssistantTab, type QuickAction } from "./components/Assistant";
import { InspirationPanel } from "./components/InspirationPanel";
import { SettingsDialog } from "./components/SettingsDialog";
import { AliasReviewDialog, CanonReviewDialog, StyleReviewDialog } from "./components/ReviewDialogs";
import { SpellMenu } from "./components/SpellMenu";
import { StatusBar } from "./components/StatusBar";
import { SprintDialog, StatsDialog } from "./components/StatsDialog";
import { remaining, sprintNotice } from "./data/stats";
import { Launch } from "./components/Launch";
import { QuickSwitcher } from "./components/QuickSwitcher";
import { ConfirmDialog, Menu, PromptDialog, type MenuItem } from "./components/Dialogs";
import { DetailsDialog, PartPickerDialog, TrashDialog } from "./components/StructureDialogs";
import { SnapshotsDialog } from "./components/SnapshotsDialog";
import { ExportDialog } from "./components/ExportDialog";
import { RenameDialog } from "./components/RenameDialog";
import { CollectionsManager, SceneCollectionsDialog } from "./components/CollectionDialogs";
import { memberIds } from "./data/collections";
import { AddCommentDialog, CommentPopover, CommentsPanel } from "./components/CommentComponents";
import { AttachDialog, ChatHistoryDialog } from "./components/ChatDialogs";
import type { Attachment } from "./data/chat";
import { Toasts, type Notice } from "./components/Toast";

const ZOOMS = [90, 100, 110, 125];
const NO_CURSOR: CursorInfo = { line: 1, col: 1, head: 0, from: 0, to: 0, canUndo: false, canRedo: false };

type Dialog =
  | { kind: "new-scene" }
  | { kind: "rename" }
  | { kind: "delete" }
  | { kind: "new-part" }
  | { kind: "rename-part"; id: string; title: string }
  | { kind: "delete-part"; id: string; title: string }
  | { kind: "pick-part"; sceneId: string; unplaced: boolean }
  | { kind: "move"; plan: MovePlan }
  | { kind: "trash" }
  | { kind: "details" }
  | { kind: "snapshots" }
  | { kind: "export" }
  | { kind: "stats" }
  | { kind: "sprint" }
  | { kind: "stop-sprint" }
  | { kind: "collections" }
  | { kind: "new-research" }
  | { kind: "chats" }
  | { kind: "attach"; items: AttachItem[]; maxWords: number; maxItems: number }
  | { kind: "research-url"; url: string }
  | { kind: "delete-research" }
  | { kind: "add-comment"; from: number; to: number; quote: string }
  | { kind: "scene-collections" }
  | { kind: "new-draft" }
  | { kind: "sync-commit"; info: Extract<SyncInfo, { repo: true }> }
  | { kind: "sync-push"; info: Extract<SyncInfo, { repo: true }> }
  | { kind: "sync-init" }
  | { kind: "new-note"; name: string; openAfter: boolean }
  | { kind: "generate"; mode: "draft" | "rewrite"; from: number; to: number; title: string; label: string; initial: string }
  | { kind: "aliases"; items: AliasSuggestion[] }
  | { kind: "rename-note"; name: string; aliases: string[] }
  | { kind: "canon"; items: CanonProposal[] }
  | { kind: "style"; markdown: string; replacing: boolean }
  | { kind: "settings"; info: SettingsInfo }
  | null;

const uid = () => crypto.randomUUID();
const sentence = (s: string) => s[0] + s.slice(1).toLowerCase();

const NOTE_TYPES: EntityType[] = ["character", "place", "object", "faction"];

export default function App() {
  // undefined = still loading, null = no project open (launch screen)
  const [ws, setWs] = useState<Workspace | null | undefined>(undefined);
  const [styleStatus, setStyleStatus] = useState<StyleStatus | null>(null);
  const renameMoved = useRef<Record<string, string>>({});   // rename: new note id -> old, to follow it on Undo
  const lastPing = useRef(0);   // writing stats: last typing ping (ms)
  const sprintFocusStarted = useRef(false);   // the sprint turned focus mode on, so it turns it off
  const [sprintFocus, setSprintFocus] = useState(() => {
    try { return localStorage.getItem("lw-sprint-focus") === "1"; } catch { return false; }
  });
  // The "Your style" card follows the project (refresh() runs after every save of style.md).
  useEffect(() => {
    if (!ws) return;
    let live = true;
    void api.styleStatus().then((r) => { if (live) setStyleStatus(r.ok ? r : null); });
    return () => { live = false; };
  }, [ws]);
  const [doc, setDoc] = useState<DocumentPayload | null>(null);
  const [docRev, setDocRev] = useState(0);
  const [spansVersion, setSpansVersion] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [rail, setRail] = useState<RailView>("binder");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [focus, setFocus] = useState(false);
  const [mode, setMode] = useState<ViewMode>("manuscript");
  const [zoom, setZoom] = useState(100);
  const [switcher, setSwitcher] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; items: MenuItem[] } | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [words, setWords] = useState(0);
  const [snapshotAt, setSnapshotAt] = useState<string | null>(null);
  const [sync, setSync] = useState<SyncInfo | null>(null);
  const syncTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [cursor, setCursor] = useState<CursorInfo>(NO_CURSOR);
  const [mentions, setMentions] = useState<SceneMention[]>([]);
  const [tab, setTab] = useState<AssistantTab>("assistant");
  const [inspRev, setInspRev] = useState(0);   // bumped when the Trash gives a picture back
  const [noteName, setNoteName] = useState<string | null>(null);
  const [note, setNote] = useState<EntityInfo | null>(null);
  const [noteVersion, setNoteVersion] = useState(0);
  const [missingTarget, setMissingTarget] = useState<string | null>(null);
  const [noteType, setNoteType] = useState<EntityType>("character");
  const [aiReady, setAiReady] = useState(false);
  const [aiRun, setAiRun] = useState<AiRunView | null>(null);
  const aiJobRef = useRef<AiJob<unknown> | null>(null);
  const stoppedRef = useRef(false); // the last AI job ended because the author pressed Stop
  const aiBusy = aiRun?.label ?? null;
  const [issues, setIssues] = useState<Issue[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [scope, setScope] = useState<"scene" | "project">("scene");
  const [reflow, setReflow] = useState(true);
  const [spellCount, setSpellCount] = useState<number | null>(null);
  const [spellVersion, setSpellVersion] = useState(0);
  const [spellTarget, setSpellTarget] = useState<SpellTarget | null>(null);
  const [partFocus, setPartFocus] = useState<string | null>(null);
  const [collection, setCollection] = useState<string | null>(null);
  const [researchMode, setResearchMode] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [chatList, setChatList] = useState<ChatSummary[] | null>(null);
  const chatIdRef = useRef<string | null>(null);   // the saved conversation behind the messages, if any
  const [chatId, setChatId] = useState<string | null>(null);   // (the same, for rendering)
  const setChat = (id: string | null) => { chatIdRef.current = id; setChatId(id); };
  const persistChat = useRef(false);               // set after a completed turn: the next messages change is saved
  const [comments, setComments] = useState<CommentRow[] | null>(null);
  const [commentPop, setCommentPop] = useState<{ id: string; x: number; y: number } | null>(null);
  const noticeId = useRef(0);
  const editorRef = useRef<EditorHandle>(null);
  const focusAfterOpen = useRef(false);
  const gotoRow = useRef<number | null>(null);
  const docRef = useRef<DocumentPayload | null>(null);
  useEffect(() => { docRef.current = doc; });
  // A conversation is saved (.assistant/chats/) after every answer, as the panel shows it.
  useEffect(() => {
    if (!persistChat.current) return;
    persistChat.current = false;
    const kept = messages.filter((m) => !(m.role === "assistant" && m.error));
    if (!kept.length) return;
    void api.saveChat(chatIdRef.current, kept, scope, attachments.map(({ kind, id }) => ({ kind, id })))
      .then((r) => { if (r.ok) { chatIdRef.current = r.id; setChatId(r.id); } });
  }, [messages, scope, attachments]);

  const notify = useCallback((text: string, tone: Notice["tone"] = "info", action?: Notice["action"]) => {
    const id = ++noticeId.current;
    setNotices((n) => [...n, { id, text, tone, action }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), tone === "error" || action ? 9000 : 3500);
  }, []);

  const refresh = useCallback(async () => {
    const r = await api.getWorkspace();
    if (!r.ok) { notify(r.error, "error"); return null; }
    setWs(r.workspace);
    return r.workspace;
  }, [notify]);

  /** Read-only git status. Trailing-throttled (2.5 s) so autosaves do not spawn git every time. */
  const refreshSync = useCallback((now = false) => {
    const run = () => { syncTimer.current = null; void api.syncStatus().then((r) => { if (r.ok) setSync(r.sync); }); };
    if (now) { if (syncTimer.current) clearTimeout(syncTimer.current); run(); return; }
    if (!syncTimer.current) syncTimer.current = setTimeout(run, 2500);
  }, []);

  // The autosave state machine for whichever document is open.
  const saver: SaveController = useMemo(() => new SaveController({
    save: (id, text, mtime, force) => api.saveDocument(id, text, mtime, force),
    onState: setSaveState,
    onSaved: (r) => {
      if (r.words !== undefined) setWords(r.words);
      if (r.snapshotAt !== undefined) setSnapshotAt(r.snapshotAt);
      void refresh();
      refreshSync();
      const id = saver.documentId; // the retrieved-context list follows what was just saved
      if (id?.startsWith("manuscript/")) {
        void api.sceneContext(id).then((c) => { if (c.ok && saver.documentId === id) setMentions(c.mentions); });
      }
    },
    onError: (m) => notify(`Save failed: ${m}`, "error"),
  }), [notify, refresh, refreshSync]);

  const openDoc = useCallback(async (id: string, opts: { force?: boolean; keepMode?: boolean } = {}) => {
    if (!opts.force) {
      if (saver.state === "conflict") { notify("Resolve the save conflict first (reload or keep your version).", "error"); return; }
      if (!(await saver.flush())) { notify("Could not save the current document; staying here.", "error"); return; }
    }
    const r = await api.readDocument(id);
    if (!r.ok) { notify(r.error, "error"); return; }
    saver.open(r.id, r.text, r.mtime);
    setDoc(r);
    setIssues([]);
    setMentions(r.mentions);
    setWords(r.words);
    setSnapshotAt(r.snapshotAt ?? null);
    setDocRev((n) => n + 1);
    setCursor(NO_CURSOR);
    if (!opts.keepMode) setMode("manuscript");
  }, [saver, notify]);

  const boot = useCallback(async () => {
    void api.aiStatus().then((r) => setAiReady(r.ok && r.hasKey));
    void api.getSettings().then((r) => { if (r.ok) { setZoom(r.editor.zoom); setReflow(r.editor.reflow); } });
    const w = await refresh();
    if (!w) return;
    refreshSync(true);
    setExpanded(collectExpanded(w.binder));
    saver.detach();
    setDoc(null);
    const first = w.scenes.find((s) => !s.frontMatter && !s.unplaced) ?? w.scenes[0];
    if (first) void openDoc(first.id, { force: true });
  }, [refresh, refreshSync, saver, openDoc]);

  useEffect(() => { void boot(); }, [boot]);

  // a just-created scene takes focus once its editor has mounted
  useEffect(() => {
    if (!doc) return;
    if (focusAfterOpen.current) { focusAfterOpen.current = false; editorRef.current?.focusEnd(); }
    if (gotoRow.current !== null) { editorRef.current?.gotoLine(gotoRow.current); gotoRow.current = null; }
  }, [docRev, doc]);

  // the Notes tab follows the entity note that is open in the editor...
  useEffect(() => {
    if (doc?.kind === "entity") { setNoteName(doc.title); setMissingTarget(null); }
  }, [doc]);

  // ...and loads whichever note it points at
  useEffect(() => {
    if (!noteName) { setNote(null); return; }
    let live = true;
    void api.getEntity(noteName).then((r) => { if (live && r.ok) setNote(r); });
    return () => { live = false; };
  }, [noteName, noteVersion]);

  // Global keys, and flushing saves when the window loses focus or goes away.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSwitcher((s) => !s); }
      else if (e.key === "F11") { e.preventDefault(); setFocus((f) => !f); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n" && !e.shiftKey) { e.preventDefault(); setDialog({ kind: "new-scene" }); }
    };
    const onHide = () => { void saver.flush(); };
    // a link pasted anywhere outside a text field offers to become a research note
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.closest("input, textarea, [contenteditable=true], .cm-editor"))) return;
      const text = e.clipboardData?.getData("text/plain")?.trim() ?? "";
      if (/^https?:\/\/\S+$/.test(text)) { e.preventDefault(); setDialog({ kind: "research-url", url: text }); }
    };
    // the terminal app may have edited the file while we were in the background
    const onFocus = async () => {
      const id = saver.documentId;
      if (!id) return;
      const r = await api.documentMtime(id);
      if (!r.ok || r.mtime === saver.baseMtime) return;
      if (saver.isDirty) saver.markConflict();
      else { await openDoc(id, { force: true }); notify("Reloaded: the file changed on disk."); }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("paste", onPaste);
    window.addEventListener("pagehide", onHide);
    window.addEventListener("blur", onHide);
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("paste", onPaste);
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("blur", onHide);
      window.removeEventListener("focus", onFocus);
    };
  }, [saver, openDoc, notify]);

  // -- focus sprint (the countdown is client-side; the server keeps the start/end and counts the words) --
  const sprint = ws?.status.stats?.sprint ?? null;
  const [nowMs, setNowMs] = useState(() => Date.now());
  const sprintStart = sprint ? sprint.startedAt : null;
  useEffect(() => {
    if (sprintStart === null) return;
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [sprintStart]);   // one timer per sprint
  const startSprint = async (minutes: number, focusMode: boolean) => {
    setDialog(null);
    const r = await api.sprintStart(minutes);
    if (!r.ok) return notify(r.error, "error");
    sprintFocusStarted.current = focusMode && !focus;
    try { localStorage.setItem("lw-sprint-focus", focusMode ? "1" : "0"); } catch { /* storage may be blocked */ }
    setSprintFocus(focusMode);
    if (focusMode) setFocus(true);
    setNowMs(Date.now());
    await refresh();
  };
  const endSprint = async (cancelled: boolean) => {
    await saver.flush();   // the last words count
    const r = await api.sprintEnd(cancelled);
    if (sprintFocusStarted.current) { sprintFocusStarted.current = false; setFocus(false); }
    await refresh();
    if (!r.ok) return notify(r.error, "error");
    notify(sprintNotice(r.sprint.minutes, r.sprint.words, cancelled),
      "info", { label: "Session stats", run: () => setDialog({ kind: "stats" }) });
  };
  const sprintEnded = useRef(false);
  const sprintDue = !!sprint && remaining(sprint, nowMs) <= 0;
  useEffect(() => {
    if (!sprint) { sprintEnded.current = false; return; }
    if (sprintDue && !sprintEnded.current) { sprintEnded.current = true; void endSprint(false); }
  });   // fires once per sprint, when its time is up
  if (ws === undefined) return <div className="lw-app lw-loading">Loading project…</div>;
  if (ws === null) {
    return (
      <div className="lw-app">
        <Launch onOpened={boot} />
        <Toasts notices={notices} onDismiss={(id) => setNotices((n) => n.filter((x) => x.id !== id))} />
      </div>
    );
  }

  const isScene = doc?.kind === "scene";
  const unit = ws.project.unit;
  const select = async (n: BinderNode) => {
    if (n.kind === "part") { setPartFocus(n.id); toggle(n.id); return; }
    if (n.kind === "trash" && !n.placeholder) { setDialog({ kind: "trash" }); return; }
    if (!isOpenable(n)) return;
    if (n.kind === "dictionary") { // first open creates dictionary.txt with a comment header
      const r = await api.openDictionary();
      if (!r.ok) return notify(r.error, "error");
    }
    if (n.kind === "style" && !ws.status.hasStyle) { // first open creates the stub, as the terminal app does
      const r = await api.ensureStyle();
      if (!r.ok) return notify(r.error, "error");
      await refresh();
    }
    void openDoc(n.id);
  };
  const toggle = (id: string) => setExpanded((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const onRail = (v: RailView) => {
    if (v === "assistant") { setAssistantOpen((o) => !o); return; }
    setRail(v); setFocus(false);
  };
  const docLabel = doc ? (doc.kind === "scene" ? `${sentence(doc.kicker)} · ${doc.title}` : doc.title) : "";
  // -- notes ------------------------------------------------------------------
  const showNote = (name: string) => {
    setMissingTarget(null); setNoteName(name); setTab("notes"); setAssistantOpen(true);
  };
  const showMissing = (target: string) => {
    setMissingTarget(target); setTab("notes"); setAssistantOpen(true);
  };
  const onCursor = (c: CursorInfo) => {
    setCursor(c);
    // the note panel follows the name under the cursor (and keeps the last one when you move away)
    const sp = editorRef.current?.spanAtCursor();
    if (sp?.entity) { setMissingTarget(null); setNoteName(sp.entity); }
    else if (sp?.kind === "unresolved") setMissingTarget(sp.target ?? null);
  };
  const getCard = async (span: Span): Promise<Card | null> => {
    if (span.kind === "unresolved") {
      return { title: span.target ?? "", kind: "no note", missing: true, body: "No note yet. Put the cursor on it and press Ctrl J to make one." };
    }
    const r = await api.getEntity(span.entity ?? span.target ?? "");
    if (!r.ok || !r.found) return null;
    return { title: r.name, kind: r.type, body: r.summary || "This note has no text yet." };
  };
  const openEntitySpan = (span: Span) => {
    if (span.entity) showNote(span.entity); else if (span.target) showMissing(span.target);
  };
  /** ctrl+J / the link button: open the note under the cursor, or make one for the selected name. */
  const makeNote = (fromKey = false): boolean => {
    const ed = editorRef.current;
    if (!ed || doc?.kind !== "scene") return false;
    const sel = ed.selection();
    const picked = sel.text.trim();
    if (picked && !picked.includes("\n")) {
      void api.getEntity(picked).then((r) => {
        if (r.ok && r.found) showNote(r.name);
        else setDialog({ kind: "new-note", name: picked, openAfter: false });
      });
      return true;
    }
    const sp = ed.spanAtCursor();
    if (sp?.entity) { showNote(sp.entity); return true; }
    if (sp?.target) { setDialog({ kind: "new-note", name: sp.target, openAfter: false }); return true; }
    if (!fromKey) notify("Select a name in the text (or put the cursor on a [[link]]) first.");
    return false;
  };
  const createNote = async (name: string, openAfter: boolean) => {
    setDialog(null);
    const r = await api.createEntity(name, noteType);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setSpansVersion((v) => v + 1);
    const c = doc?.kind === "scene" ? await api.sceneContext(doc.id, editorRef.current?.getText()) : null;
    if (c?.ok) setMentions(c.mentions);
    if (r.existed) notify(`“${r.name}” already has a note.`);
    if (openAfter) await openDoc(r.id); else showNote(r.name);
  };
  const addAlias = async (name: string, alias: string) => {
    const r = await api.addAlias(name, alias);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setNoteVersion((v) => v + 1);
    setSpansVersion((v) => v + 1);
    if (doc?.kind === "scene") {
      const c = await api.sceneContext(doc.id, editorRef.current?.getText());
      if (c.ok) setMentions(c.mentions);
    }
  };
  const openBacklink = async (sourceId: string, row: number) => {
    if (doc?.id === sourceId) { editorRef.current?.gotoLine(row); return; }
    gotoRow.current = row;
    await openDoc(sourceId);
  };

  // -- AI ------------------------------------------------------------------------
  // Everything the model returns is a suggestion: chat text, a review list, or a
  // pending <!--ai--> draft with Accept / Reject. Nothing edits prose on its own.
  const requireAi = () => {
    if (!aiReady) {
      notify("Add your OpenRouter API key first. AI features are off until then.", "error");
      void openSettings();
      return false;
    }
    return true;
  };
  /** One AI job at a time: start, poll, show the working state, resolve with the result (null: failed or stopped). */
  async function aiCall<X>(label: string, verb: string, kind: AiKind, args: Record<string, unknown>): Promise<(X & { ok: true }) | null> {
    if (!requireAi()) return null;
    if (aiJobRef.current) { notify("Wait for the current AI request to finish."); return null; }
    const mode = kind === "generate" ? "draft" : STREAMING_KINDS.includes(kind) ? "chat" : "strip";
    stoppedRef.current = false;
    const job = runAiJob<X & { ok: true }>(kind, args, { label, onText: (_d, total) => setAiRun((r) => (r ? { ...r, text: total } : r)),
      onElapsed: (elapsed) => setAiRun((r) => (r ? { ...r, elapsed } : r)) });
    aiJobRef.current = job as AiJob<unknown>;
    setAiRun({ label, verb, mode, text: "", startedAt: Date.now(), anchor: mode === "draft" ? editorRef.current?.cursorPoint() ?? null : null });
    try {
      return await job.promise;
    } catch (e) {
      if (e instanceof AiCancelled) { stoppedRef.current = true; notify("Stopped. Nothing was changed."); }
      else notify(e instanceof Error ? e.message : String(e), "error");
      return null;
    } finally { aiJobRef.current = null; setAiRun(null); void refresh(); } // refresh: the status bar's AI spend
  }
  const stopAi = () => { void aiJobRef.current?.cancel(); };
  const failedReply = (): ChatMessage => stoppedRef.current
    ? { id: uid(), role: "assistant", text: "(stopped)", error: true, stopped: true }
    : { id: uid(), role: "assistant", text: "That request failed. Nothing was changed.", error: true };
  const cost = (c: number | null | undefined) => (c != null ? ` (AI $${c.toFixed(4)})` : "");
  const liveText = () => editorRef.current?.getText() ?? "";

  const quickContinuity = async () => {
    const d = docRef.current;
    if (!d || d.kind !== "scene") return notify("Open a scene first.");
    const r = await aiCall<{ issues: Issue[]; waived: number; cost: number | null }>("Checking continuity…", "checking continuity", "continuity", { doc_id: d.id, text: liveText() });
    if (!r || docRef.current?.id !== d.id) return;
    setIssues(r.issues); setTab("assistant"); setAssistantOpen(true);
    const waived = r.waived ? ` (${r.waived} waived)` : "";
    notify((r.issues.length ? `${r.issues.length} possible conflict${r.issues.length === 1 ? "" : "s"}` : "No continuity issues found") + waived + cost(r.cost));
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
    const r = await aiCall<{ suggestions: AliasSuggestion[]; cost: number | null }>("Looking for aliases…", "looking for aliases", "aliases", { doc_id: d.id, text: liveText() });
    if (!r) return;
    if (!r.suggestions.length) return notify("No new aliases found" + cost(r.cost));
    setDialog({ kind: "aliases", items: r.suggestions });
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
    const r = await aiCall<{ updates: CanonProposal[]; cost: number | null }>("Reading the scene for new canon…", "reading for canon", "canon", { doc_id: d.id, text: liveText() });
    if (!r) return;
    if (!r.updates.length) return notify("No new canon found in this scene" + cost(r.cost));
    setDialog({ kind: "canon", items: r.updates });
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
    notify(`AI draft ready: F7 accept, F8 reject${cost(r.cost)}`);
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

  /** Say so when an attachment was trimmed to fit or could not be sent: nothing is dropped silently. */
  const reportAttached = (report: AttachReport[]) => {
    const trimmed = report.filter((a) => a.truncated && !a.skipped).map((a) => a.title);
    const skipped = report.filter((a) => a.skipped);
    if (trimmed.length) notify(`Shortened to fit: ${trimmed.join(", ")}.`);
    if (skipped.length) notify(`Not attached: ${skipped.map((a) => `${a.title} (${a.reason})`).join("; ")}.`, "error");
  };
  const sendChat = async (text: string, replaceId?: string) => {
    const ed = editorRef.current, d = docRef.current;
    let base = messages.filter((m) => !(m.role === "assistant" && m.error));
    if (replaceId) base = base.slice(0, Math.max(0, base.findIndex((m) => m.id === replaceId)) - 1); // up to, not including, the prompt being retried
    const history = base.map((m) => ({ role: m.role, text: m.text }));
    if (!requireAi()) return;
    if (!replaceId) setMessages((m) => [...m, { id: uid(), role: "user", text }]);
    else setMessages((m) => m.filter((x) => x.id !== replaceId));
    const attached = attachments.map(({ kind, id }) => ({ kind, id }));
    if (researchMode) {
      const r = await aiCall<{ reply: string; sources: { id: string; title: string; score: number }[]; attached: AttachReport[]; cost: number | null }>("Searching your notes…", "searching notes", "research", { prompt: text, history, attachments: attached });
      if (r) reportAttached(r.attached);
      persistChat.current = !!r;
      setMessages((m) => [...m, r
        ? { id: uid(), role: "assistant", text: r.reply, sources: r.sources.map((s) => ({ id: s.id, title: s.title })) }
        : failedReply()]);
      return;
    }
    const r = await aiCall<{ reply: string; attached: AttachReport[]; cost: number | null }>("Thinking…", "thinking", "ask", { prompt: text, scope, doc_id: d?.kind === "scene" ? d.id : null, text: ed ? ed.getText() : null, cursor: ed?.head() ?? 0, history, attachments: attached });
    if (r) reportAttached(r.attached);
    persistChat.current = !!r;
    setMessages((m) => [...m, r ? { id: uid(), role: "assistant", text: r.reply } : failedReply()]);
  };
  /** Brainstorm quick action: ideas to get unstuck, from the scene around the cursor + canon + style. */
  const runBrainstorm = async (replaceId?: string) => {
    const ed = editorRef.current, d = docRef.current;
    if (!requireAi()) return;
    const attached = attachments.map(({ kind, id }) => ({ kind, id }));
    if (replaceId) setMessages((m) => m.filter((x) => x.id !== replaceId));
    else setMessages((m) => [...m, { id: uid(), role: "user", text: "Brainstorm: ideas to get unstuck." }]);
    const r = await aiCall<{ reply: string; ideas: string[]; attached: AttachReport[]; cost: number | null }>("Brainstorming…", "brainstorming", "brainstorm", { doc_id: d?.kind === "scene" ? d.id : null, text: ed ? ed.getText() : null, cursor: ed?.head() ?? 0, attachments: attached });
    if (r) reportAttached(r.attached);
    persistChat.current = !!r;
    setMessages((m) => [...m, r ? { id: uid(), role: "assistant", text: r.reply, ideas: r.ideas }
      : failedReply()]);
  };
  /** "Draft from this": the ctrl+g prompt, prefilled with the idea, at the cursor. */
  const draftFromIdea = (idea: string) => {
    const ed = editorRef.current;
    if (!ed || docRef.current?.kind !== "scene") return notify("Open a scene to draft into.");
    if (!requireAi()) return;
    const head = ed.head();
    setDialog({ kind: "generate", mode: "draft", from: head, to: head, title: "Draft from this idea",
      label: "What should the AI write? (edit the idea if you like)", initial: idea });
  };
  const saveIdeaToNotes = async (idea: string) => {
    const scene = docRef.current?.kind === "scene" ? docRef.current.title : "";
    const r = await api.saveReplyToNotes(scene ? `Brainstorm idea - ${scene}` : "Brainstorm idea", idea);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    notify("Idea saved to research/assistant-notes.md", "info", { label: "Open", run: () => { void openDoc(r.id); } });
  };
  const regenerate = (id: string) => {
    const i = messages.findIndex((m) => m.id === id);
    if (messages[i]?.role === "assistant" && (messages[i] as { ideas?: string[] }).ideas) { void runBrainstorm(id); return; }
    const prompt = messages.slice(0, i).reverse().find((m) => m.role === "user");
    if (prompt) void sendChat(prompt.text, id);
  };
  const insertReplyAsDraft = async (id: string) => {
    const d = docRef.current, ed = editorRef.current, msg = messages.find((m) => m.id === id);
    if (!d || d.kind !== "scene" || !ed || !msg) return notify("Open a scene to insert into.");
    const r = await api.draftFromReply(d.id, ed.getText(), msg.text, ed.head());
    if (!r.ok) return notify(r.error, "error");
    ed.insertDraft(r.from, r.to, r.insert);
    notify("Inserted as an AI draft: F7 accept, F8 reject.");
  };
  const onQuick = (a: QuickAction) => {
    if (a === "brainstorm") void runBrainstorm();
    else if (a === "rewrite") rewriteSelection();
    else if (a === "research") {
      setResearchMode((on) => !on);
      if (!researchMode && !ws?.research.length) notify("Research answers come from your research notes. Add some under Research in the binder first (a new note, or paste a link).");
    } else void quickContinuity();
  };
  const openAiMenu = (anchor: HTMLElement) => setMenu({ anchor, items: [
    { label: "New chat", onSelect: newChat },
    { label: "Conversation history…", onSelect: () => void openChatHistory() },
    { label: "Draft at the cursor…", disabled: doc?.kind !== "scene", onSelect: () => { const ed = editorRef.current; const h = ed?.head() ?? 0; if (requireAi()) setDialog({ kind: "generate", mode: "draft", from: h, to: h, title: "Draft new prose here", label: "What should the AI write?", initial: "" }); } },
    { label: "Find aliases", disabled: doc?.kind !== "scene", onSelect: () => void findAliases() },
    { label: "Update story bible", disabled: doc?.kind !== "scene", onSelect: () => void updateBible() },
    { label: "Learn style guide", onSelect: () => void learnStyle() },
    { label: "Accept all drafts", disabled: doc?.kind !== "scene", onSelect: () => void resolveDraft(null, true) },
    { label: "Reject all drafts", disabled: doc?.kind !== "scene", onSelect: () => void resolveDraft(null, false) },
    { label: "Restore waived issues", disabled: doc?.kind !== "scene", onSelect: () => void restoreWaived() },
  ] });

  // -- settings / project ------------------------------------------------------
  const openSettings = async () => {
    const r = await api.getSettings();
    if (!r.ok) return notify(r.error, "error");
    setDialog({ kind: "settings", info: r });
  };
  const settingsSaved = (editor: { zoom: number; reflow: boolean }, _spellcheck: boolean) => {
    setZoom(editor.zoom); setReflow(editor.reflow);
    setSpellVersion((v) => v + 1);
    void api.aiStatus().then((r) => setAiReady(r.ok && r.hasKey));
    notify("Settings saved.");
  };
  // -- spelling ------------------------------------------------------------------
  const spellReplace = (t: SpellTarget, text: string) => editorRef.current?.replace(t.from, t.to, text);
  const spellAdd = async (t: SpellTarget, scope: "project" | "personal") => {
    const term = t.kind === "word" ? t.word : t.text.trim().replace(/\s+/g, " ");
    const r = await api.addToDictionary(term, scope);
    if (!r.ok) return notify(r.error, "error");
    notify(r.added ? `Added “${term}” to ${scope === "project" ? "the project" : "your"} dictionary.` : `“${term}” is already in the dictionary.`);
    setSpellVersion((v) => v + 1);
  };
  const spellIgnore = async (t: SpellTarget) => {
    if (t.kind !== "word") return;
    const r = await api.ignoreWord(t.word);
    if (!r.ok) return notify(r.error, "error");
    setSpellVersion((v) => v + 1);
  };
  /** Toolbar: the selected word or phrase goes to the project dictionary. */
  const addSelectionToDictionary = () => {
    const sel = editorRef.current?.selection();
    if (!sel || !sel.text.trim()) return;
    const from = sel.from, to = sel.to;
    void spellAdd({ kind: "phrase", from, to, text: sel.text, x: 0, y: 0 }, "project");
  };
  const jumpToMisspelling = () => { if (!editorRef.current?.gotoNextMisspelling()) notify("No misspelled words."); };
  const cycleZoom = () => {
    const next = ZOOMS[(ZOOMS.indexOf(zoom) + 1) % ZOOMS.length];
    setZoom(next);
    void api.setSettings(undefined, { zoom: next });
  };
  const openExport = async () => {
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    setDialog({ kind: "export" });
  };
  const switchProject = async () => {
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    saver.detach(); setDoc(null); setWs(null);
  };
  const openProjectMenu = (anchor: HTMLElement) => setMenu({ anchor, items: [
    { label: "Switch project…", onSelect: () => void switchProject() },
    { label: "Export…", onSelect: () => void openExport() },
    { label: "Rebuild the link index", onSelect: async () => {
      const r = await api.rebuildIndex();
      if (!r.ok) return notify(r.error, "error");
      await refresh(); setSpansVersion((v) => v + 1); setNoteVersion((v) => v + 1);
      notify("Index rebuilt from the files.");
    } },
    { label: unit === "scene" ? "Call scenes “chapters”" : "Call chapters “scenes”", onSelect: async () => {
      const next = unit === "scene" ? "chapter" : "scene";
      const r = await api.setUnit(next);
      if (!r.ok) return notify(r.error, "error");
      await refresh();
      if (docRef.current) await openDoc(docRef.current.id, { force: true });  // the kicker follows
      notify(`Labels now say “${next}”. Only the wording changes.`);
    } },
    { label: "Settings…", onSelect: () => void openSettings() },
  ] });

  const saveNow = async () => { const ok = await saver.flush(); if (ok) notify("Saved"); };
  const closeWindow = async () => { await saver.flush(); await api.close(); };

  const reloadFromDisk = async () => { if (doc) await openDoc(doc.id, { force: true }); };
  const keepMine = async () => {
    const ok = await saver.keepMine();
    notify(ok ? "Kept your version." : "Could not save your version.", ok ? "info" : "error");
  };

  // -- scene, part and trash management -------------------------------------------
  /** Open the document the user was in, at its (possibly renamed) id. */
  const reopen = async (id: string, remap?: Remap) => { await openDoc(follow(id, remap), { force: true, keepMode: true }); };
  const createScene = async (title: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newScene(title, null, doc && doc.kind === "scene" ? doc.id : null);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    focusAfterOpen.current = true;
    await openDoc(r.id, { force: true });
  };
  const renameScene = async (title: string) => {
    setDialog(null);
    if (!doc || !(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.renameScene(doc.id, title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    await openDoc(doc.id, { force: true });
  };
  const moveScene = async (delta: number) => {
    if (!doc || !(await saver.flush())) return;
    const r = await api.moveScene(doc.id, delta);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    await openDoc(r.id, { force: true });
  };
  /** Move a scene to a part / the top level / Unplaced; keeps the open document open. */
  const placeScene = async (id: string, partId: string | null, index: number | null, unplaced: boolean) => {
    if (!(await saver.flush())) { notify("Could not save the current document first.", "error"); return null; }
    const r = await api.placeScene(id, partId, index, unplaced);
    if (!r.ok) { notify(r.error, "error"); return null; }
    await refresh();
    setExpanded((s) => (partId ? new Set(s).add(partId) : s));
    if (docRef.current) await reopen(docRef.current.id, r.remap);
    return r;
  };
  /** The confirmed drag-and-drop: move, then offer to move it back. */
  const performMove = async (plan: MovePlan) => {
    setDialog(null);
    const title = ws.scenes.find((s) => s.id === plan.sceneId)?.title ?? "scene";
    const r = await placeScene(plan.sceneId, plan.partId, plan.index, plan.unplaced);
    if (!r) return;
    notify(`Moved “${title}”.`, "info", {
      label: "Undo",
      run: () => { void placeScene(r.id, plan.from.partId, plan.from.index, plan.from.unplaced).then((u) => u && notify("Moved back.")); },
    });
  };
  const deleteScene = async () => {
    setDialog(null);
    if (!doc) return;
    const id = doc.id, title = doc.title;
    saver.detach(); // before anything else: a pending autosave must not resurrect the file
    setDoc(null);
    const r = await api.deleteScene(id);
    if (!r.ok) { notify(r.error, "error"); await openDoc(id, { force: true }); return; }
    const w = await refresh();
    const next = w?.scenes.find((s) => !s.frontMatter && !s.unplaced) ?? w?.scenes[0];
    if (next) await openDoc(next.id, { force: true });
    notify(`Moved “${title}” to the Trash.`);
  };
  const createPart = async (title: string) => {
    setDialog(null);
    const r = await api.newPart(title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add(r.id));
    setPartFocus(r.id);
  };
  const renamePart = async (id: string, title: string) => {
    setDialog(null);
    const r = await api.renamePart(id, title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
  };
  const movePart = async (id: string, delta: number) => {
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.movePart(id, delta);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setPartFocus(r.id);
    setExpanded((s) => new Set(s).add(r.id));
    if (docRef.current) await reopen(docRef.current.id, r.remap);
  };
  const deletePart = async (id: string) => {
    setDialog(null);
    const r = await api.deletePart(id);
    if (!r.ok) return notify(r.error, "error");
    setPartFocus(null);
    await refresh();
  };
  const saveDetails = async (patch: DetailsPatch) => {
    setDialog(null);
    const d = docRef.current, ed = editorRef.current;
    if (!d || d.kind !== "scene" || !ed) return;
    const text = ed.getText();
    const r = await api.setSceneDetails(d.id, text, patch);
    if (!r.ok) return notify(r.error, "error");
    if (ed.getText() !== text) return notify("The text changed while saving the details; try again.", "error");
    ed.applyEdits([r.edit]);  // an ordinary edit: undoable, and autosave writes it
    setDoc((cur) => (cur && cur.id === d.id
      ? { ...cur, details: r.details, bodyStart: r.bodyStart, text: r.edit.insert + text.slice(r.edit.to) } : cur));
    void refresh();
    const c = await api.sceneContext(d.id, ed.getText());
    if (c.ok && docRef.current?.id === d.id) setMentions(c.mentions);
  };
  // -- chat history, attachments, save to notes ------------------------------------------------
  const newChat = () => {
    setChat(null); persistChat.current = false;
    setMessages([]); setAttachments([]); setDialog(null);
  };
  const openChatHistory = async () => {
    setChatList(null);
    setDialog({ kind: "chats" });
    const r = await api.listChats();
    if (r.ok) setChatList(r.chats); else notify(r.error, "error");
  };
  const loadChat = async (id: string) => {
    const r = await api.openChat(id);
    if (!r.ok) return notify(r.error, "error");
    const c = r.chat;
    const items = await api.listAttachable();
    const known = new Map((items.ok ? items.items : []).map((i) => [`${i.kind}:${i.id}`, i]));
    setChat(c.id); persistChat.current = false;
    setMessages(c.messages.map((m) => (m.role === "user" ? { id: m.id, role: "user" as const, text: m.text }
      : { id: m.id, role: "assistant" as const, text: m.text, ...(m.sources ? { sources: m.sources } : {}), ...(m.ideas ? { ideas: m.ideas } : {}) })));
    setScope(c.scope);
    setAttachments(c.attachments.flatMap((a) => {
      const hit = known.get(`${a.kind}:${a.id}`);
      return hit ? [{ kind: a.kind, id: a.id, title: hit.title, words: hit.words }] : [];
    }));
    if (c.attachments.length && !c.attachments.every((a) => known.has(`${a.kind}:${a.id}`))) notify("Some attachments of this chat no longer exist and were left off.");
    setDialog(null); setTab("assistant"); setAssistantOpen(true);
  };
  const renameChat = async (id: string, title: string) => {
    const r = await api.renameChat(id, title);
    if (!r.ok) { notify(r.error, "error"); return false; }
    setChatList(r.chats);
    return true;
  };
  const deleteChat = async (id: string) => {
    const r = await api.deleteChat(id);
    if (!r.ok) { notify(r.error, "error"); return false; }
    setChatList(r.chats);
    if (chatIdRef.current === id) setChat(null);   // the next answer starts a new saved chat
    return true;
  };
  const openAttach = async () => {
    const r = await api.listAttachable();
    if (!r.ok) return notify(r.error, "error");
    setDialog({ kind: "attach", items: r.items, maxWords: r.maxWords, maxItems: r.maxItems });
  };
  const saveReplyToNotes = async (id: string) => {
    const i = messages.findIndex((m) => m.id === id);
    const reply = messages[i];
    if (!reply || reply.role !== "assistant") return;
    const prompt = messages.slice(0, i).reverse().find((m) => m.role === "user")?.text ?? "";
    const r = await api.saveReplyToNotes(prompt, reply.text);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    notify("Saved to research/assistant-notes.md", "info", { label: "Open", run: () => { void openDoc(r.id); } });
  };

  // -- research notes ----------------------------------------------------------------------
  const createResearch = async (title: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newResearchNote(title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    focusAfterOpen.current = true;
    await openDoc(r.id, { force: true });
  };
  /** A pasted or dropped link becomes a note holding the link and a title; the page is never fetched. */
  const researchFromUrl = async (url: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newResearchFromUrl(url);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    await openDoc(r.id, { force: true });
    notify(`Saved the link as a research note: ${r.title}`);
  };
  const deleteResearch = async () => {
    setDialog(null);
    const d = docRef.current;
    if (!d || d.kind !== "research") return;
    saver.detach(); // a pending autosave must not bring the file back
    setDoc(null);
    const r = await api.deleteResearchNote(d.id);
    if (!r.ok) { notify(r.error, "error"); await openDoc(d.id, { force: true }); return; }
    const w = await refresh();
    const next = w?.scenes.find((s) => !s.frontMatter && !s.unplaced) ?? w?.scenes[0];
    if (next) await openDoc(next.id, { force: true });
    notify(`Moved the research note “${d.title}” to the Trash.`, "info", { label: "Open Trash", run: () => setDialog({ kind: "trash" }) });
  };

  // -- comments --------------------------------------------------------------------------
  /** Notes beside the scene (.comments/): the prose is never touched. */
  const startAddComment = () => {
    const ed = editorRef.current;
    if (!ed || docRef.current?.kind !== "scene") return notify("Open a scene first.");
    const sel = ed.selection();
    if (!sel.text.trim()) return notify("Select the passage to comment on first.");
    setDialog({ kind: "add-comment", from: sel.from, to: sel.to, quote: sel.text });
  };
  const addComment = async (body: string) => {
    const d = docRef.current, ed = editorRef.current, dlg = dialog;
    setDialog(null);
    if (!d || !ed || dlg?.kind !== "add-comment") return;
    const r = await api.addComment(d.id, ed.getText(), dlg.from, dlg.to, body);
    if (!r.ok) return notify(r.error, "error");
    setComments(r.comments);
    ed.reloadComments();
    setTab("notes"); setAssistantOpen(true);
    notify("Comment added. It is kept beside the scene, not in the text.");
  };
  const commentCall = async (run: (id: string, text: string) => Promise<BridgeResult<{ comments: CommentRow[] }>>) => {
    const d = docRef.current, ed = editorRef.current;
    if (!d || !ed) return;
    const r = await run(d.id, ed.getText());
    if (!r.ok) return notify(r.error, "error");
    setComments(r.comments);
    ed.reloadComments();
  };
  const openComment = (c: CommentRow) => {
    if (c.start === null || c.end === null) { setCommentPop({ id: c.id, x: Math.max(40, window.innerWidth - 700), y: 140 }); return; }
    const at = editorRef.current?.selectRange(c.start, c.end);
    setCommentPop({ id: c.id, x: at?.x ?? 400, y: at?.y ?? 200 });
  };
  const popComment = comments?.find((c) => c.id === commentPop?.id) ?? null;

  // -- rename a note everywhere ---------------------------------------------------------
  /** Scenes and notes are rewritten on disk: flush the open document first, reopen it (or follow the note's new file name) after. */
  const renameFlush = async (): Promise<boolean> => {
    if (await saver.flush()) return true;
    notify("Could not save the current document first.", "error");
    return false;
  };
  const renamePreview = async (to: string, keepOld: boolean, aliases: Record<string, string>, scope: RenameScope[]): Promise<RenamePreview | null> => {
    if (dialog?.kind !== "rename-note" || !(await renameFlush())) return null;
    const r = await api.renamePreview(dialog.name, to, keepOld, aliases, scope);
    if (!r.ok) { notify(r.error, "error"); return null; }
    return r;
  };
  const afterRename = async (changed: string[], remap: Record<string, string>, name: string | null) => {
    await refresh();
    setSpansVersion((v) => v + 1);
    setNoteName(name); setNoteVersion((v) => v + 1);
    const d = docRef.current;
    if (d && (remap[d.id] || changed.includes(d.id))) {
      saver.detach(); // the file was rewritten: a stale buffer must not be saved over it
      await openDoc(remap[d.id] ?? d.id, { force: true, keepMode: true });
    }
  };
  const renameApply = async (plan: string, accepted: string[]): Promise<RenameDone | null> => {
    if (!(await renameFlush())) return null;
    const r = await api.renameApply(plan, accepted);
    if (!r.ok) { notify(r.error, "error"); return null; }
    renameMoved.current = Object.fromEntries(Object.entries(r.remap).map(([from, to]) => [to, from]));
    await afterRename(r.changed, r.remap, r.name);
    return r;
  };
  const renameUndo = async (undoId: string): Promise<RenameUndone | null> => {
    const r = await api.renameUndo(undoId);
    if (!r.ok) { notify(r.error, "error"); return null; }
    const entity = await api.listEntities();
    const restored = entity.ok ? entity.entities.find((e) => e.id === r.id) : undefined;
    await afterRename(r.restored, renameMoved.current, restored?.name ?? null);
    return r;
  };

  // -- collections ---------------------------------------------------------------------
  /** Rename and delete rewrite the member scenes on disk: flush the open one first, reopen it after. */
  const collectionsCall = async (run: () => Promise<{ ok: true; changed?: string[] } | { ok: false; error: string }>): Promise<boolean> => {
    if (!(await saver.flush())) { notify("Could not save the current document first.", "error"); return false; }
    const r = await run();
    if (!r.ok) { notify(r.error, "error"); return false; }
    await refresh();
    const d = docRef.current;
    if (d && r.changed?.includes(d.id)) await openDoc(d.id, { force: true, keepMode: true });
    return true;
  };
  const createCollection = (name: string, color: CollectionColor) => collectionsCall(() => api.createCollection(name, color));
  const recolorCollection = (name: string, color: CollectionColor) => collectionsCall(() => api.recolorCollection(name, color));
  const renameCollection = async (name: string, to: string) => {
    const ok = await collectionsCall(() => api.renameCollection(name, to));
    if (ok && collection === name) setCollection(to);
    return ok;
  };
  const deleteCollection = async (name: string) => {
    const ok = await collectionsCall(() => api.deleteCollection(name));
    if (ok && collection === name) setCollection(null);
    return ok;
  };
  const openHistory = () => {
    if (docRef.current?.kind !== "scene") return notify(`Open a ${unit} to see its history.`);
    setDialog({ kind: "snapshots" });
  };
  /** Restore a snapshot: the buffer is flushed first, then the file is rewritten and reopened. */
  const restoreSnapshot = async (snapshotId: string): Promise<boolean> => {
    const d = docRef.current, ed = editorRef.current;
    if (!d || d.kind !== "scene" || !ed) return false;
    if (!(await saver.flush())) { notify("Could not save the current text first; nothing was restored.", "error"); return false; }
    const r = await api.restoreSnapshot(d.id, snapshotId, ed.getText());
    if (!r.ok) { notify(r.error, "error"); return false; }
    saver.detach(); // the file was rewritten: a stale buffer must not be saved over it
    await openDoc(d.id, { force: true, keepMode: true });
    await refresh();
    notify("Snapshot restored. The text from before is kept as “Before a restore”.");
    return true;
  };
  // Active-time ping for the writing stats: at most one every 15 s while typing.
  const pingTyping = () => {
    const now = Date.now();
    if (now - lastPing.current < 15_000) return;
    lastPing.current = now;
    void api.statsTouch();
  };
  const openDraftMenu = (anchor: HTMLElement) => setMenu({ anchor, items: [
    { label: `Draft ${ws.project.draft}`, separator: true, onSelect: () => {} },
    { label: `Start draft ${ws.project.draft + 1}…`, onSelect: () => setDialog({ kind: "new-draft" }) },
  ] });
  const startNewDraft = async () => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.startNewDraft();
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    const d = docRef.current;
    if (d?.kind === "scene") { const s = await api.listSnapshots(d.id); if (s.ok) setSnapshotAt(s.snapshotAt); }
    notify(`Draft ${r.previous} is saved as snapshots (“End of draft ${r.previous}”). You are now on draft ${r.draft}.`);
  };
  // -- git sync: every action below runs only because the author clicked it ----------
  const openSyncMenu = (anchor: HTMLElement) => {
    if (!sync) return;
    if (!sync.repo) {
      return setMenu({ anchor, items: [
        { label: "Initialize git for this project…", disabled: !sync.canInit, onSelect: () => setDialog({ kind: "sync-init" }) },
      ] });
    }
    const info = sync;
    setMenu({ anchor, items: [
      { label: `Commit ${info.changes} change${info.changes === 1 ? "" : "s"}…`, disabled: info.changes === 0, onSelect: () => setDialog({ kind: "sync-commit", info }) },
      ...(info.canPush ? [{ label: info.ahead ? `Push ${info.ahead} commit${info.ahead === 1 ? "" : "s"} to ${info.remote}…` : `Push to ${info.remote} (nothing to push)`,
        disabled: info.ahead === 0, onSelect: () => setDialog({ kind: "sync-push", info }) }] : []),
      { label: "Refresh", onSelect: () => refreshSync(true) },
    ] });
  };
  const syncDone = (r: { sync: SyncInfo | null }, text: string) => { setSync(r.sync); notify(text); };
  const syncCommit = async (message: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first; nothing was committed.", "error");
    const r = await api.syncCommit(message);
    if (!r.ok) { notify(r.error, "error"); return refreshSync(true); }
    syncDone(r, `Committed: ${r.summary}`);
  };
  const syncPush = async () => {
    setDialog(null);
    notify("Pushing…");
    const r = await api.syncPush();
    if (!r.ok) { notify(r.error, "error"); return refreshSync(true); }
    syncDone(r, r.summary);
  };
  const syncInit = async () => {
    setDialog(null);
    const r = await api.syncInit();
    if (!r.ok) { notify(r.error, "error"); return refreshSync(true); }
    syncDone(r, "This folder is now a git repository. Nothing is committed yet.");
  };
  const activeCollection = ws.collections.some((c) => c.name === collection) ? collection : null;
  const boardFilter = activeCollection ? { name: activeCollection, ids: memberIds(ws.collections, activeCollection)!, onClear: () => setCollection(null) } : null;
  const part = ws.parts.find((p) => p.id === (partFocus ?? doc?.partId)) ?? null;
  const openSceneMenu = (anchor: HTMLElement) => setMenu({
    anchor, items: [
      { label: `New ${unit}`, onSelect: () => setDialog({ kind: "new-scene" }) },
      { label: "New part…", onSelect: () => setDialog({ kind: "new-part" }) },
      { label: `Rename ${unit}…`, disabled: !isScene, onSelect: () => setDialog({ kind: "rename" }) },
      { label: "Move up", disabled: !isScene, onSelect: () => void moveScene(-1) },
      { label: "Move down", disabled: !isScene, onSelect: () => void moveScene(1) },
      { label: `Move ${unit} to part…`, disabled: !isScene, onSelect: () => doc && setDialog({ kind: "pick-part", sceneId: doc.id, unplaced: !!doc.unplaced }) },
      doc?.unplaced
        ? { label: "Place in the book…", onSelect: () => doc && setDialog({ kind: "pick-part", sceneId: doc.id, unplaced: true }) }
        : { label: "Move to Unplaced Scenes", disabled: !isScene, onSelect: () => doc && void placeScene(doc.id, null, null, true).then((r) => r && notify("Moved to Unplaced Scenes. It no longer counts in the book.")) },
      { label: "Collections…", disabled: !isScene, onSelect: () => setDialog({ kind: "scene-collections" }) },
      { label: "History (snapshots)…", disabled: !isScene, onSelect: openHistory },
      { label: `Delete ${unit}…`, disabled: !isScene, danger: true, onSelect: () => setDialog({ kind: "delete" }) },
      { label: "parts", separator: true, onSelect: () => {} },
      { label: part ? `Rename part “${part.title}”…` : "Rename part…", disabled: !part, onSelect: () => part && setDialog({ kind: "rename-part", id: part.id, title: part.title }) },
      { label: "Move part up", disabled: !part, onSelect: () => part && void movePart(part.id, -1) },
      { label: "Move part down", disabled: !part, onSelect: () => part && void movePart(part.id, 1) },
      { label: "Delete empty part…", disabled: !part || part.sceneIds.length > 0, danger: true, onSelect: () => part && setDialog({ kind: "delete-part", id: part.id, title: part.title }) },
      { label: "research", separator: true, onSelect: () => {} },
      { label: "New research note…", onSelect: () => setDialog({ kind: "new-research" }) },
      { label: "New research note from a link…", onSelect: () => setDialog({ kind: "research-url", url: "" }) },
      { label: "Move this research note to the Trash…", disabled: doc?.kind !== "research", onSelect: () => setDialog({ kind: "delete-research" }) },
      { label: "trash", separator: true, onSelect: () => {} },
      { label: "Open Trash…", onSelect: () => setDialog({ kind: "trash" }) },
      { label: "export", separator: true, onSelect: () => {} },
      { label: "Export…", onSelect: () => void openExport() },
    ],
  });

  const showBinder = !focus;
  const showAssistant = assistantOpen && !focus;

  return (
    <div className="lw-app" style={{ ["--lw-zoom" as string]: zoom / 100 }}>
      <TitleBar projectTitle={ws.project.title} documentLabel={docLabel} saveState={saveState}
        assistantOpen={showAssistant} onToggleAssistant={() => setAssistantOpen((o) => !o)}
        onSearch={() => setSwitcher(true)} onClose={() => void closeWindow()} onMore={openProjectMenu}
        draft={ws.project.draft} onDraft={openDraftMenu} />
      <div className="lw-workspace">
        <ActivityRail view={rail} assistantOpen={showAssistant} onView={onRail} onSettings={() => void openSettings()} onHistory={openHistory} badge={0}
          initials={ws.project.initials} author={ws.project.author} />
        {showBinder && (
          <Binder nodes={ws.binder} count={ws.project.documentCount} activeId={doc?.id ?? null} focusId={part?.id ?? null} unit={unit}
            expanded={expanded} onToggle={toggle} onSelect={(n) => void select(n)} searching={rail === "search"}
            library={rail === "library"} canNew canMenu={rail !== "library"}
            collections={ws.collections} activeCollection={activeCollection} onCollection={setCollection} onEditCollections={() => setDialog({ kind: "collections" })}
            onDropUrl={(url) => setDialog({ kind: "research-url", url })}
            onNew={() => setDialog(rail === "library" ? { kind: "new-note", name: "", openAfter: true } : { kind: "new-scene" })} onMenu={openSceneMenu} />
        )}
        <Editor doc={doc} scenes={ws.scenes} filter={boardFilter}
          onEditCollections={() => setDialog({ kind: "scene-collections" })} parts={ws.parts} unit={unit} words={words} mentions={mentions} reflow={reflow}
          sessionWords={ws.status.sessionWords} sessionMinutes={ws.status.sessionMinutes}
          onEditDetails={() => setDialog({ kind: "details" })} onMoveRequest={(plan) => setDialog({ kind: "move", plan })}
          mode={mode} onMode={setMode} focus={focus} onFocus={() => setFocus((f) => !f)} onOpen={(id) => void openDoc(id)}
          editorRef={editorRef} docRev={docRev} spansVersion={spansVersion} cursor={cursor} saveState={saveState}
          onChange={(t) => { saver.edit(t); pingTyping(); }} onCursor={onCursor} onBlur={() => void saver.flush()}
          onSaveNow={() => void saveNow()} onReload={() => void reloadFromDisk()} onKeepMine={() => void keepMine()}
          onMakeNote={() => makeNote(false)} getCard={getCard} onOpenEntity={openEntitySpan}
          onResolveDraft={(i, a) => void resolveDraft(i, a)}
          spellVersion={spellVersion} onSpellCount={setSpellCount} onSpell={setSpellTarget} onAddPhrase={addSelectionToDictionary}
          onAddComment={startAddComment} onComments={setComments}
          onComment={(id, x, y) => setCommentPop({ id, x, y })}
          extraKeys={[
            { key: "Mod-j", run: () => makeNote(true) },
            { key: "F7", run: () => resolveAtCursor(true) },
            { key: "F8", run: () => resolveAtCursor(false) },
            { key: "Mod-g", run: startGenerate },
          ]} />
        {showAssistant && (
          <Assistant tab={tab} onTab={setTab} mentions={mentions} onPickEntity={showNote}
            note={note} missingTarget={missingTarget} onOpenNote={(id) => void openDoc(id)} onAddAlias={(n, a) => void addAlias(n, a)} onRename={(n, al) => setDialog({ kind: "rename-note", name: n, aliases: al })}
            onCreateNote={(t) => setDialog({ kind: "new-note", name: t, openAfter: false })} onOpenBacklink={(id, row) => void openBacklink(id, row)}
            issues={issues} onReviewIssue={reviewIssue} onDismissIssue={(i) => void dismissIssue(i)}
            messages={messages} busy={aiBusy} run={aiRun} onStop={stopAi} aiReady={aiReady} scope={scope} onScope={() => setScope((c) => (c === "scene" ? "project" : "scene"))}
            onSend={(t) => void sendChat(t)} onRegenerate={regenerate} onInsertDraft={(id) => void insertReplyAsDraft(id)}
            researchMode={researchMode} onOpenSource={(id) => void openDoc(id)}
            onHistory={() => void openChatHistory()} onAttach={() => void openAttach()} attachments={attachments}
            onRemoveAttachment={(a) => { if (chatIdRef.current) persistChat.current = true; setAttachments((l) => l.filter((x) => !(x.kind === a.kind && x.id === a.id))); }}
            onSaveReply={(id) => void saveReplyToNotes(id)} onDraftIdea={draftFromIdea} onSaveIdea={(idea) => void saveIdeaToNotes(idea)}
            onQuick={onQuick} onMenu={openAiMenu} canInsert={doc?.kind === "scene"} onClose={() => setAssistantOpen(false)}
            notesExtra={doc?.kind === "scene" ? (
              <CommentsPanel comments={comments} onOpen={openComment}
                onResolve={(c, resolved) => void commentCall((id, text) => api.resolveComment(id, c.id, resolved, text))} />
            ) : null}
            inspiration={
              <InspirationPanel key={ws.project.path} sceneId={doc?.kind === "scene" ? doc.id : null} sceneTitle={doc?.kind === "scene" ? doc.title : ""}
                rev={inspRev} getEditor={() => { const ed = editorRef.current; return ed ? { text: ed.getText(), cursor: ed.head() } : null; }}
                requireAi={requireAi} job={aiCall} notify={notify} onSpent={() => void refresh()} />
            }
            style={ws ? styleStatus : null} onLearnStyle={() => void learnStyle()} onOpenStyle={() => void openStyle()} />
        )}
      </div>
      {aiRun?.mode === "strip" && <ProgressStrip run={aiRun} onStop={stopAi} />}
      {aiRun?.mode === "draft" && <DraftPanel run={aiRun} onStop={stopAi} />}
      <StatusBar ai={aiRun} onStopAi={stopAi} stats={ws.status.stats} onStats={() => setDialog({ kind: "stats" })}
        sprintLeft={sprint ? remaining(sprint, nowMs) : null} onSprint={() => setDialog(sprint ? { kind: "stop-sprint" } : { kind: "sprint" })} projectWords={ws.status.projectWords} aiCost={ws.status.aiCost}
        line={cursor.line} col={cursor.col} zoom={zoom} onZoom={cycleZoom}
        spelling={isScene ? spellCount : null} onSpelling={jumpToMisspelling}
        snapshotAt={isScene ? snapshotAt : undefined} onSnapshots={openHistory}
        draft={ws.project.draft} onDraft={openDraftMenu} sync={sync} onSync={openSyncMenu} />
      {switcher && <QuickSwitcher ws={ws} onClose={() => setSwitcher(false)}
        onPick={(id) => { setSwitcher(false); void openDoc(id); }} />}
      {spellTarget && (
        <SpellMenu target={spellTarget} onClose={() => setSpellTarget(null)}
          onReplace={(text) => spellReplace(spellTarget, text)} onAdd={(scope) => void spellAdd(spellTarget, scope)}
          onIgnore={() => void spellIgnore(spellTarget)} />
      )}
      {menu && <Menu anchor={menu.anchor} items={menu.items} onClose={() => setMenu(null)} />}
      {dialog?.kind === "new-scene" && (
        <PromptDialog title={`New ${unit}`} label="Title" confirm="Create" onSubmit={(t) => void createScene(t)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "new-note" && (
        <PromptDialog title="New note" label="Name" initial={dialog.name} confirm="Create"
          onSubmit={(n) => void createNote(n, dialog.openAfter)} onClose={() => setDialog(null)}>
          <div className="lw-dialog__types" role="radiogroup" aria-label="Type">
            {NOTE_TYPES.map((t) => (
              <button key={t} role="radio" aria-checked={noteType === t} className={`lw-chip lw-chip--pick${noteType === t ? " is-on" : ""}`}
                onClick={() => setNoteType(t)}>{t}</button>
            ))}
          </div>
        </PromptDialog>
      )}
      {dialog?.kind === "generate" && (
        <PromptDialog title={dialog.title} label={dialog.label} initial={dialog.initial} confirm="Generate"
          onSubmit={(t) => { const g = dialog; setDialog(null); void runGenerate(g.mode, t, g.from, g.to); }} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "rename-note" && (
        <RenameDialog name={dialog.name} aliases={dialog.aliases} onPreview={renamePreview} onApply={renameApply} onUndo={renameUndo}
          onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "aliases" && <AliasReviewDialog suggestions={dialog.items} onApply={(p) => void applyAliases(p)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "canon" && <CanonReviewDialog proposals={dialog.items} onApply={(p) => void applyCanon(p)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "style" && <StyleReviewDialog markdown={dialog.markdown} replacing={dialog.replacing} onSave={(t) => void saveStyle(t)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "settings" && <SettingsDialog initial={dialog.info} onClose={() => setDialog(null)} onSaved={settingsSaved} notify={notify} />}
      {dialog?.kind === "rename" && doc && (
        <PromptDialog title={`Rename ${unit}`} label="Title" initial={doc.title} confirm="Rename" onSubmit={(t) => void renameScene(t)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "delete" && doc && (
        <ConfirmDialog title={`Move ${unit} to the Trash`} confirm="Move to Trash"
          message={<>Move “{doc.title}” to the Trash? You can restore it from the Trash in the binder. <code>{doc.id}</code></>}
          onConfirm={() => void deleteScene()} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "new-part" && (
        <PromptDialog title="New part" label="Title" confirm="Create" onSubmit={(t) => void createPart(t)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "rename-part" && (
        <PromptDialog title="Rename part" label="Title" initial={dialog.title} confirm="Rename"
          onSubmit={(t) => void renamePart(dialog.id, t)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "delete-part" && (
        <ConfirmDialog title="Delete part" confirm="Delete part"
          message={<>Delete the empty part “{dialog.title}”?</>}
          onConfirm={() => void deletePart(dialog.id)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "pick-part" && (
        <PartPickerDialog title={dialog.unplaced ? "Place in the book" : `Move ${unit} to a part`}
          message="It goes to the end of the part you pick."
          parts={ws.parts} allowTop
          onPick={(partId) => {
            const id = dialog.sceneId;
            setDialog(null);
            void placeScene(id, partId, null, false).then((r) => r && notify(dialog.unplaced ? "Placed in the book." : "Moved."));
          }} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "move" && (
        <ConfirmDialog title={`Move ${unit}`} confirm="Move" tone="primary" message={dialog.plan.sentence}
          onConfirm={() => void performMove(dialog.plan)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "stats" && <StatsDialog onClose={() => setDialog(null)} notify={notify} />}
      {dialog?.kind === "sprint" && <SprintDialog initialFocus={sprintFocus} onClose={() => setDialog(null)} onStart={(m, f) => void startSprint(m, f)} />}
      {dialog?.kind === "stop-sprint" && (
        <ConfirmDialog title="Stop the sprint" confirm="Stop sprint"
          message={<>Stop the focus sprint now? What you wrote so far is still recorded in today’s stats.</>}
          onConfirm={() => { setDialog(null); void endSprint(true); }} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "trash" && (
        <TrashDialog onClose={() => setDialog(null)} notify={notify}
          onChanged={() => { void refresh(); setInspRev((n) => n + 1); }}
          onRestored={(id) => { setDialog(null); void openDoc(id); }} />
      )}
      {dialog?.kind === "snapshots" && doc?.kind === "scene" && (
        <SnapshotsDialog docId={doc.id} title={doc.title} unit={unit} getText={liveText} notify={notify}
          onChanged={setSnapshotAt} onRestore={restoreSnapshot} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "export" && <ExportDialog unit={unit} notify={notify} onClose={() => setDialog(null)} />}
      {dialog?.kind === "new-draft" && (
        <ConfirmDialog title={`Start draft ${ws.project.draft + 1}`} confirm="Start new draft" tone="primary"
          message={<>Every {unit} is snapshotted now as “End of draft {ws.project.draft}” (look for it under History), then the book counts as draft {ws.project.draft + 1}. Your text is not changed.</>}
          onConfirm={() => void startNewDraft()} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "sync-commit" && (
        <PromptDialog title="Commit changes" label="Message" initial={dialog.info.defaultMessage} confirm="Commit"
          onSubmit={(m) => void syncCommit(m)} onClose={() => setDialog(null)}>
          <p className="lw-dialog__message">
            Commits the {dialog.info.changes} change{dialog.info.changes === 1 ? "" : "s"} in this project folder only
            (repository <code>{dialog.info.toplevel}</code>). Nothing is pushed.
          </p>
        </PromptDialog>
      )}
      {dialog?.kind === "sync-push" && (
        <ConfirmDialog title="Push" confirm="Push" tone="primary"
          message={<>Push branch <code>{dialog.info.branch}</code> ({dialog.info.ahead} commit{dialog.info.ahead === 1 ? "" : "s"}) to the remote <code>{dialog.info.remote}</code>
            {dialog.info.remoteUrl && <> (<code>{dialog.info.remoteUrl}</code>)</>}? This sends your manuscript to that remote. It is never forced.</>}
          onConfirm={() => void syncPush()} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "sync-init" && (
        <ConfirmDialog title="Initialize git" confirm="Initialize" tone="primary"
          message={<>Turn this project folder into a git repository? A <code>.gitignore</code> hides the rebuildable index cache (<code>.lorewrite/</code>). Nothing is committed or pushed.</>}
          onConfirm={() => void syncInit()} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "add-comment" && (
        <AddCommentDialog quote={dialog.quote} onAdd={(b) => void addComment(b)} onClose={() => setDialog(null)} />
      )}
      {commentPop && popComment && (
        <CommentPopover key={popComment.id} comment={popComment} x={commentPop.x} y={commentPop.y} onClose={() => setCommentPop(null)}
          onSave={(body) => { setCommentPop(null); void commentCall((id, text) => api.editComment(id, popComment.id, body, text)); }}
          onResolve={(resolved) => { setCommentPop(null); void commentCall((id, text) => api.resolveComment(id, popComment.id, resolved, text)); }}
          onDelete={() => { setCommentPop(null); void commentCall((id, text) => api.deleteComment(id, popComment.id, text)); }} />
      )}
      {dialog?.kind === "chats" && (
        <ChatHistoryDialog chats={chatList} currentId={chatId} onOpen={(id) => void loadChat(id)} onNew={newChat}
          onRename={renameChat} onDelete={deleteChat} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "attach" && (
        <AttachDialog items={dialog.items} current={attachments} maxWords={dialog.maxWords} maxItems={dialog.maxItems}
          onSave={(picked) => { if (chatIdRef.current) persistChat.current = true; setAttachments(picked); setDialog(null); }} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "new-research" && (
        <PromptDialog title="New research note" label="Title" confirm="Create" onSubmit={(t) => void createResearch(t)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "research-url" && (
        <PromptDialog title="New research note from a link" label="Link (https://…)" initial={dialog.url} confirm="Save link"
          onSubmit={(u) => void researchFromUrl(u)} onClose={() => setDialog(null)}>
          <p className="lw-dialog__message lw-faint">Saves a note with the link and a title made from it. The page is not downloaded.</p>
        </PromptDialog>
      )}
      {dialog?.kind === "delete-research" && doc?.kind === "research" && (
        <ConfirmDialog title="Move research note to the Trash" confirm="Move to Trash"
          message={<>Move “{doc.title}” to the Trash? You can restore it from the Trash in the binder. <code>{doc.id}</code></>}
          onConfirm={() => void deleteResearch()} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "collections" && (
        <CollectionsManager collections={ws.collections} unit={unit} onCreate={createCollection} onRecolor={recolorCollection}
          onRename={renameCollection} onDelete={deleteCollection} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "scene-collections" && doc?.kind === "scene" && doc.details && (
        <SceneCollectionsDialog collections={ws.collections} current={doc.details.collections} title={doc.title}
          onSave={(names) => void saveDetails({ collections: names })}
          onManage={() => setDialog({ kind: "collections" })} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "details" && doc?.kind === "scene" && doc.details && (
        <DetailsDialog details={doc.details} entities={ws.entities} unit={unit}
          onSave={(patch) => void saveDetails(patch)} onClose={() => setDialog(null)} />
      )}
      <Toasts notices={notices} onDismiss={(id) => setNotices((n) => n.filter((x) => x.id !== id))} />
    </div>
  );
}
