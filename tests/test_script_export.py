"""Script mode export: the Fountain file, the screenplay PDF and the import back (core/export/script.py,
core/export/layouts/screenplay.py, core/fountain.py)."""

import shutil
import subprocess

import pytest

from chisel.core import export as exp
from chisel.core import fountain
from chisel.core.export.manuscript import ExportOptions, ScriptText, assemble
from chisel.core.project import Project

KITCHEN = """\
---
pov: Keith
status: draft
---
# Kitchen

INT. KITCHEN - DAY

Keith burns the toast. <!-- remember the toast -->

KEITH
(to the toast)
Burnt again, see [[Keith|me]].

CUT TO:
"""

GARDEN = """\
# The garden at night

EXT. GARDEN - NIGHT

Rain.<!--ai--> An unaccepted line.<!--/ai-->
"""


def make_script(root):
    project = Project.create(root, "The Toast", "script")
    (root / "manuscript" / "01-opening.md").unlink()
    project.update_author_info(author="Jo Writer", contact="jo@example.com\n555 0100")
    act = project.new_part("Act One")
    for title, text in (("Kitchen", KITCHEN), ("The garden at night", GARDEN)):
        path = project.next_scene_path(title, act)
        path.write_text(text, encoding="utf-8", newline="\n")
    project.create_entity("Keith", "character")
    return Project.open(root)


def test_assemble_keeps_script_text_whole(tmp_path):
    project = make_script(tmp_path / "p")
    book = assemble(project, ExportOptions(format="fountain"))
    texts = [b.text for c in book.chapters() for b in c.blocks]
    assert all(isinstance(b, ScriptText) for c in book.chapters() for b in c.blocks)
    kitchen, garden = texts
    assert kitchen.startswith("INT. KITCHEN - DAY")                 # details and the title line are gone
    assert "[[remember the toast]]" in kitchen and "<!--" not in kitchen
    assert "Burnt again, see me." in kitchen                          # the wiki-link is flattened
    assert "Keith burns the toast." in kitchen and "\n(to the toast)\n" in kitchen  # line breaks kept
    assert "unaccepted" not in garden                                 # pending AI text is left out
    assert book.scenes == 2 and book.words > 10


def test_to_fountain_has_title_page_sections_and_synopses(tmp_path):
    from chisel.core.export import script
    project = make_script(tmp_path / "p")
    out = script.to_fountain(assemble(project, ExportOptions(format="fountain")))
    assert out.startswith("Title: The Toast\nCredit: Written by\nAuthor: Jo Writer\n")
    assert "Contact:\n    jo@example.com\n    555 0100\n" in out
    assert "# Act One\n" in out
    assert "= Kitchen\n" in out and "= The garden at night\n" in out   # titles that differ from the headings
    # the file is a valid Fountain script: it parses back into the same scenes
    again = fountain.import_text(out)
    assert again.title_page["title"] == "The Toast"
    assert [(p.title, [s.title for s in p.scenes]) for p in again.parts] == \
        [("Act One", ["Kitchen", "The garden at night"])]


def test_fountain_export_file_and_options(tmp_path):
    project = make_script(tmp_path / "p")
    res = exp.run_export(project, ExportOptions(format="fountain"))
    assert res.path.suffix == ".fountain" and res.path.parent.name == "exports"
    assert res.scenes == 2 and res.pages is None
    assert "INT. KITCHEN - DAY" in res.path.read_text(encoding="utf-8")
    assert Project.open(tmp_path / "p").meta["export"]["format"] == "fountain"


def test_describe_offers_the_script_formats_only_to_scripts(tmp_path):
    script_info = exp.describe(make_script(tmp_path / "s"))
    assert [f["key"] for f in script_info["formats"]] == ["pdf", "fountain"]
    assert [l["name"] for l in script_info["layouts"]] in (["screenplay"], [])
    assert script_info["options"]["layout"] == "screenplay"
    story = Project.create(tmp_path / "n", "Novel")
    story_info = exp.describe(story)
    assert "fountain" not in [f["key"] for f in story_info["formats"]]
    assert "screenplay" not in [l["name"] for l in story_info["layouts"]]


def test_formats_are_kept_to_their_mode(tmp_path):
    project = make_script(tmp_path / "s")
    with pytest.raises(ValueError, match="PDF.*Fountain"):
        exp.run_export(project, ExportOptions(format="md"))
    novel = Project.create(tmp_path / "n", "Novel")
    with pytest.raises(ValueError, match="script projects"):
        exp.run_export(novel, ExportOptions(format="fountain"))
    with pytest.raises(ValueError, match="script projects"):
        exp.run_export(novel, ExportOptions(format="pdf", layout="screenplay"))


