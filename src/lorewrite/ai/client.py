"""OpenRouter client (OpenAI-compatible). Stub for M2+; not wired into the TUI yet.

Design notes (SPEC §8):
- Key resolution order: OPENROUTER_API_KEY env var, then keyring
  (service "lorewrite", username "openrouter").
- Model slugs are never hardcoded at runtime in production code; the
  defaults below are starting points and can be overridden in config.
"""

from __future__ import annotations

import os

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
KEYRING_SERVICE = "lorewrite"
KEYRING_USER = "openrouter"

# Sensible defaults (see research: cheap model for linking, strong for lore).
DEFAULT_FAST_MODEL = "google/gemini-2.5-flash"
DEFAULT_STRONG_MODEL = "anthropic/claude-sonnet-4.5"


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
