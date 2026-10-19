"""Research export (P5): assemble_research, the pandoc Markdown it generates, csljson, convert_research.

Tests that run pandoc skip when it is not installed; the PDF test also needs a TeX engine."""

import hashlib
import re
import shutil
import struct
import zipfile
import zlib
from datetime import datetime

import pytest

from chisel.core import drafts, entities as ent, objects
from chisel.core.export import csljson, markdown, pandoc, research
from chisel.core.export.manuscript import (
    Book, Citation, Equation, ExportOptions, Figure, Footnote, Heading, Math, Paragraph, Run, Table, assemble)
from chisel.core.project import Project

from tests.export_helpers import make_structured
from tests.research_helpers import clear_starter

has_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
has_tex = pytest.mark.skipif(shutil.which("pandoc") is None or pandoc.find_pdf_engine() is None,
                             reason="pandoc or a TeX engine is not installed")


def _png() -> bytes:
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\x00" + b"\xff\x00\x00" * 2) * 1) + chunk(b"IEND", b""))


PNG = _png()

CSL = {"id": "ABCD1234", "type": "article-journal", "title": "A Title About Flow",
       "author": [{"family": "Smith", "given": "Jane"}], "issued": {"date-parts": [[2024]]},
       "container-title": "Journal of Flow"}

INTRO = """\
---
pov: Mara
---
# Introduction

Flow is *slow* here, see [[@smith2024, p. 12]] and [[+@smith2024]]; the cost was \\$5 and the
mass obeys $a^2 + b^2 = c^2$ (see [[eq:mass]]). Results are in [[tbl:results]] and [[fig:flow]].^[A note with $x$.]

## Method

![[fig:flow]]

![[tbl:results]]

![[eq:mass]]

$$
\\int_0^1 x\\,dx
$$

Not math: $5 and $10 stay text.
"""


def make_paper(root, text=INTRO, with_source=True):
    p = clear_starter(Project.create(root, "Flow Paper", "research"))
    (root / "manuscript" / "01-introduction.md").write_text(text, encoding="utf-8", newline="\n")
    if with_source:
        e, path = p.create_entity("smith2024", "source")
        e.extra.update({"key": "smith2024", "csl": CSL, "title": "A Title About Flow"})
        ent.save_entity(e, path)
        e2, path2 = p.create_entity("unused2020", "source")
        e2.extra.update({"key": "unused2020", "csl": {**CSL, "title": "Never Cited"}})
        ent.save_entity(e2, path2)
    objects.create_figure(p, PNG, "flow", "The *flow* model")
    (root / "tables").mkdir(exist_ok=True)
    (root / "tables" / "tbl-results.md").write_text(
        "---\ncaption: Results of $n=3$ runs\n---\n\n| run | value |\n|:---|---:|\n| a | 1 |\n| b \\| c | 2 |\n",
        encoding="utf-8", newline="\n")
    (root / "equations").mkdir(exist_ok=True)
    (root / "equations" / "eq-mass.md").write_text("---\ncaption: Mass\n---\n\nm = \\rho V\n",
                                                   encoding="utf-8", newline="\n")
    return Project.open(root)


def plain_text(xml: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))


def docx_xml(path, part="word/document.xml") -> str:
    return zipfile.ZipFile(path).read(part).decode("utf-8")


# -- fiction exports are byte-identical ------------------------------------------------------------------


