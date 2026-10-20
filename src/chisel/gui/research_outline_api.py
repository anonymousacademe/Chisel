"""Research mode: the outline assistant (docs/dev/plan-research-waves-d-f.md, wave D).

Mixin of Api (the lead wires it into ResearchMixin). The AI only PROPOSES (``outline_suggest`` never changes a
file); ``outline_apply`` applies exactly the items the client sends (the ticked ones), each revalidated
against the outline as it is at that moment, with a snapshot of every section it renames or moves, and only
through the existing structure functions. Nothing is ever deleted or merged. Research projects only; the
project lock is released before the network call.
"""

from __future__ import annotations

from ..ai import outline as outline_ai
from ..ai.budget import Budget
from ..ai.client import resolve_model
from ..ai.usage import LEDGER
from ..core import scenemeta, snapshots
from ..core.paper import outlines, scope
from ..core.project import write_atomic
from . import aijobs
from ._bridge import bridge
from ._research_common import require_research


class ResearchOutlineMixin:
    # Mixin of Api: shared state (_require, _lock, index, _index_file, _stream) is on Api.

    def _outline_project(self):
        project = self._require()
        require_research(project)
        return project

    @bridge
    def outline_get_scope(self) -> dict:
        with self._lock:
            return {"text": scope.get_scope(self._outline_project())}

    @bridge
    def outline_set_scope(self, text: str) -> dict:
        with self._lock:
            scope.set_scope(self._outline_project(), text)
        return {}

    @bridge
    def outline_current(self) -> dict:
        with self._lock:
            return outlines.current_outline(self._outline_project())

    @bridge
    def outline_standard(self) -> dict:
        """The standard structure diffed against the outline. No AI, works offline."""
        with self._lock:
            return outlines.standard_diff(self._outline_project())

    @bridge
    def outline_suggest(self, instruction: str = "", guidelines: list | None = None) -> dict:
        """AI proposal: items to review, what was dropped and why, what was sent. Changes no file. Runs inside
        ai_start (kind "outline") or as a plain call."""
        from . import api as api_module        # looked up at CALL time so tests can patch it

        names = [str(n) for n in (guidelines or [])]
        with self._lock:
            project = self._outline_project()
            model = resolve_model("strong", project.meta)
            text_scope = scope.get_scope(project)
            outline = outlines.current_outline(project)
            sources = outline_ai.read_guideline_sources(project, names)      # bytes only under the lock
        context, sent = outline_ai.plan_outline(          # guideline extraction happens outside the lock
            project, text_scope, str(instruction or ""), names, Budget.for_model(model), outline, sources)
        calls = LEDGER.count()
        fn = getattr(api_module, "suggest_outline", None) or outline_ai.suggest_outline
        raw = self._stream(fn, context, model)
        aijobs.checkpoint()
        items, dropped = outline_ai.parse_outline_items(raw, outline)
        last = LEDGER.last()
        cost = last.cost if LEDGER.count() > calls and last is not None else None
        return {"items": items, "dropped": dropped, "sent": sent.to_dict(), "cost": cost, "model": model}

    # -- apply -----------------------------------------------------------------------------------------

    @staticmethod
    def _part_by_title(project, title: str):
        want = title.casefold()
        return next((p for p in project.list_parts() if project.part_title(p).casefold() == want), None)

    def _compose_remap(self, project, cum: dict, step: dict) -> None:
        """Fold one structure step's {old Path: new Path} into the cumulative {original id: current id}."""
        ids = {outlines.section_id(project, o): outlines.section_id(project, n) for o, n in step.items()}
        for k in list(cum):
            if cum[k] in ids:
                cum[k] = ids[cum[k]]
        known = set(cum) | set(cum.values())
        for old, new in ids.items():
            if old not in known:
                cum[old] = new

    @bridge
    def outline_apply(self, items: list) -> dict:
        """Apply the ticked *items* (the full item objects). Returns {changed, remap, skipped, created}."""
        changed: list[str] = []
        created: list[str] = []
        created_parts: list[str] = []
        skipped: list[dict] = []
        cum: dict[str, str] = {}
        last_add: dict[tuple[str, str], str] = {}
        with self._lock:
            project = self._outline_project()
            for raw in items if isinstance(items, list) else []:
                iid = str(raw.get("id", "")) if isinstance(raw, dict) else ""
                try:
                    self._apply_one(project, raw, cum, last_add, changed, created, created_parts)
                except _Skip as why:
                    skipped.append({"id": iid, "reason": str(why)})
                except (OSError, ValueError) as exc:        # includes NotUtf8Error: the file stays as it was
                    skipped.append({"id": iid, "reason": str(exc) or "It could not be applied."})
            if changed or created or created_parts or cum:
                self.index.rebuild(project)
        remap = {k: v for k, v in cum.items() if k != v}
        out_changed = []
        for c in changed:
            c = cum.get(c, c)
            if c not in out_changed:
                out_changed.append(c)
        out_created = [cum.get(c, c) for c in created]
        return {"changed": out_changed, "remap": remap, "skipped": skipped, "created": out_created,
                "createdParts": created_parts}

    def _apply_one(self, project, raw, cum, last_add, changed, created, created_parts) -> None:
        if not isinstance(raw, dict):
            raise _Skip("It is not an item.")
        item = dict(raw)
        for key in ("section", "after"):                     # earlier items may have renumbered the files
            ref = str(item.get(key) or "")
            item[key] = cum.get(ref, ref)
        outline = outlines.current_outline(project)
        action = str(item.get("action") or "").strip().casefold()
        if action == "keep":
            raise _Skip("Kept as it is.")
        if action not in ("add", "rename", "move"):
            raise _Skip("This is advice only; nothing was changed." if action in ("advice", *outline_ai.DELETE_LIKE)
                        else "Unknown action.")
        clean, reason = outline_ai.clean_item(item, outline, set())
        if clean is None:
            raise _Skip(reason)
        if clean["action"] != action:
            raise _Skip("This is advice only; nothing was changed.")
        if action == "rename":
            self._apply_rename(project, clean, changed)
        elif action == "move":
            self._apply_move(project, clean, cum, changed, created_parts)
        else:
            self._apply_add(project, clean, cum, last_add, created, created_parts)

    def _dest(self, project, title: str, created_parts: list):
        """The part folder called *title* (created when it does not exist yet), None for the top level."""
        if not title:
            return None
        part = self._part_by_title(project, title)
        if part is None:
            part = project.new_part(title)
            created_parts.append(title)
        return part

    @staticmethod
    def _index_for(project, part, after_path, moving=None) -> int:
        others = [p for p in project.part_scenes(part) if p != moving]
        if not after_path:
            return 0
        try:
            return others.index(after_path) + 1
        except ValueError:
            raise _Skip("The section it should follow is not in that part any more.") from None

    def _apply_rename(self, project, item, changed) -> None:
        path = project.root / item["section"]
        if not project.is_scene_path(path) or not path.is_file():
            raise _Skip("That section no longer exists.")
        snapshots.create(project, path, "before-outline-rename")      # first: nothing is touched without one
        project.rename_scene(path, item["newTitle"])
        changed.append(item["section"])

    def _apply_move(self, project, item, cum, changed, created_parts) -> None:
        path = project.root / item["section"]
        if not project.is_scene_path(path) or not path.is_file() or path not in project.list_scenes():
            raise _Skip("That section no longer exists.")
        after_path = project.root / item["after"] if item["after"] else None
        part = self._dest(project, item["part"], created_parts)
        index = self._index_for(project, part, after_path, moving=path)
        snapshots.create(project, path, "before-outline-move")
        new = project.place_scene(path, part, index)
        self._compose_remap(project, cum, dict(project.last_renames))
        changed.append(outlines.section_id(project, new))

    def _apply_add(self, project, item, cum, last_add, created, created_parts) -> None:
        key = (item["part"].casefold(), item["after"])
        prior = last_add.get(key, "")                        # several adds after the same section keep their order
        after = cum.get(prior, prior) or item["after"]
        after_path = project.root / after if after else None
        part = self._dest(project, item["part"], created_parts)
        index = self._index_for(project, part, after_path)
        path = project.next_scene_path(item["title"], part)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = scenemeta.set_details(f"# {item['title']}\n\n", purpose=item.get("purpose", ""))
        write_atomic(path, text)
        new = project.place_scene(path, part, index)
        self._compose_remap(project, cum, {o: n for o, n in project.last_renames.items() if o != path})
        last_add[key] = outlines.section_id(project, new)
        created.append(outlines.section_id(project, new))


class _Skip(Exception):
    """An item that is not applied, with the reason shown to the author."""
