"""Compatibility alias for :mod:`lvgl_ai.control.errors`.

Deprecated import path: the implementation lives in :mod:`lvgl_ai.control`;
this module only re-exports it for callers that still use ``lvgl_ai.core``.
"""

from __future__ import annotations

from ..control.errors import *  # noqa: F401,F403
