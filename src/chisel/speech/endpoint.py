"""Voices from a speech server that speaks the OpenAI ``/v1/audio/speech`` protocol.

That covers a local server on the author's machine (Kokoro-FastAPI, openedai-speech, LocalAI: free) and cloud
services (OpenAI and the many services that copy its API: paid per character). The address is the author's
choice; an optional key lives in the OS keyring (never in a file). Nothing is sent until the author presses Play
with this engine selected."""

from __future__ import annotations

import ipaddress
import json
import os
import urllib.error
import urllib.parse
import urllib.request

KEYRING_SERVICE = "chisel"
KEYRING_USER = "speech-endpoint"
ENV_KEY = "CHISEL_SPEECH_API_KEY"
TIMEOUT = 60

# What a few well-known services charge, US dollars per million characters, as published when this was written
# (see SPEC "Read aloud"). Shown as an estimate only; the author's bill is the truth.
PRICES = {
    # gpt-4o-mini-tts is billed per minute of audio (about $0.015): about 900 characters a minute
    "api.openai.com": {"tts-1": 15.0, "tts-1-hd": 30.0, "gpt-4o-mini-tts": 16.7},
}
OPENAI_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")
CHARS_PER_HOUR = 54_000          # about 150 words a minute


def normalize_base(raw: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(f"The speech server address must start with http:// or https:// (got {value!r})")
    return value


def is_local(base: str) -> bool:
    """True for a server on this machine or the local network (no per-character cost)."""
    host = urllib.parse.urlparse(base).hostname or ""
    if host in ("localhost",) or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def price_per_million(base: str, model: str) -> float | None:
    """Published price for this service and model, None when unknown, 0 for a local server."""
    if is_local(base):
        return 0.0
    host = urllib.parse.urlparse(base).hostname or ""
    return PRICES.get(host, {}).get(model)


def cost(chars: int, base: str, model: str) -> float | None:
    price = price_per_million(base, model)
    return None if price is None else chars * price / 1_000_000


def get_key() -> str | None:
    key = os.environ.get(ENV_KEY)
    if key:
        return key
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        return None


def set_key(key: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)


def clear_key() -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass


def _headers(key: str | None) -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "chisel-writer (read aloud)"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _error(exc: Exception, base: str) -> RuntimeError:
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            detail = (body.get("error") or {}).get("message", "") if isinstance(body.get("error"), dict) \
                else str(body.get("detail") or body.get("error") or "")
        except Exception:
            pass
        who = "OpenRouter" if base == "OpenRouter" else "The speech server"
        if exc.code in (401, 403):
            return RuntimeError(f"{who} refused the key ({exc.code}). {detail}".strip())
        if exc.code == 402:
            return RuntimeError(f"{who} says the account is out of credit (402). {detail}".strip())
        return RuntimeError(f"{who} answered {exc.code}. {detail}".strip())
    return RuntimeError(f"Could not reach {base}: {exc}" if base == "OpenRouter"
                        else f"Could not reach the speech server at {base}: {exc}")


def render(base: str, model: str, voice: str, text: str, speed: float = 1.0, key: str | None = None,
           opener=urllib.request.urlopen) -> bytes:
    """WAV bytes for *text*. Raises RuntimeError with a message for the author."""
    base = normalize_base(base)
    body = {"model": model, "input": text, "voice": voice, "response_format": "wav",
            "speed": min(4.0, max(0.25, float(speed)))}
    req = urllib.request.Request(f"{base}/audio/speech", data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(key), method="POST")
    try:
        with opener(req, timeout=TIMEOUT) as r:
            data = r.read()
    except (urllib.error.URLError, OSError) as exc:
        raise _error(exc, base) from exc
    if not data.startswith(b"RIFF"):
        raise RuntimeError("The speech server did not send a WAV clip (does it support response_format=wav?)")
    return data


def list_voices(base: str, key: str | None = None, opener=urllib.request.urlopen) -> list[str]:
    """Voice names the server reports (``/audio/voices``, used by Kokoro-FastAPI and others); for OpenAI and
    servers that do not say, the OpenAI voice names."""
    base = normalize_base(base)
    if (urllib.parse.urlparse(base).hostname or "") == "api.openai.com":
        return list(OPENAI_VOICES)
    req = urllib.request.Request(f"{base}/audio/voices", headers=_headers(key))
    try:
        with opener(req, timeout=10) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return list(OPENAI_VOICES)
    raw = payload.get("voices") if isinstance(payload, dict) else payload
    names = []
    for v in raw or []:
        name = v if isinstance(v, str) else (v.get("id") or v.get("name") if isinstance(v, dict) else None)
        if isinstance(name, str) and name:
            names.append(name)
    return names or list(OPENAI_VOICES)
