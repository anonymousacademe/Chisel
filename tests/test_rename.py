"""core/rename.py: rename an entity everywhere, with preview, snapshots and undo."""

from pathlib import Path

import pytest

from chisel.core import comments, drafts, rename, snapshots
from chisel.core import entities as ent
from chisel.core.project import Project


@pytest.fixture(autouse=True)
def _clear_daily():
    snapshots._daily_done.clear()
    yield
    snapshots._daily_done.clear()


def make(tmp_path: Path) -> Project:
    project = Project.create(tmp_path / "book", "Book")
    (project.root / "manuscript" / "01-opening.md").unlink()
    return project


def scene(project: Project, name: str, text: str) -> Path:
    p = project.manuscript_dir / name
    p.write_text(text, encoding="utf-8")
    return p


def entity(project: Project, name: str, etype="character", aliases=()):
    e, _ = project.create_entity(name, etype)
    for a in aliases:
        ent.add_alias(e, a)
    return ent.load_entity(project.entity_path(e))


def plan_for(project, name, new, **kw):
    e = ent.resolve(name, project.load_entities())
    return rename.plan_rename(project, e, new, **kw)


def apply_all(project, plan):
    return rename.apply_rename(project, plan, plan.default_ids())


def test_mentions_possessives_and_case(tmp_path):
    project = make(tmp_path)
    entity(project, "the captain")
    s = scene(project, "01-a.md", "The captain left. Then the captain's hat fell; the captains stayed.\n")
    plan = plan_for(project, "the captain", "the baron")
    assert [o.before for o in plan.occurrences] == ["The captain", "the captain"]
    assert [o.after for o in plan.occurrences] == ["The baron", "the baron"]  # sentence-start capital kept
    apply_all(project, plan)
    assert s.read_text(encoding="utf-8") == "The baron left. Then the baron's hat fell; the captains stayed.\n"


def test_overlapping_names_longest_wins(tmp_path):
    project = make(tmp_path)
    entity(project, "Elara")
    entity(project, "Elara Vance")
    s = scene(project, "01-a.md", "Elara met Elara Vance. Elara Vance's coat.\n")
    plan = plan_for(project, "Elara", "Ela")
    assert [o.before for o in plan.occurrences] == ["Elara"]
    apply_all(project, plan)
    assert s.read_text(encoding="utf-8") == "Ela met Elara Vance. Elara Vance's coat.\n"


def test_alias_stays_when_only_name_renamed(tmp_path):
    project = make(tmp_path)
    entity(project, "Elara Vance", aliases=["Elara"])
    s = scene(project, "01-a.md", "Elara Vance smiled; Elara waved.\n")
    plan = plan_for(project, "Elara Vance", "Mara Stone")
    assert [o.before for o in plan.occurrences] == ["Elara Vance"]
    apply_all(project, plan)
    assert s.read_text(encoding="utf-8") == "Mara Stone smiled; Elara waved.\n"
    e = ent.load_entity(project.entity_path(ent.Entity("Mara Stone")))
    assert e.name == "Mara Stone"
    assert e.aliases == ["Elara", "Elara Vance"]  # old name kept as an alias


def test_per_alias_rename_and_no_keep(tmp_path):
    project = make(tmp_path)
    entity(project, "Elara Vance", aliases=["Elara"])
    s = scene(project, "01-a.md", "Elara Vance smiled; Elara waved.\n")
    plan = plan_for(project, "Elara Vance", "Mara Stone", keep_old_as_alias=False,
                    rename_aliases={"Elara": "Mara"})
    apply_all(project, plan)
    assert s.read_text(encoding="utf-8") == "Mara Stone smiled; Mara waved.\n"
    e = ent.load_entity(project.entity_path(ent.Entity("Mara Stone")))
    assert e.aliases == ["Mara"]


