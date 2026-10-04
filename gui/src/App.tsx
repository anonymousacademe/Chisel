import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./backend/api";
import { DraftPanel, ProgressStrip } from "./components/AiProgress";
import type {
  AttachReport, BinderNode, DocumentPayload, EntityInfo, EntityType, Issue, SceneMention, SentReport as SentInfo, Workspace,
} from "./data/types";
import { collectExpanded, isOpenable } from "./data/tree";
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
import { scopeLabel, subjectArgs, subjectOf } from "./data/subject";
import { atmosphere } from "./audio/store";
import { SpellMenu } from "./components/SpellMenu";
import { StatusBar } from "./components/StatusBar";
import { remaining, sprintNotice } from "./data/stats";
import { Launch } from "./components/Launch";
import { QuickSwitcher } from "./components/QuickSwitcher";
import { Menu, type MenuItem } from "./components/Dialogs";
import { memberIds } from "./data/collections";
import { CommentsPanel } from "./components/CommentComponents";
import { AppDialogs } from "./components/AppDialogs";
import { Toasts } from "./components/Toast";
import type { Dialog } from "./data/dialog";
import { firstScene, sentence } from "./data/appLogic";
import { useComments } from "./hooks/useComments";
import { useRenameEverywhere } from "./hooks/useRenameEverywhere";
import { useCollectionOps } from "./hooks/useCollectionOps";
import { useSyncActions } from "./hooks/useSyncActions";
import { useSceneOps } from "./hooks/useSceneOps";
import { useAiStatus } from "./hooks/useAiStatus";
import { useStyleStatus } from "./hooks/useStyleStatus";
import { useAiJob } from "./hooks/useAiJob";
import { useNotebookOps } from "./hooks/useNotebookOps";
import { useAiActions } from "./hooks/useAiActions";
import { useNotices } from "./hooks/useNotices";
import { useSyncStatus } from "./hooks/useSyncStatus";
import { useChatState } from "./hooks/useChatState";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { useSprintClock } from "./hooks/useSprintClock";

const ZOOMS = [90, 100, 110, 125];
const NO_CURSOR: CursorInfo = { line: 1, col: 1, head: 0, from: 0, to: 0, canUndo: false, canRedo: false };


const uid = () => crypto.randomUUID();

