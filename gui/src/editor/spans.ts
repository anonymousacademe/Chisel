// Spans come from Python (lorewrite.core.spans) in UTF-16 offsets. This file
// only maps them to editor decorations; it never decides what a mention is.

export type SpanKind = "mention" | "link" | "unresolved" | "pending" | "expand";

export interface Span {
  kind: SpanKind;
  start: number;
  end: number;
  target?: string;
  entity?: string;
  etype?: string;
  innerStart?: number;   // links: the visible part (display text, else the name)
  innerEnd?: number;
  bodyStart?: number;    // pending drafts: text between the markers
  bodyEnd?: number;
  id?: string | null;
  instruction?: string;
}

/** A misspelled word from Python (lorewrite.core.spelling), UTF-16 offsets. */
export interface Misspelling { start: number; end: number; word: string }

/** The misspelling containing *pos* (edges count: a click at the end of a word). */
export function misspellingAt(list: Misspelling[], pos: number): Misspelling | undefined {
  return list.find((m) => pos >= m.start && pos <= m.end);
}

/** The first misspelling starting after *pos*, wrapping to the first; undefined when there are none. */
export function nextMisspelling(list: Misspelling[], pos: number): Misspelling | undefined {
  const sorted = [...list].sort((a, b) => a.start - b.start);
  return sorted.find((m) => m.start > pos) ?? sorted[0];
}

/** Decoration specs for misspellings: a class only, clamped to the document. */
export function misspellSpecs(list: Misspelling[], docLength: number): Spec[] {
  return list
    .filter((m) => m.start >= 0 && m.end <= docLength && m.start < m.end)
    .map((m) => ({ from: m.start, to: m.end, type: "mark" as const, cls: "lw-misspelled" }));
}

/** A decoration to draw: either style a range or hide it. */
export interface Spec {
  from: number;
  to: number;
  type: "mark" | "hide";
  cls?: string;
  attrs?: Record<string, string>;
}

/**
 * Decoration specs for spans. *head* is the cursor position: a link that
 * contains it shows its brackets (Obsidian live preview); all others hide
 * `[[`, `Name|` and `]]`. Pending-draft markers are always hidden.
 */
export function specsFor(spans: Span[], head: number, docLength: number): Spec[] {
  const out: Spec[] = [];
  const ok = (a: number, b: number) => a >= 0 && b <= docLength && a <= b;
  for (const s of spans) {
    if (!ok(s.start, s.end)) continue;
    switch (s.kind) {
      case "mention":
        out.push({ from: s.start, to: s.end, type: "mark", cls: "lw-mention", attrs: { "data-entity": s.entity ?? "" } });
        break;
      case "link":
      case "unresolved": {
        const cls = s.kind === "link" ? "lw-link-span" : "lw-link-span lw-link-span--unresolved";
        const a = s.innerStart ?? s.start, b = s.innerEnd ?? s.end;
        if (!ok(a, b) || a < s.start || b > s.end) break;
        const attrs = { "data-entity": s.entity ?? "", "data-target": s.target ?? "" };
        if (head >= s.start && head <= s.end) {
          // cursor inside: show the raw brackets, dimmed
          if (s.start < a) out.push({ from: s.start, to: a, type: "mark", cls: "lw-bracket" });
          if (b < s.end) out.push({ from: b, to: s.end, type: "mark", cls: "lw-bracket" });
        } else {
          if (s.start < a) out.push({ from: s.start, to: a, type: "hide" });
          if (b < s.end) out.push({ from: b, to: s.end, type: "hide" });
        }
        if (a < b) out.push({ from: a, to: b, type: "mark", cls, attrs });
        break;
      }
      case "pending": {
        const a = s.bodyStart ?? s.start, b = s.bodyEnd ?? s.end;
        if (!ok(a, b) || a < s.start || b > s.end) break;
        if (s.start < a) out.push({ from: s.start, to: a, type: "hide" });
        if (b < s.end) out.push({ from: b, to: s.end, type: "hide" });
        if (a < b) out.push({ from: a, to: b, type: "mark", cls: "lw-draft", attrs: { "data-draft": s.id ?? "" } });
        break;
      }
      case "expand":
        out.push({ from: s.start, to: s.end, type: "mark", cls: "lw-expand" });
        break;
    }
  }
  return out;
}

/** The pending draft containing *pos* (edges count), for f7/f8 and the inline widget. */
export function pendingAt(spans: Span[], pos: number): Span | undefined {
  return spans.find((s) => s.kind === "pending" && pos >= s.start && pos <= s.end);
}

/** A title line: the first non-blank line, if it is a "# " heading. Returns its [from, to) in *text*. */
export function titleLine(text: string): { from: number; to: number; prefix: number } | null {
  let pos = 0;
  for (;;) {
    const nl = text.indexOf("\n", pos);
    const end = nl === -1 ? text.length : nl;
    const line = text.slice(pos, end);
    if (line.trim() === "") {
      if (nl === -1) return null;
      pos = nl + 1;
      continue;
    }
    return line.startsWith("# ") ? { from: pos, to: end, prefix: 2 } : null;
  }
}

/** Line range [from, to] of a YAML frontmatter block at the top of an entity note, or null. */
export function frontmatterRange(text: string): { from: number; to: number } | null {
  const m = /^---\n[\s\S]*?\n---(?:\n|$)/.exec(text);
  return m ? { from: 0, to: m[0].length } : null;
}

const BLOCK_START = /^(#{1,6}\s|>|[-*+]\s|\d+[.)]\s|```|~~~|---|\|)/;

/**
 * Offsets of single newlines inside a paragraph. Hard-wrapped Markdown (the
 * terminal app's files, other editors) is shown reflowed: these newlines are
 * drawn as a space, the file is never changed. Blank lines, headings, quotes,
 * lists, fences, and lines ending in two spaces (a Markdown hard break) stay
 * separate. *skip* is a range to leave alone (frontmatter).
 */
export function softBreaks(text: string, skip?: { from: number; to: number } | null): number[] {
  const out: number[] = [];
  const lines = text.split("\n");
  let pos = 0;
  for (let i = 0; i < lines.length - 1; i++) {
    const cur = lines[i], next = lines[i + 1];
    const nl = pos + cur.length;
    const skipped = skip && nl >= skip.from && nl < skip.to;
    if (!skipped && cur.trim() && next.trim() && !BLOCK_START.test(cur) && !BLOCK_START.test(next) && !cur.endsWith("  ")) {
      out.push(nl);
    }
    pos = nl + 1;
  }
  return out;
}
