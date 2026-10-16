from chisel.core.zotero import annotation_to_markdown, html_to_markdown


def test_basic_formatting():
    md = html_to_markdown("<p>A <strong>bold</strong> and <em>soft</em> <code>x</code>.</p><p>Two</p>")
    assert md == "A **bold** and *soft* `x`.\n\nTwo"


def test_script_iframe_style_dropped_with_content():
    md = html_to_markdown('<p>ok</p><script>alert(1)</script><iframe src="http://e"><p>in</p></iframe>'
                          "<style>p{}</style><object>obj</object><p>end</p>")
    assert md == "ok\n\nend"
    assert "alert" not in md and "iframe" not in md


def test_unsafe_links_lose_the_link_keep_text():
    md = html_to_markdown('<a href="javascript:alert(1)">click</a> <a href=" JaVa\tscript:x">t</a>'
                          ' <a href="data:text/html,x">d</a> <a href="https://x.org/a(b)">ok</a>'
                          ' <a href="mailto:a@b.c">m</a>')
    assert "javascript" not in md.lower() and "data:" not in md
    assert "click" in md and "[ok](https://x.org/a%28b%29)" in md and "[m](mailto:a@b.c)" in md


def test_event_handlers_and_raw_html_never_survive():
    md = html_to_markdown('<p onclick="x()">hi <img src=x onerror=alert(1) alt="pic"> <b onmouseover=y>b</b></p>'
                          "&lt;script&gt;z&lt;/script&gt;")
    assert "onclick" not in md and "onerror" not in md and "<" not in md.replace("\\<", "")
    assert "pic" in md


def test_text_cannot_become_wikilink_citation_math_or_marker():
    md = html_to_markdown("<p>see [[Evil]] and [@key] cost $5$ <!--ai--> *x*</p>")
    import re
    assert not re.search(r"(?<!\\)\[", md)  # every bracket is backslash-escaped
    assert "\\[\\[Evil\\]\\]" in md and "\\$5\\$" in md
    assert "<!--ai-->" not in md


def test_nested_lists():
    md = html_to_markdown("<ul><li>a<ul><li>a1</li><li>a2<ol><li>x</li><li>y</li></ol></li></ul></li><li>b</li></ul>")
    assert md.split("\n") == ["- a", "  - a1", "  - a2", "    1. x", "    2. y", "- b"]


def test_ordered_list_and_blockquote_and_headings():
    md = html_to_markdown("<h2>Title</h2><ol><li>one</li><li>two</li></ol><blockquote><p>q</p></blockquote>")
    assert md == "## Title\n\n1. one\n2. two\n\n> q"


def test_line_start_markdown_is_escaped():
    md = html_to_markdown("<p># not a heading</p><p>1. not a list</p>")
    assert md.startswith("\\# ") and "\n\n\\1. " in md


def test_pre_and_unclosed_and_empty():
    assert html_to_markdown("<pre>a <b>b</b>\n  c</pre>") == "```\na b\n  c\n```"
    assert html_to_markdown("<p>one<p>two") == "one\n\ntwo"
    assert html_to_markdown("") == "" and html_to_markdown("   ") == ""


def test_br_makes_hard_break():
    assert html_to_markdown("<p>a<br>b</p>") == "a  \nb"


def test_annotation_markdown():
    md = annotation_to_markdown("The [[x]] result", "my *take*", "12")
    assert md.startswith("> The \\[\\[x\\]\\] result") and "(p. 12)" in md and "\\*take\\*" in md
    assert annotation_to_markdown("", "", "") == ""
