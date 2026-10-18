"""Which engine reads aloud, and one door to render a clip with it.

Engines: ``browser`` (the system voices; the editor speaks itself, nothing here), ``kokoro`` (natural voices
downloaded from Hugging Face, run on this computer) and ``endpoint`` (an OpenAI-compatible speech server, local
or cloud). The choice and the server's address and model are a user setting (``speech``); the key is in the
keyring (endpoint.py)."""

from __future__ import annotations

import atexit

from ..ai import usage
from ..core import settings as user_settings
from . import cache, endpoint, kokoro

ENGINES = ("browser", "kokoro", "endpoint")
SETTING = "speech"
DEFAULTS = {"engine": "browser", "baseUrl": "http://127.0.0.1:8880/v1", "model": "kokoro"}

_kokoro = kokoro.KokoroEngine()
atexit.register(_kokoro.stop)


def get_prefs() -> dict:
    raw = user_settings.get(SETTING) or {}
    prefs = dict(DEFAULTS)
    if isinstance(raw, dict):
        prefs.update({k: str(raw[k]) for k in DEFAULTS if isinstance(raw.get(k), str) and raw[k].strip()})
    if prefs["engine"] not in ENGINES:
        prefs["engine"] = "browser"
    return prefs


def set_prefs(changes: dict) -> dict:
    prefs = get_prefs()
    for k in DEFAULTS:
        if k in (changes or {}):
            value = str(changes[k] or "").strip()
            if k == "engine" and value not in ENGINES:
                raise ValueError(f"unknown speech engine: {value}")
            if k == "baseUrl":
                value = endpoint.normalize_base(value)
            if value:
                prefs[k] = value
    user_settings.set(SETTING, prefs)
    if prefs["engine"] != "kokoro":
        _kokoro.stop()
    return prefs


def describe(prefs: dict | None = None) -> dict:
    """The endpoint's cost facts for the reader: local or cloud, price per million characters (None: unknown)
    and the estimate for an hour of listening."""
    prefs = prefs or get_prefs()
    try:
        base = endpoint.normalize_base(prefs["baseUrl"])
    except ValueError:
        return {"local": False, "pricePerMillion": None, "perHour": None}
    price = endpoint.price_per_million(base, prefs["model"])
    return {"local": endpoint.is_local(base), "pricePerMillion": price,
            "perHour": None if price is None else round(price * endpoint.CHARS_PER_HOUR / 1_000_000, 2)}


def render(text: str, voice: str, speed: float = 1.0, engine: str | None = None) -> dict:
    """{wav: bytes, cached, chars, cost} for *text* in *voice* with the chosen engine (or *engine*).
    A clip already rendered with the same engine, model, voice and speed comes from the cache (no cost)."""
    prefs = get_prefs()
    engine = engine or prefs["engine"]
    text = text.strip()
    if not text:
        raise ValueError("nothing to read")
    if not voice:
        raise ValueError("choose a voice")
    if engine == "kokoro":
        model = "kokoro-82m"
    elif engine == "endpoint":
        model = f"{endpoint.normalize_base(prefs['baseUrl'])}|{prefs['model']}"
    else:
        raise ValueError("the system voices are played by the window, not rendered")
    clip_key = cache.key(engine, model, voice, speed, text)
    found = cache.get(clip_key)
    if found is not None:
        return {"wav": found, "cached": True, "chars": len(text), "cost": 0.0}
    if engine == "kokoro":
        wav = _kokoro.render(text, voice, speed)
        spent: float | None = 0.0
    else:
        base = endpoint.normalize_base(prefs["baseUrl"])
        wav = endpoint.render(base, prefs["model"], voice, text, speed, endpoint.get_key())
        spent = endpoint.cost(len(text), base, prefs["model"])
        if not endpoint.is_local(base):          # an estimate, in the session's spend beside the AI calls
            usage.LEDGER.record(prefs["model"], "read aloud", spent)
    cache.put(clip_key, wav)
    return {"wav": wav, "cached": False, "chars": len(text), "cost": spent}


def warm() -> bool:
    """Start the local engine and load its model now (a few seconds), so the first Play does not wait for it.
    No sound and no network; False when the local voices are not the chosen engine or not installed."""
    if get_prefs()["engine"] != "kokoro" or _kokoro.running:
        return False
    from . import models

    st = models.status()
    if not (st["installed"] and st["engine"] and st["voices"]):
        return False
    _kokoro.render("Ready.", st["voices"][0]["id"])
    return True


def stop() -> None:
    """End the local engine's worker (app shutdown, or another engine chosen)."""
    _kokoro.stop()
