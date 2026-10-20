import type { RestoreResult } from "../data/restoreText";
import type { Misspelling, Span } from "../editor/spans";
import type {
  AliasSuggestion, AttachItem, RenameDone, RenamePreview, RenameScope, RenameUndone, AttachKind, AttachReport, CanonProposal, ChatSummary, CollectionColor, CommentRow, SavedChat, SentReport, CollectionSummary, DiffSegment, SnapshotRow, SyncInfo, DetailsPatch, DocumentPayload, Remap, RelationshipSuggestion, SceneDetails, TrashItem, Unit, DraftEdit, EntityInfo, EntitySummary, EntityType, GenerateResult,
  InspirationImage, Issue, ModelKind, ModelOption, RecentProject, SceneMention, SettingsInfo, EditorPrefs, SprintRecord, SprintState, StatsSummary, StyleStatus, Workspace, ProjectMode,
} from "../data/types";
import type { AtmosphereInfo, KeyClass, PackRow, Prefs, Station } from "../data/atmosphere";
import type { ExportInfo, ExportOptions, ExportStatus, ExportSummary } from "../data/export";
import type { FountainImport } from "../data/script";
import type {
  DownloadStatus, EndpointCost, EngineId, KokoroStatus, OpenRouterModel, ReadOptions, ReadPlan, SpeechInfo, SpeechPrefs,
  VoiceInfo,
} from "../reader/types";
import type { ObjectInfo } from "../editor/objects";
import type { CustomRequirement, RequirementsProposal, OutlineApplied,OutlineCurrent, OutlineItem, OutlineProposal, OutlineStandard, GuidelineFile, GuidelineText, JournalProfile, RequirementsReport, ResearchKind, ResearchSettings, SourceCardInfo, SourceHit, SourceRow, SyncApplied, SyncPlan, SyncScope, ZoteroCollection, ZoteroSettings, ZoteroStatus } from "../data/research";
import { call } from "./transport";

/** AI job kinds (the AI job contract): the first four stream text, the rest answer once. */
export type AiKind = "ask" | "research" | "brainstorm" | "generate" | "continuity" | "voice" | "canon" | "aliases" | "relationships" | "outline" | "requirements" | "style" | "image" | "image_regenerate" | "describe_scene";
export const STREAMING_KINDS: readonly AiKind[] = ["ask", "research", "brainstorm", "generate"];
export type AiState = "running" | "done" | "cancelled" | "error";
export interface AiPoll {
  state: AiState;
  /** Streamed text from character offset `since`; "" for non-streaming kinds. */
  text: string;
  /** Total streamed characters so far. */
  length: number;
  elapsed: number;
  /** Exactly what the synchronous bridge method returns; only when done. */
  result?: Record<string, unknown>;
  error?: string;
  cost: number | null;
}

