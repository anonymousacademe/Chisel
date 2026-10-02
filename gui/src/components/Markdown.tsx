import { useMemo } from "react";
import { renderMarkdown, linkFromEvent } from "../data/markdown";

/** A reply rendered as Markdown. Links open only on a click, in the system browser. */
export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const html = useMemo(() => renderMarkdown(text), [text]);
  return (
    <div className={`lw-md ${className}`} dangerouslySetInnerHTML={{ __html: html }}
      onClick={(e) => {
        const href = linkFromEvent(e.target);
        if (e.target instanceof Element && e.target.closest("a")) e.preventDefault(); // never navigate the app window
        if (href) window.open(href, "_blank", "noopener,noreferrer");
      }} />
  );
}