@pytest.mark.parametrize("name,opts,pandoc_sha,plain_sha,words", [
    ("default", ExportOptions(),
     "3b9ba5d69002d3aa4fabdcb867097d1dcf4005dd25a72ecdbf221e95ae899081",
     "b8fbd17ff3b03357e2a671c9721582f02f32f836977a5bc9a856106a1b5b4d45", 55),
    ("numbers", ExportOptions(numbering="numbers", include_drafts=True),
     "f9cb6c22e37a89f01773719cf84b97f8b3c9b4e68243191c76214f7c977ea478",
     "9e3140e5a3db2fd5af0faf118eded7d1152e35290594d6604433c5e01124db56", 59),
    ("continuous", ExportOptions(continuous=True, numbering="titles-only", include_front_matter=False),
     "e63c06cf9b5497ad16ab6492dfb6f1015231e82298259c4bae0e294869386d47",
     "7594eb6675a13f48080083aa5ca2daeda8ae9cbcb26558e336236a12e1c0a284", 50),
])
def test_fiction_markdown_is_byte_identical_to_before(tmp_path, name, opts, pandoc_sha, plain_sha, words):
    """The hashes were taken from the code before P5 touched manuscript.py / pandoc.py."""
    book = assemble(make_structured(tmp_path / "p"), opts)
    assert hashlib.sha256(markdown.to_markdown(book, pandoc=True).encode()).hexdigest() == pandoc_sha
    assert hashlib.sha256(markdown.to_markdown(book).encode()).hexdigest() == plain_sha
    assert book.words == words and (book.cited, book.bibliography, book.unresolved) == ([], [], [])
    assert not any(w.blocking for w in book.warnings)


def test_fiction_pandoc_reader_is_unchanged():
    assert hashlib.sha256(pandoc._READER.encode()).hexdigest() == \
        "ff9ff2cdb532330b78ab5a8ef24e001c9965db728349adc7163215d7214e218e"


def test_story_scene_with_citation_text_still_flattens_links(tmp_path):
    p = make_structured(tmp_path / "p")
    (tmp_path / "p" / "manuscript" / "99-x.md").write_text(
        "# X\n\nA [[@k]] and [[fig:a]] and [[Mara|M]].\n", encoding="utf-8")
    text = markdown.to_markdown(assemble(Project.open(tmp_path / "p")), pandoc=True)
    assert "@k" in text.replace("\\@", "@") and "M" in text and "Mara|M" not in text


def test_research_export_needs_a_research_project(tmp_path):
    with pytest.raises(ValueError, match="research project"):
        research.assemble_research(make_structured(tmp_path / "p"))


# -- assemble_research: what is read -------------------------------------------------------------------


def test_assemble_nodes_numbers_and_bibliography(tmp_path):
    book = research.assemble_research(make_paper(tmp_path / "p"))
    (chapter,) = list(book.chapters())
    assert chapter.title == "Introduction" and book.scenes == 1
    kinds = [type(b).__name__ for b in chapter.blocks]
    assert kinds == ["Paragraph", "Heading", "Figure", "Table", "Equation", "Paragraph", "Paragraph"]
    first = chapter.blocks[0]
    nodes = [type(r).__name__ for r in first.runs]
    assert nodes.count("Citation") == 2 and "Math" in nodes and "Footnote" in nodes
    cites = [r for r in first.runs if isinstance(r, Citation)]
    assert cites[0].kind == "bracketed" and cites[0].refs[0].locator == "p. 12"
    assert cites[1].kind == "narrative"
    text = first.text
    assert "Eq. (1)" in text and "Table 1" in text and "Figure 1" in text and "[[" not in text
    fig, tbl, eq = chapter.blocks[2:5]
    assert (fig.number, tbl.number, eq.number) == ("1", "1", "1")
    assert fig.path.endswith("figures/fig-flow.png") and fig.width is None
    assert [c[0][0].text for c in tbl.cells[1:]] == ["a", "b | c"]      # the escaped pipe is one cell
    assert tbl.align == ("left", "right")
    display = chapter.blocks[5]
    assert [type(r).__name__ for r in display.runs] == ["Math"] and display.runs[0].display
    assert display.runs[0].tex.replace(" ", "") == "\\int_0^1x\\,dx"
    # "$5 and $10" is not math (pandoc's rule)
    assert not any(isinstance(r, Math) for r in chapter.blocks[6].runs)
    assert book.cited == ["smith2024"]
    assert [e["id"] for e in book.bibliography] == ["smith2024"]    # the uncited source is not in it
    assert book.bibliography[0]["title"] == "A Title About Flow" and book.unresolved == []
    assert not [w for w in book.warnings if w.blocking]
    assert book.words > 10


