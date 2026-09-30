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

    api = Boom()
    assert api.bad() == {"ok": False, "error": "ValueError: nope"}
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
