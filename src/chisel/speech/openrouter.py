"""Voices through OpenRouter (``POST /audio/speech``), with the OpenRouter key the AI features already use.

OpenRouter routes to many speech services (ElevenLabs, Google, Microsoft, xAI, Kokoro...). Its catalogue
(``GET /models?output_modalities=speech``, public) gives each model's voices (``supported_voices``) and price; a
model priced per character has ``pricing.prompt`` in US$ per character and ``pricing.completion`` 0. Others (per
second or per audio token) cannot be estimated ahead and are shown as "check its price". Clips come back as MP3:
OpenRouter's other format, raw PCM, does not say its sample rate, which differs between services.

Nothing is fetched or sent until the author chooses this engine (the catalogue) or presses Play / Hear (a clip)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from ..ai import client
from . import endpoint

BASE = client.OPENROUTER_BASE_URL
TIMEOUT = 60
DEFAULT_MODEL = "elevenlabs/eleven-turbo-v2.5"
UA = {"User-Agent": "chisel-writer (read aloud)"}

_catalogue: list[dict] | None = None
_lock = threading.Lock()


def parse_catalogue(payload: dict) -> list[dict]:
    """[{id, name, voices, pricePerMillion, perHour}] for the speech models that name their voices (a model
    without a voice list cannot be cast), cheapest known price first."""
    out = []
    for m in (payload.get("data") if isinstance(payload, dict) else None) or []:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str):
            continue
        voices = [v for v in m.get("supported_voices") or [] if isinstance(v, str) and v]
        if not voices:
            continue
        pricing = m.get("pricing") if isinstance(m.get("pricing"), dict) else {}
        try:
            prompt, completion = float(pricing.get("prompt") or 0), float(pricing.get("completion") or 0)
        except (TypeError, ValueError):
            prompt, completion = 0.0, 1.0
        per_million = round(prompt * 1_000_000, 2) if completion == 0 else None
        out.append({"id": m["id"], "name": str(m.get("name") or m["id"]), "voices": voices,
                    "pricePerMillion": per_million,
                    "perHour": None if per_million is None else round(per_million * endpoint.CHARS_PER_HOUR / 1_000_000, 2)})
    out.sort(key=lambda r: (r["pricePerMillion"] is None, r["pricePerMillion"] or 0, r["id"]))
    return out


def catalogue(opener=None, refresh: bool = False) -> list[dict]:
    """OpenRouter's speech models, fetched once a session. Raises RuntimeError when it cannot be reached."""
    global _catalogue
    opener = opener or urllib.request.urlopen          # looked up per call, so tests can replace it
    with _lock:
        if _catalogue is not None and not refresh:
            return _catalogue
        req = urllib.request.Request(f"{BASE}/models?output_modalities=speech", headers=UA)
        try:
            with opener(req, timeout=15) as r:
                _catalogue = parse_catalogue(json.loads(r.read().decode("utf-8")))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise RuntimeError(f"Could not reach OpenRouter for its voices: {exc}") from exc
        return _catalogue


def known(model: str) -> dict | None:
    """The catalogue row for *model* if the catalogue was already fetched (never fetches)."""
    return next((m for m in _catalogue or [] if m["id"] == model), None)


def cost(chars: int, model: str) -> float | None:
    row = known(model)
    price = row["pricePerMillion"] if row else None
    return None if price is None else chars * price / 1_000_000


def render(model: str, voice: str, text: str, speed: float = 1.0, key: str | None = None,
           opener=None) -> bytes:
    """MP3 bytes for *text*. Raises RuntimeError with a message for the author."""
    opener = opener or urllib.request.urlopen
    key = key if key is not None else client.get_api_key()
    if not key:
        raise RuntimeError("OpenRouter voices use your OpenRouter key: add it in Settings > AI first.")
    body: dict = {"model": model, "input": text, "voice": voice, "response_format": "mp3"}
    if abs(float(speed) - 1.0) > 1e-6:
        body["speed"] = float(speed)          # some services refuse any speed but the default: sent only when changed
    req = urllib.request.Request(f"{BASE}/audio/speech", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={**UA, "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with opener(req, timeout=TIMEOUT) as r:
            data = r.read()
    except (urllib.error.URLError, OSError) as exc:
        raise endpoint._error(exc, "OpenRouter") from exc
    if not data or data[:1] in (b"{", b"["):
        raise RuntimeError("OpenRouter did not send audio for this passage")
    return data