def test_assemble_reads_only_the_book(tmp_path):
    root = tmp_path / "p"
    p = make_paper(root)
    (root / "manuscript" / "_unplaced").mkdir()
    (root / "manuscript" / "_unplaced" / "01-parked.md").write_text("# Parked\n\nPARKEDTEXT\n", encoding="utf-8")
    (root / ".trash").mkdir()
    (root / ".trash" / "manuscript__02-gone.md").write_text("# Gone\n\nTRASHTEXT\n", encoding="utf-8")
    (root / "notebook").mkdir(exist_ok=True)
    (root / "notebook" / "idea.md").write_text("NOTEBOOKTEXT\n", encoding="utf-8")
    (root / "manuscript" / "02-results.md").write_text(
        "---\nstatus: SECRETDETAIL\n---\n# Results\n\nKept <!--ai id=\"abc123\"-->AIDRAFT<!--/ai--> text. {{expand: EXPANDNOTE}}\n"
        "<!-- a comment: COMMENTTEXT -->\n", encoding="utf-8")
    drafts.save_originals(root, root / "manuscript" / "02-results.md", {"abc123": "ORIGINALTEXT"})
    book = research.assemble_research(Project.open(root), ExportOptions(format="docx"))
    md = research.research_markdown(book, "docx")
    assert "ORIGINALTEXT" in md
    for banned in ("PARKEDTEXT", "TRASHTEXT", "NOTEBOOKTEXT", "SECRETDETAIL", "COMMENTTEXT", "EXPANDNOTE", "AIDRAFT"):
        assert banned not in md
    assert any(w.kind == "expand" for w in book.warnings) and book.draft_scenes
    assert book.scenes == 2
    accepted = research.assemble_research(Project.open(root), ExportOptions(format="docx", include_drafts=True))
    md2 = research.research_markdown(accepted, "docx")
    assert "AIDRAFT" in md2 and "ORIGINALTEXT" not in md2


def test_unresolved_citation_and_missing_references_block(tmp_path):
    root = tmp_path / "p"
    make_paper(root, text="# A\n\nSee [[@nokey]] and [[fig:ghost]].\n\n![[fig:ghost]]\n![[tbl:ghost]]\n![[eq:ghost]]\n")
    book = research.assemble_research(Project.open(root))
    kinds = sorted(w.kind for w in book.warnings if w.blocking)
    assert kinds == ["citation-unresolved", "ref-missing", "ref-missing", "ref-missing", "ref-missing"]
    assert book.unresolved == ["nokey"] and book.bibliography == []
    with pytest.raises(RuntimeError, match="blocked.*@nokey"):
        research.convert_research(book, "docx", tmp_path / "o.docx", csl=research.bundled_csl(),
                                  reference_doc=None, resource_path=root)
    assert not (tmp_path / "o.docx").exists()
    md = research.research_markdown(book, "docx")
    assert "\\[\\@nokey\\]" in md and "Figure ??" in md       # override: literal text, never a citation


def test_citation_keys_are_case_sensitive(tmp_path):
    root = tmp_path / "p"
    make_paper(root, text="# A\n\nSee [[@Smith2024]].\n")
    book = research.assemble_research(Project.open(root))
    assert book.unresolved == ["Smith2024"]


# -- escaping -------------------------------------------------------------------------------------------


