"""Wave F0: create_table / create_equation / update_object / trash_object / object_references /
object_suggest_label, the Figures / Tables / Equations binder groups and the placement / objref spans."""

import pytest

from chisel.core import objects
from chisel.core.project import Project
from chisel.core.spans import compute_spans, to_utf16
from chisel.gui.api import Api
from chisel.gui.workspace import build_workspace
from tests.research_helpers import clear_starter

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"


@pytest.fixture
def rp(tmp_path):
    project = clear_starter(Project.create(tmp_path / "paper", "Paper", "research"))
    api = Api()
    api._load(project)
    return api, project


def write_scene(project, text, name="01-a.md"):
    project.manuscript_dir.mkdir(exist_ok=True)
    p = project.manuscript_dir / name
    p.write_text("# A\n\n" + text, encoding="utf-8", newline="\n")
    return p


def spans(api, text):
    return api.link_spans("manuscript/01-a.md", text)["spans"]


# -- create_table ------------------------------------------------------------------------------


def test_create_table_canonical_and_listed(rp):
    api, project = rp
    r = api.create_table("results", "Main | results", [["a", "b"], ["1", "2"]], ["left", "right"])
    assert r["ok"] and r["id"] == "tbl:results" and r["object"]["caption"] == "Main | results"
    text = (project.root / "tables" / "tbl-results.md").read_text(encoding="utf-8")
    assert "| a | b |\n| :--- | ---: |\n| 1 | 2 |" in text
    assert api.read_table("tbl:results")["cells"] == [["a", "b"], ["1", "2"]]


def test_create_table_defaults_align_and_pads_rows(rp):
    api, project = rp
    assert api.create_table("t", "c", [["a", "b"], ["1"]], [])["ok"]
    assert api.read_table("tbl:t")["cells"] == [["a", "b"], ["1", ""]]


def test_create_table_caps_and_errors(rp):
    api, project = rp
    assert not api.create_table("t", "c", [["a"]] * 201, ["default"])["ok"]
    assert not api.create_table("t", "c", [["a"] * 31], ["default"] * 31)["ok"]
    assert not api.create_table("t", "c", [["x" * 2001]], ["default"])["ok"]
    assert api.create_table("t", "c", [["x" * 2000]] * 200, ["default"])["ok"]
    assert not api.create_table("t2", "c", [["a", "b"]], ["default"])["ok"]       # more cells than columns
    assert not api.create_table("t2", "c", [["a"]], ["wide"])["ok"]               # bad alignment
    assert not api.create_table("t2", "c", [], ["default"])["ok"]
    assert not api.create_table("bad label", "c", [["a"]], ["default"])["ok"]
    assert not api.create_table("../x", "c", [["a"]], ["default"])["ok"]
    assert not (project.root / "tables" / "tbl-t2.md").exists()


def test_create_table_never_overwrites(rp):
    api, project = rp
    assert api.create_table("t", "first", [["a"]], ["default"])["ok"]
    r = api.create_table("t", "second", [["z"]], ["default"])
    assert not r["ok"] and "already exists" in r["error"]
    assert "first" in (project.root / "tables" / "tbl-t.md").read_text(encoding="utf-8")


# -- create_equation ---------------------------------------------------------------------------


def test_create_equation(rp):
    api, project = rp
    r = api.create_equation("energy", r"E = mc^2", "Mass-energy")
    assert r["ok"] and r["id"] == "eq:energy"
    assert api.object_render(["eq:energy"])["objects"][0]["latex"] == "E = mc^2"
    assert r["object"]["caption"] == "Mass-energy"
    assert api.create_equation("plain", "x").get("ok")
    text = (project.root / "equations" / "eq-plain.md").read_text(encoding="utf-8")
    assert "caption" not in text


def test_create_equation_errors_and_cap(rp):
    api, project = rp
    assert not api.create_equation("e", "   ")["ok"]
    assert not api.create_equation("e", "x" * 10_001)["ok"]
    assert api.create_equation("e", "x" * 10_000)["ok"]
    r = api.create_equation("e", "y")
    assert not r["ok"] and "already exists" in r["error"]
    assert not api.create_equation("a b", "y")["ok"]