def test_links_with_display_text(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara Vale", aliases=["Mara"])
    s = scene(project, "01-a.md",
              "[[Mara Vale]] and [[Mara Vale|Mara Vale]] and [[mara vale|she]] and [[Mara|Mara]].\n")
    plan = plan_for(project, "Mara Vale", "Nia Vale")
    assert len(plan.occurrences) == 3  # [[Mara|Mara]] is the alias, kept
    apply_all(project, plan)
    assert s.read_text(encoding="utf-8") == (
        "[[Nia Vale]] and [[Nia Vale|Nia Vale]] and [[Nia Vale|she]] and [[Mara|Mara]].\n")


def test_frontmatter_pov_and_place_only(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara Vale")
    s = scene(project, "01-a.md",
              "---\npov: Mara Vale\nplace: \"Mara Vale\"\npurpose: Mara Vale arrives\n---\n# T\n\nMara Vale.\n")
    plan = plan_for(project, "Mara Vale", "Nia: Vale")
    assert [o.kind for o in plan.occurrences] == ["pov", "place", "mention"]
    apply_all(project, plan)
    text = s.read_text(encoding="utf-8")
    assert "pov: 'Nia: Vale'\n" in text
    assert "purpose: Mara Vale arrives" in text  # not prose, not a mention field
    assert text.endswith("\nNia: Vale.\n")


def test_ordinary_word_name_with_unticked_occurrences(tmp_path):
    project = make(tmp_path)
    entity(project, "Will")
    s = scene(project, "01-a.md", "Will came. She said Will you stay? Will asked.\n")
    plan = plan_for(project, "Will", "Wren")
    assert len(plan.occurrences) == 3
    keep = plan.occurrences[1].id  # "Will you stay?" is the ordinary word
    ids = [o.id for o in plan.occurrences if o.id != keep]
    rename.apply_rename(project, plan, ids)
    assert s.read_text(encoding="utf-8") == "Wren came. She said Will you stay? Wren asked.\n"


def test_pending_draft_bodies_flagged_and_unticked(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    text = 'Mara ran. <!--ai id="abc123-->x<!--/ai--> <!--ai-->Mara fell.<!--/ai-->\n'
    s = scene(project, "01-a.md", text)
    plan = plan_for(project, "Mara", "Nia")
    flags = [(o.before, o.in_draft) for o in plan.occurrences]
    assert flags == [("Mara", False), ("Mara", True)]
    assert plan.default_ids() == [plan.occurrences[0].id]
    result = apply_all(project, plan)
    assert s.read_text(encoding="utf-8") == (
        'Nia ran. <!--ai id="abc123-->x<!--/ai--> <!--ai-->Mara fell.<!--/ai-->\n')
    # ticked explicitly -> changed, markers intact
    rename.undo_rename(project, result.undo_id)
    assert s.read_text(encoding="utf-8") == text
    plan = plan_for(project, "Mara", "Nia")
    rename.apply_rename(project, plan, [o.id for o in plan.occurrences])
    assert "<!--ai-->Nia fell.<!--/ai-->" in s.read_text(encoding="utf-8")


def test_snapshots_before_write_and_undo(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara", aliases=["M"])
    a = scene(project, "01-a.md", "Mara one.\n")
    b = scene(project, "02-b.md", "No one here.\n")
    plan = plan_for(project, "Mara", "Nia")
    assert plan.files() == ["manuscript/01-a.md"]
    result = apply_all(project, plan)
    assert a.read_text(encoding="utf-8") == "Nia one.\n"
    assert list(result.snapshots) == ["manuscript/01-a.md"]
    snap = snapshots.list_snapshots(project, a)
    assert [s.label for s in snap] == ["before-rename"]
    assert snapshots.read_text(project, a, snap[0].name) == "Mara one.\n"
    assert snapshots.list_snapshots(project, b) == []  # untouched scene: no snapshot
    assert result.remap == {"entities/characters/mara.md": "entities/characters/nia.md"}
    assert not (project.root / "entities/characters/mara.md").exists()

    undone = rename.undo_rename(project, result.undo_id)
    assert undone.skipped == []
    assert a.read_text(encoding="utf-8") == "Mara one.\n"
    e = ent.load_entity(project.root / "entities/characters/mara.md")
    assert (e.name, e.aliases) == ("Mara", ["M"])
    assert not (project.root / "entities/characters/nia.md").exists()


def test_undo_skips_scene_edited_since(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    a = scene(project, "01-a.md", "Mara one.\n")
    result = apply_all(project, plan_for(project, "Mara", "Nia"))
    a.write_text("Nia one. More words.\n", encoding="utf-8")
    undone = rename.undo_rename(project, result.undo_id)
    assert "manuscript/01-a.md" in undone.skipped
    assert a.read_text(encoding="utf-8") == "Nia one. More words.\n"


def test_nothing_changes_at_plan_time(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    a = scene(project, "01-a.md", "Mara one.\n")
    plan_for(project, "Mara", "Nia")
    assert a.read_text(encoding="utf-8") == "Mara one.\n"
    assert (project.root / "entities/characters/mara.md").exists()
    assert snapshots.list_snapshots(project, a) == []


def test_stale_preview_is_refused_before_any_write(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    a = scene(project, "01-a.md", "Mara one.\n")
    b = scene(project, "02-b.md", "Mara two.\n")
    plan = plan_for(project, "Mara", "Nia")
    b.write_text("Mara two, edited.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed since the preview"):
        apply_all(project, plan)
    assert a.read_text(encoding="utf-8") == "Mara one.\n"
    assert snapshots.list_snapshots(project, a) == []
    assert (project.root / "entities/characters/mara.md").exists()


def test_validation(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara", aliases=["M"])
    entity(project, "Nia")
    e = ent.resolve("Mara", project.load_entities())
    with pytest.raises(ValueError, match="another note"):
        rename.plan_rename(project, e, "nia")
    with pytest.raises(ValueError, match="same"):
        rename.plan_rename(project, e, "Mara")
    with pytest.raises(ValueError, match="not an alias"):
        rename.plan_rename(project, e, "Zed", rename_aliases={"Q": "R"})
    with pytest.raises(ValueError, match="empty"):
        rename.plan_rename(project, e, "  ")
    with pytest.raises(ValueError, match="can't be used"):
        rename.plan_rename(project, e, "A/B")


def test_comments_keep_their_anchor_and_bodies_optional(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    text = "Before. Mara walked into the room slowly. After.\n"
    s = scene(project, "01-a.md", text)
    start = text.index("Mara")
    c = comments.add(project.root, s, text, start, start + len("Mara walked"), "Ask Mara about this")
    plan = plan_for(project, "Mara", "Nia", scope=("scenes", "comments"))
    assert any(o.kind == "comment" for o in plan.occurrences)
    apply_all(project, plan)
    new_text = s.read_text(encoding="utf-8")
    [placed] = comments.place(new_text, comments.load(project.root, s))
    assert new_text[placed.start:placed.end] == "Nia walked"
    assert placed.comment.body == "Ask Nia about this"
    assert placed.comment.id == c.id


def test_entity_and_research_scope(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    other = entity(project, "Elias")
    other.body = "Elias trusts Mara.\n"
    ent.save_entity(other, other.path)
    from chisel.core import research
    note = research.new_note(project, "Tides", "Mara studied the tides.\n")
    plan = plan_for(project, "Mara", "Nia", scope=("entities", "research"))
    files = plan.files()
    assert "entities/characters/elias.md" in files and "notebook/tides.md" in files
    apply_all(project, plan)
    assert "Elias trusts Nia." in other.path.read_text(encoding="utf-8")
    assert note.read_text(encoding="utf-8").endswith("Nia studied the tides.\n")
    # default scope leaves research alone
    plan = plan_for(project, "Nia", "Mara")
    assert "notebook/tides.md" not in plan.files()


def test_draft_sidecar_and_part_scene_ids(tmp_path):
    project = make(tmp_path)
    entity(project, "Mara")
    part = project.new_part("Part One")
    s = project.next_scene_path("Rain", part)
    s.write_text("# Rain\n\nMara ran. <!--ai id=\"abc123\"-->new<!--/ai-->\n", encoding="utf-8")
    drafts.save_originals(project.root, s, {"abc123": "old"})
    result = apply_all(project, plan_for(project, "Mara", "Nia"))
    assert "Nia ran." in s.read_text(encoding="utf-8")
    assert drafts.load_originals(project.root, s) == {"abc123": "old"}
    rename.undo_rename(project, result.undo_id)
    assert "Mara ran." in s.read_text(encoding="utf-8")
    assert drafts.load_originals(project.root, s) == {"abc123": "old"}


def test_index_rebuilt_when_given(tmp_path):
    from chisel.core.index import Index
    project = make(tmp_path)
    entity(project, "Mara")
    scene(project, "01-a.md", "Mara one.\n")
    index = Index(project.index_path)
    index.rebuild(project)
    plan = plan_for(project, "Mara", "Nia")
    rename.apply_rename(project, plan, plan.default_ids(), index=index)
    e = ent.resolve("Nia", project.load_entities())
    assert [b.line for b in index.backlinks(e)] == ["Nia one."]
    index.close()


def test_failure_rolls_back(tmp_path, monkeypatch):
    project = make(tmp_path)
    entity(project, "Mara")
    a = scene(project, "01-a.md", "Mara one.\n")
    plan = plan_for(project, "Mara", "Nia")
    real = ent.save_entity

    def boom(*args, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(rename.ent, "save_entity", boom)
    with pytest.raises(OSError):
        apply_all(project, plan)
    monkeypatch.setattr(rename.ent, "save_entity", real)
    assert a.read_text(encoding="utf-8") == "Mara one.\n"
    assert (project.root / "entities/characters/mara.md").exists()