def test_author_text_is_strictly_escaped_and_generated_constructs_are_not(tmp_path):
    root = tmp_path / "p"
    hostile = ("# H\n\nBold? 1 * 2 and _x_ and #tag | pipe ^up ~t {b} <b>raw</b> @someone C:\\temp \\\\ \\$9\n\n"
               "```{=latex}\n\\input{/etc/passwd}\n```\n\n"
               "- not a list\n\n2. not a list either\n\n: not a caption\n\n"
               "[link](http://example.com) ![img](http://example.com/x.png) [^1]\n")
    make_paper(root, text=hostile)
    md = research.research_markdown(research.assemble_research(Project.open(root)), "docx")
    body = md.split("---\n", 2)[2]
    assert "1 \\* 2" in body and "and *x* and" in body and "\\#tag" in body and "\\|" in body and "\\^up" in body
    assert "\\~t" in body and "\\{b\\}" in body and "\\<b\\>raw\\</b\\>" in body and "\\@someone" in body
    assert "\\\\temp" in body and "\\$9" in body
    assert "```" not in body and "{=latex}" not in body.replace("\\{=latex\\}", "")    # backticks are dropped
    assert "\\[link\\](http" in body and "!\\[img\\](http" in body
    assert "\\- not a list" in body and "2\\. not a list" in body and "\\: not a caption" in body
    assert "@" not in re.sub(r"\\@", "", body)      # no unescaped citation sign anywhere
    assert "$" not in re.sub(r"\\\$", "", body)     # and no unescaped math sign


def test_unsafe_tex_never_reaches_the_output(tmp_path):
    root = tmp_path / "p"
    make_paper(root, text="# A\n\nInline $\\input{secret}$ and $x^^5cinput$ and $\\leq \\deg$.\n\n![[eq:bad]]\n")
    (root / "equations" / "eq-bad.md").write_text("---\n---\n\n\\write18{rm -rf}\n", encoding="utf-8")
    book = research.assemble_research(Project.open(root))
    md = research.research_markdown(book, "tex")
    assert "\\input" not in md and "\\write" not in md and "^^" not in md
    assert md.count("\\[math left out\\]") == 2 and "\\leq \\deg" in md          # \leq and \deg are fine
    assert sum(w.kind == "math-unsafe" for w in book.warnings) == 3
    assert research.tex_is_safe("\\leq \\letter \\deg \\frac{a}{b}") and not research.tex_is_safe("\\let\\x\\y")


def test_math_spans_follow_strip_math():
    for text in ["a $x$ b", "$a$5 b$ c", "$$x$$ and $y$", "cost $5 and $10", "\\$a$ b$", "$$\nx\n\ny\n$$ z"]:
        mask = objects.strip_math(text, mode="research")
        rebuilt = list(text)
        for s, e in research._math_spans(text):
            rebuilt[s:e] = [c if c == "\n" else " " for c in text[s:e]]
        assert "".join(rebuilt) == mask, text


def test_inline_constructs_render_as_pandoc_syntax(tmp_path):
    root = tmp_path / "p"
    make_paper(root, text="# A\n\nSee [[see @smith2024, p. 12; -@unused2020]] and [@smith2024] then [[+@smith2024]].\n")
    book = research.assemble_research(Project.open(root))
    md = research.research_markdown(book, "docx")
    assert "[see @smith2024, p. 12; -@unused2020]" in md
    assert "[@smith2024]" in md and "; @" not in md.replace("; -@", "")
    assert re.search(r"then @smith2024\.", md)


def test_equation_markdown_per_format(tmp_path):
    book = research.assemble_research(make_paper(tmp_path / "p"))
    docx = research.research_markdown(book, "docx")
    tex = research.research_markdown(book, "tex")
    assert re.search(r"^-+  -+\n\$\$m = \\rho V\$\$ +\(1\)\n-+  -+$", docx, re.M)
    assert "```{=latex}\n\\begin{equation}\\tag{1}\\label{eq:mass}\nm = \\rho V\n\\end{equation}\n```" in tex
    assert "```{=latex}" not in docx
    assert "![Figure 1. The *flow* model](<" in docx and "){#fig:flow}" in docx
    assert "Table: Table 1. Results of $n=3$ runs" in docx
    assert "| run | value |\n| :---------- | -----: |\n| a | 1 |\n| b &#124; c | 2 |\n" in docx


# -- csljson --------------------------------------------------------------------------------------------


