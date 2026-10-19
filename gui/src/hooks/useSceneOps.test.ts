import { describe, expect, it, vi } from "vitest";

vi.mock("../backend/api", () => ({
  api: { deletePart: vi.fn(async () => ({ ok: true, remap: {}, warning: "Some parts could not be renumbered." })) },
}));

import { useSceneOps } from "./useSceneOps";

describe("deletePart", () => {
  it("shows the renumber warning from the bridge", async () => {
    const notify = vi.fn();
    const ops = useSceneOps({
      saver: { flush: async () => true }, ws: null, doc: null, docRef: { current: null }, editorRef: { current: null },
      notify, refresh: async () => null, openDoc: async () => {}, setDoc: () => {}, setDialog: () => {},
      setExpanded: () => {}, setPartFocus: () => {}, setMentions: () => {}, focusNextOpen: () => {},
    } as never);
    await ops.deletePart("manuscript/01-a");
    expect(notify).toHaveBeenCalledWith("Some parts could not be renumbered.", "warning");
  });
});
