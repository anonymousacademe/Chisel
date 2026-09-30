export type NoteBlock =
  | { kind: "heading"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "para"; text: string };

/** Note bodies are hard-wrapped Markdown: paragraphs reflow, "- " lines become a list, "#" lines a heading. */
export function noteBlocks(body: string): NoteBlock[] {
  const blocks: NoteBlock[] = [];
  for (const raw of body.trim().split(/\n\s*\n/)) {
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
    let para: string[] = [];
    let list: string[] = [];
    const flush = () => {
      if (para.length) blocks.push({ kind: "para", text: para.join(" ") });
      if (list.length) blocks.push({ kind: "list", items: list });
      para = []; list = [];
    };
    for (const line of lines) {
      const h = /^#{1,6}\s+(.*)$/.exec(line);
      const li = /^[-*]\s+(.*)$/.exec(line);
      if (h) { flush(); blocks.push({ kind: "heading", text: h[1] }); }
      else if (li) { if (para.length) flush(); list.push(li[1]); }
      else if (list.length) list[list.length - 1] += ` ${line}`; // wrapped list item
      else para.push(line);
    }
    flush();
  }
  return blocks;
}
