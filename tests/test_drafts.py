"""Pending AI text: core marking mechanism + editor styling + f7/f8 + counts."""

from pathlib import Path

import pytest

from lorewrite.core import drafts
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp, _word_count

# -- core ---------------------------------------------------------------------------


def test_wrap_insertion_and_find():
    text = "Before. " + drafts.wrap("Generated line.") + " After."
    assert "<!--ai-->Generated line.<!--/ai-->" in text
    (p,) = drafts.find_pending(text)
    assert text[p.body_start:p.body_end] == "Generated line."
    assert p.original is None
    assert text[p.start:p.end] == "<!--ai-->Generated line.<!--/ai-->"


def test_wrap_replacement_roundtrips_original():
    original = "Naïve café — “quoted” 日本語 -->"
    wrapped = drafts.wrap("New text", original)
    text = f"a {wrapped} b"
    (p,) = drafts.find_pending(text)
    assert p.original == original
    assert "-->" not in wrapped.split('replaces="')[1].split('"')[0]  # base64 only
    assert drafts.reject(text, p) == f"a {original} b"
    assert drafts.accept(text, p) == "a New text b"


def test_accept_and_reject_insertion():
    text = "x " + drafts.wrap("hello") + " y"
    (p,) = drafts.find_pending(text)
    assert drafts.accept(text, p) == "x hello y"
    assert drafts.reject(text, p) == "x  y"


def test_multiple_drafts_and_accept_all_reject_all():
    text = ("A " + drafts.wrap("one") + " B " + drafts.wrap("two", "TWO ORIG")
            + " C " + drafts.wrap("three") + " D")
    assert len(drafts.find_pending(text)) == 3
    assert drafts.accept_all(text) == "A one B two C three D"
    assert drafts.reject_all(text) == "A  B TWO ORIG C  D"
    assert drafts.strip_pending(text) == drafts.reject_all(text)


def test_multiline_body_and_original():
    text = "top\n" + drafts.wrap("l1\nl2\n\nl3", "o1\no2") + "\nbottom"
    (p,) = drafts.find_pending(text)
    assert text[p.body_start:p.body_end] == "l1\nl2\n\nl3"
    assert drafts.reject(text, p) == "top\no1\no2\nbottom"


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
    '<!--ai replaces="!!!not base64!!!">-->x<!--/ai-->',
    '<!--ai replaces="/w==">-->x<!--/ai-->',   # bad utf-8 payload / attr shape
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


def test_corrupt_replaces_payload_left_as_plain_text():
    text = '<!--ai replaces="@@@@">x<!--/ai-->'
    assert drafts.find_pending(text) == []
    assert drafts.strip_pending(text) == text


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


def _scene(proj: Project, body: str) -> Path:
    path = proj.manuscript_dir / "02-scene.md"
    path.write_text(body, encoding="utf-8")
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
    app = LorewriteApp(project)
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
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        assert "{{expand: the rain}}" in _styled(app, 2, _faded(app))


async def test_f7_accepts_and_f8_rejects_draft_under_cursor(project):
    body = "# S\n\nOne " + drafts.wrap("alpha") + " two " + drafts.wrap("beta", "ORIG") + " end.\n"
    scene = _scene(project, body)
    app = LorewriteApp(project)
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
        assert app.editor.text.startswith("# S\n\nOne alpha two <!--ai replaces=")
        # cursor into the second draft, then reject: original restored
        line = app.editor.text.split("\n")[2]
        app.editor.move_cursor((2, line.index("beta") + 1))
        await pilot.pause()
        await pilot.press("f8")
        await pilot.pause()
        assert app.editor.text == "# S\n\nOne alpha two ORIG end.\n"
        assert app.editor.text.count("<!--") == 0
        # select-all moved to f5, f7 no longer selects everything
        await pilot.press("f7")
        await pilot.pause()
        assert app.editor.selected_text == ""


async def test_f5_selects_all(project):
    scene = _scene(project, "# S\n\ntext\n")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        await pilot.press("f5")
        await pilot.pause()
        assert app.editor.selected_text == app.editor.text


async def test_accept_all_and_reject_all_via_palette_methods(project):
    body = ("# S\n\nA " + drafts.wrap("one") + " B " + drafts.wrap("two", "TWO")
            + " C\n")
    scene = _scene(project, body)
    app = LorewriteApp(project)
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
            "lorewrite.tui.commands", fromlist=["ActionProvider"]).ActionProvider.ACTIONS]
        assert "Accept all AI drafts in this scene" in titles
        assert "Reject all AI drafts in this scene" in titles


async def test_no_draft_under_cursor_notifies(project, monkeypatch):
    scene = _scene(project, "# S\n\nplain\n")
    notified = []
    monkeypatch.setattr(LorewriteApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    app = LorewriteApp(project)
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
    app = LorewriteApp(project)
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
    import lorewrite.tui.app as app_mod

    seen = {}

    def fake(text, entities, model):
        seen["text"] = text
        return []

    monkeypatch.setattr(app_mod, "suggest_links", fake)
    scene = _scene(project, "# S\n\nBorin sat. " + drafts.wrap("SECRET DRAFT") + "\n")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_find_aliases()
        await pilot.pause(1.0)
    assert "SECRET DRAFT" not in seen["text"] and "<!--" not in seen["text"]


def test_style_sampling_ignores_pending(tmp_path):
    from lorewrite.core.style import sample_manuscript

    proj = Project.create(tmp_path / "n", title="N")
    para = " ".join(f"w{i}" for i in range(30))
    (proj.manuscript_dir / "01-opening.md").write_text(
        "# S\n\n" + para + "\n\n" + drafts.wrap(para.replace("w", "GHOST")) + "\n")
    texts = [p for _, p in sample_manuscript(proj)]
    assert texts == [para]


async def test_teardown_with_pending_draft_does_not_crash(project):
    scene = _scene(project, "# S\n\ntext " + drafts.wrap("draft") + "\n")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.editor.move_cursor((2, 4))
        await pilot.press("x")  # dirty buffer -> pending autosave at teardown
    assert "<!--ai-->draft<!--/ai-->" in scene.read_text()