def test_a_story_export_is_unchanged_by_script_mode(tmp_path):
    novel = Project.create(tmp_path / "n", "Novel")
    (novel.manuscript_dir / "01-opening.md").write_text("# One\n\nHard\nwrapped line.\n", encoding="utf-8")
    book = assemble(novel, ExportOptions())
    assert [b.text for c in book.chapters() for b in c.blocks] == ["Hard wrapped line."]


# -- the PDF ---------------------------------------------------------------------------------------

try:
    import reportlab  # noqa: F401
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
needs_pdf = pytest.mark.skipif(not HAS_REPORTLAB, reason="needs ReportLab")

CHAR = 7.2012       # one Liberation Mono character at 12 pt


@pytest.fixture
def drawn(monkeypatch):
    """Everything the screenplay layout draws, per page: [(x, y, text, right_aligned)]."""
    from reportlab.pdfgen.canvas import Canvas
    pages, current = [], []
    real_show, real_str, real_right = Canvas.showPage, Canvas.drawString, Canvas.drawRightString

    def show(self):
        pages.append(list(current))
        current.clear()
        real_show(self)

    monkeypatch.setattr(Canvas, "showPage", show)
    monkeypatch.setattr(Canvas, "drawString", lambda self, x, y, t, *a, **k: (current.append((x, y, t, False)),
                                                                              real_str(self, x, y, t, *a, **k))[1])
    monkeypatch.setattr(Canvas, "drawRightString", lambda self, x, y, t, *a, **k: (current.append((x, y, t, True)),
                                                                                    real_right(self, x, y, t, *a, **k))[1])
    return pages


@needs_pdf
def test_screenplay_pdf_positions_elements(tmp_path, drawn):
    project = make_script(tmp_path / "p")
    res = exp.run_export(project, ExportOptions(format="pdf"))
    assert res.format == "pdf" and res.pages == 2 == len(drawn)       # title page + one script page
    title = " ".join(t for _x, _y, t, _r in drawn[0])
    assert "THE TOAST" in title and "Written by" in title and "Jo Writer" in title and "jo@example.com" in title
    page = {t: (x, y) for x, y, t, _r in drawn[1]}
    left = page["INT. KITCHEN - DAY"][0]
    assert page["Keith burns the toast."][0] == left                  # headings and action: the left margin
    speech, paren, cue = (page[k][0] for k in ("Burnt again, see me.", "(to the toast)", "KEITH"))
    assert speech == pytest.approx(left + 10 * CHAR, abs=0.1)
    assert paren == pytest.approx(left + 16 * CHAR, abs=0.1)
    assert cue == pytest.approx(left + 22 * CHAR, abs=0.1)
    assert page["CUT TO:"][0] == pytest.approx(left + 53 * CHAR, abs=0.1)     # flush to the right margin
    ys = [page[k][1] for k in ("INT. KITCHEN - DAY", "Keith burns the toast.", "KEITH", "(to the toast)",
                               "Burnt again, see me.", "CUT TO:")]
    assert ys == sorted(ys, reverse=True)
    assert page["KEITH"][1] - page["(to the toast)"][1] == pytest.approx(12)  # six lines to the inch
    assert not any("remember the toast" in t or "[[" in t or "<!--" in t for _x, _y, t, _r in drawn[1])
    assert not any(r for _x, _y, _t, r in drawn[1])                   # script page 1 has no number


@needs_pdf
def test_long_scripts_paginate_and_number_pages(tmp_path, drawn):
    project = make_script(tmp_path / "p")
    beats = "\n\n".join(f"Action beat number {i} happens here." for i in range(120))
    big = f"# Long\n\nINT. HALL - DAY\n\n{beats}\n"
    project.next_scene_path("Long", None).write_text(big, encoding="utf-8", newline="\n")
    res = exp.run_export(project, ExportOptions(format="pdf"))
    assert res.pages == len(drawn) > 4
    numbers = [t for page in drawn[2:] for _x, _y, t, right in page if right]
    assert numbers[:2] == ["2.", "3."]
    assert all(len([1 for _x, _y, _t, right in page if not right]) <= fountain.LINES_PER_PAGE for page in drawn)
