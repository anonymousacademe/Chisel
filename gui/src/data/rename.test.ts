import { describe, expect, it } from "vitest";
import { aliasRenames, countTicked, defaultTicks } from "./rename";
import type { RenamePreview } from "./types";

const occ = (id: string, inDraft = false) => ({ id, kind: "mention", line: 1, pre: "", before: "Mara", after: "Nia", post: "", inDraft, defaultOn: !inDraft });
const preview: RenamePreview = {
  plan: "p", name: "Mara", newName: "Nia", aliases: [], newId: "x",
  files: [
    { file: "a.md", kind: "scene", title: "A", occurrences: [occ("1"), occ("2", true)] },
    { file: "b.md", kind: "scene", title: "B", occurrences: [occ("3")] },
  ],
};

describe("rename helpers", () => {
  it("leaves occurrences inside AI drafts unticked", () => {
    expect([...defaultTicks(preview)]).toEqual(["1", "3"]);
  });
  it("counts what is ticked", () => {
    expect(countTicked(preview.files, new Set(["1", "2"]))).toEqual({ occurrences: 2, files: 1 });
    expect(countTicked(preview.files, new Set())).toEqual({ occurrences: 0, files: 0 });
  });
  it("only changed, non-blank aliases are renames", () => {
    expect(aliasRenames({ Mara: "Nia", Em: "Em", Q: "  " })).toEqual({ Mara: "Nia" });
  });
});
