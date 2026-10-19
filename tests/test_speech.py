"""Read aloud voices (chisel/speech/): catalogue, download, clip cache, speech server, the local worker, the bridge.
No network: every request goes through a fake opener; the worker is a fake script or a fake Kokoro module."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import textwrap
import types
import urllib.error

import pytest

from chisel.gui.api import Api
from chisel.speech import cache, catalogue, endpoint, engine, kokoro, kokoro_worker, models

WAV = b"RIFF" + b"\0" * 40


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# -- catalogue ------------------------------------------------------------------


def test_describe_voice_reads_language_gender_and_rank():
    v = catalogue.describe_voice("bf_emma")
    assert (v["name"], v["lang"], v["gender"]) == ("Emma", "en-gb", "female")
    assert v["label"] == "Emma (English (UK), female)"
    assert catalogue.describe_voice("af_heart")["rank"] == 0
    # suggested voices first, then other English, then the other languages
    assert catalogue.describe_voice("am_santa")["rank"] < catalogue.describe_voice("ef_dora")["rank"]
    assert catalogue.language_of("jf_alpha") == "ja"


# -- download -------------------------------------------------------------------


def _hub(model: bytes, voices: dict[str, bytes], sha: str | None = None, seen: list | None = None):
    """A fake Hugging Face: the API, the two trees and the files."""
    trees = {
        "onnx": [{"type": "file", "path": "onnx/model_quantized.onnx", "size": len(model),
                  "lfs": {"oid": sha or hashlib.sha256(model).hexdigest()}}],
        "voices": [{"type": "file", "path": f"voices/{n}.bin", "size": len(b)} for n, b in voices.items()],
    }

    def opener(req, timeout=None):
        url = req.full_url
        if seen is not None:
            seen.append(url)
        if url.endswith(catalogue.HF_REPO):
            return Resp(json.dumps({"sha": "abc123"}).encode())
        if "/tree/abc123/" in url:
            return Resp(json.dumps(trees[url.rsplit("/", 1)[-1]]).encode())
        if url.endswith("onnx/model_quantized.onnx"):
            return Resp(model)
        for n, b in voices.items():
            if url.endswith(f"voices/{n}.bin"):
                return Resp(b)
        raise urllib.error.URLError(f"unexpected {url}")
    return opener


def test_download_verifies_installs_and_reports(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(catalogue, "VOICE_BYTES", 256 * 4 * 2)
    voice = np.arange(512, dtype=np.float32).tobytes()
    seen: list[str] = []
    stages = []
    out = models.download("standard", lambda s, f: stages.append((s, f)),
                          opener=_hub(b"model-bytes", {"af_heart": voice, "bm_george": voice}, seen=seen))
    folder = models.model_dir()
    assert (folder / "model.onnx").read_bytes() == b"model-bytes"
    styles = np.load(folder / "voices.npz")
    assert sorted(styles.files) == ["af_heart", "bm_george"] and styles["af_heart"].shape == (2, 1, 256)
    m = models.manifest()
    assert m["revision"] == "abc123" and m["licence"] == "Apache-2.0" and m["voices"] == ["af_heart", "bm_george"]
    assert out["installed"] and [v["id"] for v in out["voices"]] == ["af_heart", "bm_george"]
    assert stages[-1] == ("Installed", 1.0)
    assert all("resolve/abc123/" in u for u in seen if "/resolve/" in u)       # pinned to the revision listed
    assert not list(folder.parent.glob("*.partial"))


def test_download_with_a_bad_checksum_installs_nothing(tmp_path):
    pytest.importorskip("numpy")
    with pytest.raises(RuntimeError, match="checksum"):
        models.download("standard", opener=_hub(b"model", {"af_heart": b"\0" * 1024}, sha="0" * 64))
    assert not models.status()["installed"]
    assert not models.model_dir().exists() and not list(models.model_dir().parent.glob("*.partial"))


def test_download_can_be_cancelled_and_keeps_the_old_install(tmp_path):
    pytest.importorskip("numpy")
    folder = models.model_dir()
    folder.mkdir(parents=True)
    for name in ("model.onnx", "voices.npz"):
        (folder / name).write_bytes(b"old")
    (folder / "manifest.json").write_text(json.dumps({"voices": ["af_heart"]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="cancelled"):
        models.download("standard", opener=_hub(b"model", {"af_heart": b"\0" * 1024}), cancelled=lambda: True)
    assert (folder / "model.onnx").read_bytes() == b"old" and models.status()["installed"]


def test_download_refuses_an_unknown_variant_and_an_unreachable_hub():
    with pytest.raises(ValueError):
        models.download("enormous")
    pytest.importorskip("numpy")

    def offline(req, timeout=None):
        raise urllib.error.URLError("offline")
    with pytest.raises(RuntimeError, match="Hugging Face"):
        models.download("standard", opener=offline)


def test_remove_deletes_the_voices():
    folder = models.model_dir()
    folder.mkdir(parents=True)
    (folder / "model.onnx").write_bytes(b"x")
    assert models.remove() and not folder.exists() and not models.remove()


# -- clip cache -----------------------------------------------------------------


def test_cache_round_trip_and_prune():
    k1 = cache.key("kokoro", "m", "af_heart", 1.0, "Hello")
    assert k1 != cache.key("kokoro", "m", "af_heart", 1.25, "Hello") != cache.key("kokoro", "m", "bf_emma", 1.0, "Hello")
    assert cache.get(k1) is None
    cache.put(k1, WAV)
    assert cache.get(k1) == WAV
    assert cache.clips_dir().is_relative_to(kokoro_worker.Path(__import__("os").environ["CHISEL_STATE_DIR"]))
    for i in range(5):
        cache.put(cache.key("e", "m", "v", 1, str(i)), b"x" * 100)
    cache.prune(limit=250)
    assert sum(p.stat().st_size for p in cache.clips_dir().glob("*.wav")) <= 250
    assert cache.clear() >= 1 and not list(cache.clips_dir().glob("*.wav"))


# -- speech server --------------------------------------------------------------


def test_endpoint_render_sends_the_openai_shape():
    sent = {}

    def opener(req, timeout=None):
        sent.update(url=req.full_url, body=json.loads(req.data), auth=req.get_header("Authorization"))
        return Resp(WAV)
    assert endpoint.render("http://127.0.0.1:8880/v1/", "kokoro", "af_heart", "Hi.", 1.25, "k1", opener) == WAV
    assert sent["url"] == "http://127.0.0.1:8880/v1/audio/speech"
    assert sent["body"] == {"model": "kokoro", "input": "Hi.", "voice": "af_heart", "response_format": "wav", "speed": 1.25}
    assert sent["auth"] == "Bearer k1"


def test_endpoint_errors_are_messages_for_the_author():
    def refused(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b'{"error": {"message": "bad key"}}'))
    with pytest.raises(RuntimeError, match="refused the key.*bad key"):
        endpoint.render("https://api.openai.com/v1", "tts-1", "nova", "Hi", opener=refused)
    with pytest.raises(RuntimeError, match="WAV"):
        endpoint.render("http://localhost:1/v1", "m", "v", "Hi", opener=lambda req, timeout=None: Resp(b"ID3mp3"))
    with pytest.raises(ValueError):
        endpoint.render("ftp://x", "m", "v", "Hi")


def test_endpoint_cost_and_locality():
    assert endpoint.is_local("http://127.0.0.1:8880/v1") and endpoint.is_local("http://192.168.1.5/v1")
    assert endpoint.is_local("http://localhost:8000") and not endpoint.is_local("https://api.openai.com/v1")
    assert endpoint.cost(1_000_000, "https://api.openai.com/v1", "tts-1") == 15.0
    assert endpoint.cost(500, "http://localhost:8880/v1", "anything") == 0.0
    assert endpoint.cost(500, "https://example.com/v1", "x") is None


def test_endpoint_voices_from_the_server_or_the_openai_names():
    got = endpoint.list_voices("http://localhost:8880/v1",
                               opener=lambda req, timeout=None: Resp(json.dumps({"voices": ["af_heart", "bm_george"]}).encode()))
    assert got == ["af_heart", "bm_george"]

    def offline(req, timeout=None):
        raise urllib.error.URLError("x")
    assert endpoint.list_voices("http://localhost:9/v1", opener=offline) == list(endpoint.OPENAI_VOICES)
    assert endpoint.list_voices("https://api.openai.com/v1", opener=offline) == list(endpoint.OPENAI_VOICES)


# -- prefs and render -----------------------------------------------------------


def test_prefs_default_validate_and_save():
    assert engine.get_prefs()["engine"] == "browser"
    saved = engine.set_prefs({"engine": "endpoint", "baseUrl": "http://localhost:8880/v1/", "model": "kokoro"})
    assert saved == {"engine": "endpoint", "baseUrl": "http://localhost:8880/v1", "model": "kokoro",
                     "orModel": "elevenlabs/eleven-turbo-v2.5"}
    assert engine.get_prefs() == saved
    with pytest.raises(ValueError):
        engine.set_prefs({"engine": "telepathy"})
    with pytest.raises(ValueError):
        engine.set_prefs({"baseUrl": "file:///etc"})


def test_render_uses_the_cache_and_counts_cloud_cost(monkeypatch):
    from chisel.ai import usage

    calls = []
    monkeypatch.setattr(endpoint, "render", lambda *a, **k: calls.append(a) or WAV)
    monkeypatch.setattr(endpoint, "get_key", lambda: None)
    engine.set_prefs({"engine": "endpoint", "baseUrl": "https://api.openai.com/v1", "model": "tts-1"})
    before = usage.LEDGER.count()
    first = engine.render("Hello there.", "nova", 1.0)
    again = engine.render("Hello there.", "nova", 1.0)
    assert first["wav"] == again["wav"] == WAV and len(calls) == 1
    assert not first["cached"] and again["cached"] and again["cost"] == 0.0
    assert first["cost"] == pytest.approx(12 * 15 / 1_000_000)
    assert usage.LEDGER.count() == before + 1
    with pytest.raises(ValueError):
        engine.render("Hi", "nova", engine="browser")
    with pytest.raises(ValueError):
        engine.render("   ", "nova")


# -- the local engine's worker --------------------------------------------------


def test_kokoro_engine_talks_to_a_worker_and_skips_noise(tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(textwrap.dedent("""
        import base64, json, sys
        print("a native library said hello", flush=True)
        for line in sys.stdin:
            req = json.loads(line)
            if req["text"] == "boom":
                print(json.dumps({"id": req["id"], "ok": False, "error": "ValueError: boom"}), flush=True)
                continue
            body = ("RIFF" + req["voice"] + "|" + req["lang"] + "|" + str(req["speed"]) + "|" + req["text"]).encode()
            print(json.dumps({"id": req["id"], "ok": True, "wav": base64.b64encode(body).decode()}), flush=True)
    """), encoding="utf-8", newline="\n")
    eng = kokoro.KokoroEngine([sys.executable, "-I", str(script)])
    try:
        assert eng.render("Café, “quoted”.", "bf_emma", 1.25) == "RIFFbf_emma|en-gb|1.25|Café, “quoted”.".encode()
        with pytest.raises(RuntimeError, match="boom"):
            eng.render("boom", "af_heart")
        assert eng.render("again", "af_heart").startswith(b"RIFFaf_heart")      # still running after an error
        assert eng.running
    finally:
        eng.stop()
    assert not eng.running


def test_kokoro_engine_reports_a_dead_worker_and_a_missing_install(tmp_path, monkeypatch):
    script = tmp_path / "dies.py"
    script.write_text("import sys\nsys.exit(3)\n", encoding="utf-8", newline="\n")
    eng = kokoro.KokoroEngine([sys.executable, "-I", str(script)])
    with pytest.raises(RuntimeError, match="stopped"):
        eng.render("Hi", "af_heart")
    monkeypatch.setattr(models, "engine_available", lambda: True)
    with pytest.raises(RuntimeError, match="Download the natural voices"):
        kokoro.KokoroEngine().render("Hi", "af_heart")


def test_worker_main_renders_with_kokoro(monkeypatch, tmp_path):
    np = pytest.importorskip("numpy")
    made = []

    class FakeKokoro:
        def __init__(self, model, voices):
            made.append((model, voices))

        def create(self, text, voice, speed, lang):
            if text == "bad":
                raise ValueError("no phonemes")
            return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setitem(sys.modules, "kokoro_onnx", types.SimpleNamespace(Kokoro=FakeKokoro))
    requests = [{"id": 1, "text": "Hello", "voice": "af_heart", "speed": 9, "lang": "en-us"},
                {"id": 2, "text": "bad", "voice": "af_heart"}]
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert kokoro_worker.main([str(tmp_path)]) == 0
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["ok"] and replies[0]["seconds"] == 0.1
    import base64
    assert base64.b64decode(replies[0]["wav"])[:4] == b"RIFF"
    assert replies[1] == {"id": 2, "ok": False, "error": "ValueError: no phonemes"}
    assert len(made) == 1                                   # loaded once


# -- bridge ---------------------------------------------------------------------


def test_bridge_info_set_clip_and_remove(monkeypatch):
    api = Api()
    info = api.speech_info()
    assert info["ok"] and info["prefs"]["engine"] == "browser" and not info["kokoro"]["installed"]
    assert {v["id"] for v in info["kokoro"]["variants"]} == {"standard", "high"}
    assert not api.speech_set({"engine": "nope"})["ok"]
    r = api.speech_set({"engine": "endpoint", "baseUrl": "http://127.0.0.1:8880/v1"})
    assert r["ok"] and r["endpoint"]["local"] and r["endpoint"]["pricePerMillion"] == 0.0
    monkeypatch.setattr(endpoint, "render", lambda *a, **k: WAV)
    clip = api.speech_clip("Hello.", "af_heart", 1.0)
    assert clip["ok"] and clip["dataUrl"].startswith("data:audio/wav;base64,UklGR") and clip["cost"] == 0.0
    assert api.speech_clip("Hello.", "af_heart", 1.0)["cached"]
    assert not api.speech_clip("Hello.", "af_heart", 1.0, "browser")["ok"]
    monkeypatch.setattr(endpoint, "list_voices", lambda base, key=None: ["a", "b"])
    assert [v["id"] for v in api.speech_voices("endpoint")["voices"]] == ["a", "b"]
    removed = api.speech_remove()
    assert removed["ok"] and removed["clips"] == 1


def test_bridge_key_goes_to_the_keyring(fake_keyring):
    api = Api()
    assert api.speech_set_key("sk-test")["hasKey"]
    assert endpoint.get_key() == "sk-test"
    assert not api.speech_set_key("")["hasKey"]


def test_bridge_download_job(monkeypatch):
    import time

    def fake_download(variant, progress, cancelled=lambda: False):
        progress("Downloading the model", 0.5)
        return {}
    monkeypatch.setattr(models, "download", fake_download)
    api = Api()
    job = api.speech_download_start("standard")["job"]
    for _ in range(100):
        st = api.speech_download_status(job)
        if st["state"] != "running":
            break
        time.sleep(0.02)
    assert st["state"] == "done" and "kokoro" in st
    assert not api.speech_download_status("v999")["ok"]


def test_warm_only_for_installed_local_voices(monkeypatch):
    assert engine.warm() is False                         # system voices chosen
    engine.set_prefs({"engine": "kokoro"})
    assert engine.warm() is False                         # nothing downloaded
    assert Api().speech_warm() == {"ok": True, "warmed": False}


def test_a_frozen_app_says_the_local_engine_is_not_in_the_installer(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    st = models.status()
    assert not st["engine"] and "installer" in st["hint"]


def _wav(samples, rate=1000):
    import array
    import wave as wavemod
    out = io.BytesIO()
    with wavemod.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array.array("h", samples).tobytes())
    return out.getvalue()


def test_pacing_trims_every_clip_to_the_same_lead_and_tail():
    import array
    import wave as wavemod
    from chisel.speech import pacing

    def frames(data):
        with wavemod.open(io.BytesIO(data), "rb") as w:
            a = array.array("h")
            a.frombytes(w.readframes(w.getnframes()))
            return a

    long_silence = _wav([0] * 900 + [5000] * 100 + [0] * 900)
    short_silence = _wav([5000] * 100 + [0] * 10)
    a, b = frames(pacing.trim(long_silence)), frames(pacing.trim(short_silence))
    assert len(a) == 30 + 100 + 220                      # 30 ms lead, the sound, 220 ms tail at 1 kHz
    assert len(b) == 100 + 220                           # no lead to keep; the tail is padded up
    assert pacing.trim(_wav([0] * 50)) == _wav([0] * 50)          # all silence: unchanged
    assert pacing.trim(WAV) == WAV                                 # not a readable WAV: unchanged


# -- OpenRouter -----------------------------------------------------------------

MP3 = b"ID3\x04" + b"\0" * 60
CATALOGUE = {"data": [
    {"id": "elevenlabs/eleven-turbo-v2.5", "name": "ElevenLabs: Turbo v2.5", "supported_voices": ["george", "sarah"],
     "pricing": {"prompt": "0.00002", "completion": "0"}},
    {"id": "google/gemini-tts", "name": "Gemini TTS", "supported_voices": ["Kore"],
     "pricing": {"prompt": "0.0000005", "completion": "0.000009"}},
    {"id": "fish-audio/s1", "name": "No voice list", "supported_voices": [], "pricing": {"prompt": "0.000015"}},
    {"id": "hexgrad/kokoro-82m", "name": "Kokoro", "supported_voices": ["af_heart"],
     "pricing": {"prompt": "0.00000062", "completion": "0"}},
]}


@pytest.fixture
def openrouter_hub(monkeypatch):
    from chisel.ai import client
    from chisel.speech import openrouter

    sent = []

    def opener(req, timeout=None):
        sent.append(req)
        if req.full_url.endswith("/models?output_modalities=speech"):
            return Resp(json.dumps(CATALOGUE).encode())
        if req.full_url.endswith("/audio/speech"):
            return Resp(MP3)
        raise urllib.error.URLError(req.full_url)

    monkeypatch.setattr(openrouter, "_catalogue", None)
    monkeypatch.setattr(openrouter.urllib.request, "urlopen", opener)
    monkeypatch.setattr(client, "get_api_key", lambda: "or-key")
    return sent


def test_openrouter_catalogue_keeps_castable_models_with_prices(openrouter_hub):
    from chisel.speech import openrouter

    rows = openrouter.catalogue(opener=openrouter.urllib.request.urlopen)
    assert [r["id"] for r in rows] == ["hexgrad/kokoro-82m", "elevenlabs/eleven-turbo-v2.5", "google/gemini-tts"]
    eleven = openrouter.known("elevenlabs/eleven-turbo-v2.5")
    assert eleven["pricePerMillion"] == 20.0 and eleven["perHour"] == 1.08
    assert openrouter.known("google/gemini-tts")["pricePerMillion"] is None      # priced per audio token: unknown
    openrouter.catalogue(opener=openrouter.urllib.request.urlopen)
    assert len(openrouter_hub) == 1                                              # fetched once a session


def test_openrouter_render_sends_mp3_request_with_the_ai_key(openrouter_hub):
    from chisel.speech import openrouter

    out = openrouter.render("elevenlabs/eleven-turbo-v2.5", "george", "Hello.", 1.0,
                            opener=openrouter.urllib.request.urlopen)
    req = openrouter_hub[-1]
    assert out == MP3 and req.get_header("Authorization") == "Bearer or-key"
    assert json.loads(req.data) == {"model": "elevenlabs/eleven-turbo-v2.5", "input": "Hello.", "voice": "george",
                                    "response_format": "mp3"}                 # no speed at the default
    openrouter.render("m", "v", "Hi", 1.25, opener=openrouter.urllib.request.urlopen)
    assert json.loads(openrouter_hub[-1].data)["speed"] == 1.25
    with pytest.raises(RuntimeError, match="OpenRouter key"):
        openrouter.render("m", "v", "Hi", key="")
    with pytest.raises(RuntimeError, match="did not send audio"):
        openrouter.render("m", "v", "Hi", key="k", opener=lambda req, timeout=None: Resp(b'{"error": 1}'))

    def broke(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 402, "x", {}, io.BytesIO(b'{"error": {"message": "add credits"}}'))
    with pytest.raises(RuntimeError, match="out of credit.*add credits"):
        openrouter.render("m", "v", "Hi", key="k", opener=broke)


def test_bridge_openrouter_models_voices_and_an_mp3_clip(openrouter_hub):
    from chisel.ai import usage

    api = Api()
    info = api.speech_info()
    assert info["hasOpenRouterKey"] and info["prefs"]["orModel"] == "elevenlabs/eleven-turbo-v2.5"
    assert len(openrouter_hub) == 0                                    # opening the reader fetches nothing
    models_ = api.speech_models()
    assert models_["ok"] and models_["openrouter"]["perHour"] == 1.08
    assert api.speech_set({"engine": "openrouter"})["ok"]
    assert [v["id"] for v in api.speech_voices("openrouter")["voices"]] == ["george", "sarah"]
    before = usage.LEDGER.count()
    clip = api.speech_clip("Hello there.", "george", 1.0)
    assert clip["ok"] and clip["dataUrl"].startswith("data:audio/mpeg;base64,") and not clip["cached"]
    assert clip["cost"] == pytest.approx(12 * 20 / 1_000_000) and usage.LEDGER.count() == before + 1
    again = api.speech_clip("Hello there.", "george", 1.0)
    assert again["cached"] and again["dataUrl"] == clip["dataUrl"]
    api.speech_set({"orModel": "gone/model"})
    assert "does not list" in api.speech_voices("openrouter")["error"]