def test_markers_stripped_from_caption_alt_and_latex(rp):
    api, project = rp
    api.create_equation("m", r"a <!-- x --> \frac{{1}}{2} <!<!---->--", "cap <!--ai--> {{expand: x}}\nline")
    obj = api.object_render(["eq:m"])["objects"][0]
    for bad in ("<!--", "-->", "{{", "}}"):
        assert bad not in obj["latex"] and bad not in obj["caption"]
    assert "\n" not in obj["caption"]
    assert r"\frac" in obj["latex"]
    assert objects.clean_line("a <!<!---->-- b {{{x}}}") == "a b {x}"


# -- update_object -----------------------------------------------------------------------------


def test_update_figure_keeps_other_keys(rp):
    api, project = rp
    objects.create_figure(project, PNG, "flow", "Old")
    md = project.root / "figures" / "fig-flow.md"
    md.write_text(md.read_text(encoding="utf-8") + "", encoding="utf-8", newline="\n")
    text = md.read_text(encoding="utf-8").replace("---\n", "---\nsource: static\nextra: [1, 2]\n", 1)
    md.write_text(text + "notes here\n", encoding="utf-8", newline="\n")
    r = api.update_object("fig:flow", caption="New <!--c--> one", alt="A flow", width=6.5)
    assert r["ok"] and r["object"]["caption"] == "New c one" and r["object"]["width"] == 6.5
    after = md.read_text(encoding="utf-8")
    assert "extra:" in after and "- 1" in after and "file: figures/fig-flow.png" in after and after.endswith("notes here\n")
    assert api.update_object("fig:flow", alt="")["object"]["alt"] == ""
    assert "alt:" not in md.read_text(encoding="utf-8")


@pytest.mark.parametrize("width", [0.5, 21, "wide", float("nan")])
def test_update_figure_width_range(rp, width):
    api, project = rp
    objects.create_figure(project, PNG, "flow", "Old")
    assert not api.update_object("fig:flow", width=width)["ok"]


def test_update_equation_and_table(rp):
    api, project = rp
    api.create_equation("e", "a", "")
    r = api.update_object("eq:e", latex="b = 2", caption="Why")
    assert r["ok"] and api.object_render(["eq:e"])["objects"][0]["latex"] == "b = 2"
    api.create_table("t", "old", [["a"], ["1"]], ["default"])
    assert api.update_object("tbl:t", caption="new")["object"]["caption"] == "new"
    assert api.read_table("tbl:t")["cells"] == [["a"], ["1"]]
    assert not api.update_object("tbl:t", latex="x")["ok"]
    assert not api.update_object("eq:e", width=3)["ok"]
    assert not api.update_object("fig:nope", caption="x")["ok"]


# -- trash_object ------------------------------------------------------------------------------


def test_trash_object_round_trip_with_image_and_csv(rp):
    api, project = rp
    objects.create_figure(project, PNG, "flow", "The flow")
    api.create_table("t", "T", [["a"], ["1"]], ["default"])
    (project.root / "tables" / "tbl-t.csv").write_text("a\n1\n", encoding="utf-8", newline="\n")
    write_scene(project, "![[fig:flow]]\n\nSee [[tbl:t]].\n")
    r = api.trash_object("fig:flow")
    assert r == {"ok": True, "trashed": True, "name": "The flow"}
    assert not (project.root / "figures" / "fig-flow.png").exists()
    assert "![[fig:flow]]" in (project.manuscript_dir / "01-a.md").read_text(encoding="utf-8")
    assert api.trash_object("tbl:t")["ok"]
    assert not api.trash_object("tbl:t")["ok"]
    items = project.list_trash()
    assert sorted(i.kind for i in items) == ["object", "object"]
    for item in items:
        project.restore_scene(item.name)
    assert (project.root / "figures" / "fig-flow.png").read_bytes() == PNG
    assert (project.root / "tables" / "tbl-t.csv").read_text(encoding="utf-8") == "a\n1\n"
    assert sorted(o["id"] for o in api.list_objects()["objects"]) == ["fig:flow", "tbl:t"]


# -- object_references -------------------------------------------------------------------------


