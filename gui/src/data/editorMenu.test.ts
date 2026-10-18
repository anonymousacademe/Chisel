import { describe, expect, it } from "vitest";
import { contextActions, type MenuAction } from "./editorMenu";
import type { Span } from "../editor/spans";

const entities = [{ id: "entities/characters/keith.md", name: "Keith", type: "character" },
                  { id: "entities/places/ward-6.md", name: "Ward 6", type: "place" }];
const ids = (a: MenuAction[]) => a.map((x) => x.id);
const labels = (a: MenuAction[]) => a.map((x) => ("label" in x ? x.label : "---"));
const span = (s: Partial<Span>): Span => ({ kind: "mention", start: 0, end: 5, ...s });

describe("contextActions", () => {
  it("offers to go to the note of a known character or place", () => {
    const a = contextActions({ span: span({ entity: "Keith" }) }, entities);
    expect(a[0]).toEqual({ id: "open-note", label: "Go to note: Keith (character)", entityId: "entities/characters/keith.md" });
    expect(labels(contextActions({ span: span({ kind: "link", entity: "Ward 6" }) }, entities))[0]).toBe("Go to note: Ward 6 (place)");
  });

  it("offers to create the note a [[link]] points at", () => {
    const a = contextActions({ span: span({ kind: "unresolved", target: "Staff Room" }) }, entities);
    expect(a[0]).toEqual({ id: "create-note", label: "Create note “Staff Room”…", name: "Staff Room" });
  });

  it("offers to create a note from a plain word, but not from nothing", () => {
    expect(contextActions({ word: "Milo" }, entities)[0]).toEqual({ id: "create-note", label: "Create note from “Milo”…", name: "Milo" });
    for (const word of [undefined, "", "a", "42", "--"]) {
      expect(ids(contextActions({ word }, entities))).not.toContain("create-note");
    }
  });

  it("does not offer a go-to for a name whose note is not in the list", () => {
    expect(ids(contextActions({ span: span({ entity: "Gone" }) }, entities))).not.toContain("open-note");
  });

  it("lists selection actions and an enabled Cut / Copy for a selection", () => {
    const a = contextActions({ selection: "the night bus" }, entities);
    expect(labels(a)).toEqual(["Create note from “the night bus”…", "---", "Send selection to notebook", "Add selection to dictionary",
      "---", "Cut", "Copy", "Paste", "Select all"]);
    expect(a.filter((x) => x.id === "cut" || x.id === "copy").every((x) => !("disabled" in x && x.disabled))).toBe(true);
  });

  it("does not offer a note from a multi-line selection", () => {
    expect(ids(contextActions({ selection: "one\ntwo" }, entities))).not.toContain("create-note");
  });

  it("always offers the clipboard, with Cut and Copy disabled when nothing is selected", () => {
    const a = contextActions({}, entities);
    expect(labels(a)).toEqual(["Cut", "Copy", "Paste", "Select all"]);
    expect(a.filter((x) => x.id === "cut" || x.id === "copy").every((x) => "disabled" in x && x.disabled)).toBe(true);
  });

  it("separates the groups and never starts or ends with a separator", () => {
    for (const t of [{}, { word: "Milo" }, { selection: "x y" }, { span: span({ entity: "Keith" }), selection: "Keith" }]) {
      const a = ids(contextActions(t, entities));
      expect(a[0]).not.toBe("separator");
      expect(a[a.length - 1]).not.toBe("separator");
      expect(a.join(",")).not.toContain("separator,separator");
    }
  });

  it("shortens long names in labels", () => {
    const long = "A very long name that goes on and on and on";
    expect(labels(contextActions({ span: span({ kind: "unresolved", target: long }) }, entities))[0]).toBe(`Create note “${long.slice(0, 27)}…”…`);
  });
});
