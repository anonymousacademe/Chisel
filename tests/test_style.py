"""Style guide: sampling, proposal -> Markdown, save/backup, TUI flow (mocked AI)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import chisel.tui.app as app_mod
from chisel.ai.style import (
    StyleProposal,
    build_proposal,
    learn_style,
    parse_reply,
    validate_indexes,
)
from chisel.core import style as style_mod
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.stylereview import StyleReviewScreen


def para(tag: str, words: int = 30) -> str:
    return " ".join(f"{tag}{i}" for i in range(words))


def _scene(proj: Project, name: str, paragraphs: list[str], title="T") -> Path:
    path = proj.manuscript_dir / name
    path.write_text(f"# {title}\n\n" + "\n\n".join(paragraphs) + "\n")
    return path


@pytest.fixture
def proj(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", title="Style")
    (p.manuscript_dir / "01-opening.md").unlink()
    return p


# -- sampling -------------------------------------------------------------------------


def test_sampling_skips_headings_and_short_paragraphs(proj):
    _scene(proj, "01-a.md", ["Too short to count.", para("a"), para("b", 26)])
    samples = style_mod.sample_manuscript(proj)
    texts = [p for _, p in samples]
    assert para("a") in texts and para("b", 26) in texts
    assert all(len(t.split()) >= 25 for t in texts)
    assert not any(t.startswith("#") for t in texts)


def test_sampling_skips_heading_blocks_even_when_long(proj):
    long_heading = "# " + " ".join("word" for _ in range(40))
    path = proj.manuscript_dir / "01-a.md"
    path.write_text(long_heading + "\n\n" + para("p") + "\n")
    assert [p for _, p in style_mod.sample_manuscript(proj)] == [para("p")]


def test_sampling_spreads_across_scenes_and_stays_in_budget(proj):
    for n in range(1, 6):
        _scene(proj, f"0{n}-s.md", [para(f"s{n}p{i}") for i in range(20)])
    samples = style_mod.sample_manuscript(proj, max_words=600)
    words = sum(len(p.split()) for _, p in samples)
    assert words <= 600
    scenes = {rel for rel, _ in samples}
    assert len(scenes) == 5  # every scene represented
    # within a scene, picks come from beginning to end, not just the start
    first = [p for rel, p in samples if rel.endswith("01-s.md")]
    assert len(first) >= 2
    assert first[0].startswith("s1p0") and not first[-1].startswith("s1p1 ")


def test_sampling_many_scenes_tiny_budget_still_bounded(proj):
    for n in range(1, 10):
        _scene(proj, f"0{n}-s.md", [para(f"s{n}")])
    samples = style_mod.sample_manuscript(proj, max_words=100)
    assert 1 <= len(samples)
    assert sum(len(p.split()) for _, p in samples) <= 100


def test_sampling_empty_project(proj):
    assert style_mod.sample_manuscript(proj) == []


# -- exemplars & markdown --------------------------------------------------------------


def test_exemplars_section_blockquotes_with_source_filename():
    samples = [("manuscript/01-a.md", "First line\nsecond line"),
               ("manuscript/02-b.md", "Other paragraph")]
    out = style_mod.exemplars_section(samples, [1, 0])
    assert out.startswith("## Exemplars")
    assert "> Other paragraph\n>\n> — 02-b.md" in out
    assert "> First line\n> second line\n>\n> — 01-a.md" in out


def test_exemplars_ignore_bad_and_duplicate_indexes():
    samples = [("manuscript/01-a.md", "Only one")]
    out = style_mod.exemplars_section(samples, [5, -1, 0, 0, True, "x"])
    assert out.count("> Only one") == 1


def test_proposal_to_markdown_has_all_sections():
    samples = [("manuscript/01-a.md", para("a")), ("manuscript/02-b.md", para("b"))]
    data = {"voice": "- close third", "rhythm": "- short", "diction": "- plain",
            "dialogue": "- said only", "avoid": "- adverbs",
            "exemplar_indexes": [1]}
    proposal = build_proposal(data, samples)
    md = proposal.markdown
    for heading in ("## Voice", "## Rhythm & syntax", "## Diction", "## Dialogue",
                    "## Avoid", "## Exemplars"):
        assert heading in md
    assert "- close third" in md and "- adverbs" in md
    assert para("b") in md and para("a") not in md
    assert "— 02-b.md" in md


def test_bad_indexes_dropped():
    assert validate_indexes([0, 0, 7, -2, "1", 1.5, None, True, 1, 2, 3], 4) == [0, 1, 2]
    assert validate_indexes("nope", 4) == []
    samples = [("manuscript/a.md", para("a"))]
    proposal = build_proposal({"voice": "v", "exemplar_indexes": [9, 0]}, samples)
    assert proposal.exemplar_indexes == [0]


def test_parse_reply_tolerates_fences_and_chatter():
    assert parse_reply('{"a": 1}') == {"a": 1}
    assert parse_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_reply('Sure! Here it is: {"a": 1} Hope that helps') == {"a": 1}
    assert parse_reply("nothing") == {}
    assert parse_reply("[1]") == {}
    assert parse_reply(None) == {}


def _client(content: str, cost=0.01):
    seen = {}

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(cost=cost))

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions())), seen


def test_learn_style_with_fake_client_does_not_require_structured_outputs():
    from chisel.ai.usage import LEDGER

    samples = [("manuscript/01-a.md", para("a"))]
    reply = json.dumps({"voice": "v", "rhythm": "r", "diction": "d",
                        "dialogue": "q", "avoid": "x", "exemplar_indexes": [0]})
    client, seen = _client(reply)
    proposal = learn_style(samples, "some/model", client=client)
    assert isinstance(proposal, StyleProposal)
    assert seen["model"] == "some/model"
    assert "provider" not in seen["extra_body"]  # writing model may lack it
    assert seen["extra_body"]["usage"] == {"include": True}
    assert "[0] (manuscript/01-a.md)" in seen["messages"][1]["content"]
    assert LEDGER.session_total() == 0.01


def test_learn_style_errors():
    with pytest.raises(ValueError):
        learn_style([], "m", client=_client("{}")[0])
    with pytest.raises(ValueError):
        learn_style([("a.md", para("a"))], "m", client=_client("garbage")[0])


# -- save / backup / stub ---------------------------------------------------------------


def test_save_style_atomic_and_backup(proj):
    assert style_mod.load_style(proj) is None
    path = style_mod.save_style(proj, "first\n")
    assert path == proj.root / "style.md" and path.read_text() == "first\n"
    assert not (proj.root / "style.md.bak").exists()
    style_mod.save_style(proj, "second\n")
    assert path.read_text() == "second\n"
    assert (proj.root / "style.md.bak").read_text() == "first\n"
    assert not list(proj.root.glob("*.tmp"))
    assert style_mod.load_style(proj) == "second\n"


def test_load_style_blank_is_none(proj):
    (proj.root / "style.md").write_text("  \n")
    assert style_mod.load_style(proj) is None


def test_style_stays_out_of_cache_dir(proj):
    style_mod.save_style(proj, "x")
    assert style_mod.style_path(proj).parent == proj.root


# -- TUI ------------------------------------------------------------------------------------


def _fake_learn(samples, model, **kw):
    return build_proposal({"voice": "- close third", "rhythm": "r", "diction": "d",
                           "dialogue": "q", "avoid": "a", "exemplar_indexes": [0]},
                          samples)


async def test_open_style_guide_creates_stub_without_mention_highlighting(proj):
    proj.create_entity("Borin")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert not (proj.root / "style.md").exists()
        app.action_open_style_guide()
        await pilot.pause()
        assert app.current_path == proj.root / "style.md"
        assert (proj.root / "style.md").read_text().startswith("# Style guide")
        assert "## Exemplars" in app.editor.text
        assert app.editor.mention_names == []  # not a scene
        app.editor.insert("Borin ")
        app.save_current()
        rows = app.idx._conn.execute(
            "SELECT count(*) FROM links WHERE source = 'style.md'").fetchone()[0]
        assert rows == 0  # not indexed


async def test_learn_style_flow_saves_with_backup(proj, monkeypatch):
    _scene(proj, "01-a.md", [para("a"), para("b")])
    (proj.root / "style.md").write_text("OLD GUIDE\n")
    monkeypatch.setattr(app_mod, "learn_style", _fake_learn)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_learn_style()
        await pilot.pause(1.0)
        assert isinstance(app.screen, StyleReviewScreen)
        assert app.screen._replacing is True
        assert (proj.root / "style.md").read_text() == "OLD GUIDE\n"  # not yet
        await pilot.press("enter")
        await pilot.pause()
    text = (proj.root / "style.md").read_text()
    assert "- close third" in text and "## Exemplars" in text
    assert (proj.root / "style.md.bak").read_text() == "OLD GUIDE\n"


async def test_learn_style_discard_writes_nothing(proj, monkeypatch):
    _scene(proj, "01-a.md", [para("a")])
    monkeypatch.setattr(app_mod, "learn_style", _fake_learn)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_learn_style()
        await pilot.pause(1.0)
        assert isinstance(app.screen, StyleReviewScreen)
        await pilot.press("escape")
        await pilot.pause()
    assert not (proj.root / "style.md").exists()


async def test_learn_style_without_prose_warns(proj, monkeypatch):
    called = []
    monkeypatch.setattr(app_mod, "learn_style",
                        lambda *a, **k: called.append(1))
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_learn_style()
        await pilot.pause()
    assert not called and any("Nothing to learn" in m for m in notified)


async def test_learn_style_failure_notifies(proj, monkeypatch):
    _scene(proj, "01-a.md", [para("a")])

    def boom(samples, model):
        raise RuntimeError("No OpenRouter API key")

    monkeypatch.setattr(app_mod, "learn_style", boom)
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_learn_style()
        await pilot.pause(1.0)
    assert any("Style guide failed" in m for m in notified)


async def test_style_actions_in_palette(proj):
    from chisel.tui.commands import ActionProvider

    titles = [t for t, _, _ in ActionProvider.ACTIONS]
    assert "AI: learn style guide from manuscript" in titles
    assert "Open style guide" in titles


async def test_style_review_renders_bullet_lists_at_natural_height(proj):
    # a bare `Horizontal { height: 1fr }` app rule once inflated Markdown list
    # items so only the first bullet of the preview was visible
    md = "# Style guide\n\n## Voice\n\n- one\n- two\n- three\n\n## Diction\n\n- four\n"
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(StyleReviewScreen(md, False))
        await pilot.pause(1.0)
        lists = list(app.screen.query("MarkdownBulletList"))
        assert len(lists) == 2
        assert [lst.size.height for lst in lists] == [3, 1]
