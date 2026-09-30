import { describe, expect, it } from "vitest";
import { noteBlocks } from "./noteBlocks";

describe("noteBlocks", () => {
  it("reflows hard-wrapped paragraphs and splits headings and lists", () => {
    const body = "The AI construct riding\nin Rook's jack.\n\n## Canon (auto)\n\n- Runs from the jack\n  behind Rook's ear.\n- Can read logs.\n";
    expect(noteBlocks(body)).toEqual([
      { kind: "para", text: "The AI construct riding in Rook's jack." },
      { kind: "heading", text: "Canon (auto)" },
      { kind: "list", items: ["Runs from the jack behind Rook's ear.", "Can read logs."] },
    ]);
  });
  it("handles empty text", () => {
    expect(noteBlocks("  \n ")).toEqual([]);
  });
});
