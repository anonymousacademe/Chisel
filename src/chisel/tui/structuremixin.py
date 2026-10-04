"""Manuscript structure actions for the terminal app: scenes, parts, Parked scenes and the Trash.

A mixin for ChiselApp (same pattern as aimixin); the app owns the state it uses.
"""

from __future__ import annotations

from pathlib import Path
from ..core import fsutil, inspiration
from ..core import research as research_notes
from ..core.project import retitle_text
from .structurescreens import ChoiceScreen, TrashScreen
from .dialogs import ConfirmScreen, NamePrompt


class StructureMixin:
    def action_new_scene(self) -> None:
        self.create_scene_prompt()

    def create_scene_prompt(self) -> None:
        def _create(title: str | None) -> None:
            if not title:
                return
            part = self.project.default_part_for_new(self.current_path)
            path = self.project.next_scene_path(title, part)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {title}\n\n", encoding="utf-8", newline="\n")
            self.refresh_sidebar()
            self.open_file(path)

        self.push_screen(NamePrompt(f"New {self.project.unit} title:"), _create)

    # -- scene organization -----------------------------------------------------

    def _current_scene_path(self) -> Path | None:
        """The open file, if it's a manuscript scene (not an entity note)."""
        if self.project is None or self.current_path is None:
            return None
        if self.project.is_scene_path(self.current_path):
            return self.current_path
        return None

    def rename_scene_prompt(self) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        current = self.project.scene_title(path)

        def _rename(title: str | None) -> None:
            if not title or title == current:
                return
            if not fsutil.is_valid_utf8(path):
                self._warn_not_utf8(fsutil.NotUtf8Error(path))
                return
            # retitle the editor buffer, then save — a disk-side rename would
            # be clobbered by the next autosave of the stale buffer
            self.editor.load_text(retitle_text(self.editor.text, title))
            self.save_current()
            self.refresh_sidebar()
            self.notify(f"Renamed to '{title}'", timeout=1)

        self.push_screen(NamePrompt(f"Rename '{current}' to:"), _rename)

    def delete_scene_confirm(self) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        title = self.project.scene_title(path)
        unit = self.project.unit

        def _delete(ok: bool) -> None:
            if not ok:
                return
            rel = path.relative_to(self.project.root).as_posix()
            self.project.delete_scene(path)  # to the Trash, with its draft sidecar
            self.idx.remove_file(rel)
            # detach BEFORE open_file, whose save step would otherwise
            # resurrect the deleted file from the editor buffer
            self.current_path = None
            self.editor.load_text("")
            self.refresh_sidebar()
            scenes = self.project.list_scenes()
            if scenes:
                self.open_file(scenes[0])
            else:
                self.update_status()
            self.notify(f"Moved '{title}' to the Trash", timeout=2)

        self.push_screen(
            ConfirmScreen(
                f"Move {unit} '{title}' to the Trash?\n"
                "You can restore it from Action · Open Trash.",
                confirm_label="Move to Trash"),
            _delete,
        )

    def _move_scene(self, delta: int) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self.save_current()
        new_path = self.project.move_scene(path, delta)
        if new_path is None:
            self.notify("Already at the edge of its part", severity="warning")
            return
        self.current_path = new_path  # content unchanged; only the name moved
        self.idx.rebuild(self.project)
        self.refresh_sidebar()
        self.update_status()
        self.notify(f"Moved to {new_path.name}", timeout=1)

    def move_scene_up(self) -> None:
        self._move_scene(-1)

    def move_scene_down(self) -> None:
        self._move_scene(1)

    # -- parts, unplaced scenes, trash ------------------------------------------

    def _part_options(self, include_top: bool = False) -> list[tuple[str, object]]:
        options: list[tuple[str, object]] = [
            (self.project.part_title(p), p) for p in self.project.list_parts()]
        if include_top:
            options.append(("(no part - top level)", "top"))
        return options

    def _with_part(self, prompt: str, then) -> None:
        """Ask which part, defaulting to the open scene's part; run then(part)."""
        options = self._part_options()
        if not options:
            self.notify("There are no parts yet - Action · New part",
                        severity="warning")
            return
        path = self._current_scene_path()
        current = self.project.part_of(path) if path else None
        self.push_screen(ChoiceScreen(prompt, options, initial=current),
                         lambda chosen: chosen is not None and then(chosen))

    def _structure_changed(self, reopen: Path | None = None) -> None:
        """After parts/scenes moved on disk: refresh index and sidebar and
        keep the open scene open at its (possibly new) path."""
        if reopen is not None:
            self.current_path = reopen
        self.idx.rebuild(self.project)
        self.refresh_sidebar()
        self.update_status()

    def new_part_prompt(self) -> None:
        def _create(title: str | None) -> None:
            if not title:
                return
            try:
                part = self.project.new_part(title)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self.refresh_sidebar()
            self.notify(f"Created part '{self.project.part_title(part)}'", timeout=2)

        self.push_screen(NamePrompt("New part title:"), _create)

    def rename_part_prompt(self) -> None:
        def _go(part: Path) -> None:
            def _rename(title: str | None) -> None:
                if not title:
                    return
                self.project.rename_part(part, title)
                self.refresh_sidebar()

            self.push_screen(
                NamePrompt(f"Rename part '{self.project.part_title(part)}' to:"), _rename)

        self._with_part("Rename which part?", _go)

    def _move_part(self, delta: int) -> None:
        def _go(part: Path) -> None:
            self.save_current()
            parts = self.project.list_parts()
            j = parts.index(part) + delta
            neighbor = parts[j] if 0 <= j < len(parts) else None
            new = self.project.move_part(part, delta)
            if new is None:
                self.notify("Already at the edge", severity="warning")
                return
            cur, reopen = self.current_path, None
            if cur is not None and cur.parent == part:
                reopen = new / cur.name
            elif cur is not None and neighbor is not None and cur.parent == neighbor:
                prefix = part.name.split("-", 1)[0]
                reopen = neighbor.with_name(
                    f"{prefix}-{neighbor.name.split('-', 1)[1]}") / cur.name
            self._structure_changed(reopen)
            self.notify(f"Moved part '{self.project.part_title(new)}'", timeout=1)

        self._with_part("Move which part?", _go)

    def move_part_up(self) -> None:
        self._move_part(-1)

    def move_part_down(self) -> None:
        self._move_part(1)

    def delete_part_confirm(self) -> None:
        def _go(part: Path) -> None:
            title = self.project.part_title(part)
            if self.project.part_scenes(part):
                self.notify(f"'{title}' still has scenes - move them out first",
                            severity="warning")
                return

            def _delete(ok: bool) -> None:
                if not ok:
                    return
                try:
                    self.project.delete_part(part)
                except ValueError as exc:
                    self.notify(str(exc), severity="warning")
                    return
                self.refresh_sidebar()
                self.notify(f"Deleted part '{title}'", timeout=2)

            self.push_screen(ConfirmScreen(f"Delete the empty part '{title}'?"), _delete)

        self._with_part("Delete which (empty) part?", _go)

    def _place_in(self, path: Path, prompt: str, done: str) -> None:
        """Ask for a part (or the top level) and move *path* to its end."""
        def _go(chosen) -> None:
            self.save_current()
            part = None if chosen == "top" else chosen
            new = self.project.move_scene_to_part(path, part)
            self._structure_changed(new if path == self.current_path else None)
            self.notify(done, timeout=2)

        self.push_screen(ChoiceScreen(prompt, self._part_options(include_top=True)),
                         lambda chosen: chosen is not None and _go(chosen))

    def move_scene_to_part_prompt(self) -> None:
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self._place_in(path, f"Move '{self.project.scene_title(path)}' to which part?",
                       "Moved (at the end of the part)")

    def unplace_scene_action(self) -> None:
        """Move the open scene out of the book into Unplaced Scenes."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if self.project.is_unplaced(path):
            self.notify("Already unplaced - use Action · Place scene in the book",
                        severity="warning")
            return
        self.save_current()
        new = self.project.unplace_scene(path)
        self._structure_changed(new)
        self.notify("Moved to Unplaced scenes (not counted in the book)", timeout=2)

    def place_scene_action(self) -> None:
        """Bring the open unplaced scene back into the book."""
        path = self._current_scene_path()
        if path is None or not self.project.is_unplaced(path):
            self.notify("Open an unplaced scene first", severity="warning")
            return
        self._place_in(path, "Place in which part?", "Placed in the book")

    def open_trash(self) -> None:
        items = self.project.list_trash()

        def _act(result) -> None:
            if result is None:
                return
            what, name = result
            if what == "restore":
                new = self.project.restore_scene(name)
                if new.parent == inspiration.inspiration_dir(self.project):   # reference images: no sidebar row
                    self.notify("Restored the inspiration image", timeout=3)
                elif research_notes.is_research_path(self.project, new):   # not indexed, no sidebar row
                    self.notify(f"Restored the notebook note to {new.relative_to(self.project.root)}", timeout=3)
                else:
                    self.idx.rebuild(self.project)
                    self.refresh_sidebar()
                    self.notify("Restored to "
                                f"{new.relative_to(self.project.manuscript_dir)}", timeout=2)
                self.open_trash()
            elif what == "delete":
                item = next((i for i in items if i.name == name), None)

                def _forever(ok: bool) -> None:
                    if ok:
                        self.project.delete_forever(name)
                    self.open_trash()

                self.push_screen(ConfirmScreen(
                    f"Delete '{item.title if item else name}' forever?\n"
                    "This cannot be undone.", confirm_label="Delete forever"), _forever)
            elif what == "empty":
                def _empty(ok: bool) -> None:
                    if ok:
                        n = self.project.empty_trash()
                        self.notify(f"Emptied the Trash ({n})", timeout=2)
                    self.open_trash()

                self.push_screen(ConfirmScreen(
                    f"Delete all {len(items)} item(s) in the Trash forever?\n"
                    "This cannot be undone.", confirm_label="Empty Trash"), _empty)

        self.push_screen(TrashScreen(items), _act)

    # -- snapshots (Wave 2.1) -----------------------------------------------------
