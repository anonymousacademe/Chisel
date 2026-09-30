"""OpenRouter client (OpenAI-compatible): key resolution, client, model catalog.

Design notes (SPEC §8):
- Key resolution order: OPENROUTER_API_KEY env var, then keyring
  (service "lorewrite", username "openrouter").
- Model slugs are never hardcoded at runtime in production code; the
  defaults below are starting points and can be overridden in config.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
KEYRING_SERVICE = "lorewrite"
KEYRING_USER = "openrouter"

# Sensible defaults (see research: cheap model for linking, strong for lore).
DEFAULT_FAST_MODEL = "google/gemini-2.5-flash"
DEFAULT_STRONG_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_WRITING_MODEL = DEFAULT_STRONG_MODEL  # drafting & rewrites (plain text)


MODEL_DEFAULTS = {
    "fast": DEFAULT_FAST_MODEL,
    "strong": DEFAULT_STRONG_MODEL,
    "writing": DEFAULT_WRITING_MODEL,
}


def resolve_model(kind: str, project_meta: dict | None = None) -> str:
    """The model for *kind* (fast | strong | writing).

    Precedence: project.toml [ai] <kind>_model > global settings
    <kind>_model > built-in default.
    """
    from ..core import settings as user_settings

    key = f"{kind}_model"
    raw = ((project_meta or {}).get("ai") or {}).get(key)
    if raw:
        return str(raw)
    return user_settings.get(key) or MODEL_DEFAULTS[kind]


def usage_extra_body(extra: dict | None = None) -> dict:
    """extra_body for chat calls: ask OpenRouter to report cost, and merge
    any existing provider options (e.g. require_parameters)."""
    body = dict(extra or {})
    body["usage"] = {**(body.get("usage") or {}), "include": True}
    return body



def get_api_key() -> str | None:
    """Resolve the OpenRouter API key: env first, then keyring."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        return None


def set_api_key(key: str) -> None:
    """Store the key in the OS keyring."""
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)


def clear_api_key() -> None:
    """Remove the key from the OS keyring. Tolerates it being absent."""
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass


def make_client():
    """Build an OpenAI client pointed at OpenRouter. Raises if no key."""
    from openai import OpenAI

    key = get_api_key()
    if not key:
        raise RuntimeError(
            "No OpenRouter API key. Set OPENROUTER_API_KEY or store one "
            "via lorewrite.ai.client.set_api_key()."
        )
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)


# -- model catalog -------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    prompt_per_m: float | None  # USD per million tokens
    completion_per_m: float | None
    context_length: int | None


_models_payload: dict | None = None


def _per_million(raw) -> float | None:
    try:
        return float(raw) * 1_000_000
    except (TypeError, ValueError):
        return None


def parse_models(payload: dict, structured_only: bool = True) -> list[ModelInfo]:
    """Models usable by lorewrite, sorted by name.

    The structured-output calls (linking, continuity) send a strict JSON schema
    with provider.require_parameters, so by default models without
    structured-output support are left out. Drafting is plain text, so the
    writing-model picker passes structured_only=False for the whole catalog.
    """
    models = []
    for m in payload.get("data") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        if structured_only and "structured_outputs" not in (
                m.get("supported_parameters") or []):
            continue
        pricing = m.get("pricing") or {}
        models.append(ModelInfo(
            id=m["id"],
            name=m.get("name") or m["id"],
            prompt_per_m=_per_million(pricing.get("prompt")),
            completion_per_m=_per_million(pricing.get("completion")),
            context_length=m.get("context_length"),
        ))
    return sorted(models, key=lambda m: m.name.lower())


def list_models(timeout: float = 10, structured_only: bool = True) -> list[ModelInfo]:
    """Fetch the OpenRouter model catalog (public; no key needed).

    The raw payload is cached for the session and filtered per call.
    Raises on network or parse failure.
    """
    global _models_payload
    if _models_payload is None:
        with urllib.request.urlopen(
            f"{OPENROUTER_BASE_URL}/models", timeout=timeout
        ) as resp:
            _models_payload = json.load(resp)
    return parse_models(_models_payload, structured_only)
