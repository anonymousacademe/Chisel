// Brainstorm about a selected passage: how the passage is shown in the chip and in the chat. Python builds the
// request (Api.brainstorm with focus / direction); this is wording only.
import type { BrainFocus } from "./types";

/** The passage on one line, cut at a word near *max* characters ("…" when cut). */
export function focusExcerpt(text: string, max = 60): string {
  const one = text.replace(/\s+/g, " ").trim();
  if (one.length <= max) return one;
  const cut = one.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,.;:!?-]+$/, "")}…`;
}

/** The author's side of the chat for a focused Brainstorm. */
export function focusPrompt(f: Pick<BrainFocus, "text" | "direction">): string {
  const about = `Brainstorm about “${focusExcerpt(f.text)}”`;
  return f.direction.trim() ? `${about}: ${f.direction.trim()}` : about;
}
