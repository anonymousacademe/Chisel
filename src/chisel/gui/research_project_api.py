"""Research mode: the project's kind, journal profile and requirements checklist.

Mixin of Api (api.py): every public method is a bridge method; shared state (``_lock``, ``_require``) is on Api.
Rules: research projects only (``require_research``), project access under ``self._lock``, and changing the
journal never rewrites any project file except ``project.toml`` ``[research]``. Profiles are read-only package
data (core/paper/journals/).
"""

from __future__ import annotations

from ..core.paper import journals, requirements
from ._bridge import bridge
from ._research_common import require_research


def _profile_row(p: journals.Profile) -> dict:
    return {"id": p.id, "name": p.name, "publisher": p.publisher, "kind": p.kind,
            "source": p.source, "readOn": p.read_on}


class ResearchProjectMixin:
    def _research_settings_reply(self, project) -> dict:
        profile = project.research_profile()
        return {"kind": project.research_kind,
                "journal": profile.id if profile else "",
                "journalName": profile.name if profile else "",
                "citationStyle": project.citation_style,
                "source": profile.source if profile else "",
                "readOn": profile.read_on if profile else ""}

    @bridge
    def research_profiles(self) -> dict:
        return {"profiles": [_profile_row(p) for p in journals.list_profiles()]}

    @bridge
    def research_get_settings(self) -> dict:
        with self._lock:
            project = self._require()
            require_research(project)
            return self._research_settings_reply(project)

    @bridge
    def research_set_settings(self, kind: str, journal: str = "") -> dict:
        kind = str(kind or "").strip()
        journal = str(journal or "").strip()
        if kind not in journals.KINDS:
            raise ValueError(f"The kind must be one of: {', '.join(journals.KINDS)}.")
        if journal:
            profile = journals.load_profile(journal)       # ValueError: unknown profile
            if profile.kind != kind:
                raise ValueError(f"{profile.name} is a profile for a {profile.kind}, not a {kind}.")
        with self._lock:
            project = self._require()
            require_research(project)
            project.update_research_settings(kind=kind, journal=journal)
            return self._research_settings_reply(project)

    @bridge
    def research_requirements(self) -> dict:
        with self._lock:
            project = self._require()
            require_research(project)
            profile = project.research_profile()
            rows = requirements.evaluate(project)
        summary = {"ok": 0, "warn": 0, "info": 0, "advice": 0}
        groups: list[dict] = []
        index: dict[str, dict] = {}
        for r in rows:
            if r["status"] in summary:
                summary[r["status"]] += 1
            group = index.get(r["group"])
            if group is None:
                group = index[r["group"]] = {"title": r["group"], "items": []}
                groups.append(group)
            group["items"].append({"id": r["id"], "title": r["title"], "status": r["status"],
                                   "message": r["message"]})
        return {"journal": profile.id if profile else "", "name": profile.name if profile else "",
                "source": profile.source if profile else "", "readOn": profile.read_on if profile else "",
                "summary": summary, "groups": groups}
