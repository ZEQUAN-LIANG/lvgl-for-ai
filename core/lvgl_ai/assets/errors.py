"""Errors raised by the LVGL asset converters."""

from __future__ import annotations


class AssetError(RuntimeError):
    """A user-facing asset conversion error.

    The CLI catches this type and prints ``[assets] error: ...`` without a
    traceback.  Raised for bad inputs, unsupported formats, size-limit
    violations and output conflicts.
    """
