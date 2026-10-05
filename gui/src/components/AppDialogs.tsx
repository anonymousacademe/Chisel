import type { ComponentProps, Dispatch, SetStateAction, MutableRefObject } from "react";
import { api } from "../backend/api";
import type { Dialog } from "../data/dialog";
import type { AliasSuggestion, ChatSummary, CommentRow, DetailsPatch, DocumentPayload, EntityType, RelationshipSuggestion, Workspace } from "../data/types";
import type { MovePlan } from "../data/reorder";
import type { BridgeResult } from "../backend/transport";
import type { Attachment } from "../data/chat";
import type { NoteTemplate } from "../data/notebook";
import type { Notice } from "./Toast";
import { NOTE_TYPES } from "../data/appLogic";
import { AddCommentDialog, CommentPopover } from "./CommentComponents";
import { AtmospherePanel } from "./AtmospherePanel";
import { AliasReviewDialog, CanonReviewDialog, RelationshipsReviewDialog, StyleReviewDialog } from "./ReviewDialogs";
import { SprintDialog, StatsDialog } from "./StatsDialog";
import { ConfirmDialog, Modal, PromptDialog } from "./Dialogs";
import { SentReport } from "./SentReport";
import { PartPickerDialog, TrashDialog, DetailsDialog } from "./StructureDialogs";
import { SnapshotsDialog } from "./SnapshotsDialog";
import { ExportDialog } from "./ExportDialog";
import { RenameDialog } from "./RenameDialog";
import { CollectionsManager, SceneCollectionsDialog } from "./CollectionDialogs";
import { AttachDialog, ChatHistoryDialog } from "./ChatDialogs";
import { NewNoteDialog, NotebookDialog } from "./NotebookDialogs";
import { SettingsDialog } from "./SettingsDialog";

