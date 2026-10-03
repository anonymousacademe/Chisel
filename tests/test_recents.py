from pathlib import Path

from chisel.core.recents import add_recent, load_recents, remove_recent


def test_add_and_load(tmp_path: Path):
    add_recent(tmp_path / "a", "Novel A", tmp_path)
    add_recent(tmp_path / "b", "Novel B", tmp_path)
    recents = load_recents(tmp_path)
    assert [r.title for r in recents] == ["Novel B", "Novel A"]  # newest first
    assert recents[0].path == (tmp_path / "b").resolve()


def test_dedupe_moves_to_front(tmp_path: Path):
    add_recent(tmp_path / "a", "A", tmp_path)
    add_recent(tmp_path / "b", "B", tmp_path)
    add_recent(tmp_path / "a", "A", tmp_path)
    recents = load_recents(tmp_path)
    assert [r.title for r in recents] == ["A", "B"]


def test_cap_at_ten(tmp_path: Path):
    for i in range(15):
        add_recent(tmp_path / f"n{i}", f"N{i}", tmp_path)
    assert len(load_recents(tmp_path)) == 10


def test_remove(tmp_path: Path):
    add_recent(tmp_path / "a", "A", tmp_path)
    add_recent(tmp_path / "b", "B", tmp_path)
    remove_recent(tmp_path / "a", tmp_path)
    assert [r.title for r in load_recents(tmp_path)] == ["B"]


def test_missing_or_corrupt_file(tmp_path: Path):
    assert load_recents(tmp_path) == []
    (tmp_path / "recent.json").write_text("not json{")
    assert load_recents(tmp_path) == []


def test_env_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path))
    add_recent(tmp_path / "a", "A")
    assert (tmp_path / "recent.json").is_file()
    assert load_recents()[0].title == "A"
