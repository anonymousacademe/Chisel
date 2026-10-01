import type { Misspelling, Span } from "../editor/spans";
import type {
  AliasSuggestion, CanonProposal, CollectionColor, CollectionSummary, DiffSegment, SnapshotRow, SyncInfo, DetailsPatch, DocumentPayload, Remap, SceneDetails, TrashItem, Unit, DraftEdit, EntityInfo, EntitySummary, EntityType, GenerateResult,
  Issue, ModelKind, ModelOption, RecentProject, SceneMention, SettingsInfo, EditorPrefs, StyleStatus, Workspace,
} from "../data/types";
import { call } from "./transport";

/** Typed wrappers over the bridge; method names match lorewrite.gui.api.Api. */
export const api = {
  getWorkspace: () => call<{ workspace: Workspace | null }>("get_workspace"),
  readDocument: (id: string) => call<DocumentPayload>("read_document", id),
  openProject: (path: string) => call("open_project", path),
  newProject: (title: string, path: string) => call("new_project", title, path),
  suggestProjectPath: (title: string) => call<{ path: string }>("suggest_project_path", title),
  recentProjects: () => call<{ recents: RecentProject[] }>("recent_projects"),
  chooseFolder: () => call<{ path: string | null }>("choose_folder"),
  saveDocument: (id: string, text: string, baseMtime: string | null, force = false) =>
    call<{ saved: boolean; conflict?: boolean; mtime: string; words?: number; snapshotAt?: string | null }>("save_document", id, text, baseMtime, force),
  documentMtime: (id: string) => call<{ mtime: string }>("document_mtime", id),
  linkSpans: (id: string, text: string) => call<{ spans: Span[] }>("link_spans", id, text),
  spelling: (id: string, text: string) => call<{ enabled: boolean; spans: Misspelling[] }>("spelling", id, text),
  spellingSuggestions: (word: string) => call<{ suggestions: string[] }>("spelling_suggestions", word),
  addToDictionary: (term: string, scope: "project" | "personal") => call<{ added: boolean }>("add_to_dictionary", term, scope),
  ignoreWord: (word: string) => call("ignore_word", word),
  openDictionary: () => call<{ id: string }>("open_dictionary"),
  newScene: (title: string, partId: string | null = null, nearId: string | null = null) =>
    call<{ id: string }>("new_scene", title, partId, nearId),
  renameScene: (id: string, title: string) => call<{ id: string }>("rename_scene", id, title),
  moveScene: (id: string, delta: number) => call<{ id: string; remap: Remap }>("move_scene", id, delta),
  /** Move to a part (null = top level) at a 0-based index (null = end), or to Unplaced. */
  placeScene: (id: string, partId: string | null, index: number | null = null, unplaced = false) =>
    call<{ id: string; remap: Remap }>("place_scene", id, partId, index, unplaced),
  /** Moves the scene to the Trash. */
  deleteScene: (id: string) => call("delete_scene", id),
  newPart: (title: string) => call<{ id: string }>("new_part", title),
  renamePart: (id: string, title: string) => call<{ id: string }>("rename_part", id, title),
  movePart: (id: string, delta: number) => call<{ id: string; remap: Remap }>("move_part", id, delta),
  deletePart: (id: string) => call("delete_part", id),
  listTrash: () => call<{ items: TrashItem[] }>("list_trash"),
  restoreTrash: (name: string) => call<{ id: string; unplaced: boolean }>("restore_trash", name),
  deleteForever: (name: string) => call("delete_forever", name),
  emptyTrash: () => call<{ deleted: number }>("empty_trash"),
  /** The edit (UTF-16) that rewrites the frontmatter block of the editor's text; nothing is saved here. */
  setSceneDetails: (id: string, text: string, fields: DetailsPatch) =>
    call<{ edit: { from: number; to: number; insert: string }; details: SceneDetails; bodyStart: number }>("set_scene_details", id, text, fields),
  // snapshots: `text` is the editor buffer, so unsaved words are kept and compared too
  listSnapshots: (id: string, text?: string) => call<{ items: SnapshotRow[]; words: number; snapshotAt: string | null }>("list_snapshots", id, text ?? null),
  createSnapshot: (id: string, label: string, text?: string) => call<{ id: string; snapshotAt: string }>("create_snapshot", id, label, text ?? null),
  compareSnapshot: (id: string, snapshotId: string, text?: string) =>
    call<{ segments: DiffSegment[]; added: number; removed: number }>("compare_snapshot", id, snapshotId, text ?? null),
  /** Rewrites the scene file: detach the save controller and reopen the document afterwards. */
  restoreSnapshot: (id: string, snapshotId: string, text?: string) => call<{ snapshotAt: string | null }>("restore_snapshot", id, snapshotId, text ?? null),
  deleteSnapshot: (id: string, snapshotId: string) => call<{ snapshotAt: string | null }>("delete_snapshot", id, snapshotId),
  /** Snapshots every scene as end-of-draft-N and counts up. */
  startNewDraft: () => call<{ draft: number; previous: number }>("start_new_draft"),
  snapshotAll: (label: string) => call<{ count: number }>("snapshot_all", label),
  // git sync: status is read-only; the three actions run only when the author clicks them
  syncStatus: () => call<{ sync: SyncInfo | null }>("sync_status"),
  syncCommit: (message: string) => call<{ summary: string; sync: SyncInfo | null }>("sync_commit", message),
  syncPush: () => call<{ summary: string; sync: SyncInfo | null }>("sync_push"),
  syncInit: () => call<{ sync: SyncInfo | null }>("sync_init"),
  // collections: definitions in project.toml; membership is set per scene through setSceneDetails
  createCollection: (name: string, color: CollectionColor) => call<{ collections: CollectionSummary[] }>("create_collection", name, color),
  recolorCollection: (name: string, color: CollectionColor) => call<{ collections: CollectionSummary[] }>("recolor_collection", name, color),
  /** Rewrites the member scenes' files (`changed` = their ids): flush first, reopen the open one after. */
  renameCollection: (name: string, newName: string) => call<{ collections: CollectionSummary[]; changed: string[] }>("rename_collection", name, newName),
  deleteCollection: (name: string) => call<{ collections: CollectionSummary[]; changed: string[] }>("delete_collection", name),
  setUnit: (unit: Unit) => call<{ unit: Unit }>("set_unit", unit),
  rebuildIndex: () => call("rebuild_index"),
  sceneContext: (id: string, text?: string) => call<{ mentions: SceneMention[] }>("scene_context", id, text ?? null),
  listEntities: () => call<{ entities: EntitySummary[] }>("list_entities"),
  getEntity: (name: string) => call<EntityInfo>("get_entity", name),
  createEntity: (name: string, type: EntityType) => call<{ id: string; name: string; existed: boolean }>("create_entity", name, type),
  addAlias: (name: string, alias: string) => call("add_alias", name, alias),
  // AI (every result is a suggestion the UI must confirm; nothing here edits prose)
  aiStatus: () => call<{ hasKey: boolean; models: Record<"fast" | "strong" | "writing", string> }>("ai_status"),
  usage: () => call<{ cost: number; calls: number }>("usage"),
  findAliases: (id: string, text: string) => call<{ suggestions: AliasSuggestion[]; cost: number | null }>("find_aliases", id, text),
  applyAliases: (items: { entity: string; surface: string }[]) => call<{ added: number }>("apply_aliases", items),
  checkContinuity: (id: string, text: string) => call<{ issues: Issue[]; waived: number; cost: number | null }>("check_continuity", id, text),
  waive: (key: string, id: string) => call("waive", key, id),
  restoreWaivers: (id: string) => call<{ restored: number }>("restore_waivers", id),
  proposeCanon: (id: string, text: string) => call<{ updates: CanonProposal[]; cost: number | null }>("propose_canon", id, text),
  applyCanon: (updates: { entity: string; facts: string[] }[]) => call<{ applied: number }>("apply_canon", updates),
  learnStyle: () => call<{ markdown: string; replacing: boolean; samples: number; cost: number | null }>("learn_style"),
  ensureStyle: () => call<{ id: string }>("ensure_style"),
  styleStatus: () => call<StyleStatus>("style_status"),
  saveStyle: (text: string) => call<{ id: string }>("save_style", text),
  generate: (mode: string, instruction: string, id: string, text: string, start: number, end: number) =>
    call<GenerateResult>("generate", mode, instruction, id, text, start, end),
  draftFromReply: (id: string, text: string, body: string, at: number) =>
    call<{ insert: string; from: number; to: number }>("draft_from_reply", id, text, body, at),
  registerDraft: (id: string, draftId: string, original: string) => call("register_draft", id, draftId, original),
  resolveDrafts: (id: string, text: string, accept: boolean, index: number | null = null) =>
    call<{ edits: DraftEdit[]; skipped: number; found: number }>("resolve_drafts", id, text, accept, index),
  ask: (prompt: string, scope: "scene" | "project", id: string | null, text: string | null, cursor: number,
    history: { role: string; text: string }[]) =>
    call<{ reply: string; cost: number | null }>("ask", prompt, scope, id, text, cursor, history),
  getSettings: () => call<SettingsInfo>("get_settings"),
  setSettings: (models?: Partial<Record<ModelKind, string>>, editor?: Partial<EditorPrefs>, spellcheck?: boolean, autoSnapshot?: boolean) =>
    call("set_settings", models ?? null, editor ?? null, spellcheck ?? null, autoSnapshot ?? null),
  setApiKey: (key: string) => call("set_api_key", key),
  clearApiKey: () => call<{ stillSet: boolean; note: string }>("clear_api_key"),
  listModels: (structuredOnly: boolean) => call<{ models: ModelOption[] }>("list_models", structuredOnly),
  minimize: () => call("minimize"),
  toggleMaximize: () => call("toggle_maximize"),
  close: () => call("close"),
};
