"""Compatibility alias for :mod:`lvgl_ai.control.build_plan`.

Deprecated import path: the implementation lives in :mod:`lvgl_ai.control`;
this module only re-exports it for callers that still use ``lvgl_ai.core``.
"""

from __future__ import annotations

from ..control.build_plan import *  # noqa: F401,F403
