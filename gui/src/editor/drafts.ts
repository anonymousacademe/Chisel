// Plumbing for inserting generated text. The text itself (and the <!--ai-->
// marker format) comes from Python; this only decides *where* it lands when the
// buffer may have changed while the model was working.

export interface DraftResult { mode: "draft" | "expand" | "rewrite"; from: number; to: number; original: string | null }

/**
 * Where the generated draft goes now. `snapshot` is the buffer the request was
 * made from, `current` the buffer now, `cursor` the current cursor.
 * - draft: the original spot if nothing changed, else the cursor.
 * - rewrite/expand: the original range if its text is unchanged, else the one
 *   unique place the original text still occurs, else null (discard).
 */
export function anchorDraft(current: string, snapshot: string, r: DraftResult, cursor: number): { from: number; to: number } | null {
  if (r.mode === "draft") {
    return current === snapshot ? { from: r.from, to: r.to } : { from: cursor, to: cursor };
  }
  const original = r.original ?? "";
  if (current.slice(r.from, r.to) === original) return { from: r.from, to: r.to };
  if (!original) return null;
  const first = current.indexOf(original);
  if (first === -1 || current.indexOf(original, first + 1) !== -1) return null;
  return { from: first, to: first + original.length };
}