def test_csljson_only_cited_sources_with_the_citation_key_as_id(tmp_path):
    p = make_paper(tmp_path / "p")
    entities = p.load_entities()
    entries, unresolved = csljson.build(entities, ["smith2024", "smith2024", "ghost", "Smith2024"])
    assert [e["id"] for e in entries] == ["smith2024"] and unresolved == ["ghost", "Smith2024"]
    assert entries[0]["title"] == "A Title About Flow" and CSL["id"] == "ABCD1234"       # stored data untouched
    assert csljson.build(entities, [])[0] == []
    import json
    assert json.loads(csljson.dumps(entries))[0]["author"][0]["family"] == "Smith"


def test_csljson_fallback_for_a_note_without_csl(tmp_path):
    p = Project.create(tmp_path / "p", "P", "research")
    e, path = p.create_entity("hand2020", "source")
    e.extra.update({"key": "hand2020", "title": "Hand made", "authors": ["Roe, Ann", "Initech"], "year": 2020})
    ent.save_entity(e, path)
    (entry,), _ = csljson.build(p.load_entities(), ["hand2020"])
    assert entry["id"] == "hand2020" and entry["type"] == "document" and entry["title"] == "Hand made"
    assert entry["author"] == [{"family": "Roe", "given": "Ann"}, {"literal": "Initech"}]
    assert entry["issued"] == {"date-parts": [[2020]]}


def test_bundled_styles_are_independent_and_dependent_ones_refused(tmp_path):
    styles = research.bundled_styles()
    assert {"apa", "ieee", "chicago-author-date"} <= set(styles)
    for path in styles.values():
        research.check_csl(path)
        assert "CC BY-SA" in path.read_text(encoding="utf-8") or "Creative Commons" in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="unknown citation style"):
        research.bundled_csl("../../etc/passwd")
    dep = tmp_path / "dep.csl"
    dep.write_text('<style xmlns="http://purl.org/net/xbiblio/csl"><info><link href="http://x" '
                   'rel="independent-parent"/></info></style>', encoding="utf-8")
    with pytest.raises(ValueError, match="dependent"):
        research.check_csl(dep)
    junk = tmp_path / "junk.csl"
    junk.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="not a CSL"):
        research.check_csl(junk)


# -- pandoc ---------------------------------------------------------------------------------------------


@has_pandoc
def test_docx_round_trip_equation_bookmark_citations_and_bibliography(tmp_path):
    root = tmp_path / "my project"                       # a space in the path, as on the author's machine
    p = make_paper(root)
    book = research.assemble_research(p, ExportOptions(format="docx", toc=False))
    out = root / "exports" / "paper.docx"
    out.parent.mkdir()
    res = research.convert_research(book, "docx", out, csl=research.bundled_csl("apa"),
                                    reference_doc=None, resource_path=root)
    assert res.rel == "exports/paper.docx" and res.format == "docx" and res.words == book.words
    xml = docx_xml(out)
    assert xml.count("<m:oMath>") + xml.count("<m:oMath ") >= 3          # inline, display, numbered equation
    assert re.search(r'<w:bookmarkStart [^>]*w:name="fig:flow"', xml)
    assert "<w:drawing>" in xml and "media/" in docx_xml(out, "word/_rels/document.xml.rels")
    text = plain_text(xml)
    sq = re.sub(r"\s+", "", text)                                       # tag boundaries add spaces
    assert "(Smith,2024,p.12)" in sq and "Smith(2024)" in sq            # bracketed and narrative, APA
    assert "Smith,J.(2024)." in sq and "atitleaboutflow" in sq.lower() and "JournalofFlow" in sq
    assert "NeverCited" not in sq                                       # only cited sources are listed
    assert "References" in text and "Figure1.Theflowmodel" in sq
    assert "Table1.Resultsofn=3runs" in sq and "b|c" in sq and "m=ρV(1)" in sq
    assert "Anotewithx" in re.sub(r"\s+", "", plain_text(docx_xml(out, "word/footnotes.xml")))
    assert "$5" in text and "$5and$10staytext" in sq                    # prose dollars stay text
    assert "[[" not in text and "@smith2024" not in text                # citeproc replaced the key
    assert not list((root / "exports").glob("*.part"))


