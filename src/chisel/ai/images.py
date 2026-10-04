"""AI inspiration images (SPEC "Inspiration images"): picture a setting.

Two calls, both started by an explicit click and neither touching the prose:

- ``suggest_prompt`` - **Describe this scene**: a cheap text model turns the
  passage around the cursor and the place/character notes into one visual
  paragraph. The author edits it before generating. It uses the *fast* model:
  it is a short, mechanical summary (no voice to match, no schema needed),
  the author prefers cheap models, and the click should come back quickly -
  the writing model's prose skill buys nothing here.
- ``generate`` - an OpenRouter chat completion with image output. The reply's
  ``message.images`` holds data URLs (JPEG or PNG); several are all kept. The
  call is recorded in the spend ledger as feature ``image``. No JSON schema and
  no ``provider.require_parameters``: image models do not take them.

The pictures are stored by ``core.inspiration``.
"""

from __future__ import annotations

import base64
import binascii
import re

from ..core import inspiration as store
from ..core import settings as user_settings
from .client import is_local, openrouter_extra_body, usage_extra_body
from .usage import record_response

DEFAULT_STYLE = "cinematic, atmospheric, no text, no watermark"
STYLE_MAX = 300
PROMPT_MAX = 2000
SETTING_STYLE = "image_style"

_DATA_URL = re.compile(r"\Adata:(?P<mime>[\w.+/-]*)(?P<params>(?:;[^,;]*)*?)(?P<b64>;base64)?,(?P<data>.*)\Z",
                       re.DOTALL)

DESCRIBE_SYSTEM_PROMPT = """\
You write prompts for an image generator, to give a novelist a picture of the
setting of the scene they are writing. Reference art for the author's desk,
never an illustration of the book.

Output ONE paragraph of plain text (50-90 words) and nothing else: no
preamble, no quotation marks, no Markdown, no list.
Describe what the camera sees: the place, the architecture and objects, the
light and its source, the weather and time of day, the colour palette, the mood
and the era. Prefer concrete visual detail from the passage and the notes.
Rules:
- The image must contain no text, lettering, signs with words, logos or captions.
- Do not name real people, brands or artists. Fictional characters may appear
  only as unnamed figures, and only when the passage needs them in the frame.
- Describe a setting, not a plot: no events that need explaining.
"""


class ImageError(ValueError):
    """Shown to the author as-is (no image came back, a bad reply, ...)."""


def style_suffix() -> str:
    """The author's style suffix (Settings), else the default. "" is allowed:
    an empty setting means the author turned the suffix off."""
    raw = user_settings.get(SETTING_STYLE)
    return DEFAULT_STYLE if raw is None else " ".join(str(raw).split())[:STYLE_MAX]


def full_prompt(prompt: str, suffix: str | None = None) -> str:
    """What is sent: the author's prompt plus the style suffix."""
    prompt = " ".join((prompt or "").split())
    suffix = style_suffix() if suffix is None else " ".join(suffix.split())
    if not suffix:
        return prompt
    return prompt if suffix.casefold() in prompt.casefold() else f"{prompt.rstrip('.')}. {suffix}"


# -- parsing --------------------------------------------------------------------


