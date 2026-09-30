import type { Span } from "../editor/spans";
import type {
  AliasSuggestion, CanonProposal, DocumentPayload, DraftEdit, EntityInfo, EntitySummary, EntityType, GenerateResult,
  Issue, ModelKind, ModelOption, RecentProject, SceneMention, SettingsInfo, EditorPrefs, Workspace,
} from "../data/types";
import { call } from "./transport";

/** Typed wrappers over the bridge; method names match lorewrite.gui.api.Api. */
export const api = {
  getWorkspace: () => call<{ workspace: Workspace | null }>("get_workspace"),
  readDocument: (id: string) => call<DocumentPayload>("read_document", id),
  openProject: (path: string) => call("open_project", path),
  newProject: (title: string, path: string) => call("new_project", title, path),
  recentProjects: () => call<{ recents: RecentProject[] }>("recent_projects"),
  chooseFolder: () => call<{ path: string | null }>("choose_folder"),
  saveDocument: (id: string, text: string, baseMtime: string | null, force = false) =>
    call<{ saved: boolean; conflict?: boolean; mtime: string; words?: number }>("save_document", id, text, baseMtime, force),
  documentMtime: (id: string) => call<{ mtime: string }>("document_mtime", id),
  linkSpans: (id: string, text: string) => call<{ spans: Span[] }>("link_spans", id, text),
  newScene: (title: string) => call<{ id: string }>("new_scene", title),
  renameScene: (id: string, title: string) => call<{ id: string }>("rename_scene", id, title),
  moveScene: (id: string, delta: number) => call<{ id: string }>("move_scene", id, delta),
  deleteScene: (id: string) => call("delete_scene", id),
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
  setSettings: (models?: Partial<Record<ModelKind, string>>, editor?: Partial<EditorPrefs>) => call("set_settings", models ?? null, editor ?? null),
  setApiKey: (key: string) => call("set_api_key", key),
  clearApiKey: () => call<{ stillSet: boolean; note: string }>("clear_api_key"),
  listModels: (structuredOnly: boolean) => call<{ models: ModelOption[] }>("list_models", structuredOnly),
  minimize: () => call("minimize"),
  toggleMaximize: () => call("toggle_maximize"),
  close: () => call("close"),
};