@has_pandoc
def test_docx_numbered_headings_and_front_matter_unnumbered(tmp_path):
    root = tmp_path / "p"
    p = make_paper(root, text="# Intro\n\nBody.\n\n## Sub\n\nMore.\n")
    (root / "manuscript" / "00-front-matter").mkdir()
    (root / "manuscript" / "00-front-matter" / "01-abstract.md").write_text("# Abstract\n\nShort.\n", encoding="utf-8")
    book = research.assemble_research(Project.open(root), ExportOptions(format="docx", toc=False))
    out = tmp_path / "h.docx"
    research.convert_research(book, "docx", out, csl=None, reference_doc=None, resource_path=root)
    text = plain_text(docx_xml(out))
    assert re.search(r"1\s+Intro", text) and re.search(r"1\.1\s+Sub", text)
    assert "Abstract" in text and not re.search(r"\d\s+Abstract", text)
    book_t = research.assemble_research(Project.open(root), ExportOptions(format="docx", toc=False,
                                                                         numbering="titles-only"))
    research.convert_research(book_t, "docx", tmp_path / "t.docx", csl=None, reference_doc=None, resource_path=root)
    assert not re.search(r"1\s+Intro", plain_text(docx_xml(tmp_path / "t.docx")))


@has_pandoc
def test_unresolved_override_exports_literal_text(tmp_path):
    root = tmp_path / "p"
    make_paper(root, text="# A\n\nSee [[@nokey]] and [[fig:ghost]].\n")
    book = research.assemble_research(Project.open(root))
    out = tmp_path / "o.docx"
    research.convert_research(book, "docx", out, csl=None, reference_doc=None, resource_path=root,
                              allow_unresolved=True)
    text = plain_text(docx_xml(out))
    assert "[@nokey]" in text and "Figure ??" in text


@has_pandoc
def test_hostile_author_text_stays_text_in_docx(tmp_path):
    root = tmp_path / "p"
    make_paper(root, text="# H\n\n<b>raw</b> <script>x</script> @someone [link](http://example.com) "
                          "![img](http://example.com/x.png) \\input{x} `code` *a* ^[n]\n")
    book = research.assemble_research(Project.open(root))
    out = tmp_path / "o.docx"
    research.convert_research(book, "docx", out, csl=None, reference_doc=None, resource_path=root)
    xml = docx_xml(out)
    text = plain_text(xml)
    assert "<b>raw</b>" in xml.replace("&lt;", "<").replace("&gt;", ">") and "@someone" in text
    assert "[link](http://example.com)" in text and "![img](http://example.com/x.png)" in text
    assert "<w:hyperlink" not in xml and "<w:drawing>" not in xml


@has_pandoc
def test_latex_output(tmp_path):
    root = tmp_path / "p"
    p = make_paper(root)
    book = research.assemble_research(p, ExportOptions(format="tex", toc=False))
    out = tmp_path / "paper.tex"
    research.convert_research(book, "tex", out, csl=research.bundled_csl(), reference_doc=None, resource_path=root)
    tex = out.read_text(encoding="utf-8")
    assert "\\begin{equation}\\tag{1}\\label{eq:mass}" in tex and "m = \\rho V" in tex
    assert "\\includegraphics" in tex and "figures/fig-flow.png" in tex.replace("\\", "/")
    assert "\\(a^2 + b^2 = c^2\\)" in tex and "\\[\\int_0^1 x\\,dx\\]" in tex and "\\section{Introduction}" in tex and "\\subsection{Method}" in tex
    assert "Smith" in tex and "Journal of Flow" in tex and "Never Cited" not in tex
    assert "\\input" not in tex and "\\write" not in tex


