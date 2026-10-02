"""Rename a character everywhere, for the terminal app (SPEC "Rename a character").

A mixin for ``LorewriteApp``. Palette: ``Entity · Rename everywhere…`` (the open
note, or the name under the cursor) and ``Entity · Undo last rename``. The
core (``core/rename.py``) previews without writing, snapshots every affected
scene, and applies only the ticked occurrences.
"""

from __future__ import annotations

from pathlib import Path

from ..core import entities as ent
from ..core import rename as renaming
from ..core import research as research_notes
from ..core.links import link_at, rowcol_to_offset
from .renamescreens import RenameForm, RenameFormScreen, RenamePreviewScreen


class RenameMixin:
    def _rename_target(self) -> ent.Entity | None:
        """The note being renamed: the open entity note, else the name at the cursor."""
        path = self.current_path
        if path is not None:
            for entity in self.entities:
                if entity.path is not None and entity.path.resolve() == path.resolve():
                    return entity
        if path is not None and self._editor is not None:
            text = self.editor.text
            link = link_at(text, rowcol_to_offset(text, *self.editor.cursor_location),
                           self.editor.mention_names)
            if link is not None:
                return ent.resolve(link.target, self.entities)
        return None

    def _rename_titles(self, plan: renaming.RenamePlan) -> dict[str, str]:
        titles = {}
        for rel in plan.files():
            path = self.project.root / rel
            kind = plan.kinds.get(rel, "scene")
            if kind == "scene":
                titles[rel] = self.project.scene_title(path)
            elif kind == "entity":
                titles[rel] = ent.load_entity(path).name
            else:
                titles[rel] = research_notes.title_of(path)
        return titles

    def rename_entity_prompt(self) -> None:
        entity = self._rename_target()
        if entity is None:
            self.notify("Open the note, or put the cursor on the name, first.",
                        severity="warning")
            return
        self.save_current()

        def _form(form: RenameForm | None) -> None:
            if form is None:
                return
            self.save_current()  # the preview reads the files
            fresh = ent.resolve(entity.name, self.entities) or entity
            try:
                plan = renaming.plan_rename(
                    self.project, fresh, form.new_name, keep_old_as_alias=form.keep_old,
                    rename_aliases={a: b for a, b in form.aliases.items() if b and b != a},
                    scope=form.scope)
            except (ValueError, LookupError) as exc:
                self.notify(str(exc), severity="warning")
                return
            self.push_screen(RenamePreviewScreen(plan, self._rename_titles(plan)),
                             lambda ids: self._rename_apply(plan, ids))

        self.push_screen(RenameFormScreen(entity.name, list(entity.aliases)), _form)

    def _rename_apply(self, plan: renaming.RenamePlan, ids: list[str] | None) -> None:
        if ids is None:
            return
        self.save_current()
        try:
            result = renaming.apply_rename(self.project, plan, ids, index=self.idx)
        except (ValueError, OSError, LookupError) as exc:
            self.notify(f"Nothing was renamed: {exc}", severity="error")
            return
        self._rename_refresh(result.changed, result.remap)
        self.notify(
            f"Renamed to '{plan.new_name}': {result.replacements} change"
            f"{'' if result.replacements == 1 else 's'}, {result.scenes} scene"
            f"{'' if result.scenes == 1 else 's'} (snapshots 'before-rename'). "
            "Palette: Entity · Undo last rename.", timeout=8)

    def rename_undo_action(self) -> None:
        last = renaming.latest_undo(self.project)
        if last is None:
            self.notify("No rename to undo.", severity="warning")
            return
        undo_id, old, new = last
        self.save_current()
        try:
            result = renaming.undo_rename(self.project, undo_id, index=self.idx)
        except (ValueError, OSError, LookupError) as exc:
            self.notify(f"Could not undo: {exc}", severity="error")
            return
        remap = {}
        if self.current_path is not None and not self.current_path.exists():
            remap = {self.current_path.relative_to(self.project.root).as_posix(): result.entity_file}
        self._rename_refresh(result.restored, remap)
        skipped = f" Left alone (edited since): {', '.join(result.skipped)}." if result.skipped else ""
        self.notify(f"Undid the rename of '{old}' to '{new}'.{skipped}", timeout=8)

    def _rename_refresh(self, changed: list[str], remap: dict[str, str]) -> None:
        """Files were rewritten behind the editor: re-read the open one (following
        the note's new file name) without saving the stale buffer over it."""
        root = self.project.root
        current = self.current_path
        self.reload_entities()
        for rel in changed:
            path = root / rel
            if self._is_scene(path) and path.is_file() and path != current:
                self._stats_seen(path.read_text(encoding="utf-8"), path)
        if current is not None:
            rel = current.relative_to(root).as_posix()
            if rel in remap or rel in changed:
                target = root / remap.get(rel, rel)
                self.current_path = None  # open_file must not save the stale buffer
                self._dirty = False
                if target.is_file():
                    self.open_file(target)
        self.refresh_sidebar()
        self.editor.refresh_links()
