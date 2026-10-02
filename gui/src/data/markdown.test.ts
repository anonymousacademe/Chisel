// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { linkFromEvent, renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders the common Markdown", () => {
    const h = renderMarkdown("# Title\n\n**bold** and *italic*\n\n- a\n- b\n\n> quote\n\n`code`");
    for (const t of ["<h1", "<strong>bold</strong>", "<em>italic</em>", "<ul>", "<li>a</li>", "<blockquote>", "<code>code</code>"]) expect(h).toContain(t);
  });
  it("never lets HTML through", () => {
    const h = renderMarkdown('<script>alert(1)</script> <img src=x onerror=alert(1)> <b onclick="x()">hi</b>\n\n<div>block</div>');
    expect(h).not.toMatch(/<(script|img|div|b)\b/i);
    expect(h).toContain("&lt;script&gt;");
  });
  it("drops javascript: links and images, keeps http links", () => {
    expect(renderMarkdown("[x](javascript:alert(1))")).not.toMatch(/javascript/i);
    expect(renderMarkdown("![pic](http://e.com/a.png)")).not.toContain("<img");
    expect(renderMarkdown("[ok](https://example.com)")).toContain('href="https://example.com"');
  });
  it("finds the link under a click", () => {
    document.body.innerHTML = renderMarkdown("[ok](https://example.com) plain");
    expect(linkFromEvent(document.querySelector("a"))).toBe("https://example.com");
    expect(linkFromEvent(document.querySelector("p"))).toBeNull();
  });
});
