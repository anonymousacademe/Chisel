import { describe, expect, it } from "vitest";
import { attachKey, restoreAttachments, savedToMessages } from "./chat";
import type { AttachItem } from "./types";

describe("saved chats", () => {
  it("restores messages without inventing optional fields", () => {
    const out = savedToMessages([
      { id: "1", role: "user", text: "hi" },
      { id: "2", role: "assistant", text: "yo", ideas: ["a"], error: true },
      { id: "3", role: "assistant", text: "src", sources: [{ id: "n", title: "N" }] },
    ]);
    expect(out[0]).toEqual({ id: "1", role: "user", text: "hi" });
    expect(out[1]).toEqual({ id: "2", role: "assistant", text: "yo", ideas: ["a"] });
    expect(out[2]).toEqual({ id: "3", role: "assistant", text: "src", sources: [{ id: "n", title: "N" }] });
  });
  it("keeps only attachments that still exist and reports the rest", () => {
    const item: AttachItem = { kind: "scene", id: "manuscript/a.md", title: "A", words: 10 };
    const known = new Map([[attachKey(item), item]]);
    const r = restoreAttachments([{ kind: "scene", id: "manuscript/a.md" }, { kind: "note", id: "gone" }], known);
    expect(r.attachments).toEqual([{ kind: "scene", id: "manuscript/a.md", title: "A", words: 10 }]);
    expect(r.missing).toBe(true);
    expect(restoreAttachments([], known)).toEqual({ attachments: [], missing: false });
  });
});
