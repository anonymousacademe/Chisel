// Live-preview Markdown: which syntax marks (`**`, `*`, backticks, `#`, `>`, `-`) to hide.
// Spans come from the Lezer Markdown tree (never a regex); this only decides, per mark,
// whether it is hidden (cursor away) or dimmed (cursor inside or touching its span).
// Display only: no offset moves, so spell check, mentions and comments are unaffected.
import type { Tree } from "@lezer/common";

export interface FormatSpec {
  from: number;
  to: number;
  type: "hide" | "mark" | "line";
  cls?: string;
}

const INLINE = new Set(["StrongEmphasis", "Emphasis", "InlineCode"]);

export interface FormatOptions {
  /** Start of the scene's title line: its "# " is handled by the title block. */
  titleFrom?: number | null;
  /** Block rendering (style guide): quotes without ">", bullets as dots. */
  blocks?: boolean;
}

/** Specs for the marks of *tree* over *text*; *head* is the cursor offset. */
export function formatSpecs(tree: Tree, text: string, head: number, opts: FormatOptions = {}): FormatSpec[] {
  const out: FormatSpec[] = [];
  const lineBounds = (pos: number) => {
    const a = text.lastIndexOf("\n", pos - 1) + 1;
    const b = text.indexOf("\n", pos);
    return { from: a, to: b === -1 ? text.length : b };
  };
  const onLine = (pos: number) => { const l = lineBounds(pos); return head >= l.from && head <= l.to; };
  // a mark plus the single space that follows it ("## ", "> ", "- ")
  const withSpace = (to: number) => (text[to] === " " ? to + 1 : to);

  tree.iterate({
    enter(node) {
      const name = node.name;
      if (name === "EmphasisMark" || name === "CodeMark") {
        const parent = node.node.parent;
        if (!parent || !INLINE.has(parent.name)) return;
        const near = head >= parent.from && head <= parent.to;
        out.push(near ? { from: node.from, to: node.to, type: "mark", cls: "lw-syn" } : { from: node.from, to: node.to, type: "hide" });
      } else if (name === "HeaderMark") {
        if (opts.titleFrom != null && node.from === opts.titleFrom) return;
        const to = withSpace(node.to);
        out.push(onLine(node.from) ? { from: node.from, to: node.to, type: "mark", cls: "lw-syn" } : { from: node.from, to: to, type: "hide" });
      } else if (name === "QuoteMark") {
        const to = withSpace(node.to);
        if (!opts.blocks || onLine(node.from)) out.push({ from: node.from, to: node.to, type: "mark", cls: "lw-syn" });
        else out.push({ from: node.from, to, type: "hide" });
      } else if (opts.blocks && name === "ListMark" && node.node.parent?.parent?.name === "BulletList") {
        const l = lineBounds(node.from);
        out.push({ from: l.from, to: l.from, type: "line", cls: "lw-li" });
        if (onLine(node.from)) out.push({ from: node.from, to: node.to, type: "mark", cls: "lw-syn" });
        else out.push({ from: node.from, to: withSpace(node.to), type: "hide" });
      }
    },
  });
  return out;
}
