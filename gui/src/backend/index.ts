import type { Workspace } from "../data/types";
import { mockWorkspace } from "../data/mock";

/**
 * Everything the UI needs from LoreWriter's core. Implement these three calls
 * in src-tauri/src/lib.rs (or a Python sidecar it spawns) to connect the real
 * project data; until then the mock backend is used.
 */
export interface Backend {
  getWorkspace(): Promise<Workspace>;
  saveDocument(id: string, paragraphs: string[]): Promise<void>;
  askAssistant(prompt: string, scope: string): Promise<string>;
}

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const mockBackend: Backend = {
  async getWorkspace() { return structuredClone(mockWorkspace); },
  async saveDocument() { /* in-memory only */ },
  async askAssistant(prompt) {
    await new Promise((r) => setTimeout(r, 600));
    return `(Mock backend) I'd answer “${prompt}” using the current scene and project notes once the LoreWriter core is connected.`;
  },
};

const tauriBackend: Backend = {
  async getWorkspace() {
    const { invoke } = await import("@tauri-apps/api/core");
    try { return await invoke<Workspace>("get_workspace"); }
    catch { return mockBackend.getWorkspace(); }
  },
  async saveDocument(id, paragraphs) {
    const { invoke } = await import("@tauri-apps/api/core");
    try { await invoke("save_document", { id, paragraphs }); } catch { /* not wired yet */ }
  },
  async askAssistant(prompt, scope) {
    const { invoke } = await import("@tauri-apps/api/core");
    try { return await invoke<string>("ask_assistant", { prompt, scope }); }
    catch { return mockBackend.askAssistant(prompt, scope); }
  },
};

export const backend: Backend = isTauri ? tauriBackend : mockBackend;
export { isTauri };