def test_object_references_book_only(rp):
    api, project = rp
    api.create_equation("e", "x")
    write_scene(project, "![[eq:e]]\n\nText with [[eq:e]] here.\n\n`[[eq:e]]`\n", "01-a.md")
    write_scene(project, "Again [[eq:e]]\n", "02-b.md")
    unplaced = project.manuscript_dir / "_unplaced"
    unplaced.mkdir()
    (unplaced / "01-p.md").write_text("# P\n\n![[eq:e]]\n[[eq:e]] x\n", encoding="utf-8", newline="\n")
    r = api.object_references("eq:e")
    assert r["ok"]
    assert [(p["doc"], p["row"]) for p in r["placements"]] == [("manuscript/01-a.md", 2)]
    assert [(p["doc"], p["row"]) for p in r["refs"]] == [("manuscript/01-a.md", 4), ("manuscript/02-b.md", 2)]
    assert r["placements"][0]["title"] == "A"
    assert api.object_references("eq:missing")["ok"] is False


# -- object_suggest_label ----------------------------------------------------------------------


def test_suggest_label(rp):
    api, project = rp
    assert api.object_suggest_label("fig", "Flow rate vs. depth (m)")["label"] == "flow-rate-vs-depth-m"
    assert api.object_suggest_label("tbl", "")["label"] == "table"
    assert api.object_suggest_label("eq", "Über ∑")["label"] == "uber"
    api.create_equation("equation", "x")
    api.create_equation("equation-2", "x")
    assert api.object_suggest_label("eq", "")["label"] == "equation-3"
    assert api.object_suggest_label("eq", "x" * 100)["label"] == "x" * 40
    assert not api.object_suggest_label("zzz", "x")["ok"]
    assert objects._LABEL_RE.match(api.object_suggest_label("fig", "!!!")["label"])


def test_methods_refuse_story_projects(tmp_path):
    api = Api()
    api._load(Project.create(tmp_path / "s", "S", "story"))
    for r in (api.create_equation("e", "x"), api.create_table("t", "c", [["a"]], []),
              api.object_suggest_label("fig", "x"), api.trash_object("fig:x")):
        assert not r["ok"]


# -- binder ------------------------------------------------------------------------------------


def groups(project):
    ws = build_workspace(project, [], baseline_words=0, session_minutes=0, ai_cost=0)
    return [n for n in ws["binder"] if n["kind"] == "objects"], ws


def test_binder_groups_for_research(rp):
    api, project = rp
    ids = [n["id"] for n in groups(project)[0]]
    assert ids == []
    objects.create_figure(project, PNG, "a", "Alpha")
    objects.create_figure(project, PNG, "b", "")
    api.create_equation("e", "x")
    api.create_table("t", "Tab", [["a"]], ["default"])
    write_scene(project, "![[tbl:t]]\n\n![[fig:b]]\n\n![[fig:a]]\n")
    g, ws = groups(project)
    assert [(n["id"], n["title"]) for n in g] == [("group:figures", "Figures"), ("group:tables", "Tables"),
                                                  ("group:equations", "Equations")]
    figs = {c["id"]: c for c in g[0]["children"]}
    assert figs["fig:b"]["title"] == "Figure 1: b" and figs["fig:a"]["title"] == "Figure 2: Alpha"
    assert figs["fig:a"]["kind"] == "object" and figs["fig:a"]["meta"] == "current"
    assert g[1]["children"][0]["title"] == "Table 1: Tab"
    assert g[2]["children"][0]["title"] == "Equation: x" or g[2]["children"][0]["title"].startswith("Equation")
    kinds = [n["id"] for n in ws["binder"]]
    assert kinds.index("group:world") < kinds.index("group:figures") < kinds.index("group:style") \
        if "group:style" in kinds else True


def test_binder_has_no_object_groups_in_story_or_script(tmp_path):
    for mode in ("story", "script"):
        project = Project.create(tmp_path / mode, mode, mode)
        (project.root / "figures").mkdir()
        (project.root / "figures" / "fig-a.md").write_text("---\ncaption: x\n---\n", encoding="utf-8", newline="\n")
        g, ws = groups(project)
        assert g == [] and not any(n["id"].startswith("group:fig") for n in ws["binder"])


# -- spans -------------------------------------------------------------------------------------


