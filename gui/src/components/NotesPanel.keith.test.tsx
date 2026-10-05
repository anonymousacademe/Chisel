// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { NotesPanel } from "./NotesPanel";
import type { EntityInfo } from "../data/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// the exact payload the bridge returns for the Keith note (empty body, no
// relationships, two backlinks)
const keith = {
  found: true,
  id: "entities/characters/keith.md",
  name: "Keith",
  type: "character",
  aliases: ["Keef", "K-Dawg"],
  body: "",
  canon: "",
  summary: "",
  backlinks: [
    { sourceId: "manuscript/01-opening.md", sourceKind: "scene", sourceTitle: "Opening", row: 2, line: "This is a book about [[Keith]]." },
    { sourceId: "manuscript/01-opening.md", sourceKind: "scene", sourceTitle: "Opening", row: 8, line: "Keith sleeps through it." },
  ],
  born: "",
  bornInvalid: false,
  ageNow: "",
  relationships: [],
} as unknown as EntityInfo;

describe("NotesPanel (keith regression)", () => {
  it("renders a character with an empty body and no relationships", () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    let root: Root | null = createRoot(el);
    let error: unknown = null;
    try {
      act(() => {
        root!.render(<NotesPanel note={keith} missingTarget={null} onOpenNote={() => {}}
          onAddAlias={() => {}} onSetBorn={() => {}} onSuggestRelationships={() => {}}
          onRename={() => {}} onCreateNote={() => {}} onOpenBacklink={() => {}} />);
      });
    } catch (e) {
      error = e;
    }
    expect(error).toBeNull();
    expect(el.textContent).toContain("Keith");
    act(() => { root!.unmount(); });
    root = null;
    el.remove();
  });
});
