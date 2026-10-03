"""Environment overrides with deprecated aliases from the LoreWriter era.

``get_env("STATE_DIR")`` reads ``CHISEL_STATE_DIR`` and, only when that is unset or
empty, the deprecated ``LOREWRITE_STATE_DIR``. The new name always wins.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

PREFIX = "CHISEL_"
LEGACY_PREFIX = "LOREWRITE_"  # deprecated alias, still honoured for the user-settable folders


def get_env(name: str, default: str | None = None) -> str | None:
    """The value of CHISEL_<name>, else the deprecated LOREWRITE_<name>, else *default*."""
    value = os.environ.get(PREFIX + name)
    if value:
        return value
    legacy = os.environ.get(LEGACY_PREFIX + name)
    if legacy:
        log.warning("%s%s is deprecated; set %s%s instead", LEGACY_PREFIX, name, PREFIX, name)
        return legacy
    return default
