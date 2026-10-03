"""Bridge helpers for inspiration images: JSON rows, data URLs, saving a batch.

``gui/api.py`` keeps thin ``@bridge`` wrappers; the logic is here so it is
testable without the AI. An image's link (``for``) is the project-relative path of
any item (scene, entity note, notebook note), which is also that item's GUI
document id.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from pathlib import Path

from ..ai import images as image_ai
from ..ai.client import resolve_model
from ..core import inspiration as store
from ..core.inspiration import get  # noqa: F401  (re-exported for the Api)

UPLOAD_MAX = 10 * 1024 * 1024          # bytes of picture the author may add
UPLOAD_MIME = ("image/jpeg", "image/png", "image/webp")
_DATA_URL = re.compile(r"\Adata:(?P<mime>[^;,]*)(?P<params>(?:;[^,;]*)*?);base64,(?P<data>.*)\Z", re.DOTALL)


def row(img: store.Image, unlinked: bool = False) -> dict:
    """*unlinked*: its item (``for``) no longer exists (renamed away by hand, in the Trash,
    deleted); the link is kept, so a restore reconnects it."""
    return {
        "id": img.id, "ext": img.ext, "prompt": img.prompt, "model": img.model,
        "for": img.link, "scene": img.link,   # "scene" is the old name of "for"
        "created": img.created, "cost": img.cost, "pinned": img.pinned,
        "title": img.title, "notes": img.notes, "label": img.label,
        "source": img.source, "unlinked": unlinked,
    }


def listing(project) -> dict:
    return {
        "images": [row(i, bool(i.link) and not (project.root / i.link).is_file())
                   for i in store.list_images(project)],
        "model": resolve_model("image", project.meta),
        "style": image_ai.style_suffix(),
    }


def data_url(project, image_id: str) -> str:
    data, mime = store.read_file(project, image_id)
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def save_pictures(project, pictures: list[tuple[bytes, str]], prompt: str, model: str,
                  scene: str, pin: bool, cost: float | None) -> dict:
    saved = store.save_batch(project, pictures, prompt, model, scene, pin, cost)
    return {"images": [row(i) for i in saved], "cost": cost}


def decode_upload(data_url_text: str) -> tuple[bytes, str]:
    """``data:image/png;base64,...`` -> (bytes, ext) for a picture the author adds.
    ValueError (shown as-is) unless it is a JPG, PNG or WebP that is really what its mime
    type says (GIF, SVG and anything else are refused) and is at most ``UPLOAD_MAX`` bytes."""
    m = _DATA_URL.match((data_url_text or "").strip()) if isinstance(data_url_text, str) else None
    if m is None:
        raise ValueError("that is not a picture file")
    mime = m.group("mime").strip().lower()
    if mime not in UPLOAD_MIME:
        raise ValueError("only JPG, PNG and WebP pictures can be added")
    payload = re.sub(r"\s+", "", m.group("data"))
    if len(payload) > math.ceil(UPLOAD_MAX / 3) * 4:   # before decoding: do not inflate a huge string
        raise ValueError(f"the picture is larger than {UPLOAD_MAX // (1024 * 1024)} MB")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("the picture data is damaged") from None
    if not data:
        raise ValueError("the picture is empty")
    if len(data) > UPLOAD_MAX:
        raise ValueError(f"the picture is larger than {UPLOAD_MAX // (1024 * 1024)} MB")
    ext = store.sniff_ext(data)
    if ext is None or ext != store.normalize_ext(mime):
        raise ValueError("the file is not a real JPG, PNG or WebP picture")
    return data, ext


def upload_title(name) -> str:
    """The display name for an uploaded picture: its file name without folders or
    extension. Never used as a file name (the store slugs the title)."""
    base = re.split(r"[\\/]", str(name or ""))[-1]
    base = re.sub(r"\.[A-Za-z0-9]{1,5}\Z", "", base)
    return " ".join(re.sub(r"[\x00-\x1f]", " ", base).split())[:store.TITLE_MAX] or "Added picture"


def save_upload(project, name, data_url_text: str, link: str = "") -> dict:
    """Store a picture the author added (``source: upload``, model ``upload``, no cost, not
    pinned) in the same folder as the generated ones, optionally for the item *link*."""
    data, ext = decode_upload(data_url_text)
    img = store.save(project, data, ext, {"title": upload_title(name), "model": "upload",
                                          "source": "upload", "for": link, "cost": None})
    return {"image": row(img)}


def update(project, image_id: str, fields: dict, item_path) -> dict:
    """Apply the editable fields the UI may send; *item_path* maps a document id (any
    kind) to its path (raising for anything that is not a document)."""
    kwargs: dict = {}
    for key, value in (fields or {}).items():
        if key == "pinned":
            kwargs["pinned"] = bool(value)
        elif key in ("for", "scene"):
            kwargs["link"] = "" if not value else str(item_path(str(value)).relative_to(project.root.resolve()).as_posix())
        elif key in ("title", "notes"):
            kwargs[key] = str(value or "")
        else:
            raise ValueError(f"cannot change {key}")
    return row(store.update(project, image_id, **kwargs))


def reveal(path: Path) -> bool:
    """Open the folder holding *path* in the file manager; only called from an
    explicit click in the real window."""
    return store.open_path(path.parent)
