"""Edge cases of the guidelines store (core/paper/guidelines.py)."""

import pytest

from chisel.core.paper import guidelines as gl
from chisel.core.project import Project


@pytest.fixture
def project(tmp_path):
    return Project.create(tmp_path / "paper", "Paper", "research")


def test_name_with_spaces_and_capitals_is_slugified(project):
    name = gl.add_bytes(project, "Journal Author Guidelines 2026.TXT", b"be brief")
    assert name == "journal-author-guidelines-2026.txt"
    assert (project.root / "guidelines" / name).read_bytes() == b"be brief"


def test_same_file_added_twice_gets_two_names(project, tmp_path):
    src = tmp_path / "call.txt"
    src.write_text("page limit", encoding="utf-8")
    first = gl.add_file(project, src)
    second = gl.add_file(project, src)
    assert (first, second) == ("call.txt", "call-2.txt")
    assert first != second
    first_bytes = (project.root / "guidelines" / first).read_bytes()
    second_bytes = (project.root / "guidelines" / second).read_bytes()
    assert first_bytes == second_bytes


def test_pasted_text_is_listed_as_a_note(project):
    gl.add_bytes(project, "appendix.md", b"# Appendix\n")
    name = gl.add_text(project, "Funder call", "Page limit: 5.")
    rows = {r["name"]: r for r in gl.list_files(project)}
    assert name == "funder-call.md"
    assert rows[name]["type"] == "note"
    assert rows["appendix.md"]["type"] == "md"


def test_empty_pasted_text_is_refused(project):
    with pytest.raises(gl.GuidelineError):
        gl.add_text(project, "Blank", " \n\t ")
    assert gl.list_files(project) == []


def test_remove_then_list(project):
    gl.add_bytes(project, "keep.txt", b"keep")
    gone = gl.add_bytes(project, "gone.txt", b"gone")
    gl.remove(project, gone)
    assert [r["name"] for r in gl.list_files(project)] == ["keep.txt"]
    with pytest.raises(FileNotFoundError):
        gl.read_text(project, gone)
    with pytest.raises(FileNotFoundError):
        gl.remove(project, gone)


def test_small_read_limit_sets_truncated(project):
    name = gl.add_bytes(project, "rules.txt", b"x" * 40)
    out = gl.read_text(project, name, limit=10)
    assert out["truncated"] is True
    assert len(out["text"]) == 10
    assert out["chars"] == 40
    assert out["message"] == ""
    exact = gl.read_text(project, name, limit=40)
    assert exact["truncated"] is False
    assert len(exact["text"]) == 40


def test_hand_placed_txt_with_non_utf8_bytes_is_read(project):
    folder = project.root / "guidelines"
    folder.mkdir(exist_ok=True)
    (folder / "legacy.txt").write_bytes(b"caf\xe9 rules\n")
    rows = {r["name"]: r for r in gl.list_files(project)}
    assert rows["legacy.txt"]["extracted"] is True
    out = gl.read_text(project, "legacy.txt")
    assert "caf" in out["text"] and "\ufffd" in out["text"]
    assert out["truncated"] is False
