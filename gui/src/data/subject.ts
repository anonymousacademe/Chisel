/**
 * The *subject* of an assistant question: the item open in the left menu (a character / place / object
 * note, a notebook note or a scene). It rides along automatically; the author sees it as a chip in the
 * chat header and can remove it for the current chat. Pure helpers: Python builds the actual context.
 */
export interface OpenItem { id: string; kind: string; title: string; kicker?: string }

export interface Subject {
  id: string;
  kind: "scene" | "entity" | "research";
  /** "About: Mara Vale (character)". */
  label: string;
}

const NOUN: Record<string, string> = { scene: "scene", research: "notebook note" };

/**
 * The subject for the open item, or null when none is sent: nothing open, a file that is not a subject
 * (style guide, dictionary), the chip removed, Ask-my-notebook mode (it answers from the notes), or a scene
 * while the whole project is asked about (no scene text goes then).
 */
export function subjectOf(doc: OpenItem | null | undefined, opts: { scope: "scene" | "project"; removed: boolean; researchMode: boolean }): Subject | null {
  if (!doc || opts.removed || opts.researchMode) return null;
  if (doc.kind !== "scene" && doc.kind !== "entity" && doc.kind !== "research") return null;
  if (doc.kind === "scene" && opts.scope === "project") return null;
  const noun = doc.kind === "entity" ? (doc.kicker ?? "note").toLowerCase() : NOUN[doc.kind];
  return { id: doc.id, kind: doc.kind, label: `About: ${doc.title} (${noun})` };
}

/**
 * What goes over the bridge: scenes keep travelling as `doc_id` (the scene context, with the editor text);
 * notes travel as `subject_id`, which the core appends to the project context.
 */
export function subjectArgs(doc: OpenItem | null | undefined, subject: Subject | null): { doc_id: string | null; subject_id: string | null } {
  const scene = !!doc && doc.kind === "scene" && subject?.kind === "scene";
  return { doc_id: scene ? doc!.id : null, subject_id: subject && subject.kind !== "scene" ? subject.id : null };
}

/** The scope control's label: what the assistant reads right now. */
export function scopeLabel(scope: "scene" | "project", subject: Subject | null): string {
  if (!subject) return "Project";
  if (subject.kind !== "scene") return "Project + this note";   // a note joins the project context in either scope
  return scope === "scene" ? "Current scene" : "Project";
}
