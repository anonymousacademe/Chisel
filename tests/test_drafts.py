"""Pending AI text: core marking mechanism + editor styling + f7/f8 + counts."""

from pathlib import Path

import pytest

from chisel.core import drafts
from chisel.core.project import Project
from chisel.tui.app import ChiselApp, _word_count

# -- core ---------------------------------------------------------------------------


def test_wrap_insertion_and_find():
    text = "Before. " + drafts.wrap("Generated line.") + " After."
    assert "<!--ai-->Generated line.<!--/ai-->" in text
    (p,) = drafts.find_pending(text)
    assert text[p.body_start:p.body_end] == "Generated line."
    assert p.id is None
    assert text[p.start:p.end] == "<!--ai-->Generated line.<!--/ai-->"


def test_wrap_replacement_roundtrips_original():
    original = "Naïve café — “quoted” 日本語 --> <!--ai-->"
    wrapped = drafts.wrap("New text", "k3f9q2")
    assert wrapped == '<!--ai id="k3f9q2"-->New text<!--/ai-->'
    text = f"a {wrapped} b"
    (p,) = drafts.find_pending(text)
    assert p.id == "k3f9q2"
    originals = {"k3f9q2": original}
    assert drafts.reject(text, p, originals) == f"a {original} b"
    assert drafts.accept(text, p) == "a New text b"


def test_reject_refuses_when_original_missing():
    text = "a " + drafts.wrap("New", "abc123") + " b"
    (p,) = drafts.find_pending(text)
    for originals in (None, {}, {"other1": "x"}):
        with pytest.raises(drafts.MissingOriginal):
            drafts.reject(text, p, originals)


def test_new_id_is_six_base36_and_unique():
    ids = set()
    for _ in range(200):
        i = drafts.new_id(ids)
        assert len(i) == 6 and i.isalnum() and i == i.lower()
        assert i not in ids
        ids.add(i)


def test_sidecar_roundtrip_atomic_and_deleted_when_empty(tmp_path):
    scene = tmp_path / "manuscript" / "01-a.md"
    drafts.add_original(tmp_path, scene, "aaaaaa", "one")
    drafts.add_original(tmp_path, scene, "bbbbbb", "two ü")
    path = tmp_path / ".drafts" / "manuscript__01-a.md.json"
    assert path.is_file() and not list(tmp_path.rglob("*.tmp"))
    assert drafts.load_originals(tmp_path, scene) == {"aaaaaa": "one", "bbbbbb": "two ü"}
    assert drafts.all_ids(tmp_path) == {"aaaaaa", "bbbbbb"}
    drafts.drop_original(tmp_path, scene, "aaaaaa")
    assert drafts.load_originals(tmp_path, scene) == {"bbbbbb": "two ü"}
    drafts.drop_original(tmp_path, scene, "bbbbbb")
    assert not path.exists()
    assert drafts.load_originals(tmp_path, scene) == {}


def test_sidecar_corrupt_file_reads_as_empty(tmp_path):
    scene = tmp_path / "01-a.md"
    (tmp_path / ".drafts").mkdir()
    (tmp_path / ".drafts" / "manuscript__01-a.md.json").write_text("{not json")
    assert drafts.load_originals(tmp_path, scene) == {}


def test_accept_and_reject_insertion():
    text = "x " + drafts.wrap("hello") + " y"
    (p,) = drafts.find_pending(text)
    assert drafts.accept(text, p) == "x hello y"
    assert drafts.reject(text, p) == "x  y"


def test_multiple_drafts_and_accept_all_reject_all():
    text = ("A " + drafts.wrap("one") + " B " + drafts.wrap("two", "abc123")
            + " C " + drafts.wrap("three") + " D")
    originals = {"abc123": "TWO ORIG"}
    assert len(drafts.find_pending(text)) == 3
    assert drafts.accept_all(text) == "A one B two C three D"
    assert drafts.reject_all(text, originals) == "A  B TWO ORIG C  D"
    assert drafts.strip_pending(text, originals) == drafts.reject_all(text, originals)
    # lenient view when the sidecar is gone: the replaced span is just dropped
    assert drafts.strip_pending(text) == "A  B  C  D"


