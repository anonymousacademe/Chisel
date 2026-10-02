/** Starting points for a new Notebook note (the text itself is made in core.research.TEMPLATES). */
export type NoteTemplate = "blank" | "idea" | "location" | "timeline";

export const NOTE_TEMPLATES: { id: NoteTemplate; label: string; detail: string }[] = [
  { id: "blank", label: "Blank", detail: "just a title" },
  { id: "idea", label: "Idea", detail: "the idea, why it matters, where it could go" },
  { id: "location", label: "Location", detail: "look, people, history, scenes set here" },
  { id: "timeline", label: "Timeline", detail: "a table of when, what, where" },
];

/** One line under the Ask my notebook quick action. */
export const ASK_NOTEBOOK_HINT = "Answers from your notes, with citations";
