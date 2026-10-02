"""Headless dev server: the built UI (see webroot.py) + a JSON bridge onto the same Api.

    python -m lorewrite.gui.devserver --project PATH [--mock-ai]

Serves the built UI and POST /api/<method> (body: {"args": [...]}) on a random
free port of 127.0.0.1 (printed on stdout). For headless-browser screenshots
and debugging; the real app uses pywebview's js_api instead.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import Api
from .webroot import require_dist


def make_handler(api: Api, dist: Path):
    methods = set(api.bridge_methods())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # quiet
            pass

        def _host_ok(self) -> bool:  # refuse DNS-rebinding style requests
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            rel = self.path.split("?", 1)[0].lstrip("/") or "index.html"
            target = (dist / rel).resolve()
            if dist.resolve() not in target.parents and target != dist.resolve():
                return self._send(404, b"not found", "text/plain")
            if not target.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype)

        def do_POST(self) -> None:
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            name = self.path.removeprefix("/api/")
            if not self.path.startswith("/api/") or name not in methods:
                return self._send(404, b'{"ok": false, "error": "no such method"}',
                                  "application/json")
            # Only our own fetch() sends application/json; any other origin would need
            # a CORS preflight (never answered), so a web page cannot drive this API.
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return self._send(415, b'{"ok": false, "error": "JSON only"}', "application/json")
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                args = payload.get("args", [])
            except (json.JSONDecodeError, AttributeError):
                args = []
            result = getattr(api, name)(*args)
            self._send(200, json.dumps(result).encode("utf-8"), "application/json")

    return Handler


def serve(api: Api, dist: Path | None = None, port: int = 0) -> ThreadingHTTPServer:
    dist = dist if dist is not None else require_dist("lorewrite-devserver")
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(api, dist))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lorewrite-devserver")
    parser.add_argument("--project", type=Path, default=None)
    parser.add_argument("--mock-ai", action="store_true",
                        help="answer AI calls with canned results (no network)")
    args = parser.parse_args(argv)
    if args.mock_ai:
        from . import api as api_module
        from . import mockai

        mockai.install(api_module)
    api = Api()
    if args.project is not None and hasattr(api, "open_project"):
        api.open_project(str(args.project))
    server = serve(api)
    print(f"http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
