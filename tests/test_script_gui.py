"""Script mode in the desktop bridge: workspace pages, editor spans, cue mentions, spelling, Fountain import."""

import pytest

from chisel.core import fountain, fountainio
from chisel.core.project import Project
from chisel.core.spans import compute_spans
from chisel.gui import workspace as ws
from chisel.gui.api import Api
from tests.test_script_export import KITCHEN, make_script

SCENE_ID = "manuscript/01-act-one/01-kitchen.md"

IMPORT = """\
Title: Short Film
Author: Pat Example
Contact:
    pat@example.com

FADE IN:

# Act Two

= The call
INT. OFFICE - NIGHT

Phone rings. [[answer it?]]

PAT
Hello?

EXT. STREET - DAY

Rain.
"""


def open_script(tmp_path):
    root = tmp_path / "s"
    make_script(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


# -- the workspace ---------------------------------------------------------------------------------


def test_workspace_labels_and_pages_for_a_script(tmp_path):
    api, _ = open_script(tmp_path)
    w = api.get_workspace()["workspace"]
    assert w["project"]["mode"] == "script"
    assert w["project"]["labels"] == {"manuscript": "Script", "parked": "Parked scenes",
                                      "characters": "Characters", "world": "Locations and props"}
    scenes = {s["id"]: s for s in w["scenes"]}
    assert scenes[SCENE_ID]["pages"] > 0
    assert w["status"]["projectPages"] == pytest.approx(sum(s["pages"] for s in w["scenes"]))
    assert w["status"]["pagesLabel"] == fountain.format_pages(w["status"]["projectPages"])


def test_a_story_workspace_has_no_page_fields(tmp_path):
    from tests.gui_helpers import make_project
    make_project(tmp_path / "p")
    api = Api()
    assert api.open_project(str(tmp_path / "p"))["ok"]
    w = api.get_workspace()["workspace"]
    assert "projectPages" not in w["status"] and "pagesLabel" not in w["status"]
    assert all("pages" not in s for s in w["scenes"])


def test_pages_ignore_unaccepted_ai_text(tmp_path):
    api, root = open_script(tmp_path)
    path = root / SCENE_ID
    base = ws.scene_summaries(Project.open(root))[0]["pages"]
    path.write_text(path.read_text(encoding="utf-8") + "\n<!--ai-->" + "Long invented action. " * 400 + "<!--/ai-->\n",
                    encoding="utf-8", newline="\n")
    assert ws.scene_summaries(Project.open(root))[0]["pages"] == base


# -- editor spans ----------------------------------------------------------------------------------


def test_link_spans_carry_script_lines_and_cue_mentions(tmp_path):
    api, root = open_script(tmp_path)
    text = (root / SCENE_ID).read_text(encoding="utf-8")
    spans = api.link_spans(SCENE_ID, text)["spans"]
    elements = {s["element"] for s in spans if s["kind"] == "script"}
    assert {"scene_heading", "character", "parenthetical", "dialogue", "transition"} <= elements
    # the speaker KEITH is the character Keith, although mentions are case-sensitive in prose
    cue = text.index("KEITH")
    assert any(s["kind"] == "mention" and s["start"] == cue and s["end"] == cue + 5 and s["entity"] == "Keith"
               for s in spans)
    # and the details block is not formatted as script
    assert not any(s["kind"] == "script" and s["start"] < text.index("# Kitchen") for s in spans)


def test_a_story_scene_gets_no_script_spans(tmp_path):
    from tests.gui_helpers import make_project
    make_project(tmp_path / "p")
    api = Api()
    api.open_project(str(tmp_path / "p"))
    text = (tmp_path / "p" / "manuscript" / "01-arrival.md").read_text(encoding="utf-8")
    assert not any(s["kind"] == "script" for s in api.link_spans("manuscript/01-arrival.md", text)["spans"])


def test_cue_mentions_skip_linked_cues_and_pending_drafts():
    from chisel.core import entities as ent
    keith = ent.Entity(name="Keith", type="character", aliases=["Keefer"])
    text = ("# T\n\nINT. A - DAY\n\nKEEFER\nHi.\n\n[[Keith]]\nNo.\n\n"
            "<!--ai-->\nKEITH\nDrafted.\n<!--/ai-->\n")
    spans = compute_spans(text, [keith], script=True)
    mentions = [(text[s["start"]:s["end"]], s["kind"]) for s in spans if s["kind"] in ("mention", "link")]
    assert ("KEEFER", "mention") in mentions                       # an alias counts, case-insensitively
    assert ("[[Keith]]", "link") in mentions
    assert ("KEITH", "mention") not in mentions                    # a cue inside an unaccepted draft is not canon


def test_scene_context_counts_cues_in_scripts_only(tmp_path):
    api, root = open_script(tmp_path)
    text = (root / SCENE_ID).read_text(encoding="utf-8")
    [row] = [m for m in api.scene_context(SCENE_ID, text)["mentions"] if m["name"] == "Keith"]
    assert row["count"] == 4                      # details (pov), the prose mention, the cue and the [[Keith|me]] link
    assert [m for m in ws.scene_context(text, api.entities, api.index) if m["name"] == "Keith"][0]["count"] == 3
    prose = ws.scene_context("KEITH said hi.", api.entities, api.index)
    assert prose == []                                             # in prose the case matters, as before


# -- spelling --------------------------------------------------------------------------------------


def test_spelling_skips_headings_cues_transitions_and_notes(tmp_path):
    api, root = open_script(tmp_path)
    text = ("# Kitchen\n\nINT. KITCHN - DAY\n\nKeith recieve the toast.\n\nZORBLAX (V.O.)\n"
            "Hello there.\n\n<!-- wrongg note -->\n\nSMASH TOO:\n\nNext.\n")
    words = [s["word"] for s in api.spelling(SCENE_ID, text)["spans"]]
    assert words == ["recieve"]
    assert api.spelling(SCENE_ID, text)["enabled"]


# -- import ------------------------------------------------------------------------------------------


def test_import_adds_parts_and_scenes_after_the_existing_ones(tmp_path):
    api, root = open_script(tmp_path)
    src = tmp_path / "in.fountain"
    src.write_text(IMPORT, encoding="utf-8")
    r = api.import_fountain(str(src))
    assert r["ok"] and r["imported"]["scenes"] == 2 and r["imported"]["parts"] == 1
    assert r["imported"]["first"].startswith("manuscript/02-act-two/") and r["imported"]["name"] == "in.fountain"
    w = api.get_workspace()["workspace"]
    assert [p["title"] for p in w["parts"]] == ["Act One", "Act Two"]              # after the existing part
    titles = [s["title"] for s in w["scenes"]]
    assert titles[-2:] == ["The call", "EXT. STREET - DAY"]
    first = (root / r["imported"]["first"]).read_text(encoding="utf-8")
    assert first.startswith("# The call\n\nFADE IN:\n\nINT. OFFICE - NIGHT\n")
    assert "<!-- answer it? -->" in first and "[[" not in first                   # not a link to a missing note


def test_import_fills_only_empty_project_details(tmp_path):
    api, root = open_script(tmp_path)
    src = tmp_path / "in.fountain"
    src.write_text(IMPORT, encoding="utf-8")
    r = api.import_fountain(str(src))["imported"]
    assert r["filled"] == []                      # author and contact were already set by make_script
    fresh = Project.create(tmp_path / "fresh", "Fresh", "script")
    got = fountainio.import_into(fresh, IMPORT, "in.fountain")
    assert got["filled"] == ["author", "contact"]
    info = Project.open(tmp_path / "fresh").author_info()
    assert info["author"] == "Pat Example" and info["contact"] == "pat@example.com"


def test_import_into_an_empty_flat_project_stays_flat(tmp_path):
    p = Project.create(tmp_path / "f", "F", "script")
    (p.manuscript_dir / "01-opening.md").unlink()
    got = fountainio.import_into(p, "INT. A - DAY\n\nHi.\n\nINT. B - DAY\n\nHo.\n")
    assert got["scenes"] == 2 and got["parts"] == 0
    assert [s.name for s in p.list_scenes()] == ["01-int-a-day.md", "02-int-b-day.md"]


def test_import_refuses_what_it_cannot_use(tmp_path):
    api, root = open_script(tmp_path)
    empty = tmp_path / "e.fountain"
    empty.write_text("Title: Nothing\n\n", encoding="utf-8")
    r = api.import_fountain(str(empty))
    assert not r["ok"] and "no scenes" in r["error"]
    assert not api.import_fountain(str(tmp_path / "missing.fountain"))["ok"]
    big = tmp_path / "big.fountain"
    big.write_bytes(b"x" * (fountainio.MAX_BYTES + 1))
    assert "larger" in api.import_fountain(str(big))["error"]
    from tests.gui_helpers import make_project
    make_project(tmp_path / "novel")
    story = Api()
    story.open_project(str(tmp_path / "novel"))
    r = story.import_fountain(str(tmp_path / "in.fountain"))
    assert not r["ok"] and "script projects" in r["error"]


def test_import_reads_a_bom_and_windows_1252(tmp_path):
    p = Project.create(tmp_path / "f", "F", "script")
    assert "INT. CAFÉ - DAY" in fountainio.read_file(_write(tmp_path / "a.fountain", b"\xef\xbb\xbfINT. CAF\xc3\x89 - DAY\n"))
    assert "INT. CAFÉ - DAY" in fountainio.read_file(_write(tmp_path / "b.fountain", "INT. CAFÉ - DAY\n".encode("cp1252")))
    assert p.mode == "script"


def _write(path, data):
    path.write_bytes(data)
    return path


def test_the_picker_is_not_used_without_a_window(tmp_path):
    api, _ = open_script(tmp_path)
    r = api.import_fountain()
    assert not r["ok"] and "desktop window" in r["error"]


def test_import_method_is_a_bridge_method():
    assert hasattr(Api().facade(), "import_fountain")


# -- the round trip through the files on disk ----------------------------------------------------------


def test_export_then_import_keeps_the_scenes(tmp_path):
    from chisel.core import export as exp
    from chisel.core.export.manuscript import ExportOptions
    project = make_script(tmp_path / "a")
    out = exp.run_export(project, ExportOptions(format="fountain")).path.read_text(encoding="utf-8")
    other = Project.create(tmp_path / "b", "B", "script")
    (other.manuscript_dir / "01-opening.md").unlink()
    got = fountainio.import_into(other, out)
    assert got["scenes"] == 2 and got["parts"] == 1
    titles = [s["title"] for s in ws.scene_summaries(Project.open(tmp_path / "b"))]
    assert titles == ["Kitchen", "The garden at night"]
    kitchen = next(p for p in Project.open(tmp_path / "b").list_scenes()).read_text(encoding="utf-8")
    assert "<!-- remember the toast -->" in kitchen and "KEITH\n(to the toast)\nBurnt again, see me." in kitchen
    assert KITCHEN.split("\n")[0] == "---"      # (the source scene kept its details; they are not exported)