/** Typed wrappers over the bridge; method names match chisel.gui.api.Api. */
export const api = {
  getWorkspace: () => call<{ workspace: Workspace | null }>("get_workspace"),
  readDocument: (id: string) => call<DocumentPayload>("read_document", id),
  openProject: (path: string) => call("open_project", path),
  newProject: (title: string, path: string, mode: ProjectMode = "story", kind?: ResearchKind, journal?: string) =>
    kind === undefined ? call("new_project", title, path, mode) : call("new_project", title, path, mode, kind, journal ?? ""),
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
  deleteScene: (id: string) => call<{ remap: Remap }>("delete_scene", id),
  newPart: (title: string) => call<{ id: string }>("new_part", title),
  renamePart: (id: string, title: string) => call<{ id: string }>("rename_part", id, title),
  movePart: (id: string, delta: number) => call<{ id: string; remap: Remap }>("move_part", id, delta),
  deletePart: (id: string) => call<{ remap: Remap; warning?: string }>("delete_part", id),
  listTrash: () => call<{ items: TrashItem[] }>("list_trash"),
  restoreTrash: (name: string) => call<RestoreResult>("restore_trash", name),
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
  // export (M7): the file is written by a worker thread; poll exportStatus. Open only on a click.
  exportInfo: () => call<ExportInfo>("export_info"),
  /** Script projects: add a .fountain file's scenes (the window asks for the file; path is for the dev server). */
  /** Tab in a script scene: the line rewritten as the next (previous) element; Python holds the rules. */
  /** Read aloud: what to speak in the open document, with the editor text (python: core/reader.py). */
  readPlan: (docId: string, text: string, options: ReadOptions) => call<ReadPlan>("read_plan", docId, text, options),
  /** Read aloud voices (python: chisel/speech/, gui/speech_api.py). Network only on these clicks. */
  speechInfo: () => call<SpeechInfo>("speech_info"),
  speechSet: (prefs: Partial<SpeechPrefs>) => call<{ prefs: SpeechPrefs; endpoint: EndpointCost; openrouter: EndpointCost }>("speech_set", prefs),
  speechModels: (refresh = false) => call<{ models: OpenRouterModel[]; openrouter: EndpointCost }>("speech_models", refresh),
  speechSetKey: (key: string) => call<{ hasKey: boolean }>("speech_set_key", key),
  speechVoices: (engine: EngineId) => call<{ voices: VoiceInfo[] }>("speech_voices", engine),
  speechClip: (text: string, voice: string, rate: number, engine: EngineId) =>
    call<{ dataUrl: string; cached: boolean; chars: number; cost: number | null }>("speech_clip", text, voice, rate, engine),
  speechWarm: () => call<{ warmed: boolean }>("speech_warm"),
  speechDownloadStart: (variant: string) => call<{ job: string }>("speech_download_start", variant),
  speechDownloadStatus: (job: string) => call<DownloadStatus>("speech_download_status", job),
  speechDownloadCancel: (job: string) => call("speech_download_cancel", job),
  speechRemove: () => call<{ removed: boolean; kokoro: KokoroStatus }>("speech_remove"),
  scriptCycle: (line: string, element: string, reverse = false) => call<{ line: string }>("script_cycle", line, element, reverse),
  importFountain: (path?: string) => call<{ imported: FountainImport | null }>("import_fountain", path),
  exportSummary: (options: ExportOptions) => call<{ summary: ExportSummary }>("export_summary", options),
  exportStart: (options: ExportOptions) => call<{ job: string }>("export_start", options),
  exportStatus: (job: string) => call<ExportStatus>("export_status", job),
  exportOpen: (name: string, folder = false) => call("export_open", name, folder),
  // Research mode: Zotero settings, sync (the preview never writes) and the Sources list
  zoteroCollections: () => call<{ collections: ZoteroCollection[] }>("zotero_collections"),
  zoteroGetSettings: () => call<ZoteroSettings>("zotero_get_settings"),
  zoteroSetSettings: (userId: string, webBase: string, local: boolean, localBase: string, file: string) =>
    call<ZoteroSettings>("zotero_set_settings", userId, webBase, local, localBase, file),
  zoteroSetKey: (key: string) => call<{ keySet: boolean }>("zotero_set_key", key),
  zoteroClearKey: () => call<{ keySet: boolean }>("zotero_clear_key"),
  zoteroStatus: () => call<ZoteroStatus>("zotero_status"),
  zoteroSavedCollections: () => call<{ keys: string[] }>("zotero_saved_collections"),
  zoteroSyncPlan: (scope: SyncScope = {}) => call<SyncPlan>("zotero_sync_plan", scope),
  zoteroSyncApply: (ticked: string[], token: string) => call<SyncApplied>("zotero_sync_apply", ticked, token),
  listSources: () => call<{ sources: SourceRow[] }>("list_sources"),
  searchSources: (query: string, limit = 30) => call<{ sources: SourceHit[] }>("search_sources", query, limit),
  /** Editor widgets (figures, tables, equations): one entry per id; a bad id is an entry with `error`. */
  objectRender: (ids: string[], images = true) => call<{ objects: ObjectInfo[] }>("object_render", ids, images),
  objectImage: (label: string) => call<{ label: string; dataUrl: string }>("object_image", label),
  sourceCard: (id: string) => call<SourceCardInfo>("source_card", id),
  zoteroItemCollections: (id: string) => call<{ collections: string[] }>("zotero_item_collections", id),
  openInZotero: (id: string) => call("open_in_zotero", id),
  // Research mode: journal profile, requirements check, guideline files
  researchProfiles: () => call<{ profiles: JournalProfile[] }>("research_profiles"),
  researchGetSettings: () => call<ResearchSettings>("research_get_settings"),
  researchSetSettings: (kind: ResearchKind, journal: string) => call<ResearchSettings>("research_set_settings", kind, journal),
  researchRequirements: () => call<RequirementsReport>("research_requirements"),
  guidelinesList: () => call<{ files: GuidelineFile[] }>("guidelines_list"),
  guidelinesAdd: () => call<{ added: string[]; skipped: { name: string; reason: string }[] }>("guidelines_add"),
  guidelinesAddText: (title: string, text: string) => call<{ name: string }>("guidelines_add_text", title, text),
  guidelinesRead: (name: string, limit = 20000) => call<GuidelineText>("guidelines_read", name, limit),
  guidelinesRemove: (name: string) => call("guidelines_remove", name),
  // Outline assistant: the scope paragraph, the current outline, the standard structure (no AI) and apply (ticked items only).
  // outline_suggest runs as an AI job (aiStart kind "outline"); the direct call is the same method run synchronously.
  outlineGetScope: () => call<{ text: string }>("outline_get_scope"),
  outlineSetScope: (text: string) => call("outline_set_scope", text),
  outlineCurrent: () => call<OutlineCurrent>("outline_current"),
  outlineStandard: () => call<OutlineStandard>("outline_standard"),
  outlineSuggest: (instruction: string, guidelines: string[]) => call<OutlineProposal>("outline_suggest", instruction, guidelines),
  outlineApply: (items: OutlineItem[]) => call<OutlineApplied>("outline_apply", items),
  // Custom requirements (requirements.toml). requirements_suggest runs as an AI job (aiStart kind "requirements") and never changes a file.
  requirementsCustom: () => call<{ rows: CustomRequirement[]; warning?: string }>("requirements_custom"),
  requirementsSave: (rows: CustomRequirement[]) => call<{ rows: CustomRequirement[] }>("requirements_save", rows),
  requirementsRemove: (id: string) => call<{ rows: CustomRequirement[] }>("requirements_remove", id),
  requirementsSuggest: (instruction: string, guidelines: string[]) => call<RequirementsProposal>("requirements_suggest", instruction, guidelines),
  // Notebook notes (notebook/; "research" internally): plain Markdown, never indexed
  newResearchNote: (title: string, template = "") => call<{ id: string }>("new_research_note", title, template),
  /** Copies the selected passage into notebook/clippings.md (the scene is not changed). */
  sendToNotebook: (text: string, id = "") => call<{ id: string }>("send_to_notebook", text, id),
  newResearchFromUrl: (url: string, title = "") => call<{ id: string; title: string }>("new_research_from_url", url, title),
  deleteResearchNote: (id: string) => call("delete_research_note", id),
  /** Ask my notebook: answer from the notebook notes + canon; `sources` are the notes it was given, in citation order. */
  research: (prompt: string, history: { role: string; text: string }[], attachments: { kind: AttachKind; id: string }[] = []) =>
    call<{ reply: string; sources: { id: string; title: string; score: number }[]; attached: AttachReport[]; cost: number | null; sent: SentReport }>("research", prompt, history, attachments),
  // comments: notes beside the scene (.comments/), positioned against the editor's text
  listComments: (id: string, text: string) => call<{ comments: CommentRow[] }>("list_comments", id, text),
  addComment: (id: string, text: string, start: number, end: number, body: string) =>
    call<{ id: string; comments: CommentRow[] }>("add_comment", id, text, start, end, body),
  editComment: (id: string, commentId: string, body: string, text: string) =>
    call<{ comments: CommentRow[] }>("edit_comment", id, commentId, body, text),
  resolveComment: (id: string, commentId: string, resolved: boolean, text: string) =>
    call<{ comments: CommentRow[] }>("resolve_comment", id, commentId, resolved, text),
  deleteComment: (id: string, commentId: string, text: string) =>
    call<{ comments: CommentRow[] }>("delete_comment", id, commentId, text),
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
  getEntity: (name: string, sceneId?: string) => call<EntityInfo>("get_entity", name, sceneId ?? null),
  setEntityBorn: (name: string, born: string) => call<{ born: string; invalid: boolean }>("set_entity_born", name, born),
  checkStoryTime: (text: string) => call<{ valid: boolean; normalized: string }>("check_story_time", text),
  createEntity: (name: string, type: EntityType) => call<{ id: string; name: string; existed: boolean }>("create_entity", name, type),
  addAlias: (name: string, alias: string) => call("add_alias", name, alias),
  // rename a note everywhere: preview writes nothing; apply snapshots every scene first; undo restores
  renamePreview: (name: string, newName: string, keepOld: boolean, renameAliases: Record<string, string>, scope: RenameScope[]) =>
    call<RenamePreview>("rename_preview", name, newName, keepOld, renameAliases, scope),
  renameApply: (plan: string, accepted: string[]) => call<RenameDone>("rename_apply", plan, accepted),
  renameUndo: (undoId: string) => call<RenameUndone>("rename_undo", undoId),
  // AI jobs: `args` are the keyword arguments of the synchronous method for that kind (snake_case)
  aiStart: (kind: AiKind, args: Record<string, unknown>) => call<{ job: string }>("ai_start", kind, args),
  aiPoll: (job: string, since = 0) => call<AiPoll>("ai_poll", job, since),
  aiCancel: (job: string) => call<{ state: "cancelled" }>("ai_cancel", job),
  // AI (every result is a suggestion the UI must confirm; nothing here edits prose)
  aiStatus: () => call<{ hasKey: boolean; models: Record<ModelKind, string> }>("ai_status"),
  usage: () => call<{ cost: number; calls: number }>("usage"),
  findAliases: (id: string, text: string) => call<{ suggestions: AliasSuggestion[]; cost: number | null; sent: SentReport }>("find_aliases", id, text),
  applyAliases: (items: { entity: string; surface: string }[]) => call<{ added: number }>("apply_aliases", items),
  suggestRelationships: (name: string) => call<{ suggestions: RelationshipSuggestion[]; cost: number | null; sent: SentReport }>("suggest_relationships", name),
  applyRelationships: (name: string, items: { target: string; label: string }[]) => call<{ applied: number }>("apply_relationships", name, items),
  checkContinuity: (id: string, text: string) => call<{ issues: Issue[]; waived: number; cost: number | null; sent: SentReport }>("check_continuity", id, text),
  waive: (key: string, id: string) => call("waive", key, id),
  restoreWaivers: (id: string) => call<{ restored: number }>("restore_waivers", id),
  proposeCanon: (id: string, text: string) => call<{ updates: CanonProposal[]; cost: number | null; sent: SentReport }>("propose_canon", id, text),
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
  /** `subjectId`: the open item (character / place / object note, notebook note) the question is about; null = none. */
  ask: (prompt: string, scope: "scene" | "project", id: string | null, text: string | null, cursor: number,
    history: { role: string; text: string }[], attachments: { kind: AttachKind; id: string }[] = [], subjectId: string | null = null) =>
    call<{ reply: string; attached: AttachReport[]; cost: number | null; sent: SentReport }>("ask", prompt, scope, id, text, cursor, history, attachments, subjectId),
  // saved conversations and attachments (.assistant/chats/)
  listAttachable: () => call<{ items: AttachItem[]; maxWords: number; maxItems: number }>("list_attachable"),
  listChats: () => call<{ chats: ChatSummary[] }>("list_chats"),
  openChat: (id: string) => call<{ chat: SavedChat }>("open_chat", id),
  /** Stores the conversation exactly as the client has it; a null id makes a new chat. */
  saveChat: (id: string | null, messages: unknown[], scope: "scene" | "project", attachments: { kind: AttachKind; id: string }[]) =>
    call<{ id: string; title: string }>("save_chat", id, messages, scope, attachments),
  renameChat: (id: string, title: string) => call<{ chats: ChatSummary[] }>("rename_chat", id, title),
  deleteChat: (id: string) => call<{ chats: ChatSummary[] }>("delete_chat", id),
  /** Appends the reply, with the date and the prompt, to notebook/assistant-notes.md. */
  saveReplyToNotes: (prompt: string, reply: string) => call<{ id: string }>("save_reply_to_notes", prompt, reply),
  /** Brainstorm: 3-5 "unstuck" ideas for the open scene (null: the whole project); chat text only. */
  brainstorm: (docId: string | null, text: string | null, cursor: number, attachments: { kind: AttachKind; id: string }[] = [], subjectId: string | null = null) =>
    call<{ reply: string; ideas: string[]; attached: AttachReport[]; cost: number | null; sent: SentReport }>("brainstorm", docId, text, cursor, attachments, subjectId),
  // inspiration pictures (inspiration/): reference only, never inserted into prose; generating costs money
  /** Every picture; with `docId` (any document) `mine` lists the ids of the pictures made for it. */
  listInspiration: (docId?: string) => call<{ images: InspirationImage[]; model: string; style: string; mine?: string[] }>("list_inspiration", docId ?? null),
  /** Add a picture of the author's own (a data URL; JPG, PNG or WebP up to 10 MB), optionally for an item. Nothing is sent to an AI. */
  uploadInspiration: (name: string, dataUrl: string, docId: string | null) =>
    call<{ image: InspirationImage }>("upload_inspiration", name, dataUrl, docId),
  /** The picture as a data URL (files inside inspiration/ only). */
  inspirationImage: (id: string) => call<{ dataUrl: string }>("inspiration_image", id),
  /** "Describe this": a visual prompt from the passage around the cursor (scene) or the note's text; nothing is generated. */
  describeScene: (id: string, text: string, cursor: number) => call<{ prompt: string; model: string; cost: number | null }>("describe_scene", id, text, cursor),
  generateInspiration: (prompt: string, docId: string | null, pin: boolean) =>
    call<{ images: InspirationImage[]; cost: number | null }>("generate_inspiration", prompt, docId, pin),
  regenerateInspiration: (id: string) => call<{ images: InspirationImage[]; cost: number | null }>("regenerate_inspiration", id),
  updateInspiration: (id: string, fields: { pinned?: boolean; for?: string; title?: string; notes?: string }) =>
    call<{ image: InspirationImage }>("update_inspiration", id, fields),
  /** Moves the picture to the Trash. */
  deleteInspiration: (id: string) => call("delete_inspiration", id),
  revealInspiration: (id: string) => call<{ path: string; opened: boolean }>("reveal_inspiration", id),
  // atmosphere: typing sounds and ambience (user data dir + user settings, never the project)
  getAtmosphere: () => call<AtmosphereInfo>("get_atmosphere"),
  setAtmosphere: (prefs: Prefs) => call<{ prefs: Prefs }>("set_atmosphere", prefs),
  setStations: (stations: { name: string; url: string }[] | null) => call<{ stations: Station[] }>("set_stations", stations),
  /** A custom pack's sounds as data URLs by key class (files inside sounds/<pack>/ only). */
  soundPack: (pack: string) => call<{ id: string; name: string; volume: number; sounds: Partial<Record<KeyClass, string[]>> }>("sound_pack", pack),
  ambienceLoop: (name: string) => call<{ dataUrl: string }>("ambience_loop", name),
  /** Native file dialog; `imported` is null when the author cancels. */
  importSoundPack: () => call<{ imported: { id: string; files: number } | null; packs: PackRow[] }>("import_sound_pack"),
  exportSoundPack: (pack: string) => call<{ path: string | null }>("export_sound_pack", pack),
  openSoundsFolder: (which: "sounds" | "ambience") => call<{ path: string; opened: boolean }>("open_sounds_folder", which),
  getSettings: () => call<SettingsInfo>("get_settings"),
  setSettings: (models?: Partial<Record<ModelKind, string>>, editor?: Partial<EditorPrefs>, spellcheck?: boolean, autoSnapshot?: boolean, dailyTarget?: number, imageStyle?: string, localBaseUrl?: string) =>
    call("set_settings", models ?? null, editor ?? null, spellcheck ?? null, autoSnapshot ?? null, dailyTarget ?? null, imageStyle ?? null, localBaseUrl ?? null),
  getProjectInfo: () => call<{ author: string; pen_name: string; subtitle: string; copyright: string; contact: string; language: string }>("get_project_info"),
  setProjectInfo: (author: string, pen_name: string, subtitle: string, copyright_: string, contact: string, language: string) =>
    call("set_project_info", author, pen_name, subtitle, copyright_, contact, language),
  /** Session stats page data; stats live in the user state dir, not the project. */
  statsSummary: () => call<{ stats: StatsSummary }>("stats_summary"),
  /** Focus sprint: start (1-240 minutes) / end (the words written are recorded in today's stats). */
  sprintStart: (minutes: number) => call<{ sprint: SprintState }>("sprint_start", minutes),
  sprintEnd: (cancelled = false) => call<{ sprint: SprintRecord }>("sprint_end", cancelled),
  /** The author is typing (active-time ping, throttled by the caller). */
  statsTouch: () => call("stats_touch"),
  setApiKey: (key: string) => call("set_api_key", key),
  clearApiKey: () => call<{ stillSet: boolean; note: string }>("clear_api_key"),
  listModels: (structuredOnly: boolean, modality?: "image") => call<{ models: ModelOption[] }>("list_models", structuredOnly, modality ?? null),
  /** Models installed on the author's own OpenAI-compatible server (Ollama by default). */
  listLocalModels: (baseUrl = "") => call<{ models: ModelOption[]; baseUrl: string }>("list_local_models", baseUrl),
  /** Opens a link in the system browser (http/https/mailto only; call it only from a click). */
  openExternal: (url: string) => call("open_external", url),
  minimize: () => call("minimize"),
  toggleMaximize: () => call("toggle_maximize"),
  close: () => call("close"),
  /** Windows only: drag the frameless window with the native move loop. */
  beginWindowDrag: () => call("begin_window_drag"),
};
