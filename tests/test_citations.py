"""Citation parsing, the link-parser exclusion rule and the citations index (research mode, P1)."""

from chisel.core import entities as ent
from chisel.core.index import Index
from chisel.core.links import find_all_links, find_citations, find_links, find_mentions
from chisel.core.project import Project


def keys(c):
    return [r.key for r in c.refs]


def test_forms_and_kinds():
    text = "A [[@smith2024]] b [[+@lee2023]] c [@kim2020; @roe2019] d"
    a, b, c = find_citations(text)
    assert (a.kind, keys(a)) == ("bracketed", ["smith2024"])
    assert (b.kind, keys(b)) == ("narrative", ["lee2023"])
    assert (c.kind, keys(c)) == ("pandoc", ["kim2020", "roe2019"])
    assert text[a.start:a.end] == a.raw == "[[@smith2024]]"
    assert text[c.start:c.end] == "[@kim2020; @roe2019]"


def test_prefix_locator_suffix_and_suppress():
    (c,) = find_citations("[[see @smith2024, p. 12; -@lee2023, emphasis added]]")
    s, l = c.refs
    assert (s.prefix, s.locator, s.suffix, s.suppress_author) == ("see", "p. 12", "", False)
    assert (l.key, l.suppress_author, l.locator, l.suffix) == ("lee2023", True, "", "emphasis added")
    (c,) = find_citations("[[@a, pp. 3-5, and passim]]")
    assert (c.refs[0].locator, c.refs[0].suffix) == ("pp. 3-5", "and passim")


def test_case_sensitive_and_unicode_keys():
    (c,) = find_citations("[[@Müller2020; @smith:2024.b; @Smith2024]]")
    assert keys(c) == ["Müller2020", "smith:2024.b", "Smith2024"]


def test_pipe_and_offsets_in_code_points():
    text = "😀 [[@k1|x]] tail"
    (c,) = find_citations(text)
    assert keys(c) == ["k1"]
    assert text[c.start:c.end] == "[[@k1|x]]"


def test_not_citations():
    assert find_citations("mail me a@b.com, or [[Elara]], [[fig:x]], [text](url)") == []
    assert find_citations("[@k](http://x)") == []
    assert find_citations("no at sign [[Name|see x]]") == []
    # a display text mentioning " @" belongs to an ordinary link
    assert find_citations("[[Elara|call @home]]") == []
    assert [l.target for l in find_links("[[Elara|call @home]]")] == ["Elara"]


def test_pandoc_inside_wiki_form_not_duplicated():
    assert len(find_citations("[[see @a]] and [@b]")) == 2


def test_links_ignore_foreign_targets():
    text = "[[@a]] [[-@a]] [[+@a]] [[see @a, p. 2]] [[fig:x]] [[tbl:y]] [[eq:z]] [[smith2024]] [[Elara]]"
    assert [l.target for l in find_links(text)] == ["smith2024", "Elara"]
    assert [l.target for l in find_all_links(text, ["Elara"])] == ["smith2024", "Elara"]


def test_mentions_skip_citation_text():
    text = "[[see @elara-paper]] Elara walked."
    assert [m.target for m in find_mentions(text, ["Elara", "elara-paper"])] == ["Elara"]


def test_resolve_key_is_case_sensitive_and_source_only():
    src = ent.Entity(name="smith2024", type="source")
    concept = ent.Entity(name="kalman2020", type="concept")
    other = ent.Entity(name="Smith2024", type="source", extra={"key": "Smith2024"})
    es = [concept, src, other]
    assert ent.resolve_key("smith2024", es) is src
    assert ent.resolve_key("Smith2024", es) is other
    assert ent.resolve_key("SMITH2024", es) is None
    assert ent.resolve_key("kalman2020", es) is None          # a Concept cannot shadow a key
    assert ent.resolve("smith2024", es) is src                # ordinary [[smith2024]] still links


def test_index_citers_case_sensitive(tmp_path):
    p = Project.create(tmp_path / "paper", "P", mode="research")
    (p.manuscript_dir / "01-intro.md").write_text(
        "As [[@Smith2024]] and [[see @smith2024, p. 2]] but [[smith2024]] is a link.\n",
        encoding="utf-8", newline="\n")
    idx = Index(p.index_path)
    idx.rebuild(p)
    assert [b.source for b in idx.citers("smith2024")] == ["manuscript/01-intro.md"]
    assert len(idx.citers("Smith2024")) == 1
    assert idx.citers("SMITH2024") == []
    rows = idx._conn.execute(
        "SELECT target FROM links WHERE source = 'manuscript/01-intro.md'").fetchall()
    assert [r[0] for r in rows] == ["smith2024"]   # the plain link is a link; citations are not
    idx.close()


def test_story_index_has_no_citations_and_mode_change_needs_rebuild(tmp_path):
    p = Project.create(tmp_path / "book", "B")
    (p.manuscript_dir / "01-opening.md").write_text("[[@a]] text\n", encoding="utf-8", newline="\n")
    idx = Index(p.index_path)
    idx.rebuild(p)
    assert idx.citers("a") == []
    assert not idx.needs_rebuild(p)
    p.update_mode("research")
    assert idx.needs_rebuild(p)
    idx.rebuild(p)
    assert len(idx.citers("a")) == 1 and not idx.needs_rebuild(p)
    idx.close()