export default function App() {
  // undefined = still loading, null = no project open (launch screen)
  const [ws, setWs] = useState<Workspace | null | undefined>(undefined);
  const styleStatus = useStyleStatus();
  const lastPing = useRef(0);   // writing stats: last typing ping (ms)
  const sprintFocusStarted = useRef(false);   // the sprint turned focus mode on, so it turns it off
  const [sprintFocus, setSprintFocus] = useState(() => {
    try { return localStorage.getItem("lw-sprint-focus") === "1"; } catch { return false; }
  });
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
  const { notices, notify, dismiss } = useNotices();
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [words, setWords] = useState(0);
  const [snapshotAt, setSnapshotAt] = useState<string | null>(null);
  const { sync, setSync, refreshSync } = useSyncStatus();
  const [cursor, setCursor] = useState<CursorInfo>(NO_CURSOR);
  const [mentions, setMentions] = useState<SceneMention[]>([]);
  const [tab, setTab] = useState<AssistantTab>("assistant");
  const [inspRev, setInspRev] = useState(0);   // bumped when the Trash gives a picture back
  const [noteName, setNoteName] = useState<string | null>(null);
  const [note, setNote] = useState<EntityInfo | null>(null);
  const [_noteVersion, setNoteVersion] = useState(0);
  const [missingTarget, setMissingTarget] = useState<string | null>(null);
  const [noteType, setNoteType] = useState<EntityType>("character");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [issuesSent, setIssuesSent] = useState<SentInfo | null>(null);   // what the last continuity check sent
  const [reflow, setReflow] = useState(true);
  const [spellCount, setSpellCount] = useState<number | null>(null);
  const [spellVersion, setSpellVersion] = useState(0);
  const [spellTarget, setSpellTarget] = useState<SpellTarget | null>(null);
  const [partFocus, setPartFocus] = useState<string | null>(null);
  const [researchMode, setResearchMode] = useState(false);
  const editorRef = useRef<EditorHandle>(null);
  const focusAfterOpen = useRef(false);
  const gotoRow = useRef<number | null>(null);
  const docRef = useRef<DocumentPayload | null>(null);
  useEffect(() => { docRef.current = doc; });

  const refresh = useCallback(async () => {
    const r = await api.getWorkspace();
    if (!r.ok) { notify(r.error, "error"); return null; }
    setWs(r.workspace);
    return r.workspace;
  }, [notify]);

  const openSettings = async () => {
    const r = await api.getSettings();
    if (!r.ok) return notify(r.error, "error");
    setDialog({ kind: "settings", info: r });
  };
  const aiReady = useAiStatus();
  const { aiRun, aiBusy, requireAi, aiCall, stopAi, failedReply } = useAiJob({ notify, refresh, editorRef, openSettings, aiReady });

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
    setIssues([]); setIssuesSent(null);
    setMentions(r.mentions);
    setWords(r.words);
    setSnapshotAt(r.snapshotAt ?? null);
    setDocRev((n) => n + 1);
    setCursor(NO_CURSOR);
    if (!opts.keepMode) setMode("manuscript");
  }, [saver, notify]);

  const boot = useCallback(async () => {
    void atmosphere.load();
    void api.getSettings().then((r) => { if (r.ok) { setZoom(r.editor.zoom); setReflow(r.editor.reflow); } });
    const w = await refresh();
    if (!w) return;
    refreshSync(true);
    setExpanded(collectExpanded(w.binder));
    saver.detach();
    setDoc(null);
    const first = firstScene(w.scenes);
    if (first) void openDoc(first.id, { force: true });
  }, [refresh, refreshSync, saver, openDoc]);

  // initialize application state on first mount
  useEffect(() => {
    void atmosphere.load();
    void api.getSettings().then((r) => { 
      if (r.ok) { 
        setZoom(r.editor.zoom); 
        setReflow(r.editor.reflow); 
      } 
    });
  }, []);

  // boot the application
  const bootWithoutState = useCallback(async () => {
    const w = await refresh();
    if (!w) return;
    refreshSync(true);
    setExpanded(collectExpanded(w.binder));
    saver.detach();
    setDoc(null);
    const first = firstScene(w.scenes);
    if (first) void openDoc(first.id, { force: true });
  }, [refresh, refreshSync, saver, openDoc]);

  useEffect(() => {
    // deferred out of the effect body: the boot sequence sets state, and calling it
    // synchronously here would cascade renders before the first paint
    const t = setTimeout(() => void bootWithoutState(), 0);
    return () => clearTimeout(t);
  }, [bootWithoutState]);

  // (for a scene, the note also shows the character's age there: Python computes it)
  const sceneDocId = doc?.kind === "scene" ? doc.id : undefined;

  // a just-created scene takes focus once its editor has mounted
  useEffect(() => {
    if (!doc) return;
    if (focusAfterOpen.current) { focusAfterOpen.current = false; editorRef.current?.focusEnd(); }
    if (gotoRow.current !== null) { editorRef.current?.gotoLine(gotoRow.current); gotoRow.current = null; }
  }, [docRev, doc]);

  // derive note state from document during render
  const noteState = useMemo(() => {
    if (doc?.kind === "entity") {
      return { noteName: doc.title, missingTarget: null };
    }
    return { noteName: null, missingTarget: null };
  }, [doc]);
  
  // update note state when derived value changes
  if (noteState.noteName !== null) {
    setNoteName(noteState.noteName);
    setMissingTarget(noteState.missingTarget);
  }

 
  // (for a scene, the note also shows the character's age there: Python computes it)
   
  // handle note loading with useEffect (this is a legitimate case for setState in effect)
  useEffect(() => {
    if (noteName) {
      let live = true;
      void api.getEntity(noteName, sceneDocId).then((r) => { 
        if (live && r.ok) setNote(r); 
      });
      return () => { live = false; };
    }
  }, [noteName, sceneDocId]);

  const { comments, setComments, commentPop, setCommentPop, startAddComment, addComment, commentCall, openComment, popComment } =
    useComments({ editorRef, docRef, dialog, setDialog, notify, setTab, setAssistantOpen });
  const { renamePreview, renameApply, renameUndo } = useRenameEverywhere({ saver, docRef, dialog, notify, refresh, openDoc, setSpansVersion, setNoteVersion, setNoteName });
  const { collection, setCollection, createCollection, recolorCollection, renameCollection, deleteCollection } = useCollectionOps({ saver, docRef, notify, refresh, openDoc });
  const { syncCommit, syncPush, syncInit } = useSyncActions({ saver, notify, setDialog, setSync, refreshSync });
  const { messages, setMessages, scope, setScope, subjectRemoved, setSubjectRemoved, attachments, setAttachments, chatList, chatId, chatIdRef, setPersist,
    newChat, openChatHistory, loadChat, renameChat, deleteChat, openAttach } = useChatState({ notify, setDialog, setTab, setAssistantOpen });
  const focusNextOpen = () => { focusAfterOpen.current = true; };
  const { createScene, renameScene, moveScene, placeScene, performMove, deleteScene, createPart, renamePart, movePart, deletePart, saveDetails } =
    useSceneOps({ saver, ws, doc, docRef, editorRef, notify, refresh, openDoc, setDoc, setDialog, setExpanded, setPartFocus, setMentions, focusNextOpen });
  const { createResearch, researchFromUrl, deleteResearch, sendSelectionToNotebook } =
    useNotebookOps({ saver, docRef, editorRef, notify, refresh, openDoc, setDoc, setDialog, setExpanded, focusNextOpen });
  const { liveText, quickContinuity, reviewIssue, dismissIssue, restoreWaived, findAliases, applyAliases, updateBible, applyCanon,
    openStyle, learnStyle, saveStyle, runGenerate, startGenerate, rewriteSelection, resolveDraft, resolveAtCursor } =
    useAiActions({ saver, ws, docRef, editorRef, notify, refresh, openDoc, aiCall, requireAi, setDialog, setIssues, setIssuesSent, setTab,
      setAssistantOpen, setSpansVersion, setNoteVersion, setMentions });
  useGlobalShortcuts({ saver, openDoc, notify, setSwitcher, setFocus, setDialog });
 
  // -- focus sprint (the countdown is client-side; the server keeps the start/end and counts the words) --
  const sprint = ws?.status.stats?.sprint ?? null;
  const endSprint = async (cancelled: boolean) => {
    await saver.flush();   // the last words count
    const r = await api.sprintEnd(cancelled);
    if (sprintFocusStarted.current) { sprintFocusStarted.current = false; setFocus(false); }
    await refresh();
    if (!r.ok) return notify(r.error, "error");
    notify(sprintNotice(r.sprint.minutes, r.sprint.words, cancelled),
      "info", { label: "Session stats", run: () => setDialog({ kind: "stats" }) });
  };
  const { nowMs, setNowMs } = useSprintClock(sprint, () => void endSprint(false));   // above the early returns
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
  if (ws === undefined) return <div className="lw-app lw-loading">Loading project…</div>;
  if (ws === null) {
    return (
      <div className="lw-app">
        <Launch onOpened={boot} />
        <Toasts notices={notices} onDismiss={dismiss} />
      </div>
    );
  }

  const isScene = doc?.kind === "scene";
  // The open item can be the assistant's subject (chip) and can have pictures when it is a scene or a note.
  const eligibleSubject = doc?.kind === "scene" || doc?.kind === "entity" || doc?.kind === "research";
  const pictureItem = eligibleSubject;
  const subject = subjectOf(doc, { scope, removed: subjectRemoved, researchMode });
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
  const setBorn = async (name: string, born: string) => {
    const open = doc?.kind === "entity" ? doc.id : null;   // the note's own file is rewritten: flush first, reopen after
    if (open && !(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.setEntityBorn(name, born);
    if (!r.ok) return notify(r.error, "error");
    setNoteVersion((v) => v + 1);
    if (open) await openDoc(open, { force: true, keepMode: true });
  };
  const openBacklink = async (sourceId: string, row: number) => {
    if (doc?.id === sourceId) { editorRef.current?.gotoLine(row); return; }
    gotoRow.current = row;
    await openDoc(sourceId);
  };

  // -- AI ------------------------------------------------------------------------
  // Everything the model returns is a suggestion: chat text, a review list, or a
  // pending <!--ai--> draft with Accept / Reject. Nothing edits prose on its own.

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
      const r = await aiCall<{ reply: string; sources: { id: string; title: string; score: number }[]; attached: AttachReport[]; cost: number | null; sent: SentInfo }>("Searching your notes…", "searching notes", "research", { prompt: text, history, attachments: attached });
      if (r) reportAttached(r.attached);
      setPersist(!!r);
      setMessages((m) => [...m, r
        ? { id: uid(), role: "assistant", text: r.reply, sources: r.sources.map((s) => ({ id: s.id, title: s.title })), sent: r.sent }
        : failedReply()]);
      return;
    }
    // the open item is the subject of the question (shown as a chip); scenes travel as doc_id, notes as subject_id
    const sent = subjectArgs(d, subjectOf(d, { scope, removed: subjectRemoved, researchMode }));
    const r = await aiCall<{ reply: string; attached: AttachReport[]; cost: number | null; sent: SentInfo }>("Thinking…", "thinking", "ask", { prompt: text, scope, ...sent, text: ed && sent.doc_id ? ed.getText() : null, cursor: ed?.head() ?? 0, history, attachments: attached });
    if (r) reportAttached(r.attached);
    setPersist(!!r);
    setMessages((m) => [...m, r ? { id: uid(), role: "assistant", text: r.reply, sent: r.sent } : failedReply()]);
  };
  /** Brainstorm quick action: ideas to get unstuck, from the scene around the cursor + canon + style. */
  const runBrainstorm = async (replaceId?: string) => {
    const ed = editorRef.current, d = docRef.current;
    if (!requireAi()) return;
    const attached = attachments.map(({ kind, id }) => ({ kind, id }));
    const sent = subjectArgs(d, subjectOf(d, { scope: "scene", removed: subjectRemoved, researchMode: false }));
    if (replaceId) setMessages((m) => m.filter((x) => x.id !== replaceId));
    else setMessages((m) => [...m, { id: uid(), role: "user", text: "Brainstorm: ideas to get unstuck." }]);
    const r = await aiCall<{ reply: string; ideas: string[]; attached: AttachReport[]; cost: number | null; sent: SentInfo }>("Brainstorming…", "brainstorming", "brainstorm", { ...sent, text: ed && sent.doc_id ? ed.getText() : null, cursor: ed?.head() ?? 0, attachments: attached });
    if (r) reportAttached(r.attached);
    setPersist(!!r);
    setMessages((m) => [...m, r ? { id: uid(), role: "assistant", text: r.reply, ideas: r.ideas, sent: r.sent }
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
      if (!researchMode && !ws?.research.length) notify("Ask my notebook answers from your notebook notes. Add some under Notebook in the binder first (+ New note, or paste a link).");
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
  const settingsSaved = (editor: { zoom: number; reflow: boolean }, _spellcheck: boolean) => {
    setZoom(editor.zoom); setReflow(editor.reflow);
    setSpellVersion((v) => v + 1);
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

  const openSelectionMenu = (x: number, y: number) => setMenu({
    anchor: { getBoundingClientRect: () => new DOMRect(x, y - 4, 0, 0) } as unknown as HTMLElement,
    items: [
      { label: "Send selection to notebook", onSelect: () => void sendSelectionToNotebook() },
      { label: "Add selection to dictionary", onSelect: addSelectionToDictionary },
    ],
  });

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
        : { label: "Move to Parked scenes", disabled: !isScene, onSelect: () => doc && void placeScene(doc.id, null, null, true).then((r) => r && notify("Moved to Parked scenes. It no longer counts in the book.")) },
      { label: "Collections…", disabled: !isScene, onSelect: () => setDialog({ kind: "scene-collections" }) },
      { label: "History (snapshots)…", disabled: !isScene, onSelect: openHistory },
      { label: `Delete ${unit}…`, disabled: !isScene, danger: true, onSelect: () => setDialog({ kind: "delete" }) },
      { label: "parts", separator: true, onSelect: () => {} },
      { label: part ? `Rename part “${part.title}”…` : "Rename part…", disabled: !part, onSelect: () => part && setDialog({ kind: "rename-part", id: part.id, title: part.title }) },
      { label: "Move part up", disabled: !part, onSelect: () => part && void movePart(part.id, -1) },
      { label: "Move part down", disabled: !part, onSelect: () => part && void movePart(part.id, 1) },
      { label: "Delete empty part…", disabled: !part || part.sceneIds.length > 0, danger: true, onSelect: () => part && setDialog({ kind: "delete-part", id: part.id, title: part.title }) },
      { label: "notebook", separator: true, onSelect: () => {} },
      { label: "Open the Notebook…", onSelect: () => setDialog({ kind: "notebook" }) },
      { label: "New note…", onSelect: () => setDialog({ kind: "new-research" }) },
      { label: "New note from a link…", onSelect: () => setDialog({ kind: "research-url", url: "" }) },
      { label: "Send selection to notebook", disabled: !isScene, onSelect: () => void sendSelectionToNotebook() },
      { label: "Move this notebook note to the Trash…", disabled: doc?.kind !== "research", onSelect: () => setDialog({ kind: "delete-research" }) },
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
            onNewNote={() => setDialog({ kind: "new-research" })}
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
          spellVersion={spellVersion} onSpellCount={setSpellCount} onSpell={setSpellTarget} onSelectionMenu={openSelectionMenu} onAddPhrase={addSelectionToDictionary}
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
            note={note} missingTarget={missingTarget} onOpenNote={(id) => void openDoc(id)} onAddAlias={(n, a) => void addAlias(n, a)} onSetBorn={(n, b) => void setBorn(n, b)} onRename={(n, al) => setDialog({ kind: "rename-note", name: n, aliases: al })}
            onCreateNote={(t) => setDialog({ kind: "new-note", name: t, openAfter: false })} onOpenBacklink={(id, row) => void openBacklink(id, row)}
            issues={issues} issuesSent={issuesSent} onReviewIssue={reviewIssue} onDismissIssue={(i) => void dismissIssue(i)}
            messages={messages} busy={aiBusy} run={aiRun} onStop={stopAi} aiReady={aiReady} scope={scope} onScope={() => setScope((c) => (c === "scene" ? "project" : "scene"))}
            scopeText={scopeLabel(scope, subject)} subject={subject} onRemoveSubject={() => setSubjectRemoved(true)}
            onRestoreSubject={subjectRemoved && !researchMode && eligibleSubject ? () => setSubjectRemoved(false) : undefined}
            onSend={(t) => void sendChat(t)} onRegenerate={regenerate} onInsertDraft={(id) => void insertReplyAsDraft(id)}
            researchMode={researchMode} onOpenSource={(id) => void openDoc(id)}
            onHistory={() => void openChatHistory()} onAttach={() => void openAttach()} attachments={attachments}
            onRemoveAttachment={(a) => { if (chatIdRef.current) setPersist(true); setAttachments((l) => l.filter((x) => !(x.kind === a.kind && x.id === a.id))); }}
            onSaveReply={(id) => void saveReplyToNotes(id)} onDraftIdea={draftFromIdea} onSaveIdea={(idea) => void saveIdeaToNotes(idea)}
            onQuick={onQuick} onMenu={openAiMenu} canInsert={doc?.kind === "scene"} onClose={() => setAssistantOpen(false)}
            notesExtra={doc?.kind === "scene" ? (
              <CommentsPanel comments={comments} onOpen={openComment}
                onResolve={(c, resolved) => void commentCall((id, text) => api.resolveComment(id, c.id, resolved, text))} />
            ) : null}
            inspiration={
              <InspirationPanel key={ws.project.path} itemId={pictureItem ? doc!.id : null} itemTitle={pictureItem ? doc!.title : ""} itemKind={pictureItem ? doc!.kind : null}
                rev={inspRev} getEditor={() => { const ed = editorRef.current; return ed ? { text: ed.getText(), cursor: ed.head() } : null; }}
                requireAi={requireAi} job={aiCall} notify={notify} onSpent={() => void refresh()} />
            }
            style={ws ? styleStatus : null} onLearnStyle={() => void learnStyle()} onOpenStyle={() => void openStyle()} />
        )}
      </div>
      {aiRun?.mode === "strip" && <ProgressStrip run={aiRun} onStop={stopAi} />}
      {aiRun?.mode === "draft" && <DraftPanel run={aiRun} onStop={stopAi} />}
      <StatusBar onSound={() => setDialog({ kind: "sound" })} ai={aiRun} onStopAi={stopAi} stats={ws.status.stats} onStats={() => setDialog({ kind: "stats" })}
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
      <AppDialogs ws={ws} doc={doc} unit={unit} dialog={dialog} setDialog={setDialog} notify={notify} refresh={refresh} openDoc={openDoc} liveText={liveText}
        noteType={noteType} setNoteType={setNoteType} createNote={createNote} runGenerate={runGenerate}
        applyAliases={applyAliases} applyCanon={applyCanon} saveStyle={saveStyle} settingsSaved={settingsSaved}
        renamePreview={renamePreview} renameApply={renameApply} renameUndo={renameUndo}
        createScene={createScene} renameScene={renameScene} deleteScene={deleteScene} createPart={createPart} renamePart={renamePart}
        deletePart={deletePart} placeScene={placeScene} performMove={performMove} saveDetails={saveDetails}
        sprintFocus={sprintFocus} startSprint={startSprint} endSprint={endSprint} setInspRev={setInspRev}
        restoreSnapshot={restoreSnapshot} setSnapshotAt={setSnapshotAt} startNewDraft={startNewDraft}
        syncCommit={syncCommit} syncPush={syncPush} syncInit={syncInit}
        addComment={addComment} commentPop={commentPop} setCommentPop={setCommentPop} popComment={popComment} commentCall={commentCall}
        chatList={chatList} chatId={chatId} chatIdRef={chatIdRef} setPersist={setPersist} attachments={attachments} setAttachments={setAttachments}
        loadChat={loadChat} newChat={newChat} renameChat={renameChat} deleteChat={deleteChat}
        createResearch={createResearch} researchFromUrl={researchFromUrl} deleteResearch={deleteResearch}
        researchMode={researchMode} setAssistantOpen={setAssistantOpen} onQuick={onQuick}
        createCollection={createCollection} recolorCollection={recolorCollection} renameCollection={renameCollection} deleteCollection={deleteCollection} />
      <Toasts notices={notices} onDismiss={dismiss} />
    </div>
  );
}