type Notify = (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
type Collections = ComponentProps<typeof CollectionsManager>;
type Rename = ComponentProps<typeof RenameDialog>;

/** Everything App owns that a dialog needs: state, and the handlers a dialog's buttons run. */
export interface AppDialogsProps {
  ws: Workspace;
  doc: DocumentPayload | null;
  unit: Workspace["project"]["unit"];
  dialog: Dialog;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  notify: Notify;
  refresh: () => Promise<unknown>;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
  liveText: () => string;
  // notes
  noteType: EntityType;
  setNoteType: (t: EntityType) => void;
  createNote: (name: string, openAfter: boolean) => Promise<void>;
  // AI reviews and drafting
  runGenerate: (mode: "draft" | "expand" | "rewrite", instruction: string, from: number, to: number) => Promise<void>;
  applyAliases: (picked: AliasSuggestion[]) => Promise<void>;
  applyRelationships: (name: string, picked: RelationshipSuggestion[]) => Promise<void>;
  applyCanon: (picked: { entity: string; facts: string[] }[]) => Promise<void>;
  saveStyle: (text: string) => Promise<void>;
  settingsSaved: (editor: { zoom: number; reflow: boolean }, spellcheck: boolean) => void;
  // rename a note everywhere
  renamePreview: Rename["onPreview"];
  renameApply: Rename["onApply"];
  renameUndo: Rename["onUndo"];
  // scenes and parts
  createScene: (title: string) => Promise<void>;
  renameScene: (title: string) => Promise<void>;
  deleteScene: () => Promise<void>;
  createPart: (title: string) => Promise<void>;
  renamePart: (id: string, title: string) => Promise<void>;
  deletePart: (id: string) => Promise<void>;
  placeScene: (id: string, partId: string | null, index: number | null, unplaced: boolean) => Promise<unknown>;
  performMove: (plan: MovePlan) => Promise<void>;
  saveDetails: (patch: DetailsPatch) => Promise<void>;
  // sprint
  sprintFocus: boolean;
  startSprint: (minutes: number, focusMode: boolean) => Promise<void>;
  endSprint: (cancelled: boolean) => Promise<void>;
  // trash, history, drafts, git
  setInspRev: Dispatch<SetStateAction<number>>;
  restoreSnapshot: (snapshotId: string) => Promise<boolean>;
  setSnapshotAt: Dispatch<SetStateAction<string | null>>;
  startNewDraft: () => Promise<void>;
  syncCommit: (message: string) => Promise<void>;
  syncPush: () => Promise<void>;
  syncInit: () => Promise<void>;
  // comments
  addComment: (body: string) => Promise<void>;
  commentPop: { id: string; x: number; y: number } | null;
  setCommentPop: (p: { id: string; x: number; y: number } | null) => void;
  popComment: CommentRow | null;
  commentCall: (run: (id: string, text: string) => Promise<BridgeResult<{ comments: CommentRow[] }>>) => Promise<void>;
  // chats and attachments
  chatList: ChatSummary[] | null;
  chatId: string | null;
  chatIdRef: MutableRefObject<string | null>;
  setPersist: (on: boolean) => void;
  attachments: Attachment[];
  setAttachments: Dispatch<SetStateAction<Attachment[]>>;
  loadChat: (id: string) => Promise<void>;
  newChat: () => void;
  renameChat: ComponentProps<typeof ChatHistoryDialog>["onRename"];
  deleteChat: ComponentProps<typeof ChatHistoryDialog>["onDelete"];
  // notebook
  createResearch: (title: string, template?: NoteTemplate) => Promise<void>;
  researchFromUrl: (url: string) => Promise<void>;
  deleteResearch: () => Promise<void>;
  researchMode: boolean;
  setAssistantOpen: Dispatch<SetStateAction<boolean>>;
  onQuick: (a: "research") => void;
  // collections
  createCollection: Collections["onCreate"];
  recolorCollection: Collections["onRecolor"];
  renameCollection: Collections["onRename"];
  deleteCollection: Collections["onDelete"];
}

/** Renders whichever modal dialog (and the comment popover) is open. Pure view: App owns all state and logic. */
export function AppDialogs(p: AppDialogsProps) {
  const {
    ws, doc, unit, dialog, setDialog, notify, refresh, openDoc, liveText, noteType, setNoteType, createNote, runGenerate,
    applyAliases, applyRelationships, applyCanon, saveStyle, settingsSaved, renamePreview, renameApply, renameUndo, createScene, renameScene, deleteScene,
    createPart, renamePart, deletePart, placeScene, performMove, saveDetails, sprintFocus, startSprint, endSprint, setInspRev,
    restoreSnapshot, setSnapshotAt, startNewDraft, syncCommit, syncPush, syncInit, addComment, commentPop, setCommentPop, popComment,
    commentCall, chatList, chatId, chatIdRef, setPersist, attachments, setAttachments, loadChat, newChat, renameChat, deleteChat,
    createResearch, researchFromUrl, deleteResearch, researchMode, setAssistantOpen, onQuick,
    createCollection, recolorCollection, renameCollection, deleteCollection,
  } = p;
  return (
    <>
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
      {dialog?.kind === "aliases" && <AliasReviewDialog suggestions={dialog.items} sent={dialog.sent} onApply={(p) => void applyAliases(p)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "relationships" && (
        <RelationshipsReviewDialog name={dialog.name} items={dialog.items} sent={dialog.sent}
          onApply={(picked) => void applyRelationships(dialog.name, picked)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "sent" && (
        <Modal title="What was sent" onClose={() => setDialog(null)}>
          <SentReport report={dialog.report} open />
          <div className="lw-dialog__buttons"><button className="lw-btn lw-btn--primary" onClick={() => setDialog(null)}>Close</button></div>
        </Modal>
      )}
      {dialog?.kind === "canon" && <CanonReviewDialog proposals={dialog.items} sent={dialog.sent} onApply={(p) => void applyCanon(p)} onClose={() => setDialog(null)} />}
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
      {dialog?.kind === "sound" && <AtmospherePanel onClose={() => setDialog(null)} notify={notify} />}
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
          message={<>Turn this project folder into a git repository? A <code>.gitignore</code> hides the rebuildable index cache (<code>.chisel/</code>). Nothing is committed or pushed.</>}
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
          onSave={(picked) => { if (chatIdRef.current) setPersist(true); setAttachments(picked); setDialog(null); }} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "new-research" && (
        <NewNoteDialog onSubmit={(t, tpl) => void createResearch(t, tpl)} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "notebook" && (
        <NotebookDialog notes={ws.research} onClose={() => setDialog(null)}
          onOpen={(id) => { setDialog(null); void openDoc(id); }}
          onNew={() => setDialog({ kind: "new-research" })}
          onFromLink={() => setDialog({ kind: "research-url", url: "" })}
          onAsk={() => { setDialog(null); setAssistantOpen(true); if (!researchMode) onQuick("research"); }} />
      )}
      {dialog?.kind === "research-url" && (
        <PromptDialog title="New note from a link" label="Link (https://…)" initial={dialog.url} confirm="Save link"
          onSubmit={(u) => void researchFromUrl(u)} onClose={() => setDialog(null)}>
          <p className="lw-dialog__message lw-faint">Saves a note with the link and a title made from it. The page is not downloaded.</p>
        </PromptDialog>
      )}
      {dialog?.kind === "delete-research" && doc?.kind === "research" && (
        <ConfirmDialog title="Move notebook note to the Trash" confirm="Move to Trash"
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
          when={ws.scenes.find((s) => s.id === doc.id)?.when} timeline={ws.timeline}
          onSave={(patch) => void saveDetails(patch)} onClose={() => setDialog(null)} />
      )}
    </>
  );
}
