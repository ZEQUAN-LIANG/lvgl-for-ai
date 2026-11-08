"""Compatibility alias for :mod:`lvgl_ai.png_codec`.

Deprecated import path: the PNG codec implementation lives in
:mod:`lvgl_ai.png_codec`; this module only re-exports it for callers that
still use ``lvgl_ai.region``.
"""

from __future__ import annotations

from .png_codec import *  # noqa: F401,F403
