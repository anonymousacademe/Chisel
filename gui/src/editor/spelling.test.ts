import { describe, expect, it } from "vitest";
import { EditorState } from "@codemirror/state";
import { setSpelling, spellingField } from "./cm";

// Underlines must follow the text through edits until Python's next answer arrives.
const make = () => {
  let state = EditorState.create({ doc: "I will recieve it, teh end", extensions: [spellingField] });
  state = state.update({ effects: setSpelling.of([{ start: 7, end: 14, word: "recieve" }, { start: 19, end: 22, word: "teh" }]) }).state;
  return state;
};

describe("spellingField", () => {
  it("shifts ranges when text is inserted before them", () => {
    const s = make().update({ changes: { from: 0, insert: "Oh, " } }).state;
    expect(s.field(spellingField).map((m) => [m.start, m.end])).toEqual([[11, 18], [23, 26]]);
  });

  it("keeps a range when a letter is typed inside the word", () => {
    const s = make().update({ changes: { from: 10, insert: "x" } }).state;
    expect(s.field(spellingField)[0]).toMatchObject({ start: 7, end: 15 });
  });

  it("drops a range whose word was deleted", () => {
    const s = make().update({ changes: { from: 7, to: 15 } }).state;
    expect(s.field(spellingField).map((m) => m.word)).toEqual(["teh"]);
  });

  it("is replaced wholesale by a fresh answer", () => {
    const s = make().update({ effects: setSpelling.of([]) }).state;
    expect(s.field(spellingField)).toEqual([]);
  });
});
