"""Edge cases of the requirements checklist (core/paper/requirements.py)."""

import pytest

from chisel.core.paper import requirements
from chisel.core.project import Project


def make(tmp_path, journal="ems", kind="manuscript"):
    return Project.create(tmp_path / "paper", "Paper", "research", kind, journal)


def scene_for(project, title):
    for p in project.list_scenes():
        if p.read_text(encoding="utf-8").lstrip("-").find(f"# {title}\n") >= 0:
            return p
    raise AssertionError(title)


def put(project, title, body):
    p = scene_for(project, title)
    text = p.read_text(encoding="utf-8")
    p.write_text(text.rstrip("\n") + "\n\n" + body + "\n", encoding="utf-8", newline="\n")


def by_id(rows):
    return {r["id"]: r for r in rows}


def test_section_with_only_frontmatter_counts_as_empty(tmp_path):
    p = make(tmp_path)
    funding = scene_for(p, "Funding")
    funding.write_text("---\npurpose: Funding statement\n---\n", encoding="utf-8", newline="\n")
    row = by_id(requirements.evaluate(p))["funding"]
    assert row["status"] == "warn"
    assert row["message"] == "Funding is there but empty."


def test_abstract_exactly_at_the_limit_is_ok(tmp_path):
    p = make(tmp_path)
    put(p, "Abstract", " ".join(["word"] * 150))
    row = by_id(requirements.evaluate(p))["abstract-words"]
    assert row["status"] == "ok"
    assert row["message"] == "Abstract is 150 words; the limit is 150."


def test_abstract_one_word_over_the_limit_warns(tmp_path):
    p = make(tmp_path)
    put(p, "Abstract", " ".join(["word"] * 151))
    row = by_id(requirements.evaluate(p))["abstract-words"]
    assert row["status"] == "warn"
    assert row["message"] == "Abstract is 151 words; the limit is 150."


@pytest.mark.parametrize("text", [
    "water\nmodels\nsoftware",
    "water, models, software",
    "water; models; software",
])
def test_keywords_separators_count_the_same(tmp_path, text):
    p = make(tmp_path)
    put(p, "Keywords", text)
    row = by_id(requirements.evaluate(p))["keywords-count"]
    assert row["status"] == "ok"
    assert row["message"] == "Keywords has 3 items."


def test_eight_keywords_warn(tmp_path):
    p = make(tmp_path)
    put(p, "Keywords", "a\nb\nc\nd\ne\nf\ng\nh")
    row = by_id(requirements.evaluate(p))["keywords-count"]
    assert row["status"] == "warn"
    assert row["message"] == "Keywords has 8 items; expected 1 to 7."


def test_highlight_exactly_85_characters_is_ok(tmp_path):
    p = make(tmp_path)
    put(p, "Highlights", "- short one\n- short two\n- " + "x" * 85)
    row = by_id(requirements.evaluate(p))["highlights"]
    assert row["status"] == "ok"
    assert row["message"] == "Highlights has 3 items."


def test_highlight_of_86_characters_warns(tmp_path):
    p = make(tmp_path)
    put(p, "Highlights", "- short one\n- short two\n- " + "x" * 86)
    row = by_id(requirements.evaluate(p))["highlights"]
    assert row["status"] == "warn"
    assert row["message"].startswith("1 of the 3 highlights are longer than 85 characters:")
    assert "(86)" in row["message"]


def test_intro_line_before_highlights_is_not_an_item(tmp_path):
    p = make(tmp_path)
    put(p, "Highlights", "Highlights of the work:\n- one result\n- two results\n- three results")
    row = by_id(requirements.evaluate(p))["highlights"]
    assert row["status"] == "ok"
    assert row["message"] == "Highlights has 3 items."


def test_numbered_items_count_as_items(tmp_path):
    p = make(tmp_path)
    put(p, "Keywords", "1. water\n2. models\n3. software")
    row = by_id(requirements.evaluate(p))["keywords-count"]
    assert row["status"] == "ok"
    assert row["message"] == "Keywords has 3 items."


def test_first_non_empty_section_wins_when_titles_repeat(tmp_path):
    p = make(tmp_path)
    first = p.next_scene_path("Abstract")
    first.write_text("# Abstract\n", encoding="utf-8", newline="\n")
    second = p.next_scene_path("Abstract")
    second.write_text("# Abstract\n\n" + " ".join(["word"] * 150) + "\n", encoding="utf-8", newline="\n")
    row = by_id(requirements.evaluate(p))["abstract-words"]
    assert row["status"] == "ok"
    assert row["message"] == "Abstract is 150 words; the limit is 150."


def test_section_title_case_does_not_matter(tmp_path):
    p = make(tmp_path)
    funding = scene_for(p, "Funding")
    funding.write_text("---\npurpose: Funding statement\n---\n# FUNDING\n\nThere was no specific grant.\n",
                       encoding="utf-8", newline="\n")
    row = by_id(requirements.evaluate(p))["funding"]
    assert row["status"] == "ok"
    assert row["message"] == 'Found "FUNDING".'


def test_profile_of_the_wrong_kind_gives_no_results(tmp_path):
    p = make(tmp_path)
    p.update_research_settings(kind="proposal")
    assert p.journal == "ems"
    assert p.research_profile() is None
    assert requirements.evaluate(p) == []


def test_research_project_without_a_journal_gives_no_results(tmp_path):
    p = Project.create(tmp_path / "proposal", "Proposal", "research", "proposal", "")
    assert p.journal == ""
    assert p.research_profile() is None
    assert requirements.evaluate(p) == []


def test_acknowledgements_last_with_text_is_ok(tmp_path):
    p = make(tmp_path)
    put(p, "Acknowledgements", "Thanks to the reviewers.")
    row = by_id(requirements.evaluate(p))["acknowledgements-before-references"]
    assert row["status"] == "ok"
    assert row["message"] == '"Acknowledgements" is the last section.'
