"""Zotero note HTML -> Markdown, with hostile HTML stripped (plan 5.2, 10).

Pulled HTML is untrusted. Only a small set of tags is turned into Markdown; scripts, frames, objects and
styles are dropped together with their content; every other tag is unwrapped (its text is kept). Text is
escaped so it cannot become a ``[[wiki-link]]``, a ``[@citation]``, math, raw HTML or an AI-draft marker.
Only http, https and mailto links survive.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote

_DROP = {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "canvas", "head",
         "title", "frame", "frameset", "applet", "link", "meta", "base", "math", "audio", "video"}
_VOID = {"br", "hr", "img", "input", "area", "col", "wbr", "source", "track", "meta", "link", "base",
         "param", "embed"}
_BLOCK = {"p", "div", "li", "ul", "ol", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "tr",
          "table", "hr", "br"}
_SAFE_SCHEMES = ("http://", "https://", "mailto:")


class _Node:
    __slots__ = ("tag", "attrs", "kids")

    def __init__(self, tag: str, attrs: dict | None = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.kids: list = []


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.stack = [self.root]
        self.dropping = 0  # depth inside a dropped element

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.dropping:
            if tag in _DROP and tag not in _VOID:
                self.dropping += 1
            return
        if tag in _DROP:
            if tag not in _VOID:
                self.dropping = 1
            return
        node = _Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].kids.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self.dropping or tag in _DROP:
            return
        self.stack[-1].kids.append(_Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.dropping:
            if tag in _DROP:
                self.dropping -= 1
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not self.dropping:
            self.stack[-1].kids.append(data)


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\")
    for ch in "*_`[]<>$|~":
        text = text.replace(ch, "\\" + ch)
    return text


def _line_start_escape(line: str) -> str:
    s = line.lstrip(" ")
    pad = line[: len(line) - len(s)]
    m = re.match(r"(\d+)([.)])\s", s)
    if m:   # an ordered-list marker: the backslash goes before the delimiter ("1\. step"); before a digit it would print
        s = m.group(1) + "\\" + s[len(m.group(1)):]
    elif re.match(r"(#{1,6}\s|[-+]\s|={3,}|-{3,})", s):
        s = "\\" + s
    return pad + s


def _safe_url(url: str) -> str | None:
    url = (url or "").strip()
    compact = re.sub(r"[\x00-\x20]", "", url).lower()
    if not compact.startswith(_SAFE_SCHEMES):
        return None
    return quote(url, safe=":/?#[]@!$&'*+,;=%-._~").replace("(", "%28").replace(")", "%29")


def _plain(node) -> str:
    if isinstance(node, str):
        return node
    return "".join(_plain(k) for k in node.kids)


def _inline(nodes, *, pre: bool = False) -> str:
    out: list[str] = []
    for n in nodes:
        if isinstance(n, str):
            out.append(_escape(n if pre else re.sub(r"\s+", " ", n)))
            continue
        t = n.tag
        if t == "br":
            out.append("\n")
        elif t in ("strong", "b"):
            inner = _inline(n.kids).strip()
            out.append(f"**{inner}**" if inner else "")
        elif t in ("em", "i"):
            inner = _inline(n.kids).strip()
            out.append(f"*{inner}*" if inner else "")
        elif t == "code":
            raw = _plain(n)
            out.append("`" + raw.replace("`", "'") + "`" if raw.strip() else "")
        elif t == "a":
            inner = _inline(n.kids).strip()
            url = _safe_url(n.attrs.get("href", ""))
            out.append(f"[{inner}]({url})" if url and inner else inner)
        elif t == "img":
            out.append(_escape(n.attrs.get("alt", "").strip()))
        else:  # block tags met inside inline context, and unknown tags: keep the text
            out.append(_inline(n.kids, pre=pre))
    return "".join(out)


def _wrap_ul(li: _Node) -> _Node:
    ul = _Node("ul")
    ul.kids.append(li)
    return ul


def _blocks(nodes) -> list[str]:
    """Render children to a list of Markdown blocks (paragraphs, lists, quotes, code)."""
    blocks: list[str] = []
    buf: list = []

    def flush():
        if not buf:
            return
        text = _inline(buf)
        buf.clear()
        for part in re.split(r"\n{2,}", text):
            lines = [_line_start_escape(re.sub(r"[ \t]+", " ", ln).strip()) for ln in part.split("\n")]
            para = "  \n".join(ln for ln in lines if ln)
            if para.strip():
                blocks.append(para)

    for n in nodes:
        if isinstance(n, str) or n.tag not in _BLOCK:
            buf.append(n)
            continue
        t = n.tag
        if t == "br":
            buf.append(n)
            continue
        flush()
        if t in ("ul", "ol"):
            blocks.append(_list(n))
        elif t == "li":  # stray item outside a list
            blocks.append(_list(_wrap_ul(n)))
        elif t == "blockquote":
            inner = "\n\n".join(_blocks(n.kids))
            if inner.strip():
                blocks.append("\n".join("> " + ln if ln else ">" for ln in inner.split("\n")))
        elif t == "pre":
            code = _plain(n).strip("\n").replace("```", "'''")
            if code.strip():
                blocks.append("```\n" + code + "\n```")
        elif len(t) == 2 and t[0] == "h" and t[1].isdigit():
            text = _inline(n.kids).strip().replace("\n", " ")
            if text:
                blocks.append("#" * int(t[1]) + " " + text)
        elif t == "hr":
            blocks.append("---")
        else:  # p, div, table, tr
            blocks.extend(_blocks(n.kids))
    flush()
    return blocks


def _list(node: _Node) -> str:
    ordered = node.tag == "ol"
    lines: list[str] = []
    n = 0
    for li in node.kids:
        if isinstance(li, str):
            continue
        if li.tag in ("ul", "ol"):  # a list placed directly inside a list
            lines.extend("  " + ln for ln in _list(li).split("\n"))
            continue
        if li.tag != "li":
            continue
        n += 1
        marker = f"{n}. " if ordered else "- "
        text_kids = [k for k in li.kids if isinstance(k, str) or k.tag not in ("ul", "ol")]
        subs = [k for k in li.kids if not isinstance(k, str) and k.tag in ("ul", "ol")]
        first = " ".join(_blocks(text_kids)).replace("\n", " ").strip()
        pad = " " * len(marker)
        lines.append(marker + first)
        for s in subs:
            lines.extend(pad + ln for ln in _list(s).split("\n"))
    return "\n".join(lines)


def html_to_markdown(html: str) -> str:
    """Convert a Zotero note's HTML into safe Markdown (no raw HTML, scripts or unsafe links)."""
    if not html or not html.strip():
        return ""
    b = _Builder()
    try:
        b.feed(html)
        b.close()
    except Exception:  # malformed input must never break a sync; keep the visible text
        return _escape(re.sub(r"<[^>]*>", "", html)).strip()
    md = "\n\n".join(_blocks(b.root.kids))
    return md.replace("<!--", "\\<!--").strip()


def _quote(md: str) -> str:
    return "\n".join("> " + ln if ln else ">" for ln in md.split("\n"))


def annotation_to_markdown(text: str, comment: str = "", page: str = "") -> str:
    """One highlight: the quoted text, then the author's comment, then the page."""
    parts: list[str] = []
    if text and text.strip():
        parts.append(_quote(_escape(" ".join(text.split()))))
    if comment and comment.strip():
        parts.append(_escape(" ".join(comment.split())))
    if page:
        parts.append("(p. " + _escape(str(page)) + ")")
    return "\n\n".join(parts)
