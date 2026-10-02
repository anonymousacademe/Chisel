"""GUI shell: the Api bridge contract and the devserver's HTTP transport."""

import json
import threading
import urllib.error
import urllib.request

from lorewrite.gui import devserver
from lorewrite.gui.api import Api, bridge


def test_bridge_wraps_results_and_errors():
    class Boom(Api):
        @bridge
        def bad(self):
            raise ValueError("nope")

        @bridge
        def plain(self):
            return 3

        @bridge
        def bug(self):
            return {}["missing"]

    api = Boom()
    assert api.bad() == {"ok": False, "error": "nope"}  # deliberate errors: message only
    assert api.bug()["error"].startswith("KeyError")     # unexpected ones keep the class
    assert api.plain() == {"value": 3, "ok": True}
    assert api.ping() == {"pong": True, "ok": True}
    assert "ping" in api.bridge_methods()


def test_window_methods_work_without_a_window():
    api = Api()
    assert api.minimize()["ok"] and api.toggle_maximize()["ok"] and api.close()["ok"]


def test_devserver_serves_dist_and_bridge(tmp_path):
    (tmp_path / "index.html").write_text("<html>hi</html>")
    server = devserver.serve(Api(), dist=tmp_path)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}/"
        assert b"hi" in urllib.request.urlopen(base).read()
        req = urllib.request.Request(base + "api/ping", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        assert json.load(urllib.request.urlopen(req))["pong"] is True
        plain = urllib.request.Request(base + "api/ping", data=b"{}", method="POST",
                                       headers={"Content-Type": "text/plain"})
        try:
            urllib.request.urlopen(plain)
            raise AssertionError("expected 415")
        except urllib.error.HTTPError as e:
            assert e.code == 415  # simple cross-origin POSTs are refused
        bad = urllib.request.Request(base + "api/__init__", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(bad)
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        try:
            urllib.request.urlopen(base + "../secret")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_facade_exposes_only_bridge_methods(tmp_path):
    from tests.gui_helpers import make_project

    api = Api()
    make_project(tmp_path / "p")
    api.open_project(str(tmp_path / "p"))
    facade = api.facade()
    public = {n for n in dir(facade) if not n.startswith("_")}
    assert public == set(api.bridge_methods())
    # pywebview recurses into non-callable attributes: nothing like project/index/entities may show up
    assert not {"project", "index", "entities", "resolve_document", "reload_entities"} & public
    assert facade.ping()["pong"] is True
    assert all(callable(getattr(facade, n)) for n in public)


def test_mock_ai_matches_the_real_call_signatures(tmp_path, monkeypatch):
    """devserver --mock-ai must keep working when an Api call gains arguments
    (learn_style gained `manuscript`, and the mock was left behind)."""
    from lorewrite.gui import api as api_module
    from lorewrite.gui import mockai
    from tests.test_gui_api import open_api

    import inspect

    names = ("suggest_links", "check_scene", "propose_canon_updates",
             "learn_style", "generate_text", "ask_writer", "research_writer", "brainstorm_writer",
             "generate_images", "suggest_image_prompt")
    real = {n: getattr(api_module, n) for n in names}
    for name in names + ("get_api_key", "_set_api_key", "_clear_api_key", "_list_models",
                         "generate_images", "suggest_image_prompt"):
        monkeypatch.setattr(api_module, name, getattr(api_module, name))   # undone after the test
    mockai.install(api_module)
    for name in names:   # the canned call takes every argument the real one requires
        P = inspect.Parameter
        need = [p for p in inspect.signature(real[name]).parameters.values()
                if p.default is P.empty and p.kind in (P.POSITIONAL_ONLY, P.POSITIONAL_OR_KEYWORD)]
        have = list(inspect.signature(getattr(api_module, name)).parameters.values())
        room = any(p.kind is P.VAR_POSITIONAL for p in have) or \
            sum(p.kind in (P.POSITIONAL_ONLY, P.POSITIONAL_OR_KEYWORD) for p in have) >= len(need)
        assert room, f"mockai.{name} takes fewer arguments than the real call requires"
    api, _ = open_api(tmp_path)
    r = api.learn_style()
    assert r["ok"], r
    assert r["markdown"].startswith("# Style guide")
    ask = api.ask("what now?", "project")
    assert ask["ok"] and ask["reply"], ask


def test_mock_research_answers_from_notes(tmp_path, monkeypatch):
    from lorewrite.gui import api as api_module
    from lorewrite.gui import mockai
    from tests.test_gui_api import open_api

    for name in ("suggest_links", "check_scene", "propose_canon_updates", "learn_style", "generate_text",
                 "ask_writer", "research_writer", "brainstorm_writer", "generate_images",
                 "suggest_image_prompt", "get_api_key", "_set_api_key", "_clear_api_key", "_list_models"):
        monkeypatch.setattr(api_module, name, getattr(api_module, name))   # undone after the test
    mockai.install(api_module)
    api, root = open_api(tmp_path)
    assert api.research("tides?")["ok"] is False          # no notes yet: clean refusal, no AI call
    (root / "research").mkdir()
    (root / "research" / "tides.md").write_text("# Tides\n\nThe tide table says the spur floods at dusk.\n")
    r = api.research("when does the spur flood?")
    assert r["ok"] and "[1]" in r["reply"] and r["sources"][0]["id"] == "research/tides.md"
