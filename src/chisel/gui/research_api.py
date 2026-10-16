"""Research-mode bridge methods (docs/dev/research-mode-contracts.md, "GUI bridge").

Stub registered by P0 so later packages touch only this module: P7 adds the methods. Every method is
``@bridge``, takes ``self._lock`` for project access and releases it before any network call or script run.
"""

from __future__ import annotations


class ResearchMixin:
    # Mixin of Api (api.py): every public method here is a bridge method; shared state is on Api.
    pass
