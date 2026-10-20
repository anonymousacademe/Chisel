"""Research mode: the author's own requirements and the AI suggestions from guidelines (wave E).

Mixin of Api (the lead wires it into ResearchMixin). ``requirements_suggest`` only PROPOSES: it never changes a
file; the author edits and ticks rows in the client and ``requirements_save`` writes the whole list to
requirements.toml (every row validated, nothing written when one is refused). Research projects only; the
project lock is released before the network call.
"""

from __future__ import annotations

from ..ai import requirements as req_ai
from ..ai.budget import Budget
from ..ai.client import resolve_model
from ..ai.usage import LEDGER
from ..core.paper import custom_requirements as cr
from . import aijobs
from ._bridge import bridge
from ._research_common import require_research


class ResearchRequirementsMixin:
    # Mixin of Api: shared state (_require, _lock, _stream) is on Api.

    def _requirements_project(self):
        project = self._require()
        require_research(project)
        return project

    @bridge
    def requirements_custom(self) -> dict:
        with self._lock:
            rows, warning = cr.load_report(self._requirements_project())
        out = {"rows": rows}
        if warning:
            out["warning"] = warning
        return out

    @bridge
    def requirements_save(self, rows: list) -> dict:
        with self._lock:
            return {"rows": cr.save_custom(self._requirements_project(), rows)}

    @bridge
    def requirements_remove(self, id: str) -> dict:
        with self._lock:
            return {"rows": cr.remove(self._requirements_project(), id)}

    @bridge
    def requirements_suggest(self, instruction: str = "", guidelines: list | None = None) -> dict:
        """AI proposal: rows to review (each with ``verified``), what was dropped and why, what was sent.
        Changes no file. Runs inside ai_start (kind "requirements") or as a plain call."""
        from . import api as api_module        # looked up at CALL time so tests can patch it

        names = [str(n) for n in (guidelines or [])]
        with self._lock:
            project = self._requirements_project()
            model = resolve_model("strong", project.meta)
            sources = req_ai.read_guideline_sources(project, names)      # bytes only under the lock
            taken = [r["id"] for r in cr.load_custom(project)]
        texts = req_ai.load_texts(project, sources)                      # extraction outside the lock
        context, sent = req_ai.plan_requirements(project, str(instruction or ""), names, model,
                                                 Budget.for_model(model), texts=texts)
        calls = LEDGER.count()
        fn = getattr(api_module, "suggest_requirements", None) or req_ai.suggest_requirements
        raw = self._stream(fn, context, model)
        aijobs.checkpoint()
        items, dropped = req_ai.parse_requirement_rows(raw, texts, taken)
        last = LEDGER.last()
        cost = last.cost if LEDGER.count() > calls and last is not None else None
        return {"items": items, "dropped": dropped, "sent": sent.to_dict(), "cost": cost, "model": model}
