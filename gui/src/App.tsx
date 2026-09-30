import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./backend/api";
import type { BinderNode, DocumentPayload, EntityInfo, EntityType, SceneMention, Workspace } from "./data/types";
import { collectExpanded, isOpenable } from "./data/tree";
import { SaveController, type SaveState } from "./editor/saveController";
import type { Card, CursorInfo } from "./editor/cm";
import type { Span } from "./editor/spans";
import { TitleBar } from "./components/TitleBar";
import { ActivityRail, type RailView } from "./components/ActivityRail";
import { Binder } from "./components/Binder";
import { Editor, type ViewMode } from "./components/Editor";
import type { EditorHandle } from "./components/EditorPane";
import { Assistant, type AssistantTab } from "./components/Assistant";
import { StatusBar } from "./components/StatusBar";
import { Launch } from "./components/Launch";
import { QuickSwitcher } from "./components/QuickSwitcher";
import { ConfirmDialog, Menu, PromptDialog, type MenuItem } from "./components/Dialogs";
import { Toasts, type Notice } from "./components/Toast";

const ZOOMS = [90, 100, 110, 125];
const NO_CURSOR: CursorInfo = { line: 1, col: 1, head: 0, from: 0, to: 0, canUndo: false, canRedo: false };

type Dialog =
  | { kind: "new-scene" }
  | { kind: "rename" }
  | { kind: "delete" }
  | { kind: "new-note"; name: string; openAfter: boolean }
  | null;

const NOTE_TYPES: EntityType[] = ["character", "place", "object", "faction"];