def test_multiline_body_and_original():
    text = "top\n" + drafts.wrap("l1\nl2\n\nl3", "abc123") + "\nbottom"
    (p,) = drafts.find_pending(text)
    assert text[p.body_start:p.body_end] == "l1\nl2\n\nl3"
    assert drafts.reject(text, p, {"abc123": "o1\no2"}) == "top\no1\no2\nbottom"


def test_body_cannot_forge_markers():
    wrapped = drafts.wrap("evil <!--/ai--> and <!--ai--> more")
    text = "s " + wrapped + " e"
    found = drafts.find_pending(text)
    assert len(found) == 1
    assert drafts.accept(text, found[0]).startswith("s evil ")
    assert "<!--ai" not in drafts.accept(text, found[0])


@pytest.mark.parametrize("text", [
    "<!--ai-->never closed",
    "never opened<!--/ai-->",
    '<!--ai replaces="QUJD"-->x<!--/ai-->',    # the dropped base64 form
    '<!--ai id="TOOLONGID">x<!--/ai-->',
    "<!--ai <!--ai-->x<!--/ai-->",
    "<!-- ai -->x<!--/ai-->",
])
def test_malformed_markers_are_ignored_not_fatal(text):
    for p in drafts.find_pending(text):  # anything found must be well-formed
        assert text[p.body_start:p.body_end] is not None
    assert drafts.strip_pending(text) is not None  # no crash
    drafts.pending_at(text, 3)


def test_nested_outer_ignored_inner_is_pending():
    text = "<!--ai-->outer <!--ai-->inner<!--/ai--> tail<!--/ai-->"
    found = drafts.find_pending(text)
    assert [text[p.body_start:p.body_end] for p in found] == ["inner"]


def test_old_replaces_form_is_plain_text():
    text = '<!--ai replaces="QUJD"-->x<!--/ai-->'
    assert drafts.find_pending(text) == []
    assert drafts.strip_pending(text) == text


@pytest.mark.parametrize("bad", ["ABCDEF", "abc12", "abc1234", "ab-123", ""])
def test_ids_must_be_six_lowercase_base36(bad):
    text = f'<!--ai id="{bad}"-->x<!--/ai-->'
    assert drafts.find_pending(text) == []


def test_pending_at_edges_and_outside():
    text = "ab " + drafts.wrap("xyz") + " cd"
    (p,) = drafts.find_pending(text)
    assert drafts.pending_at(text, 0) is None
    assert drafts.pending_at(text, p.start) is p or drafts.pending_at(text, p.start) == p
    assert drafts.pending_at(text, p.body_start + 1) == p
    assert drafts.pending_at(text, p.end) == p
    assert drafts.pending_at(text, p.end + 2) is None


def test_expand_markers():
    text = "one {{expand: describe the rain}} two {{expand:x}} {{ expand: nope }}"
    found = drafts.find_expand_markers(text)
    assert [m.instruction for m in found] == ["describe the rain", "x"]
    assert text[found[0].start:found[0].end] == "{{expand: describe the rain}}"
    assert drafts.expand_marker_at(text, found[0].start + 3) == found[0]
    assert drafts.expand_marker_at(text, 0) is None


def test_word_count_excludes_pending_bodies():
    text = "one two " + drafts.wrap("many many many words here") + " three"
    assert _word_count(text) == 3
    assert _word_count("plain text here") == 3


# -- TUI ------------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="Drafts")
    proj.create_entity("Borin")
    return proj


def _scene(proj: Project, body: str, originals: dict | None = None) -> Path:
    path = proj.manuscript_dir / "02-scene.md"
    path.write_text(body, encoding="utf-8")
    for draft_id, original in (originals or {}).items():
        drafts.add_original(proj.root, path, draft_id, original)
    return path


def _faded(app):
    """Predicate for the editor's bracket/marker style (dim, or a theme color)."""
    ref = app.editor.bracket_style

    def matches(st) -> bool:
        if ref.color is not None:
            return st.color is not None and \
                st.color.get_truecolor() == ref.color.get_truecolor()
        return bool(st.dim)

    return matches


