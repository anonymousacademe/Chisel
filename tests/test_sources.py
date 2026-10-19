"""core/sources.py: item_to_note, replace_block, plus the escaped-bracket parsing and the rename refusal (P3)."""

import pytest

from chisel.core import entities as ent
from chisel.core import rename, sources
from chisel.core.links import find_all_links, find_citations, find_links
from chisel.core.paper.types import Annotation, ZItem
from chisel.core.project import Project
from chisel.core.sources import BEGIN, END, item_to_note, replace_block

CSL = {"id": "ABCD1234", "type": "article-journal", "title": "Kalman filters: a survey",
       "author": [{"family": "Smith", "given": "Jane"}, {"family": "Lee", "given": "Wei"}],
       "issued": {"date-parts": [[2024, 3]]}, "volume": "7", "container-title": "J. Ctrl"}


def zitem(key="ABCD1234", ckey="smith2024", notes=(), annotations=(), **kw):
    return ZItem(key=key, version=kw.pop("version", 10), csl=dict(CSL), citation_key=ckey,
                 notes=list(notes), annotations=list(annotations), **kw)


def test_new_note_shape():
    note = item_to_note(zitem(notes=["<p>Good <b>paper</b></p>"],
                              annotations=[Annotation("ANN1", "quoted text", "my comment", "4")]), None)
    assert note.type == "source" and note.name == "smith2024"
    assert note.extra["key"] == "smith2024" and note.extra["zotero_key"] == "ABCD1234"
    assert note.extra["csl"] == CSL
    assert note.extra["authors"] == ["Smith, Jane", "Lee, Wei"] and note.extra["year"] == 2024
    assert note.aliases == ["Smith and Lee 2024"]
    assert note.body.startswith(BEGIN + "\n## From Zotero\n") and "### Notes" in note.body
    assert "<b>" not in note.body
    assert "### Highlights" in note.body and "<!--zotero-ann:ANN1-->" in note.body
    assert note.body.rstrip().endswith("## My notes")
    # frontmatter round trip through a file
    again = ent.Entity.from_markdown(note.to_markdown())
    assert again.extra == note.extra and again.type == "source"


def test_no_citation_key_uses_item_key():
    note = item_to_note(zitem(ckey=None), None)
    assert note.extra["key"] == "ABCD1234" and note.extra["key_source"] == "none"


def test_existing_keeps_author_data_and_extra_order():
    old = item_to_note(zitem(), None)
    old.extra["tags"] = ["x"]
    old.aliases.append("Kalman survey")
    old.body = old.body.rstrip("\n") + "\nMy own thought with [[Link]].\n"
    csl2 = dict(CSL, title="New title")
    new = item_to_note(ZItem("ABCD1234", 11, csl2, "smith2024", notes=["<p>n</p>"]), old)
    assert new.aliases == ["Smith and Lee 2024", "Kalman survey"]
    assert new.extra["tags"] == ["x"] and new.extra["title"] == "New title"
    assert list(new.extra)[:3] == ["key", "key_source", "zotero_key"]
    assert new.body.endswith("My own thought with [[Link]].\n")
    assert new.name == old.name


def test_existing_stored_key_not_changed():
    old = item_to_note(zitem(), None)
    new = item_to_note(zitem(ckey="other2024"), old)
    assert new.extra["key"] == "smith2024"


def test_replace_block_only_between_markers():
    body = f"intro\n{BEGIN}\nold\n{END}\n\n## My notes\nmine  \r\n  end"
    out = replace_block(body, "## From Zotero\nnew")
    assert out == f"intro\n{BEGIN}\n## From Zotero\nnew\n{END}\n\n## My notes\nmine  \r\n  end"
    assert replace_block(out, "## From Zotero\nnew") == out
    assert out.split(BEGIN)[0] == body.split(BEGIN)[0]
    assert out.split(END)[1] == body.split(END)[1]


def test_replace_block_adds_markers():
    assert replace_block("", "X").startswith(f"{BEGIN}\nX\n{END}")
    out = replace_block("Author text\n", "X")
    assert out == f"{BEGIN}\nX\n{END}\n\nAuthor text\n"


@pytest.mark.parametrize("body", [f"{BEGIN} only", f"{END} {BEGIN}", f"{BEGIN}{END}{BEGIN}{END}"])
def test_replace_block_damaged_markers_refused(body):
    with pytest.raises(ValueError):
        replace_block(body, "X")


def test_hostile_note_cannot_forge_markers_or_links():
    item = zitem(notes=["<p>[[Secret]] [[@smith2024]] &lt;!-- zotero:end --&gt; </p>"])
    note = item_to_note(item, None)
    assert note.body.count(BEGIN) == 1 and note.body.count(END) == 1
    assert find_links(note.body) == [] and find_citations(note.body) == []


def test_escaped_brackets_are_not_links_or_citations():
    text = r"a \[\[x\]\] b \[\[@k\]\] c \[@k\] d \[[y]] e [[real]] f [[@k2]] g [@k3]"
    assert [l.target for l in find_links(text)] == ["real"]
    assert [l.target for l in find_all_links(text)] == ["real"]
    assert [c.refs[0].key for c in find_citations(text)] == ["k2", "k3"]


def test_rename_refused_for_sources(tmp_path):
    project = Project.create(tmp_path / "p", "P", mode="research")
    e, _ = project.create_entity("smith2024", "source")
    with pytest.raises(ValueError, match="source"):
        rename.plan_rename(project, e, "smith2025")


@pytest.mark.parametrize("text,expected", [
    ("Use the <b> tag to bold text. More here.", r"Use the \<b\> tag to bold text. More here."),
    ("if a<b and c>d holds, done.", r"if a\<b and c\>d holds, done."),
    ("- item", r"\- item"),
    ("1. step", r"1\. step"),
])
def test_plain_abstract_keeps_every_character(text, expected):
    assert sources._abstract_markdown(text) == expected


def test_html_abstract_still_converted():
    assert sources._abstract_markdown("<p>One</p><p>Two</p>") == "One\n\nTwo"
    assert sources._abstract_markdown("<b>bold</b> text") == "**bold** text"


def test_source_year_reads_raw_issued():
    from chisel.gui.workspace import _source_year
    e = ent.Entity(name="k", type="source", extra={"csl": {"issued": {"raw": "2021"}}})
    assert _source_year(e) == "2021"