def test_spans_resolved_unresolved_and_utf16(rp):
    api, project = rp
    api.create_equation("e", "x")
    objects.create_figure(project, PNG, "f", "F")
    text = "😀 intro [[fig:f]] and [[fig:zz]]\n\n![[eq:e]]\n\n![[fig:f]]\n"
    write_scene(project, text)
    got = [s for s in spans(api, text) if s["kind"] in ("placement", "objref")]
    assert [(s["kind"], s["key"], s["status"], s["display"]) for s in got] == [
        ("objref", "fig:f", "resolved", "Fig. 1"), ("objref", "fig:zz", "unresolved", "fig:zz"),
        ("placement", "eq:e", "resolved", "Eq. (1)"), ("placement", "fig:f", "resolved", "Fig. 1")]
    first = got[0]
    assert first["objectKind"] == "fig" and first["label"] == "f"
    assert text.encode("utf-16-le")[first["start"] * 2:first["end"] * 2].decode("utf-16-le") == "[[fig:f]]"
    assert not [s for s in got if s["kind"] == "objref" and s["key"] == "eq:e"]


def test_spans_ignore_code_midline_and_unplaced_numbering(rp):
    api, project = rp
    api.create_equation("e", "x")
    text = ("```\n![[eq:e]]\n[[eq:e]]\n```\n\ninline `[[eq:e]]` and `![[eq:e]]`\n\n"
            "text ![[eq:e]] mid\n\n![[eq:e]] \n")
    write_scene(project, text)
    got = [s for s in spans(api, text) if s["kind"] in ("placement", "objref")]
    assert [(s["kind"], s["start"] > 0) for s in got] == [("placement", True)]
    # mid-line "![[eq:e]]" is not a placement (and is not a reference either: the ! belongs to the link)
    assert got[0]["display"] == "Eq. (1)"
    # an object nobody places yet shows a question mark
    api.create_equation("lonely", "y")
    t2 = "see [[eq:lonely]]\n"
    write_scene(project, t2)
    assert [s["display"] for s in spans(api, t2) if s["kind"] == "objref"] == ["Eq. (?)"]


def test_spans_three_numbering_schemes(rp, monkeypatch):
    api, project = rp
    for lab in ("a", "b"):
        objects.create_figure(project, PNG, lab, lab)
    project.root.joinpath("project.toml")
    p1 = project.manuscript_dir / "01-one"
    p2 = project.manuscript_dir / "02-two"
    for p in (p1, p2):
        p.mkdir()
    (p1 / "01-s.md").write_text("# S\n\n![[fig:a]]\n", encoding="utf-8", newline="\n")
    (p2 / "01-s.md").write_text("# S\n\n![[fig:b]]\n", encoding="utf-8", newline="\n")
    text = "[[fig:a]] [[fig:b]]\n"
    out = {}
    for scheme in ("plain", "per-section", "supplementary"):
        monkeypatch.setattr(objects, "_scheme", lambda project, s, scheme=scheme: scheme)
        keys = {"fig:a", "fig:b"}
        nums = {k: n.display for k, n in objects.numbering(project).items()}
        out[scheme] = [s["display"] for s in compute_spans(text, [], object_info=(keys, nums))]
    assert out == {"plain": ["Fig. 1", "Fig. 2"], "per-section": ["Fig. 1.1", "Fig. 2.1"],
                   "supplementary": ["Fig. S1", "Fig. S2"]}


def test_spans_unchanged_without_object_info_and_for_story(tmp_path):
    text = "[[fig:f]] and ![[fig:f]]\n\n![[fig:f]]\n"
    assert not [s for s in compute_spans(text, []) if s["kind"] in ("placement", "objref")]
    story = Api()
    story._load(Project.create(tmp_path / "s", "S", "story"))
    sc = story.project.list_scenes()[0] if story.project.list_scenes() else None
    if sc is not None:
        got = story.link_spans(sc.relative_to(story.project.root).as_posix(), text)["spans"]
        assert not [s for s in got if s["kind"] in ("placement", "objref")]
    assert compute_spans("Keith [[Keith]]", [], object_info=None) == compute_spans("Keith [[Keith]]", [])
    assert to_utf16("x", []) == []


# -- review round: numbering ignores code, clean caption, limits, collisions, pixels, display ------------------


