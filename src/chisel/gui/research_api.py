"""Research-mode bridge methods (docs/dev/research-mode-contracts.md, "GUI bridge").

Stub registered by P0 so later packages touch only this module: P7 adds the methods. Every method is
``@bridge``, takes ``self._lock`` for project access and releases it before any network call or script run.
"""

from __future__ import annotations

from .research_guidelines_api import ResearchGuidelinesMixin
from .research_objects_api import ResearchObjectsMixin
from .research_outline_api import ResearchOutlineMixin
from .research_project_api import ResearchProjectMixin
from .research_requirements_api import ResearchRequirementsMixin
from .research_sources_api import ResearchSourcesMixin


class ResearchMixin(ResearchSourcesMixin, ResearchObjectsMixin, ResearchProjectMixin, ResearchGuidelinesMixin,
                    ResearchOutlineMixin, ResearchRequirementsMixin):
    # Mixin of Api (api.py): every public method here is a bridge method; shared state is on Api.
    # Sources, Zotero, checks and export: research_sources_api.py. Objects, figures, tables and AI
    # proposals: research_objects_api.py. Paper kind, journal profile, requirements: research_project_api.py.
    # Guideline documents: research_guidelines_api.py. Outline assistant: research_outline_api.py.
    # Your own requirements and AI-suggested ones: research_requirements_api.py.
    pass
