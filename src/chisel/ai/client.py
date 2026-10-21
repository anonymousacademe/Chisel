"""OpenRouter + local OpenAI-compatible clients: key resolution, client, model catalog.

Design notes (SPEC §8):
- Key resolution order: OPENROUTER_API_KEY env var, then keyring
  (service "chisel", username "openrouter").
- Model slugs are never hardcoded at runtime in production code; the
  defaults below are starting points and can be overridden in config.
- A ``local:`` prefix (``local:llama3.1``) sends the call to the author's
  own OpenAI-compatible server (Ollama by default; docs/dev/plan-local-models.md).
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, replace

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
KEYRING_SERVICE = "chisel"
KEYRING_USER = "openrouter"
LEGACY_KEYRING_SERVICE = "lorewrite"  # the LoreWriter-era entry: read when the new one is empty, copied over

# Local models (SPEC "Local models"): a model id starting with LOCAL_PREFIX runs
# on the OpenAI-compatible server at the local_base_url setting (Ollama by
# default). No key is needed; the request never leaves the machine.
LOCAL_PREFIX = "local:"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
SETTING_LOCAL_BASE_URL = "local_base_url"
LOCAL_KEY_PLACEHOLDER = "local"

# Sensible defaults (see research: cheap model for linking, strong for lore).
DEFAULT_FAST_MODEL = "google/gemini-2.5-flash"
DEFAULT_STRONG_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_WRITING_MODEL = DEFAULT_STRONG_MODEL  # drafting & rewrites (plain text)
# The cheapest OpenRouter model with image output (about $0.03 per picture).
DEFAULT_IMAGE_MODEL = "google/gemini-3.1-flash-lite-image"

MODEL_DEFAULTS = {
    "fast": DEFAULT_FAST_MODEL,
    "strong": DEFAULT_STRONG_MODEL,
    "writing": DEFAULT_WRITING_MODEL,
    "image": DEFAULT_IMAGE_MODEL,
}


def resolve_model(kind: str, project_meta: dict | None = None) -> str:
    """The model for *kind* (fast | strong | writing | image | summary).

    Precedence: project.toml [ai] <kind>_model > global settings
    <kind>_model > built-in default. ``summary`` has no default of its own: it is the writing model.
    """
    from ..core import settings as user_settings

    key = f"{kind}_model"
    raw = ((project_meta or {}).get("ai") or {}).get(key)
    if raw:
        return str(raw)
    configured = user_settings.get(key)
    if configured:
        return configured
    return resolve_model("writing", project_meta) if kind == "summary" else MODEL_DEFAULTS[kind]


def usage_extra_body(extra: dict | None = None) -> dict:
    """extra_body for chat calls: ask OpenRouter to report cost, and merge
    any existing provider options (e.g. require_parameters)."""
    body = dict(extra or {})
    body["usage"] = {**(body.get("usage") or {}), "include": True}
    return body


# Reasoning for the utility calls (SPEC "Thinking for utility calls"): some cheap models think for minutes
# before a 100-word answer. ``default`` sends nothing (today's request); ``low`` / ``off`` ask OpenRouter.
SETTING_REASONING = "reasoning"
REASONING_VALUES = ("default", "low", "off")
UTILITY_FEATURES = frozenset({"aliases", "continuity", "canon", "relationships", "voice", "summary",
                              "part summary", "style"})
_REASONING_BODIES = {"low": {"reasoning": {"effort": "low"}}, "off": {"reasoning": {"enabled": False}}}
_meta_source = None


def resolve_reasoning(project_meta: dict | None = None) -> str:
    """default | low | off. Precedence: project.toml [ai] reasoning > user settings > default; an
    unknown value falls through to the next level (finally ``default``)."""
    from ..core import settings as user_settings

    for raw in (((project_meta or {}).get("ai") or {}).get(SETTING_REASONING),
                user_settings.get(SETTING_REASONING)):
        value = str(raw or "").strip().lower()
        if value in REASONING_VALUES:
            return value
    return "default"


def reasoning_extra_body(setting: str | None) -> dict:
    """The request field for a reasoning *setting*: ``{}`` for default or anything unknown."""
    return {k: dict(v) for k, v in _REASONING_BODIES.get(str(setting or "").strip().lower(), {}).items()}


def set_meta_source(getter) -> None:
    """Register a callable returning the open project's meta (or None), so utility calls can read the
    project's [ai] reasoning without every call site carrying the project."""
    global _meta_source
    _meta_source = getter


