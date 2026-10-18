"""Shared by the research-mode bridge mixins (gui/research_sources_api.py, gui/research_objects_api.py)."""

from __future__ import annotations


def require_research(project) -> None:
    """Research bridge methods only work in a research project (a plain-words error otherwise)."""
    if getattr(project, "mode", "story") != "research":
        raise ValueError("This is not a research project. Research tools are only available in projects "
                         "created as Research.")
