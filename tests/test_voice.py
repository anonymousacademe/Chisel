"""Learning the author's voice: style-guide provenance, the "Your style"
status, and the author's own prose sent as examples when drafting."""

from pathlib import Path

from chisel.ai.style import build_proposal
from chisel.ai.writing import build_context
from chisel.core import drafts
from chisel.core import entities as ent
from chisel.core.project import Project
from chisel.core.style import (
    learned_note,
    manuscript_stats,
    save_style,
    select_voice_samples,
    style_info,
    style_markdown,
)
from chisel.gui import api as api_module
from tests.test_gui_api import open_api

FILLER = "The rain kept on against the glass while the city hummed below them"


def para(*words: str, quote: str = "") -> str:
    """A >=25-word paragraph mentioning *words*, optionally with dialogue."""
    body = " ".join(words) + " " + FILLER + " and nothing in the night would answer."
    return (f'"{quote}" ' if quote else "") + body


def make(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "book", title="Voice")
    (proj.manuscript_dir / "01-opening.md").unlink()
    ent.add_alias(proj.create_entity("Rook Tanaka")[0], "Rook")
    proj.create_entity("Kuroda")
    proj.create_entity("Hollow Market", "place")
    scenes = {
        "01-bar.md": [para("Rook sat at the bar."), para("Hollow Market smelled of rain.")],
        "02-call.md": [para("Kuroda called.", quote="Come now, Tanaka, bring your ghost"),
                       para("Nobody in particular walked past.")],
        "03-stairs.md": [para("Rook and Kuroda met on the stairs.", quote="You were up there a long time")],
    }
    for name, paras in scenes.items():
        (proj.manuscript_dir / name).write_text(
            f"# {name}\n\n" + "\n\n".join(paras) + "\n", encoding="utf-8")
    return Project.open(proj.root)


# -- provenance and status ----------------------------------------------------------


def test_learned_note_roundtrips_through_style_info(tmp_path):
    proj = make(tmp_path)
    assert style_info(proj)["exists"] is False
    words, scenes = manuscript_stats(proj)
    note = learned_note(1234, (words, scenes), "2026-09-30")
    save_style(proj, style_markdown({"voice": "Close third."}, "", note))
    info = style_info(proj)
    assert info["exists"] and info["learned"] == "2026-09-30"
    assert info["sampledWords"] == 1234 and info["manuscriptWordsThen"] == words
    assert info["stale"] is False
    assert "<!-- learned 2026-09-30 from 1,234 sampled words;" in (proj.root / "style.md").read_text()


def test_style_goes_stale_when_the_manuscript_grows(tmp_path):
    proj = make(tmp_path)
    save_style(proj, style_markdown({}, "", learned_note(500, (400, 3), "2026-01-01")))
    (proj.manuscript_dir / "04-more.md").write_text(
        "# More\n\n" + ("word " * 2000) + "\n", encoding="utf-8")
    assert style_info(proj)["stale"] is True


def test_hand_written_guide_has_no_learned_date(tmp_path):
    proj = make(tmp_path)
    save_style(proj, "# Style guide\n\nTerse.\n")
    info = style_info(proj)
    assert info["exists"] and info["learned"] is None and info["stale"] is False


def test_build_proposal_writes_the_learned_note():
    samples = [("manuscript/01.md", para("Rook."))]
    note = learned_note(30, (900, 4), "2026-09-30")
    md = build_proposal({"voice": "Close third.", "exemplar_indexes": [0]}, samples, note).markdown
    assert md.startswith("# Style guide\n\n<!-- learned 2026-09-30 from 30 sampled words;"
                         " manuscript 900 words in 4 scenes -->")


def test_pending_drafts_do_not_count_as_manuscript_words(tmp_path):
    proj = make(tmp_path)
    before = manuscript_stats(proj)[0]
    path = proj.manuscript_dir / "01-bar.md"
    path.write_text(path.read_text() + "\n" + drafts.wrap("ten more words " * 4) + "\n")
    assert manuscript_stats(proj)[0] == before


# -- the author's own prose as drafting examples -------------------------------------


def test_voice_samples_come_from_other_scenes_and_prefer_shared_characters(tmp_path):
    proj = make(tmp_path)
    ents = proj.load_entities()
    current = proj.manuscript_dir / "03-stairs.md"
    picks = select_voice_samples(proj, current, current.read_text(), ents, budget_words=40)
    assert picks, "something is always chosen"
    assert all(rel != "manuscript/03-stairs.md" for rel, _ in picks)
    # Kuroda + dialogue, like the stairs scene, beats the unrelated paragraph
    assert "Kuroda called." in picks[0][1]


def test_voice_samples_respect_the_budget_and_keep_manuscript_order(tmp_path):
    proj = make(tmp_path)
    current = proj.manuscript_dir / "03-stairs.md"
    picks = select_voice_samples(proj, current, current.read_text(),
                                 proj.load_entities(), budget_words=10_000)
    rels = [rel for rel, _ in picks]
    assert rels == sorted(rels) and len(picks) == 4
    small = select_voice_samples(proj, current, current.read_text(),
                                 proj.load_entities(), budget_words=35)
    assert len(small) == 1


def test_voice_samples_never_include_pending_ai_text(tmp_path):
    proj = make(tmp_path)
    other = proj.manuscript_dir / "01-bar.md"
    other.write_text(other.read_text() + "\n" + drafts.wrap(para("AIWROTE Rook.")) + "\n")
    current = proj.manuscript_dir / "03-stairs.md"
    picks = select_voice_samples(proj, current, current.read_text(), proj.load_entities())
    assert not any("AIWROTE" in p for _, p in picks)


def test_one_scene_project_uses_the_rest_of_that_scene(tmp_path):
    proj = Project.create(tmp_path / "solo", title="Solo")
    only = proj.manuscript_dir / "01-opening.md"
    only.write_text("# Solo\n\n" + para("The first paragraph of the only scene.") + "\n\n" + para("The second paragraph of the only scene.") + "\n")
    picks = select_voice_samples(proj, only, only.read_text(), [])
    assert len(picks) == 2


def test_build_context_includes_voice_samples_only_when_given():
    samples = [("manuscript/01.md", "She walked. The rain walked with her.")]
    with_v = build_context("# S\n\nText.", 9, [], {}, None, voice_samples=samples)
    without = build_context("# S\n\nText.", 9, [], {}, None)
    assert "THE AUTHOR'S OWN PROSE" in with_v and "The rain walked with her." in with_v
    assert "THE AUTHOR'S OWN PROSE" not in without
    assert with_v.index("THE AUTHOR'S OWN PROSE") < with_v.index("SCENE (")


# -- GUI bridge ----------------------------------------------------------------------


def test_gui_style_status_and_generate_sends_voice_samples(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    status = api.style_status()
    assert status["ok"] and status["exists"] is False and status["manuscriptWords"] > 0
    seen = {}

    def fake_generate(mode, instruction, context, model, selection=None, **kw):
        seen["context"] = context
        return "He smiled."

    monkeypatch.setattr(api_module, "generate_text", fake_generate)
    scene = "manuscript/02-the-archive.md"
    text = (root / scene).read_text()
    assert api.generate("draft", "a smile", scene, text, len(text), len(text))["ok"]
    assert "THE AUTHOR'S OWN PROSE" in seen["context"]
    assert (root / scene).read_text() == text
