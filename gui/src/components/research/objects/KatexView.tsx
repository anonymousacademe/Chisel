import katex from "katex";
import "katex/dist/katex.min.css";
import "../../../styles/objects.css";

export type Rendered = { ok: true; html: string } | { ok: false; error: string };

/** LaTeX to HTML with KaTeX. Never throws: trust is off (no links, no \href, no raw HTML) and a parse error comes back
 *  as plain text for the author to read. Empty input is not an error. */
export function renderLatex(latex: string, display = true): Rendered {
  if (!latex.trim()) return { ok: true, html: "" };
  try {
    const html = katex.renderToString(latex, {
      displayMode: display, throwOnError: true, trust: false, strict: "ignore", maxExpand: 1000, maxSize: 50, output: "htmlAndMathml",
    });
    return { ok: true, html };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg.replace(/^KaTeX parse error:\s*/, "") };
  }
}

/** A rendered equation, or the error as text under the raw LaTeX. */
export function KatexView({ latex, display = true, label = "Equation preview" }: { latex: string; display?: boolean; label?: string }) {
  const r = renderLatex(latex, display);
  if (!r.ok) {
    return (
      <div className="lw-eq__preview is-error" aria-label={label}>
        <p className="lw-eq__error" role="alert">This LaTeX does not parse: {r.error}</p>
      </div>
    );
  }
  if (!r.html) return <div className="lw-eq__preview is-empty" aria-label={label}><span className="lw-faint">The equation appears here.</span></div>;
  // KaTeX output with trust:false contains no scripts or links.
  return <div className="lw-eq__preview" role="img" aria-label={label} dangerouslySetInnerHTML={{ __html: r.html }} />;
}