def active_reasoning(model: str | None = None) -> str:
    """The reasoning setting a utility call to *model* runs with: always ``default`` for a local model."""
    if model is not None and is_local(model):
        return "default"
    try:
        meta = _meta_source() if _meta_source is not None else None
    except Exception:
        meta = None
    return resolve_reasoning(meta)


def reasoning_note(model: str | None = None) -> str:
    """"reasoning off" / "reasoning low" when a utility call to *model* runs so, else ""."""
    setting = active_reasoning(model)
    return "" if setting == "default" else f"reasoning {setting}"


def openrouter_extra_body(extra: dict | None = None, model: str | None = None,
                          reasoning: str | None = None) -> dict:
    """extra_body for a chat call to *model*.

    OpenRouter-only fields (the usage/cost ask, ``provider.require_parameters``)
    are skipped for local models: what unknown request fields a given local
    server tolerates varies, and local calls cost nothing to report.
    *reasoning* (``low`` | ``off``; utility calls only, see ``utility_extra_body``) adds the reasoning
    field and drops ``provider.require_parameters``, which is never sent together with it."""
    if model is not None and is_local(model):
        return {}
    body = usage_extra_body(extra)
    extra_reasoning = reasoning_extra_body(reasoning)
    if extra_reasoning:
        provider = {k: v for k, v in (body.get("provider") or {}).items() if k != "require_parameters"}
        body.pop("provider", None)
        if provider:
            body["provider"] = provider
        body.update(extra_reasoning)
    return body


def utility_extra_body(extra: dict | None = None, model: str | None = None) -> dict:
    """``openrouter_extra_body`` for a utility call (alias finder, continuity, canon, summaries,
    relationships, voice, style): adds the author's reasoning setting."""
    return openrouter_extra_body(extra, model=model, reasoning=active_reasoning(model))


def is_local(model: str | None) -> bool:
    """True when *model* runs on the author's own server (a ``local:`` slug)."""
    return bool(model) and str(model).startswith(LOCAL_PREFIX)


def local_model_id(model: str) -> str:
    """*model* without the ``local:`` prefix (the id the local server knows)."""
    return str(model)[len(LOCAL_PREFIX):]


def local_base_url(raw: str | None = None) -> str:
    """The local server base URL (normalized): the *raw* argument, else the
    ``local_base_url`` setting, else the Ollama default. Raises ValueError on
    anything that is not an http(s) URL."""
    from ..core import settings as user_settings

    value = str(raw if raw is not None else user_settings.get(SETTING_LOCAL_BASE_URL) or "").strip()
    if not value:
        value = DEFAULT_LOCAL_BASE_URL
    value = value.rstrip("/")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(
            f"The local AI server address must start with http:// or https:// (got {value!r})")
    return value



