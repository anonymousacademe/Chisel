"""Characters, places and objects, story time, and rename everywhere (core/rename.py)."""

from __future__ import annotations

import os
from . import workspace as ws
from ..core import drafts, entities as ent, fsutil, rename as renaming, research as research_notes, timeline
from ..core.project import Project
from ._bridge import bridge


class EntitiesMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @bridge
    def list_entities(self) -> dict:
        with self._lock:
            return {"entities": ws.entity_summaries(self._require(), self.entities)}

    @bridge
    def get_entity(self, name: str, scene_id: str | None = None) -> dict:
        """The note behind a link target (name or alias), or found=false. With
        *scene_id* (the open scene) the payload's ``ageNow`` is the age there."""
        with self._lock:
            project = self._require()
            entity = ent.resolve(name, self.entities)
            if entity is None or entity.path is None:
                return {"found": False, "name": name}
            return {"found": True,
                    **ws.entity_payload(project, entity, self.index, scene_id)}

    def _entities_changed(self) -> None:
        """Names/aliases changed: earlier scenes may now mention them."""
        self.reload_entities()
        self.index.rebuild(self._require())

    @bridge
    def create_entity(self, name: str, etype: str) -> dict:
        name = " ".join(name.split())
        if not name or "/" in name or "\\" in name:
            raise ValueError("a note needs a simple name")
        if etype not in ent.VALID_TYPES:
            raise ValueError(f"type must be one of {', '.join(ent.VALID_TYPES)}")
        with self._lock:
            project = self._require()
            existing = ent.resolve(name, self.entities)
            if existing is not None and existing.path is not None:
                return {"id": ws.rel_id(project, existing.path),
                        "name": existing.name, "existed": True}
            entity, path = project.create_entity(name, etype)
            self._entities_changed()
            return {"id": ws.rel_id(project, path), "name": entity.name,
                    "existed": False}

    @bridge
    def add_alias(self, name: str, alias: str) -> dict:
        alias = " ".join(alias.split())
        if not alias:
            raise ValueError("an alias can't be empty")
        with self._lock:
            entity = ent.resolve(name, self.entities)
            if entity is None:
                raise LookupError(f"no note named {name!r}")
            ent.add_alias(entity, alias, self.entities)
            self._entities_changed()
            return {}

    @bridge
    def set_entity_born(self, name: str, born: str) -> dict:
        """Set (or, blank, clear) a note's ``born:`` story time. A value that is
        not a story time is kept as text and reported (``invalid``)."""
        with self._lock:
            project = self._require()
            entity = ent.resolve(name, self.entities)
            if entity is None or entity.path is None:
                raise LookupError(f"no note named {name!r}")
            text = " ".join(str(born or "").split())
            if text:
                entity.extra["born"] = timeline.stored_value(text)
            else:
                entity.extra.pop("born", None)
            ent.save_entity(entity, entity.path)
            self.reload_entities()
            era = project.timeline_settings()["era"]
            return {"born": text, "invalid": bool(text) and timeline.parse_story_time(text, era) is None}

    @bridge
    def check_story_time(self, text: str) -> dict:
        """Is *text* a story time (year, optional month and day, project era)?
        Blank is valid (it means "none")."""
        with self._lock:
            era = self._require().timeline_settings()["era"]
        text = " ".join(str(text or "").split())
        when = timeline.parse_story_time(text, era) if text else None
        return {"valid": not text or when is not None,
                "normalized": when.format(era) if when else ""}

    def _rename_title(self, project: Project, rel: str, kind: str) -> str:
        path = project.root / rel
        try:
            text = fsutil.read_text_lenient(path)
        except OSError:
            return rel
        if kind == "scene":
            return ws.split_title(text)[0] or path.stem
        if kind == "entity":
            return ent.Entity.from_markdown(text, path).name
        return research_notes.title_of(path, text)

    def _rename_seen(self, project: Project, rels: list[str]) -> None:
        """Scenes rewritten behind the editor's back: new baseline, not writing."""
        if self.stats is None:
            return
        for rel in rels:
            path = project.root / rel
            if project.is_scene_path(path) and path.is_file():
                text, originals = ws.read_text(project, path)
                self.stats.seen(self._scene_key(path), drafts.count_words(text, originals))

    @bridge
    def rename_preview(self, name: str, new_name: str, keep_old_as_alias: bool = True,
                       rename_aliases: dict | None = None,
                       scope: list | None = None) -> dict:
        """What renaming a note would change, grouped by file. Read-only: nothing
        is written until rename_apply. The client flushes the open document first."""
        with self._lock:
            project = self._require()
            entity = ent.resolve(name, self.entities)
            if entity is None:
                raise LookupError(f"no note named {name!r}")
            plan = renaming.plan_rename(
                project, entity, new_name, keep_old_as_alias=bool(keep_old_as_alias),
                rename_aliases={str(k): str(v) for k, v in (rename_aliases or {}).items() if str(v).strip()},
                scope=tuple(scope) if scope is not None else renaming.DEFAULT_SCOPE)
            token = os.urandom(6).hex()
            self._rename_plan = (token, plan)
            files = []
            for rel in plan.files():
                occ = [o for o in plan.occurrences if o.file == rel]
                kind = "comment" if all(o.comment for o in occ) else plan.kinds.get(rel, "scene")
                title = self._rename_title(project, rel, plan.kinds.get(rel, "scene"))
                files.append({
                    "file": rel, "kind": kind, "title": title,
                    "occurrences": [{
                        "id": o.id, "kind": o.kind, "line": o.line, "pre": o.pre, "before": o.before,
                        "after": o.after, "post": o.post, "inDraft": o.in_draft,
                        "defaultOn": o.default_on} for o in occ]})
            return {"plan": token, "name": plan.entity, "newName": plan.new_name,
                    "aliases": plan.new_aliases, "files": files,
                    "newId": plan.new_entity_file}

    @bridge
    def rename_apply(self, plan: str, accepted: list) -> dict:
        """Apply the ticked occurrences (snapshots first) and rename the note.
        ``changed`` lists the files rewritten, ``remap`` the note's new id."""
        with self._lock:
            project = self._require()
            if self._rename_plan is None or self._rename_plan[0] != plan:
                raise ValueError("the preview is out of date; preview again")
            result = renaming.apply_rename(project, self._rename_plan[1],
                                           [str(i) for i in accepted], index=self.index)
            name = self._rename_plan[1].new_name
            self._rename_plan = None
            self.reload_entities()
            self._rename_seen(project, result.changed)
            return {"undoId": result.undo_id, "replacements": result.replacements,
                    "scenes": result.scenes, "changed": result.changed,
                    "remap": result.remap, "id": result.entity_file, "name": name}

    @bridge
    def rename_undo(self, undo_id: str) -> dict:
        """Undo a rename: scenes from their before-rename snapshots, the note and
        other files from the journal. Anything edited since is left and listed."""
        with self._lock:
            project = self._require()
            result = renaming.undo_rename(project, str(undo_id), index=self.index)
            self.reload_entities()
            self._rename_seen(project, result.restored)
            return {"restored": result.restored, "skipped": result.skipped,
                    "id": result.entity_file}
