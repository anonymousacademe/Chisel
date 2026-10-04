# Plan: Local models (Ollama / OpenAI-compatible)

Roadmap item 3 of SPEC §14. The user asked for it (2026-10-03): "build in the
local model with Ollama (be able to choose what is currently installed)".

## Design decisions

1. **A `local:` prefix on the model slug** (`local:llama3.1`) marks a model
   served by the author's own OpenAI-compatible server. Nothing else changes:
   roles (`fast` / `strong` / `writing` / `image`) keep their precedence
   (project.toml > user setting > default), `resolve_model` returns the
   prefixed slug and every consumer that treats a model as an opaque string
   keeps working (status bar, ledger, budget, sidecars' `model:` field).
2. **Base URL**: user setting `local_base_url`, default
   `http://127.0.0.1:11434/v1` (Ollama). Normalized on use (scheme + host
   required, trailing slash trimmed). No key: the OpenAI SDK gets the
   placeholder `"local"`. Privacy: a local request never leaves the machine.
3. **Routing**: `make_client(model=None)` - when the model is local the client
   points at the local base URL, otherwise OpenRouter as before. Every caller
   passes the model it is about to send.
4. **OpenRouter-only request fields are skipped for local models**:
   `usage: {include: true}` and `provider.require_parameters` (what unknown
   request fields a given server tolerates varies). The spend ledger records
   what the server reports: tokens usually, cost never (it is free).
5. **Listing installed models**: `list_local_models` GETs
   `{base}/models` (the OpenAI-compat endpoint every server has: Ollama, LM
   Studio, llama.cpp, vLLM). Context length comes from the payload when the
   server reports it, else best-effort Ollama `POST /api/show`
   (Ollama's `num_ctx` default is small; over-planning would overflow).
   Lengths are remembered in `<state dir>/model-context.json` under the
   prefixed id, so `budget.window_for` plans correctly next session too. As a
   last resort the existing `context_window` setting applies (it exists for
   exactly this), then `DEFAULT_WINDOW`.
6. **Image generation stays OpenRouter-only** in v1 (a local model chosen for
   the image role is a clean error; the image picker never lists local).
7. **Structured output**: `response_format: json_schema` is sent as before -
   Ollama supports it; servers that do not will error and the author picks a
   model that does for the fast/strong roles (same trade-off as OpenRouter).

## Touchpoints

- `ai/client.py`: prefix, base-URL helpers, `make_client(model)`,
  `list_local_models`, `chat_extra_body`-style gating helpers.
- Call sites that add OpenRouter-only fields: `ai/links.py`, `ai/continuity.py`
  (x2), `ai/writing.py` (x3), `ai/style.py`, `ai/images.py` (x2), `ai/stream.py`.
- GUI bridge (`gui/api.py`): `get_settings` / `set_settings` gain
  `local_base_url`; new `list_local_models` bridge method; `mockai.py` fakes it.
- React settings dialog: a Local AI section (base URL, "list installed"
  check) and an "Installed (local)" source in the model picker.
- TUI `settingscreen.py`: base-URL field; the `ModelPicker` toggles source
  with a key binding (not for the image field).
- SPEC §8 (provider), §14 (mark done); CHANGELOG.

## Testing

No network: `list_local_models` is tested against a threaded localhost HTTP
stub (OpenAI-compat payload + Ollama `/api/show`), `make_client` by inspecting
`base_url`, the request-field gating by fake clients that capture kwargs.
The GUI monkeypatches `_list_local_models` at `chisel.gui.api`; the TUI
monkeypatches `settingscreen.list_local_models` (same seams as the OpenRouter
picker).