def get_api_key() -> str | None:
    """Resolve the OpenRouter API key: env first, then keyring."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        import keyring

        from ..core.migrate import migrate_api_key

        return migrate_api_key(keyring, KEYRING_SERVICE, LEGACY_KEYRING_SERVICE, KEYRING_USER)
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


# Per-request read timeout (seconds) and retries. The openai SDK default is
# 600 s with 2 retries, so one stalled request could freeze an AI action for
# ~30 minutes with no feedback.
REQUEST_TIMEOUT = 180.0
MAX_RETRIES = 1


def make_client(model: str | None = None):
    """Build an OpenAI client pointed at OpenRouter (or at the local server for
    a ``local:`` model). Raises if the OpenRouter key is missing for a remote call."""
    from openai import OpenAI

    if model is not None and is_local(model):
        return OpenAI(base_url=local_base_url(), api_key=LOCAL_KEY_PLACEHOLDER,
                      timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES)
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "No OpenRouter API key. Set OPENROUTER_API_KEY or store one "
            "via chisel.ai.client.set_api_key()."
        )
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key,
                  timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES)


# -- model catalog -------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    prompt_per_m: float | None  # USD per million tokens
    completion_per_m: float | None
    context_length: int | None
    output_modalities: tuple[str, ...] = ()
    image_price: float | None = None  # USD per generated image, when the catalog says


_models_payload: dict | None = None


def _per_million(raw) -> float | None:
    try:
        return float(raw) * 1_000_000
    except (TypeError, ValueError):
        return None


def _num_or_none(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_models(payload: dict, structured_only: bool = True,
                 output_modality: str | None = None) -> list[ModelInfo]:
    """Models usable by chisel, sorted by name.

    The structured-output calls (linking, continuity) send a strict JSON schema
    with provider.require_parameters, so by default models without
    structured-output support are left out. Drafting is plain text, so the
    writing-model picker passes structured_only=False for the whole catalog.
    *output_modality* ("image") keeps only models whose
    ``architecture.output_modalities`` lists it (the image-model picker, which
    also passes structured_only=False: image models take no JSON schema).
    """
    models = []
    for m in payload.get("data") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        if structured_only and "structured_outputs" not in (
                m.get("supported_parameters") or []):
            continue
        modalities = tuple(str(x) for x in
                           ((m.get("architecture") or {}).get("output_modalities") or []))
        if output_modality is not None and output_modality not in modalities:
            continue
        pricing = m.get("pricing") or {}
        models.append(ModelInfo(
            id=m["id"],
            name=m.get("name") or m["id"],
            prompt_per_m=_per_million(pricing.get("prompt")),
            completion_per_m=_per_million(pricing.get("completion")),
            context_length=m.get("context_length"),
            output_modalities=modalities,
            image_price=_num_or_none(pricing.get("image")),
        ))
    return sorted(models, key=lambda m: m.name.lower())


def list_models(timeout: float = 10, structured_only: bool = True,
                output_modality: str | None = None) -> list[ModelInfo]:
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
        remember_context_lengths(parse_models(_models_payload, False))
    return parse_models(_models_payload, structured_only, output_modality)


# -- local models (Ollama / OpenAI-compatible) ----------------------------------


def _ollama_context_length(base: str, model_id: str, timeout: float) -> int | None:
    """Best-effort context length from Ollama's ``POST /api/show`` (its OpenAI-compat
    ``/models`` endpoint does not report one). Any failure is tolerated: the budget
    then falls back to the context_window setting."""
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        req = urllib.request.Request(
            f"{base}/api/show", method="POST",
            data=json.dumps({"model": model_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            info = (json.load(resp) or {}).get("model_info") or {}
    except Exception:
        return None
    lengths = [int(v) for k, v in info.items()
               if k.endswith("context_length") and isinstance(v, (int, float)) and v > 0]
    return max(lengths) if lengths else None


def parse_local_models(payload: dict) -> list[ModelInfo]:
    """Models installed on a local OpenAI-compatible server, sorted by name.

    The payload is the ``GET {base}/models`` response (``data[].id`` at minimum;
    ``context_length`` when the server reports it). Ids come back prefixed with
    ``local:`` so they are valid model slugs everywhere else in the app."""
    models = []
    for m in payload.get("data") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        mid = str(m["id"])
        length = m.get("context_length")
        length = int(length) if isinstance(length, (int, float)) and length > 0 else None
        models.append(ModelInfo(
            id=LOCAL_PREFIX + mid,
            name=mid,
            prompt_per_m=None,
            completion_per_m=None,
            context_length=length,
        ))
    return sorted(models, key=lambda m: m.name.lower())


def list_local_models(base_url: str | None = None,
                      timeout: float = 5.0) -> list[ModelInfo]:
    """The models installed on the local server (Ollama by default).

    Raises ``RuntimeError`` with an author-friendly message when the server
    cannot be reached. Context lengths that the server reports (directly or via
    Ollama's ``/api/show``) are remembered for the budget."""
    base = local_base_url(base_url)
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=timeout) as resp:
            payload = json.load(resp)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Couldn't reach the local AI server at {base} ({exc.__class__.__name__}). "
            "Is it running? Check the address in Settings."
        ) from exc
    models = parse_local_models(payload)
    filled = []
    for m in models:
        if m.context_length is None:
            length = _ollama_context_length(base, local_model_id(m.id), timeout)
            if length is not None:
                m = replace(m, context_length=length)
        filled.append(m)
    remember_context_lengths(filled)
    return filled


