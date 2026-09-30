import type { Workspace } from "../data/types";
import { mockWorkspace } from "../data/mock";
import { call, getTransport, initTransport } from "./transport";

/**
 * Everything the UI needs from LoreWriter's core. With a core (pywebview or
 * the devserver) calls go to lorewrite.gui.api.Api; without one (npm run dev)
 * the mock backend answers from in-memory sample data.
 */
export interface Backend {
  getWorkspace(): Promise<Workspace>;
  saveDocument(id: string, paragraphs: string[]): Promise<void>;
  askAssistant(prompt: string, scope: string): Promise<string>;
}

const mockBackend: Backend = {
  async getWorkspace() { return structuredClone(mockWorkspace); },
  async saveDocument() { /* in-memory only */ },
  async askAssistant(prompt) {
    await new Promise((r) => setTimeout(r, 600));
    return `(Mock backend) I'd answer \u201c${prompt}\u201d using the current scene and project notes once the LoreWriter core is connected.`;
  },
};

// Phase 0: the core has no project data yet, so the real transports still
// serve the mock workspace. Replaced by real adapters in phase 1.
export const backend: Backend = mockBackend;

export const windowAction = async (action: "close" | "minimize" | "toggle_maximize") => {
  if (getTransport() === "pywebview") await call(action);
};
export { initTransport, getTransport };
