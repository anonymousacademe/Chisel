"""Local models (Ollama / OpenAI-compatible): client helpers, request gating,
GUI bridge. No network: the local server is a threaded localhost HTTP stub."""

import json
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from chisel.ai import client


# -- the stub server ---------------------------------------------------------------


class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # quiet
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send(200, {"data": [
                {"id": "llama3", "context_length": 131072},
                {"id": "mistral"},  # no context_length reported
            ]})
        else:
            self._send(404, {"error": "no"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/api/show"):
            self._send(200, {"model_info": {
                "general.architecture": "llama",
                "llama.context_length": 8192,
            }})
        else:
            self._send(404, {"error": f"unexpected POST {self.path} {payload}"})


@pytest.fixture()
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


# -- client helpers -----------------------------------------------------------------


def test_local_base_url_defaults_and_normalizes(monkeypatch, tmp_path):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path))
    assert client.local_base_url() == client.DEFAULT_LOCAL_BASE_URL
    assert client.local_base_url(" http://localhost:1234/v1/ ") == "http://localhost:1234/v1"
    with pytest.raises(ValueError):
        client.local_base_url("ftp://nowhere")


def test_is_local_and_local_model_id():
    assert client.is_local("local:llama3")
    assert not client.is_local("anthropic/claude-3")
    assert not client.is_local(None)
    assert not client.is_local("locally/thing")
    assert client.local_model_id("local:llama3.1") == "llama3.1"


def test_make_client_routes_local_without_a_key(monkeypatch, tmp_path):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    c = client.make_client("local:llama3")
    assert str(c.base_url).startswith("http://127.0.0.1")  # the local server, no key needed
    with pytest.raises(RuntimeError):
        client.make_client("anthropic/claude-3")  # a remote call still needs a key


def test_openrouter_extra_body_skips_openrouter_fields_for_local():
    provider = {"provider": {"require_parameters": True}}
    assert client.openrouter_extra_body(provider, model="local:m") == {}
    body = client.openrouter_extra_body(provider, model="x/y")
    assert body["usage"] == {"include": True}
    assert body["provider"] == {"require_parameters": True}


def test_list_local_models_against_a_stub(local_server, monkeypatch, tmp_path):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path))
    models = client.list_local_models(local_server)
    assert [m.id for m in models] == ["local:llama3", "local:mistral"]
    by_id = {m.id: m for m in models}
    assert by_id["local:llama3"].context_length == 131072  # reported by /models
    assert by_id["local:mistral"].context_length == 8192   # filled in by Ollama /api/show
    assert by_id["local:llama3"].prompt_per_m is None
    # the lengths are remembered under the prefixed id for the budget
    assert client.cached_context_length("local:mistral") == 8192


def test_list_local_models_unreachable(monkeypatch, tmp_path):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        client.list_local_models("http://127.0.0.1:1/v1", timeout=0.2)
    assert "local AI server" in str(exc.value)


def test_resolve_model_keeps_local_slugs():
    assert client.resolve_model("writing", {"ai": {"writing_model": "local:llama3"}}) \
        == "local:llama3"


# -- the AI call sites skip OpenRouter-only fields for local models ------------------


class _Capture:
    """A fake client whose create() records its kwargs."""

    def __init__(self, reply):
        self.kwargs = None
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))
        self._reply = reply

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self._reply


def _fake_response(text='{"mentions": []}'):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))],
        usage=types.SimpleNamespace(cost=None, prompt_tokens=1, completion_tokens=1))


def test_suggest_links_local_sends_no_provider_or_usage():
    from chisel.ai import links
    from chisel.core.entities import Entity

    cap = _Capture(_fake_response())
    links.suggest_links("Rook Tanaka walked in.",
                        [Entity(name="Rook Tanaka", type="character")],
                        "local:llama3", client=cap)
    assert cap.kwargs["extra_body"] == {}
    assert cap.kwargs["model"] == "local:llama3"


def test_suggest_links_remote_keeps_provider():
    from chisel.ai import links
    from chisel.core.entities import Entity

    cap = _Capture(_fake_response())
    links.suggest_links("Rook Tanaka walked in.",
                        [Entity(name="Rook Tanaka", type="character")],
                        "x/y", client=cap)
    assert cap.kwargs["extra_body"]["usage"] == {"include": True}
    assert cap.kwargs["extra_body"]["provider"] == {"require_parameters": True}


def test_stream_text_local_sends_no_extra_body():
    from chisel.ai import stream

    captured = {}

    class _Stream:
        def close(self):
            pass

        def __iter__(self):
            return iter([])

    def create(**kwargs):
        captured.update(kwargs)
        return _Stream()

    fake = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    assert stream.stream_text(fake, "local:m", [{"role": "user", "content": "hi"}], "test") == ""
    assert captured["extra_body"] == {}


def test_generate_images_refuses_local():
    from chisel.ai.images import ImageError, generate

    with pytest.raises(ImageError):
        generate("a lighthouse", "local:llama3", client=object())


def test_writing_generate_local(monkeypatch):
    from chisel.ai import writing

    cap = _Capture(_fake_response(text="A cold open."))
    monkeypatch.setattr(writing, "record_response", lambda *a, **k: None)
    out = writing.generate("draft", "write a line", "The yard at dusk.",
                           "local:llama3", client=cap)
    assert out == "A cold open."
    assert cap.kwargs["extra_body"] == {}
