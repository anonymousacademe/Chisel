"""Inspiration images for the terminal app (SPEC "Inspiration images").

A mixin for ``LorewriteApp`` so the feature lives in its own file. The AI calls
are looked up on ``lorewrite.tui.app`` at call time (``generate_image``,
``suggest_image_prompt``) so tests mock them where the other AI calls are mocked.
Pictures are saved under ``<project>/inspiration/``; the desktop's viewer is
started (``xdg-open``) only when the author chooses to open one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import work

from ..ai import images as image_ai
from ..ai.usage import LEDGER
from ..core import inspiration as store
from .inspirationscreens import InspirationListScreen, InspirationPromptScreen


def _app_fn(name: str):
    from . import app as app_module

    return getattr(app_module, name)


class InspirationMixin:
    # -- helpers --------------------------------------------------------------------

    def _insp_scene_rel(self) -> str:
        path = self._current_scene_path()
        if path is None:
            return ""
        try:
            return path.relative_to(self.project.root).as_posix()
        except ValueError:
            return ""

    def _insp_scene_label(self) -> str:
        path = self._current_scene_path()
        return self.project.scene_title(path) if path is not None else ""

    def open_external(self, path: Path) -> bool:
        """Open a picture or folder with the desktop (only called after a choice)."""
        return store.open_path(path)

    def _last_cost(self, calls_before: int) -> float | None:
        last = LEDGER.last()
        return last.cost if LEDGER.count() > calls_before and last is not None else None

    # -- Action · Inspiration image… ----------------------------------------------------

    def inspiration_prompt(self, initial: str = "") -> None:
        if self.project is None:
            return
        self.push_screen(InspirationPromptScreen(initial, self._insp_scene_label()), self._inspiration_prompt_done)

    def _inspiration_prompt_done(self, result) -> None:
        if not result:
            return
        what, text, pin = result
        scene = self._insp_scene_rel()
        if what == "describe":
            if not scene:
                return
            context = image_ai.scene_context(
                self.editor.text, self._cursor_offset(), list(self.entities), self._canon_map(),
                self._originals(self.editor.text))
            self.notify("Describing the scene…", timeout=3)
            self._inspiration_describe_worker(context, self._ai_model("fast"), text)
        else:
            self.notify("Making the picture (about $0.03)…", timeout=5)
            self._inspiration_generate_worker(text, self._ai_model("image"), scene, pin and bool(scene))

    @work(exclusive=True, group="inspiration")
    async def _inspiration_describe_worker(self, context: str, model: str, keep: str) -> None:
        calls = LEDGER.count()
        try:
            text = await asyncio.to_thread(_app_fn("suggest_image_prompt"), context, model)
        except Exception as exc:
            self.notify(f"Could not describe the scene: {exc}", severity="error", timeout=6)
            self.inspiration_prompt(keep)
            return
        self._cost_note(calls)
        self.notify("Edit the description if you like, then ctrl+g to generate.", timeout=4)
        self.inspiration_prompt(text)

    @work(exclusive=True, group="inspiration")
    async def _inspiration_generate_worker(self, prompt: str, model: str, scene: str, pin: bool) -> None:
        calls = LEDGER.count()
        try:
            pictures = await asyncio.to_thread(_app_fn("generate_image"), prompt, model)
        except Exception as exc:
            self._cost_note(calls)
            self.notify(f"No picture: {exc}", severity="error", timeout=8)
            self.inspiration_prompt(prompt)      # nothing is lost: the description comes back
            return
        cost = self._last_cost(calls)
        self._cost_note(calls)
        try:
            saved = store.save_batch(self.project, pictures, prompt, model, scene, pin, cost)
        except (OSError, ValueError) as exc:
            self.notify(f"Could not save the picture: {exc}", severity="error", timeout=8)
            return
        where = ", ".join(i.path.relative_to(self.project.root).as_posix() for i in saved)
        spent = f" (AI ${cost:.4f})" if cost is not None else ""
        self.notify(f"Saved {where}{spent}. Action · Open last inspiration image shows it.", timeout=8)

    # -- the list: open / pin / trash ---------------------------------------------------

    def open_inspiration(self) -> None:
        """Action · Inspiration images: the open scene's pictures, with open / pin / trash."""
        if self.project is None:
            return
        scene = self._insp_scene_rel()
        everything = store.list_images(self.project)
        mine = [i for i in everything if scene and i.scene == scene]
        if not everything:
            self.notify("No inspiration images yet (Action · Inspiration image… makes one)", timeout=4)
            return
        self.push_screen(InspirationListScreen(mine, everything, self._insp_scene_label() if scene else ""),
                         self._inspiration_list_done)

    def _inspiration_list_done(self, result) -> None:
        if not result:
            return
        what, image_id = result
        try:
            img = store.get(self.project, image_id)
        except (FileNotFoundError, ValueError) as exc:
            self.notify(str(exc), severity="warning")
            return
        scene = self._insp_scene_rel()
        if what == "open":
            if not self.open_external(img.path):
                self.notify(f"Could not start a viewer; the file is {img.path}", severity="warning", timeout=8)
        elif what == "pin":
            on = not (img.pinned and img.scene == scene)
            if on and not scene:
                self.notify("Open a scene to pin a picture to it", severity="warning")
            else:
                store.update(self.project, image_id, pinned=on, **({"scene": scene} if on else {}))
                self.notify("Pinned to this scene" if on else "Unpinned", timeout=2)
        elif what == "trash":
            from .app import ConfirmScreen

            def _go(ok: bool) -> None:
                if ok:
                    self.project.trash_inspiration(image_id)
                    self.notify("Moved to the Trash (Action · Open Trash restores it)", timeout=3)
                    self.open_inspiration()

            self.push_screen(ConfirmScreen(f"Move the picture '{img.label}' to the Trash?\n"
                                           "You can restore it from Action · Open Trash.",
                                           confirm_label="Move to Trash"), _go)
            return
        self.open_inspiration()

    # -- opening files (only when chosen) ----------------------------------------------------

    def open_inspiration_folder(self) -> None:
        if self.project is None:
            return
        folder = store.inspiration_dir(self.project)
        folder.mkdir(parents=True, exist_ok=True)
        if not self.open_external(folder):
            self.notify(f"Could not start a file manager; the folder is {folder}", severity="warning", timeout=8)

    def open_last_inspiration(self) -> None:
        if self.project is None:
            return
        scene = self._insp_scene_rel()
        images = store.list_images(self.project, scene or None) or store.list_images(self.project)
        if not images:
            self.notify("No inspiration images yet", timeout=3)
            return
        img = images[0]
        if not self.open_external(img.path):
            self.notify(f"Could not start a viewer; the file is {img.path}", severity="warning", timeout=8)
