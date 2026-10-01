"""Api: comments (Wave 3.2). Offsets are UTF-16, like everything CodeMirror sees."""

from tests.test_gui_api import open_api

A = "manuscript/01-arrival.md"


def test_comment_lifecycle_through_the_bridge(tmp_path):
    api, root = open_api(tmp_path)
    text = (root / A).read_text(encoding="utf-8")
    start = text.index("copper")
    r = api.add_comment(A, text, start, start + 6, "smell again?")
    assert r["ok"], r
    (row,) = r["comments"]
    assert (row["start"], row["end"], row["detached"], row["row"]) == (start, start + 6, False, 3)
    assert row["quote"] == "copper" and row["body"] == "smell again?" and row["resolved"] is False
    assert (root / A).read_text(encoding="utf-8") == text       # the scene is untouched

    # the editor's text moved on: the comment follows it
    moved = "A new line first.\n" + text
    (row2,) = api.list_comments(A, moved)["comments"]
    assert moved[row2["start"]:row2["end"]] == "copper"

    assert api.edit_comment(A, row["id"], "better", moved)["comments"][0]["body"] == "better"
    assert api.resolve_comment(A, row["id"], True, moved)["comments"][0]["resolved"] is True
    assert api.delete_comment(A, row["id"], moved)["comments"] == []
    assert api.delete_comment(A, row["id"])["ok"] is False


def test_utf16_offsets_with_astral_characters(tmp_path):
    api, root = open_api(tmp_path)
    text = "# T\n\n😀😀 the rain fell on the spur and kept falling.\n"
    (root / A).write_text(text, encoding="utf-8")
    u16 = len("# T\n\n😀😀 ".encode("utf-16-le")) // 2
    r = api.add_comment(A, text, u16, u16 + len("the rain"), "x")
    assert r["ok"] and r["comments"][0]["quote"] == "the rain"
    row = r["comments"][0]
    assert (row["start"], row["end"]) == (u16, u16 + 8)


def test_only_scenes_take_comments_and_bad_input_is_a_clean_error(tmp_path):
    api, root = open_api(tmp_path)
    assert api.list_comments("project.toml")["ok"] is False
    text = (root / A).read_text(encoding="utf-8")
    assert "select some text" in api.add_comment(A, text, 5, 5, "x")["error"]
    assert "some text" in api.add_comment(A, text, 3, 8, "  ")["error"]
