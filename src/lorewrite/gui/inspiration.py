"""Bridge helpers for inspiration images: JSON rows, data URLs, saving a batch.

``gui/api.py`` keeps thin ``@bridge`` wrappers; the logic is here so it is
testable without the AI. Scene links are project-relative paths, which are also
the GUI's document ids.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ..ai import images as image_ai
from ..ai.client import resolve_model
from ..core import inspiration as store
from ..core.inspiration import get  # noqa: F401  (re-exported for the Api)


def row(img: store.Image) -> dict:
    return {
        "id": img.id, "ext": img.ext, "prompt": img.prompt, "model": img.model,
        "scene": img.scene, "created": img.created, "cost": img.cost,
        "pinned": img.pinned, "title": img.title, "notes": img.notes, "label": img.label,
    }


def listing(project) -> dict:
    return {
        "images": [row(i) for i in store.list_images(project)],
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


def update(project, image_id: str, fields: dict, scene_path) -> dict:
    """Apply the editable fields the UI may send; *scene_path* maps a scene id to
    its path (raising for anything that is not a scene)."""
    kwargs: dict = {}
    for key, value in (fields or {}).items():
        if key == "pinned":
            kwargs["pinned"] = bool(value)
        elif key == "scene":
            kwargs["scene"] = "" if not value else str(scene_path(str(value)).relative_to(project.root.resolve()).as_posix())
        elif key in ("title", "notes"):
            kwargs[key] = str(value or "")
        else:
            raise ValueError(f"cannot change {key}")
    return row(store.update(project, image_id, **kwargs))


def reveal(path: Path) -> bool:
    """Open the folder holding *path* in the file manager; only called from an
    explicit click in the real window."""
    return store.open_path(path.parent)