export default function App() {
  // undefined = still loading, null = no project open (launch screen)
  const [ws, setWs] = useState<Workspace | null | undefined>(undefined);
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
  const [cursor, setCursor] = useState<CursorInfo>(NO_CURSOR);
  const [mentions, setMentions] = useState<SceneMention[]>([]);
  const [tab, setTab] = useState<AssistantTab>("assistant");
  const [noteName, setNoteName] = useState<string | null>(null);
  const [note, setNote] = useState<EntityInfo | null>(null);
  const [noteVersion, setNoteVersion] = useState(0);
  const [missingTarget, setMissingTarget] = useState<string | null>(null);
  const [noteType, setNoteType] = useState<EntityType>("character");
  const noticeId = useRef(0);
  const editorRef = useRef<EditorHandle>(null);
  const focusAfterOpen = useRef(false);
  const gotoRow = useRef<number | null>(null);

  const notify = useCallback((text: string, tone: Notice["tone"] = "info") => {
    const id = ++noticeId.current;
    setNotices((n) => [...n, { id, text, tone }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), tone === "error" ? 8000 : 3500);
  }, []);

  const refresh = useCallback(async () => {
    const r = await api.getWorkspace();
    if (!r.ok) { notify(r.error, "error"); return null; }
    setWs(r.workspace);
    return r.workspace;
  }, [notify]);

  // The autosave state machine for whichever document is open.
  const saver: SaveController = useMemo(() => new SaveController({
    save: (id, text, mtime, force) => api.saveDocument(id, text, mtime, force),
    onState: setSaveState,
    onSaved: (r) => {
      if (r.words !== undefined) setWords(r.words);
      void refresh();
      const id = saver.documentId; // the retrieved-context list follows what was just saved
      if (id?.startsWith("manuscript/")) {
        void api.sceneContext(id).then((c) => { if (c.ok && saver.documentId === id) setMentions(c.mentions); });
      }
    },
    onError: (m) => notify(`Save failed: ${m}`, "error"),
  }), [notify, refresh]);

  const openDoc = useCallback(async (id: string, opts: { force?: boolean } = {}) => {
    if (!opts.force) {
      if (saver.state === "conflict") { notify("Resolve the save conflict first (reload or keep your version).", "error"); return; }
      if (!(await saver.flush())) { notify("Could not save the current document; staying here.", "error"); return; }
    }
    const r = await api.readDocument(id);
    if (!r.ok) { notify(r.error, "error"); return; }
    saver.open(r.id, r.text, r.mtime);
    setDoc(r);
    setMentions(r.mentions);
    setWords(r.words);
    setDocRev((n) => n + 1);
    setCursor(NO_CURSOR);
    setMode("manuscript");
  }, [saver, notify]);

  const boot = useCallback(async () => {
    const w = await refresh();
    if (!w) return;
    setExpanded(collectExpanded(w.binder));
    saver.detach();
    setDoc(null);
    if (w.scenes[0]) void openDoc(w.scenes[0].id, { force: true });
  }, [refresh, saver, openDoc]);

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
    };
    const onHide = () => { void saver.flush(); };
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
    window.addEventListener("pagehide", onHide);
    window.addEventListener("blur", onHide);
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("blur", onHide);
      window.removeEventListener("focus", onFocus);
    };
  }, [saver, openDoc, notify]);

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
  const select = (n: BinderNode) => { if (isOpenable(n)) void openDoc(n.id); };
  const toggle = (id: string) => setExpanded((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const onRail = (v: RailView) => {
    if (v === "assistant") { setAssistantOpen((o) => !o); return; }
    setRail(v); setFocus(false);
  };
  const docLabel = doc ? (doc.kind === "scene" ? `${doc.kicker.replace("SCENE", "Scene")} · ${doc.title}` : doc.title) : "";
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

  const saveNow = async () => { const ok = await saver.flush(); if (ok) notify("Saved"); };
  const closeWindow = async () => { await saver.flush(); await api.close(); };

  const reloadFromDisk = async () => { if (doc) await openDoc(doc.id, { force: true }); };
  const keepMine = async () => {
    const ok = await saver.keepMine();
    notify(ok ? "Kept your version." : "Could not save your version.", ok ? "info" : "error");
  };

  // -- scene management --------------------------------------------------------
  const createScene = async (title: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newScene(title);
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
  const deleteScene = async () => {
    setDialog(null);
    if (!doc) return;
    const id = doc.id;
    saver.detach(); // before anything else: a pending autosave must not resurrect the file
    setDoc(null);
    const r = await api.deleteScene(id);
    if (!r.ok) { notify(r.error, "error"); await openDoc(id, { force: true }); return; }
    const w = await refresh();
    if (w?.scenes[0]) await openDoc(w.scenes[0].id, { force: true });
    notify("Scene deleted.");
  };
  const openSceneMenu = (anchor: HTMLElement) => setMenu({
    anchor, items: [
      { label: "New scene", onSelect: () => setDialog({ kind: "new-scene" }) },
      { label: "Rename scene…", disabled: !isScene, onSelect: () => setDialog({ kind: "rename" }) },
      { label: "Move up", disabled: !isScene, onSelect: () => void moveScene(-1) },
      { label: "Move down", disabled: !isScene, onSelect: () => void moveScene(1) },
      { label: "Delete scene…", disabled: !isScene, danger: true, onSelect: () => setDialog({ kind: "delete" }) },
    ],
  });

  const showBinder = !focus;
  const showAssistant = assistantOpen && !focus;

  return (
    <div className="lw-app" style={{ ["--lw-zoom" as string]: zoom / 100 }}>
      <TitleBar projectTitle={ws.project.title} documentLabel={docLabel} saveState={saveState}
        assistantOpen={showAssistant} onToggleAssistant={() => setAssistantOpen((o) => !o)}
        onSearch={() => setSwitcher(true)} onClose={() => void closeWindow()} />
      <div className="lw-workspace">
        <ActivityRail view={rail} assistantOpen={showAssistant} onView={onRail} badge={0}
          initials={ws.project.initials} author={ws.project.author} />
        {showBinder && (
          <Binder nodes={ws.binder} count={ws.project.documentCount} activeId={doc?.id ?? null}
            expanded={expanded} onToggle={toggle} onSelect={select} searching={rail === "search"}
            library={rail === "library"} canNew canMenu={rail !== "library"}
            onNew={() => setDialog(rail === "library" ? { kind: "new-note", name: "", openAfter: true } : { kind: "new-scene" })} onMenu={openSceneMenu} />
        )}
        <Editor doc={doc} scenes={ws.scenes} words={words} mentions={mentions}
          sessionWords={ws.status.sessionWords} sessionMinutes={ws.status.sessionMinutes}
          mode={mode} onMode={setMode} focus={focus} onFocus={() => setFocus((f) => !f)} onOpen={(id) => void openDoc(id)}
          editorRef={editorRef} docRev={docRev} spansVersion={spansVersion} cursor={cursor} saveState={saveState}
          onChange={(t) => saver.edit(t)} onCursor={onCursor} onBlur={() => void saver.flush()}
          onSaveNow={() => void saveNow()} onReload={() => void reloadFromDisk()} onKeepMine={() => void keepMine()}
          onMakeNote={() => makeNote(false)} getCard={getCard} onOpenEntity={openEntitySpan}
          extraKeys={[{ key: "Mod-j", run: () => makeNote(true) }]} />
        {showAssistant && (
          <Assistant tab={tab} onTab={setTab} mentions={mentions} onPickEntity={showNote}
            note={note} missingTarget={missingTarget} onOpenNote={(id) => void openDoc(id)} onAddAlias={(n, a) => void addAlias(n, a)}
            onCreateNote={(t) => setDialog({ kind: "new-note", name: t, openAfter: false })} onOpenBacklink={(id, row) => void openBacklink(id, row)}
            messages={[]} busy={false} aiReady={false}
            onSend={() => {}} onClose={() => setAssistantOpen(false)} onRegenerate={() => {}}
            onReviewInsight={() => {}} onDismissInsight={() => {}} />
        )}
      </div>
      <StatusBar sessionWords={ws.status.sessionWords} projectWords={ws.status.projectWords} aiCost={ws.status.aiCost}
        line={cursor.line} col={cursor.col} zoom={zoom} onZoom={() => setZoom((z) => ZOOMS[(ZOOMS.indexOf(z) + 1) % ZOOMS.length])} />
      {switcher && <QuickSwitcher ws={ws} onClose={() => setSwitcher(false)}
        onPick={(id) => { setSwitcher(false); void openDoc(id); }} />}
      {menu && <Menu anchor={menu.anchor} items={menu.items} onClose={() => setMenu(null)} />}
      {dialog?.kind === "new-scene" && (
        <PromptDialog title="New scene" label="Title" confirm="Create" onSubmit={(t) => void createScene(t)} onClose={() => setDialog(null)} />
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
      {dialog?.kind === "rename" && doc && (
        <PromptDialog title="Rename scene" label="Title" initial={doc.title} confirm="Rename" onSubmit={(t) => void renameScene(t)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "delete" && doc && (
        <ConfirmDialog title="Delete scene" confirm="Delete"
          message={<>Delete “{doc.title}”? This removes <code>{doc.id}</code> from disk and cannot be undone.</>}
          onConfirm={() => void deleteScene()} onClose={() => setDialog(null)} />
      )}
      <Toasts notices={notices} onDismiss={(id) => setNotices((n) => n.filter((x) => x.id !== id))} />
    </div>
  );
}
