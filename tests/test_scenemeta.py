"""Scene details: YAML frontmatter at the top of a scene (Wave 1.3)."""

from pathlib import Path

import pytest

from lorewrite.core import drafts, scenemeta
from lorewrite.core import entities as ent
from lorewrite.core.index import Index
from lorewrite.core.project import Project, retitle_text
from lorewrite.core.spans import compute_spans
from lorewrite.core.style import sample_manuscript

SCENE = """\
---
pov: Mara Vale
place: Lower Meridian
purpose: First contact with Elias's signal
status: revising
target: 2400
collections: [Needs continuity pass]
---
# A City That Remembers

Mara walked down to the spur. It rained.
"""


def test_details_parsed_and_normalized():
    d = scenemeta.details(SCENE)
    assert d == {"pov": "Mara Vale", "place": "Lower Meridian",
                 "purpose": "First contact with Elias's signal",
                 "status": "revising", "when": "", "target": 2400,
                 "collections": ["Needs continuity pass"]}


def test_no_frontmatter_means_empty_details_and_no_block():
    text = "# Title\n\nBody.\n"
    assert scenemeta.find(text) is None
    assert scenemeta.body_offset(text) == 0
    assert scenemeta.details(text)["target"] is None
    assert scenemeta.header(text) == ""


def test_a_leading_horizontal_rule_is_not_frontmatter():
    text = "---\nHe waited.\n---\n# Title\n"
    assert scenemeta.find(text) is None
    assert scenemeta.strip(text) == text


def test_set_details_creates_block_only_when_a_field_is_set():
    text = "# Title\n\nBody.\n"
    out = scenemeta.set_details(text, pov="Mara Vale")
    assert out == "---\npov: Mara Vale\n---\n# Title\n\nBody.\n"
    assert scenemeta.set_details(out, pov="") == text   # clearing the last key removes the block


def test_set_details_keeps_unknown_keys_and_prose():
    text = "---\ntags: [a, b]\npov: Mara\n---\n# T\n\nBody.\n"
    out = scenemeta.set_details(text, status="draft", target="1,500")
    d = scenemeta.find(out).meta
    assert d == {"tags": ["a", "b"], "pov": "Mara", "status": "draft", "target": 1500}
    assert out.endswith("# T\n\nBody.\n")


def test_set_details_rejects_unknown_fields_and_bad_target():
    with pytest.raises(ValueError):
        scenemeta.set_details("x", mood="grim")
    with pytest.raises(ValueError):
        scenemeta.set_details("x", target="lots")


def test_set_details_unicode_and_colons_roundtrip():
    out = scenemeta.set_details("# T\n", purpose="Réveil: the ghost's note — “why”")
    assert scenemeta.details(out)["purpose"] == "Réveil: the ghost's note — “why”"


def test_strip_blank_and_word_count_exclude_the_block():
    assert scenemeta.strip(SCENE).startswith("# A City That Remembers")
    blanked = scenemeta.blank(SCENE)
    assert len(blanked) == len(SCENE) and blanked.count("\n") == SCENE.count("\n")
    assert "Mara Vale" not in blanked.split("# A City")[0]
    assert drafts.count_words(SCENE) == drafts.count_words(scenemeta.strip(SCENE))
    assert drafts.count_words(SCENE) == 13


def test_blank_keep_leaves_only_pov_and_place_values():
    kept = scenemeta.blank(SCENE, keep=scenemeta.MENTION_FIELDS)
    head = kept.split("# A City")[0]
    assert "Mara Vale" in head and "Lower Meridian" in head
    assert "Elias" not in head and "revising" not in head
    assert len(kept) == len(SCENE)


def test_header_for_prompts():
    assert scenemeta.header(SCENE) == (
        "- POV: Mara Vale\n- Place: Lower Meridian\n"
        "- Purpose: First contact with Elias's signal\n- Status: revising")


def test_retitle_and_title_skip_the_block(tmp_path: Path):
    proj = Project.create(tmp_path / "n", "N")
    path = proj.manuscript_dir / "02-x.md"
    path.write_text("---\npov: Mara\n# not a title\n---\nProse only.\n")
    # the comment-looking line is YAML, not a title
    assert proj.scene_title(path) == "02-x"
    assert retitle_text("---\npov: Mara\n---\nProse.\n", "New") == (
        "---\npov: Mara\n---\n# New\n\nProse.\n")


