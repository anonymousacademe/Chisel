import { describe, expect, it } from "vitest";
import { aiRunMode, cost, failedMessage, firstScene, keptMessages, sentence } from "./appLogic";
import type { ChatMessage } from "./types";

describe("appLogic", () => {
  it("sentence-cases a kicker", () => { expect(sentence("SCENE")).toBe("Scene"); });
  it("drops error replies but keeps everything else", () => {
    const msgs: ChatMessage[] = [
      { id: "1", role: "user", text: "hi" },
      { id: "2", role: "assistant", text: "failed", error: true },
      { id: "3", role: "assistant", text: "ok" },
    ];
    expect(keptMessages(msgs).map((m) => m.id)).toEqual(["1", "3"]);
  });
  it("picks the first placed non-front-matter scene, else the first scene", () => {
    const a = { id: "a", frontMatter: true, unplaced: false };
    const b = { id: "b", frontMatter: false, unplaced: true };
    const c = { id: "c", frontMatter: false, unplaced: false };
    expect(firstScene([a, b, c])?.id).toBe("c");
    expect(firstScene([a, b])?.id).toBe("a");
    expect(firstScene([])).toBeUndefined();
    expect(firstScene(undefined)).toBeUndefined();
  });
  it("formats the AI cost suffix", () => {
    expect(cost(0.01234)).toBe(" (AI $0.0123)");
    expect(cost(null)).toBe("");
    expect(cost(undefined)).toBe("");
    expect(cost(0)).toBe(" (AI $0.0000)");
  });
  it("picks the run mode of an AI kind", () => {
    expect(aiRunMode("generate", ["ask"])).toBe("draft");
    expect(aiRunMode("ask", ["ask"])).toBe("chat");
    expect(aiRunMode("continuity", ["ask"])).toBe("strip");
  });
  it("builds failed and stopped replies as error messages", () => {
    expect(failedMessage("x", true)).toMatchObject({ error: true, stopped: true, text: "(stopped)" });
    const f = failedMessage("y", false);
    expect(f).toMatchObject({ error: true, id: "y" });
    expect("stopped" in f).toBe(false);
  });
});