@has_tex
def test_pdf_output(tmp_path, monkeypatch):
    root = tmp_path / "p"
    p = make_paper(root)
    book = research.assemble_research(p, ExportOptions(format="pdf", toc=False))
    out = tmp_path / "paper.pdf"
    missing = []
    for engine in pandoc.TEX_ENGINES:            # a TeX install may lack a package one engine needs
        exe = shutil.which(engine)
        if exe is None:
            continue
        monkeypatch.setattr(pandoc, "find_pdf_engine", lambda exe=exe: exe)
        try:
            research.convert_research(book, "pdf", out, csl=research.bundled_csl("ieee"), reference_doc=None,
                                      resource_path=root)
        except RuntimeError as exc:
            assert str(exc).startswith(("the TeX engine needs", "pandoc failed:")), exc   # plain message
            assert not out.exists()
            missing.append(str(exc))
            continue
        assert out.read_bytes()[:5] == b"%PDF-" and out.stat().st_size > 2000
        return
    pytest.skip("no TeX engine could build the PDF here: " + "; ".join(missing))


@has_pandoc
def test_run_research_export_names_and_never_overwrites(tmp_path):
    root = tmp_path / "p"
    p = make_paper(root)
    now = datetime(2026, 10, 18, 9, 5)
    a = research.run_research_export(p, ExportOptions(format="docx"), now=now)
    b = research.run_research_export(p, ExportOptions(format="docx"), now=now)
    assert a.rel == "exports/flow-paper-docx-20261018-0905.docx" and b.rel.endswith("0905-2.docx")
    assert a.path.is_file() and b.path.is_file() and not list((root / "exports").glob(".*"))
    with pytest.raises(ValueError, match="does not write"):
        research.run_research_export(p, ExportOptions(format="md"))


@has_pandoc
def test_reference_doc_and_template_check(tmp_path):
    ref = research.starter_reference_doc(tmp_path / "ref.docx")
    core = {"Normal", "Body Text", "Heading 1", "Heading 2", "Image Caption", "Table Caption"}
    assert not core & set(research.missing_styles(ref))
    bare = tmp_path / "bare.docx"
    with zipfile.ZipFile(ref) as zin, zipfile.ZipFile(bare, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                data = re.sub(rb'<w:name w:val="(Heading 1|Image Caption)"', rb'<w:name w:val="Other"', data)
            zout.writestr(item, data)
    assert {"Heading 1", "Image Caption"} <= set(research.missing_styles(bare))
    with pytest.raises(ValueError, match="not a Word"):
        research.missing_styles(tmp_path / "nothing.docx")
    root = tmp_path / "p"
    p = make_paper(root)
    book = research.assemble_research(p, ExportOptions(format="docx"))
    research.convert_research(book, "docx", tmp_path / "t.docx", csl=None, reference_doc=ref, resource_path=root)
    assert (tmp_path / "t.docx").stat().st_size > 1000
    with pytest.raises(ValueError, match="template"):
        research.convert_research(book, "docx", tmp_path / "u.docx", csl=None,
                                  reference_doc=tmp_path / "missing.docx", resource_path=root)


def test_pandoc_missing_is_a_plain_message(tmp_path, monkeypatch):
    root = tmp_path / "p"
    book = research.assemble_research(make_paper(root))
    monkeypatch.setattr(pandoc, "find", lambda: None)
    with pytest.raises(RuntimeError, match="pandoc is not installed"):
        research.convert_research(book, "docx", tmp_path / "o.docx", csl=None, reference_doc=None,
                                  resource_path=root)


def test_pdf_without_a_tex_engine_is_a_plain_message(tmp_path, monkeypatch):
    root = tmp_path / "p"
    book = research.assemble_research(make_paper(root))
    monkeypatch.setattr(pandoc, "find", lambda: "pandoc")
    monkeypatch.setattr(pandoc, "find_pdf_engine", lambda: None)
    with pytest.raises(RuntimeError, match="TeX engine"):
        research.convert_research(book, "pdf", tmp_path / "o.pdf", csl=None, reference_doc=None, resource_path=root)
    assert not (tmp_path / "o.pdf").exists()


def test_child_processes_are_run_without_a_console():
    import inspect
    assert "NO_CONSOLE" in inspect.getsource(pandoc.run_research)
    assert "NO_CONSOLE" in inspect.getsource(research.starter_reference_doc)