def test_mentions_ignore_frontmatter_except_pov_and_place(tmp_path: Path):
    proj = Project.create(tmp_path / "n", "N")
    mara, _ = proj.create_entity("Mara Vale", "character")
    elias, _ = proj.create_entity("Elias", "character")
    meridian, _ = proj.create_entity("Lower Meridian", "place")
    path = proj.manuscript_dir / "02-x.md"
    path.write_text(SCENE)
    idx = Index(proj.index_path)
    idx.rebuild(proj)
    ents = proj.load_entities()
    rows = {e.name: [b for b in idx.backlinks(e) if b.source.endswith("02-x.md")]
            for e in ents}
    assert {b.row for b in rows["Mara Vale"]} == {1}   # the pov line ("Mara" alone is no alias)
    # POV / place count; "Elias" appears only in the purpose line (ignored)
    assert any(b.row == 1 and "pov:" in b.line for b in rows["Mara Vale"])
    assert any(b.row == 2 for b in rows["Lower Meridian"])
    assert rows["Elias"] == []
    idx.close()
    # editor spans: nothing is highlighted inside the block
    spans = compute_spans(SCENE, ents, mentions=True)
    assert all(s["start"] >= scenemeta.body_offset(SCENE) for s in spans)


def test_style_sampling_skips_frontmatter(tmp_path: Path):
    proj = Project.create(tmp_path / "n", "N")
    (proj.manuscript_dir / "01-opening.md").unlink()
    body = " ".join(["word"] * 40)
    (proj.manuscript_dir / "01-a.md").write_text(
        f"---\npurpose: {' '.join(['plan'] * 40)}\n---\n# A\n\n{body}\n")
    samples = sample_manuscript(proj)
    assert samples and all("plan" not in para for _, para in samples)


# -- AI prompts: the details become a short header, never raw YAML -----------------

from lorewrite.ai import continuity as ai_cont  # noqa: E402
from lorewrite.ai.writing import CURSOR, build_context  # noqa: E402

MARA = ent.Entity(name="Mara Vale", type="character", body="Mara is an archivist.")
SPUR = ent.Entity(name="Lower Meridian", type="place", body="A drowned district.")
YAML_SCENE = ("---\npov: Mara Vale\nplace: Lower Meridian\npurpose: First contact\n"
              "target: 2400\n---\n# A City\n\nShe walked.\n\nThen she stopped.\n")


def test_build_context_has_a_details_header_and_no_yaml():
    cursor = YAML_SCENE.index("Then")
    ctx = build_context(YAML_SCENE, cursor, [MARA, SPUR], {}, None)
    assert "SCENE DETAILS" in ctx and "- POV: Mara Vale" in ctx and "- Purpose: First contact" in ctx
    scene = ctx.split("SCENE (the new text goes at")[1]
    assert f"She walked.\n\n{CURSOR}Then she stopped." in scene
    assert "pov:" not in scene and "target" not in scene
    # the POV character and place are in the context although the prose only says "She"
    assert "### Mara Vale (character)" in ctx and "### Lower Meridian (place)" in ctx


def test_build_context_without_details_is_unchanged():
    ctx = build_context("# T\n\nHello world.\n", 6, [MARA], {}, None)
    assert "SCENE DETAILS" not in ctx


def test_build_context_selection_span_is_shifted_past_the_block():
    start = YAML_SCENE.index("She walked.")
    ctx = build_context(YAML_SCENE, 0, [], {}, None, span=(start, start + len("She walked.")))
    assert f"# A City\n\n{CURSOR}\n\nThen she stopped." in ctx


def test_continuity_prompt_sends_details_and_prose_not_frontmatter():
    prompt = ai_cont.build_check_prompt(YAML_SCENE, {"Mara Vale": "Mara is an archivist."})
    assert "SCENE DETAILS" in prompt and "- POV: Mara Vale" in prompt
    scene = prompt.split("SCENE:\n")[1]
    assert scene.startswith("# A City") and "pov:" not in scene
    plain = ai_cont.build_check_prompt("# A\n\nText.\n", {})
    assert "SCENE DETAILS" not in plain and plain.endswith("SCENE:\n# A\n\nText.\n")


def test_evidence_rows_still_refer_to_the_file_with_its_frontmatter():
    from lorewrite.core.continuity import locate_evidence
    assert locate_evidence(YAML_SCENE, "Then she stopped.") == 10
