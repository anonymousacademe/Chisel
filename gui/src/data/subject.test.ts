import { describe, expect, it } from "vitest";
import { scopeLabel, subjectArgs, subjectOf } from "./subject";

const scene = { id: "manuscript/01-a.md", kind: "scene", title: "Arrival", kicker: "SCENE 01" };
const mara = { id: "entities/characters/mara-vale.md", kind: "entity", title: "Mara Vale", kicker: "CHARACTER" };
const place = { id: "entities/places/lower-meridian.md", kind: "entity", title: "Lower Meridian", kicker: "PLACE" };
const nb = { id: "notebook/tides.md", kind: "research", title: "Tide tables", kicker: "NOTEBOOK" };
const on = { scope: "scene" as const, removed: false, researchMode: false };

describe("subjectOf", () => {
  it("names the open item as the chip says it", () => {
    expect(subjectOf(mara, on)?.label).toBe("About: Mara Vale (character)");
    expect(subjectOf(place, on)?.label).toBe("About: Lower Meridian (place)");
    expect(subjectOf(nb, on)?.label).toBe("About: Tide tables (notebook note)");
    expect(subjectOf(scene, on)?.label).toBe("About: Arrival (scene)");
  });
  it("has none for nothing open or for files that are not subjects", () => {
    expect(subjectOf(null, on)).toBeNull();
    expect(subjectOf({ id: "style.md", kind: "style", title: "Style guide" }, on)).toBeNull();
    expect(subjectOf({ id: "dictionary.txt", kind: "dictionary", title: "Dictionary" }, on)).toBeNull();
  });
  it("is off once the author removed the chip, and in Ask-my-notebook mode", () => {
    expect(subjectOf(mara, { ...on, removed: true })).toBeNull();
    expect(subjectOf(mara, { ...on, researchMode: true })).toBeNull();
  });
  it("a scene is not a subject while the whole project is asked about, a note still is", () => {
    expect(subjectOf(scene, { ...on, scope: "project" })).toBeNull();
    expect(subjectOf(mara, { ...on, scope: "project" })?.id).toBe(mara.id);
  });
});

describe("subjectArgs: what is sent follows the chip", () => {
  it("scenes travel as doc_id, notes as subject_id", () => {
    expect(subjectArgs(scene, subjectOf(scene, on))).toEqual({ doc_id: scene.id, subject_id: null });
    expect(subjectArgs(mara, subjectOf(mara, on))).toEqual({ doc_id: null, subject_id: mara.id });
    expect(subjectArgs(nb, subjectOf(nb, on))).toEqual({ doc_id: null, subject_id: nb.id });
  });
  it("sends nothing when the chip is off or removed", () => {
    expect(subjectArgs(mara, subjectOf(mara, { ...on, removed: true }))).toEqual({ doc_id: null, subject_id: null });
    expect(subjectArgs(scene, subjectOf(scene, { ...on, removed: true }))).toEqual({ doc_id: null, subject_id: null });
    expect(subjectArgs(scene, subjectOf(scene, { ...on, scope: "project" }))).toEqual({ doc_id: null, subject_id: null });
    expect(subjectArgs(null, null)).toEqual({ doc_id: null, subject_id: null });
  });
});

describe("scopeLabel", () => {
  it("says what the assistant reads", () => {
    expect(scopeLabel("scene", subjectOf(scene, on))).toBe("Current scene");
    expect(scopeLabel("scene", subjectOf(mara, on))).toBe("Project + this note");
    expect(scopeLabel("scene", null)).toBe("Project");
    expect(scopeLabel("project", subjectOf(mara, { ...on, scope: "project" }))).toBe("Project + this note");
    expect(scopeLabel("project", subjectOf(scene, on))).toBe("Project");
  });
});
