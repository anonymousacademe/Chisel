"""Api: collections (Wave 3.1)."""

from chisel.core import scenemeta
from tests.test_gui_api import open_api

A = "manuscript/01-arrival.md"
B = "manuscript/02-the-archive.md"


def test_collection_lifecycle_through_the_bridge(tmp_path):
    api, root = open_api(tmp_path)
    assert api.get_workspace()["workspace"]["collections"] == []
    r = api.create_collection("Needs continuity pass", "amber")
    assert r["ok"] and r["collections"][0]["count"] == 0

    # membership is set through the scene's own editor text (frontmatter edit)
    text = (root / A).read_text(encoding="utf-8")
    edit = api.set_scene_details(A, text, {"collections": ["Needs continuity pass"]})
    assert edit["ok"] and edit["details"]["collections"] == ["Needs continuity pass"]
    (root / A).write_text(edit["edit"]["insert"] + text, encoding="utf-8")  # autosave's job
    (root / B).write_text(scenemeta.set_details((root / B).read_text(), collections=["Needs continuity pass"]))

    ws = api.get_workspace()["workspace"]
    (c,) = ws["collections"]
    assert (c["name"], c["color"], c["count"], c["sceneIds"]) == ("Needs continuity pass", "amber", 2, [A, B])

    r = api.rename_collection("Needs continuity pass", "Continuity")
    assert r["ok"] and sorted(r["changed"]) == [A, B] and r["collections"][0]["name"] == "Continuity"
    assert scenemeta.details((root / B).read_text())["collections"] == ["Continuity"]

    assert api.recolor_collection("Continuity", "red")["collections"][0]["color"] == "red"
    r = api.delete_collection("Continuity")
    assert r["ok"] and r["collections"] == [] and sorted(r["changed"]) == [A, B]
    assert (root / B).read_text().startswith("# The Archive")        # empty block gone, scene intact
    assert api.create_collection("x", "mauve")["ok"] is False
    assert "collection" in api.delete_collection("zzz")["error"]