def _png(w, h):
    import struct
    import zlib

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff" * (3 * w) for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _jpg(w, h):
    import struct
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def test_numbering_ignores_fenced_placement(rp):
    api, project = rp
    objects.create_figure(project, PNG, "a", "A")
    objects.create_figure(project, PNG, "b", "B")
    write_scene(project, "```\n![[fig:a]]\n```\n\n![[fig:b]]\n")
    nums = objects.numbering(project)
    assert "fig:a" not in nums and nums["fig:b"].display == "1"
    assert objects.references(project, "fig", "a")["placements"] == []


def test_insert_figure_cleans_caption_and_label_limits(rp):
    api, project = rp
    from tests.test_gui_research_objects import url
    api.insert_figure(url(PNG), "c", "cap <!-- x --> {{y}}\nline2")
    cap = objects.list_objects(project)[0].caption
    assert "<!--" not in cap and "{{" not in cap and "\n" not in cap
    for r in (api.insert_figure(url(PNG), "x" * 300, ""), api.create_equation("x" * 300, "y"),
              api.create_table("x" * 300, "", [["a"]], ["default"])):
        assert not r["ok"] and "80 characters" in r["error"] and "Errno" not in r["error"]
    assert api.create_equation("x" * 80, "y")["ok"]


def test_stray_companion_is_refused_and_equation_without_caption_has_no_front_matter(rp):
    api, project = rp
    (project.root / "tables").mkdir(exist_ok=True)
    stray = project.root / "tables" / "tbl-z.csv"
    stray.write_text("a,b\n", encoding="utf-8", newline="\n")
    r = api.create_table("z", "", [["a"]], ["default"])
    assert not r["ok"] and "already exists" in r["error"]
    (project.root / "figures").mkdir(exist_ok=True)
    (project.root / "figures" / "fig-s.jpg").write_bytes(PNG)
    with pytest.raises(ValueError, match="already exists"):
        objects.create_figure(project, PNG, "s", "")
    api.create_equation("plain", "x+y")
    assert (project.root / "equations" / "eq-plain.md").read_text(encoding="utf-8") == "x+y\n"


def test_table_limits_are_one_set(rp):
    api, project = rp
    api.create_table("t", "c", [["a", "b"], ["1", "2"]], ["default", "default"])
    t = api.read_table("tbl:t")
    for cells, align in (([["a"]] * 201, ["default"]), ([["a"] * 31], ["default"] * 31), ([["x" * 2001]], ["default"])):
        r = api.save_table("tbl:t", cells, align, t["mtime"])
        assert not r["ok"]
    assert api.save_table("tbl:t", [["x" * 2000]] * 200, ["default"], t["mtime"])["ok"]


def test_restored_figure_under_new_name_points_at_its_own_image(rp):
    api, project = rp
    objects.create_figure(project, PNG, "b", "old")
    project.trash_object("figures/fig-b.md")
    objects.create_figure(project, PNG, "b", "new")
    item = project.list_trash()[0]
    final = project.restore_scene(item.name)
    assert final.name == "fig-b-2.md"
    text = final.read_text(encoding="utf-8")
    assert "fig-b-2.png" in text and "figures/fig-b.png" not in text


def test_object_render_images_false_mtime_and_pixels(rp):
    api, project = rp
    objects.create_figure(project, _png(3, 2), "p", "P")
    objects.create_figure(project, _jpg(7, 5), "j", "J")
    objects.create_figure(project, PNG, "g", "G")
    api.create_equation("e", "x")
    r = api.object_render(["fig:p", "fig:j", "fig:g", "eq:e"], images=False)["objects"]
    assert all("imageUrl" not in e for e in r)
    assert r[0]["pixels"] == [3, 2] and r[1]["pixels"] == [7, 5] and r[2]["pixels"] is None
    assert all(isinstance(e["mtime"], str) and e["mtime"].isdigit() for e in r)
    assert api.object_render(["fig:p"])["objects"][0]["imageUrl"].startswith("data:image/png")
    assert objects.image_size(b"\xff\xd8\xff garbage") is None and objects.image_size(b"") is None


def test_display_short_forms_and_latex_job():
    from chisel.core.spans import object_display
    assert [object_display("fig", "2"), object_display("tbl", "1"), object_display("eq", "3"),
            object_display("fig", None), object_display("tbl", None), object_display("eq", None)] == [
        "Fig. 2", "Table 1", "Eq. (3)", "Fig. ?", "Table ?", "Eq. (?)"]
    assert Api.AI_JOBS["latex"] == "suggest_latex"