def _styled(app, row: int, predicate) -> str:
    strip = app.editor.render_line(row)
    return "".join(seg.text for seg in strip if seg.style and predicate(seg.style))


async def test_editor_styles_ai_body_and_fades_markers(project):
    text = "# S\n\nStart " + drafts.wrap("ghost prose") + " end.\n"
    scene = _scene(project, text)
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        ai_color = app.editor.ai_style.color.get_truecolor()
        got = _styled(app, 2, lambda st: st.italic and st.color
                      and st.color.get_truecolor() == ai_color)
        assert "ghost prose" in got
        assert "Start" not in got and "end." not in got
        dim = _styled(app, 2, _faded(app))
        assert "<!--ai-->" in dim and "<!--/ai-->" in dim


async def test_expand_marker_is_faded(project):
    scene = _scene(project, "# S\n\nA {{expand: the rain}} B\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        assert "{{expand: the rain}}" in _styled(app, 2, _faded(app))


async def test_f7_accepts_and_f8_rejects_draft_under_cursor(project):
    body = ("# S\n\nOne " + drafts.wrap("alpha") + " two "
            + drafts.wrap("beta", "abc123") + " end.\n")
    scene = _scene(project, body, {"abc123": "ORIG"})
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        text = app.editor.text
        first, second = drafts.find_pending(text)
        # cursor in the first draft's body
        row, col = 2, text.split("\n")[2].index("alpha") + 2
        app.editor.move_cursor((row, col))
        await pilot.pause()
        assert "AI draft — f7 accept · f8 reject" in app._status_text
        await pilot.press("f7")
        await pilot.pause()
        assert app.editor.text.startswith('# S\n\nOne alpha two <!--ai id="abc123"-->')
        # cursor into the second draft, then reject: original restored
        line = app.editor.text.split("\n")[2]
        app.editor.move_cursor((2, line.index("beta") + 1))
        await pilot.pause()
        await pilot.press("f8")
        await pilot.pause()
        assert app.editor.text == "# S\n\nOne alpha two ORIG end.\n"
        assert app.editor.text.count("<!--") == 0
        assert not list(project.root.glob(".drafts/*"))  # entry removed, file gone
        # select-all moved to f5, f7 no longer selects everything
        await pilot.press("f7")
        await pilot.pause()
        assert app.editor.selected_text == ""


async def test_f5_selects_all(project):
    scene = _scene(project, "# S\n\ntext\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        await pilot.press("f5")
        await pilot.pause()
        assert app.editor.selected_text == app.editor.text


async def test_accept_all_and_reject_all_via_palette_methods(project):
    body = ("# S\n\nA " + drafts.wrap("one") + " B " + drafts.wrap("two", "abc123")
            + " C\n")
    scene = _scene(project, body, {"abc123": "TWO"})
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.reject_all_drafts()
        await pilot.pause()
        assert app.editor.text == "# S\n\nA  B TWO C\n"
        app.editor.load_text(body)
        app.accept_all_drafts()
        await pilot.pause()
        assert app.editor.text == "# S\n\nA one B two C\n"
        titles = [t for t, _, _ in __import__(
            "chisel.tui.commands", fromlist=["ActionProvider"]).ActionProvider.ACTIONS]
        assert "Accept all AI drafts in this scene" in titles
        assert "Reject all AI drafts in this scene" in titles


async def test_no_draft_under_cursor_notifies(project, monkeypatch):
    scene = _scene(project, "# S\n\nplain\n")
    notified = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        before = app.editor.text
        await pilot.press("f7")
        await pilot.press("f8")
        await pilot.pause()
        assert app.editor.text == before
    assert sum("No AI draft" in m for m in notified) == 2


async def test_word_counts_in_status_exclude_pending(project):
    scene = _scene(project, "# S\n\nreal words " + drafts.wrap("ghost " * 20) + "\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.update_status()
        assert "4 words" in app._status_text  # "#", "S", "real", "words"
        app._recount_project_words()
        raw = sum(len(f.read_text().split()) for f in project.list_scenes())
        assert app._project_words == _word_count(
            "\n".join(f.read_text() for f in project.list_scenes()))
        assert app._project_words < raw  # the ghost words are excluded


async def test_ai_tools_ignore_pending_bodies(project, monkeypatch):
    import chisel.tui.app as app_mod

    seen = {}

    def fake(text, entities, model):
        seen["text"] = text
        return []

    monkeypatch.setattr(app_mod, "suggest_links", fake)
    scene = _scene(project, "# S\n\nBorin sat. " + drafts.wrap("SECRET DRAFT") + "\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_find_aliases()
        await pilot.pause(1.0)
    assert "SECRET DRAFT" not in seen["text"] and "<!--" not in seen["text"]


def test_style_sampling_ignores_pending(tmp_path):
    from chisel.core.style import sample_manuscript

    proj = Project.create(tmp_path / "n", title="N")
    para = " ".join(f"w{i}" for i in range(30))
    (proj.manuscript_dir / "01-opening.md").write_text(
        "# S\n\n" + para + "\n\n" + drafts.wrap(para.replace("w", "GHOST")) + "\n")
    texts = [p for _, p in sample_manuscript(proj)]
    assert texts == [para]


async def test_teardown_with_pending_draft_does_not_crash(project):
    scene = _scene(project, "# S\n\ntext " + drafts.wrap("draft") + "\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.editor.move_cursor((2, 4))
        await pilot.press("x")  # dirty buffer -> pending autosave at teardown
    assert "<!--ai-->draft<!--/ai-->" in scene.read_text()


# -- pending drafts are not mentions (index + alias finder line numbers) --------------


def test_blank_pending_keeps_length_newlines_and_offsets():
    text = "Borin sat.\n" + drafts.wrap("Elara\nspoke", "abc123") + " Borin left.\n"
    blanked = drafts.blank_pending(text)
    assert len(blanked) == len(text)
    assert [i for i, c in enumerate(blanked) if c == "\n"] == [
        i for i, c in enumerate(text) if c == "\n"]
    assert "Elara" not in blanked and "<!--" not in blanked
    assert blanked.index("Borin left") == text.index("Borin left")
    assert drafts.blank_pending("no drafts here") == "no drafts here"


def test_index_ignores_names_inside_pending_but_keeps_real_rows(tmp_path):
    from chisel.core import entities as ent
    from chisel.core.index import Index

    proj = Project.create(tmp_path / "n", title="N")
    proj.create_entity("Borin")
    proj.create_entity("Elara")
    scene = proj.manuscript_dir / "02-s.md"
    text = ("# S\n\nOpening line.\n\nElara "
            + drafts.wrap("Borin sneered.\nBorin again.", "abc123")
            + " walked.\n\nFinally Borin left.\n")
    scene.write_text(text)
    idx = Index(proj.index_path)
    idx.rebuild(proj)
    entities = {e.name: e for e in proj.load_entities()}
    borin = idx.backlinks(entities["Borin"])
    assert [(b.source, b.row) for b in borin
            if b.source.endswith("02-s.md")] == [("manuscript/02-s.md", 7)]
    assert text.split("\n")[7].startswith("Finally Borin")   # row is the real line
    elara = [b for b in idx.backlinks(entities["Elara"]) if b.source.endswith("02-s.md")]
    assert [b.row for b in elara] == [4]
    assert "<!--" not in elara[0].line and "Borin" not in elara[0].line
    idx.close()


async def test_alias_finder_line_numbers_match_the_file_with_drafts(project, monkeypatch):
    import chisel.tui.app as app_mod
    from chisel.ai.links import Suggestion

    def fake(text, entities, model):
        i = text.index("the old smith")
        return [Suggestion("Borin", i, i + 13, "the old smith")]

    monkeypatch.setattr(app_mod, "suggest_links", fake)
    body = ("# S\n\nFirst.\n" + drafts.wrap("a\nb\nc\nd", "abc123") + "\n\n"
            "Then the old smith spoke.\n")
    scene = _scene(project, body, {"abc123": "orig"})
    real_line = body.split("\n").index("Then the old smith spoke.") + 1
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_find_aliases()
        await pilot.pause(1.0)
        row = app.screen._row_text(0).plain
        assert f"line {real_line}:" in row, row