def _as_dict(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            out = dump()
            if isinstance(out, dict):
                return out
        except Exception:
            pass
    return {k: v for k, v in getattr(obj, "__dict__", {}).items() if not k.startswith("_")}


def parse_data_url(url: str) -> tuple[bytes, str] | None:
    """``data:image/png;base64,...`` -> (bytes, ext); None for anything else
    (a remote URL is never fetched) or for undecodable / non-image data."""
    m = _DATA_URL.match((url or "").strip())
    if m is None or not m.group("b64"):
        return None
    try:
        data = base64.b64decode(re.sub(r"\s+", "", m.group("data")), validate=True)
    except (binascii.Error, ValueError):
        return None
    ext = store.sniff_ext(data)
    if ext is None:
        try:
            ext = store.normalize_ext(m.group("mime"))
        except ValueError:
            return None
    return (data, ext) if data else None


def extract_images(message) -> list[tuple[bytes, str]]:
    """Every picture in a chat message (``images`` list of ``image_url`` parts)."""
    out = []
    for part in _as_dict(message).get("images") or []:
        part = _as_dict(part)
        url = part.get("image_url")
        url = _as_dict(url).get("url") if not isinstance(url, str) else url
        parsed = parse_data_url(url or "")
        if parsed is not None:
            out.append(parsed)
    return out


def _reply_text(message) -> str:
    d = _as_dict(message)
    content = d.get("content")
    if isinstance(content, list):   # content parts
        content = " ".join(str(_as_dict(p).get("text") or "") for p in content)
    return " ".join(str(content or d.get("refusal") or "").split())


# -- network calls ----------------------------------------------------------------


def generate(prompt: str, model: str, client=None, style: str | None = None) -> list[tuple[bytes, str]]:
    """Network call: one or more pictures for *prompt* (with the style suffix
    appended; *style* overrides the setting). Synchronous - run it off the UI
    thread. Records the cost as feature ``image``. Raises ImageError when the
    reply holds no usable picture (the message carries what the model said)."""
    if is_local(model):
        raise ImageError(
            "Picture generation needs an OpenRouter image model; local servers "
            "do not generate images.")
    sent = full_prompt(prompt, style)
    if not sent:
        raise ImageError("describe the picture first")
    if client is None:
        from .client import make_client

        client = make_client(model)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": sent[:PROMPT_MAX]}],
        extra_body=usage_extra_body({"modalities": ["image", "text"]}),
    )
    record_response(response, model, "image")
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ImageError("the model returned no reply")
    message = choices[0].message
    images = extract_images(message)
    if not images:
        said = _reply_text(message)
        raise ImageError(f"The model did not return an image: {said[:300]}" if said
                         else "The model did not return an image.")
    return images


def scene_context(scene_text: str, cursor_offset: int, entities, canon_by_name: dict[str, str],
                  originals: dict[str, str] | None = None) -> str:
    """What **Describe this scene** sends: the passage around the cursor, the notes
    of the places and characters it mentions and the scene's details (POV, place).
    No style guide (the picture has no prose voice). Pending AI drafts are stripped."""
    from .writing import CURSOR, build_context

    context = build_context(scene_text, cursor_offset, entities, canon_by_name, None,
                            originals=originals)
    return context.replace(f"SCENE (the new text goes at {CURSOR}):",
                           f"PASSAGE (picture the setting around {CURSOR}):")


def build_description_request(context: str) -> str:
    if "<<CURSOR>>" not in context:   # a note (character, place, ...) has no cursor
        return f"{context}\n\nWrite the image prompt for the subject above."
    return f"{context}\n\nWrite the image prompt for the setting around <<CURSOR>>."


def clean_prompt(raw: str) -> str:
    """One tidy paragraph: no fences, labels or wrapping quotes."""
    text = (raw or "").strip()
    text = re.sub(r"\A```[^\n]*\n|\n?```\s*\Z", "", text).strip()
    text = re.sub(r"\A(?:image\s+)?prompt\s*:\s*", "", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    if len(text) > 1 and text[0] in "\"“'‘" and text[-1] in "\"”'’":
        text = text[1:-1].strip()
    return text[:PROMPT_MAX]


def suggest_prompt(scene_context: str, model: str, client=None) -> str:
    """Network call - **Describe this scene**: a one-paragraph visual prompt from
    *scene_context* (``writing.build_context`` with no style guide: the passage
    around the cursor plus place/character notes). Plain text; the author edits
    it before anything is generated. Raises ImageError on an empty reply."""
    if client is None:
        from .client import make_client

        client = make_client(model)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DESCRIBE_SYSTEM_PROMPT},
            {"role": "user", "content": build_description_request(scene_context)},
        ],
        extra_body=openrouter_extra_body(model=model),
    )
    record_response(response, model, "image-prompt")
    text = clean_prompt(_reply_text(response.choices[0].message) if response.choices else "")
    if not text:
        raise ImageError("the model returned no description")
    return text
