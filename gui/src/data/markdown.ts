// Assistant replies are untrusted model output. Markdown is rendered with raw HTML switched
// off (marked passes it through, so we escape it) and the result is sanitised again by DOMPurify.
import { Marked, type Tokens } from "marked";
import DOMPurify from "dompurify";

const escapeHtml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const md = new Marked({ gfm: true, breaks: true });
md.use({
  renderer: {
    // Raw HTML in the reply is shown as text, never as markup.
    html: ({ text }: Tokens.HTML | Tokens.Tag) => escapeHtml(text),
    // Images would load remote files on their own; show the alt text instead.
    image: ({ text }: Tokens.Image) => escapeHtml(text),
  },
});

const ALLOWED_TAGS = ["p", "br", "strong", "em", "del", "code", "pre", "blockquote", "ul", "ol", "li", "a",
  "h1", "h2", "h3", "h4", "h5", "h6", "hr", "table", "thead", "tbody", "tr", "th", "td"];

/** Markdown -> safe HTML. Links keep only http(s)/mailto targets and never navigate by themselves. */
export function renderMarkdown(text: string): string {
  const raw = md.parse(text, { async: false }) as string;
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS, ALLOWED_ATTR: ["href", "title"], ALLOWED_URI_REGEXP: /^(?:https?:|mailto:)/i,
  });
}

/** The link under a click inside rendered Markdown, if it is one we may open. */
export function linkFromEvent(target: EventTarget | null): string | null {
  const a = target instanceof Element ? target.closest("a[href]") : null;
  const href = a?.getAttribute("href") ?? "";
  return /^(?:https?:|mailto:)/i.test(href) ? href : null;
}