# -- context windows (ai.budget plans AI requests against these) -------------------------
# The catalogue is fetched only when the author opens a model picker. The context lengths it
# reported are also kept in <state dir>/model-context.json so a later session can plan against
# the real window without a network call; ai.budget never fetches anything itself.

CONTEXT_FILE = "model-context.json"
PRICING_FILE = "model-pricing.json"


def remember_context_lengths(models) -> None:
    """Keep ``{id: context_length}`` of *models* (ModelInfo) on disk. Best effort."""
    from ..core.recents import default_state_dir

    lengths = {m.id: int(m.context_length) for m in models
               if isinstance(m.context_length, (int, float)) and m.context_length > 0}
    _remember_pricing(models)
    if not lengths:
        return
    try:
        folder = default_state_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:   # keep what earlier (differently filtered) lists reported
            old = json.loads((folder / CONTEXT_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        merged = {**(old if isinstance(old, dict) else {}), **lengths}
        (folder / CONTEXT_FILE).write_text(json.dumps(merged), encoding="utf-8", newline="\n")
    except OSError:
        pass


def _remember_pricing(models) -> None:
    """Keep ``{id: [prompt USD per million, completion USD per million]}`` of *models* beside the context lengths."""
    from ..core.recents import default_state_dir

    prices = {m.id: [m.prompt_per_m, m.completion_per_m] for m in models
              if m.prompt_per_m is not None and m.completion_per_m is not None}
    if not prices:
        return
    try:
        folder = default_state_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            old = json.loads((folder / PRICING_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        merged = {**(old if isinstance(old, dict) else {}), **prices}
        (folder / PRICING_FILE).write_text(json.dumps(merged), encoding="utf-8", newline="\n")
    except OSError:
        pass


def cached_pricing(model_id: str) -> tuple[float, float] | None:
    """(prompt, completion) USD per million tokens of *model_id* from a catalogue fetched earlier, or None
    when unknown. A ``local:`` model costs nothing: (0.0, 0.0). Never touches the network."""
    if is_local(model_id):
        return 0.0, 0.0
    for m in (_models_payload or {}).get("data") or []:
        if isinstance(m, dict) and m.get("id") == model_id:
            pricing = m.get("pricing") or {}
            prompt, completion = _per_million(pricing.get("prompt")), _per_million(pricing.get("completion"))
            if prompt is not None and completion is not None:
                return prompt, completion
    from ..core.recents import default_state_dir

    try:
        data = json.loads((default_state_dir() / PRICING_FILE).read_text(encoding="utf-8"))
        row = data.get(model_id) if isinstance(data, dict) else None
        return (float(row[0]), float(row[1])) if isinstance(row, list) and len(row) == 2 else None
    except (OSError, ValueError, TypeError):
        return None


def cached_is_reasoning(model_id: str) -> bool | None:
    """Does the catalogue (this session's) list ``reasoning`` among *model_id*'s supported parameters? True / False, or
    None when the model is not in the catalogue we have (never fetched, or a local model). No network."""
    if is_local(model_id):
        return None
    for m in (_models_payload or {}).get("data") or []:
        if isinstance(m, dict) and m.get("id") == model_id:
            params = m.get("supported_parameters")
            if not isinstance(params, list):
                return None
            return "reasoning" in params or "include_reasoning" in params
    return None


def cached_context_length(model_id: str) -> int | None:
    """The context length of *model_id* from a catalogue fetched earlier (this session or a
    previous one), or None. Never touches the network."""
    for m in (_models_payload or {}).get("data") or []:
        if isinstance(m, dict) and m.get("id") == model_id:
            length = m.get("context_length")
            return int(length) if isinstance(length, (int, float)) and length > 0 else None
    from ..core.recents import default_state_dir

    try:
        data = json.loads((default_state_dir() / CONTEXT_FILE).read_text(encoding="utf-8"))
        length = data.get(model_id) if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
    return int(length) if isinstance(length, (int, float)) and length > 0 else None
