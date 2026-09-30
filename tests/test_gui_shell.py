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
        req = urllib.request.Request(base + "api/ping", data=b"{}", method="POST")
        assert json.load(urllib.request.urlopen(req))["pong"] is True
        bad = urllib.request.Request(base + "api/__init__", data=b"{}", method="POST")
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
