"""The research bridge is wired into the real Api: the methods are exposed and refuse story projects."""

import pytest

from tests.test_gui_api import open_api

RESEARCH_METHODS = [
    "zotero_status", "zotero_saved_collections", "zotero_sync_plan", "zotero_sync_apply", "zotero_get_settings", "zotero_set_settings",
    "zotero_set_key", "zotero_clear_key", "list_sources", "research_checks", "export_research_start",
    "export_research_status", "export_research_open", "list_objects", "object_numbers", "object_render",
    "object_image", "read_table", "save_table", "build_table", "apply_table", "insert_figure",
    "figure_trust_info", "trust_figure", "figure_run_start", "figure_run_status", "figure_run_cancel",
    "suggest_latex", "suggest_plot_code",
    "research_profiles", "research_get_settings", "research_set_settings", "research_requirements",
    "guidelines_list", "guidelines_add", "guidelines_add_text", "guidelines_read", "guidelines_remove",
]


def test_every_research_method_is_a_bridge_method_on_the_facade(tmp_path):
    api, _ = open_api(tmp_path)
    exposed = set(api.bridge_methods())
    assert set(RESEARCH_METHODS) <= exposed
    facade = api.facade()
    for name in RESEARCH_METHODS:
        assert callable(getattr(facade, name))


@pytest.mark.parametrize("call", [
    lambda a: a.list_sources(), lambda a: a.research_checks(), lambda a: a.list_objects(),
    lambda a: a.object_numbers(), lambda a: a.zotero_status(),
])
def test_research_methods_refuse_a_story_project(tmp_path, call):
    api, _ = open_api(tmp_path)
    assert api.new_project("Tale", str(tmp_path / "tale"))["ok"] is True
    r = call(api)
    assert r["ok"] is False and "not a research project" in r["error"]


def test_research_methods_work_in_a_research_project(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.new_project("Paper", str(tmp_path / "paper"), "research")["ok"] is True
    assert api.list_objects()["ok"] is True
    assert api.list_sources() == {"ok": True, "sources": []}
    assert api.research_checks()["blocking"] is False
