"""Key and character tokens accepted by ``Runtime.key`` and ``lvgl-ai-input-v1``.

The ``LV_KEY_*`` table mirrors ``lv_key_t`` in LVGL 9.6's public header
``include/lvgl/core/lv_group.h``. Names are case-insensitive and may carry the
``LV_KEY_`` prefix; the canonical name (without prefix, uppercase) is what the
timeline records. LVGL 9.6 defines no ``LV_KEY_INSERT``, so ``INSERT`` is an
unknown key.

Text input uses one printable ASCII character per keypress. The stable token
is ``CHAR_<code>`` (for example ``CHAR_65`` for ``A``); :func:`char_key` builds
it and :func:`resolve_key` accepts it case-insensitively. Unicode and IME input
are out of scope.

Version-specific tables for 8.x / 9.5 / 9.4 / 9.1 belong to tickets 08/09.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import ScenarioError

LV_KEY_PREFIX = "LV_KEY_"
CHAR_PREFIX = "CHAR_"
ASCII_PRINTABLE_MIN = 32
ASCII_PRINTABLE_MAX = 126

# Sorted by LVGL's enum, not alphabetically, to make header comparison easy.
LV_KEYS: dict[str, int] = {
    "UP": 17,
    "DOWN": 18,
    "RIGHT": 19,
    "LEFT": 20,
    "ESC": 27,
    "DEL": 127,
    "BACKSPACE": 8,
    "ENTER": 10,
    "NEXT": 9,
    "PREV": 11,
    "HOME": 2,
    "END": 3,
}

KEY_NAMES = tuple(LV_KEYS)
_CHAR_RE = re.compile(r"CHAR_([0-9]+)\Z")


def char_key(char: str) -> str:
    """Return the stable ``CHAR_<code>`` token for one printable ASCII char."""
    return f"{CHAR_PREFIX}{ord(char)}"


def resolve_key(name: Any, *, step: int | None = None) -> tuple[str, int]:
    """Return ``(canonical_name, lv_key_code)`` for ``name``.

    Raises :class:`ScenarioError` for a non-string or unknown key. ``step`` is
    included in the message and attached to the error when the key came from
    a ``lvgl-ai-input-v1`` event list.
    """
    prefix = "" if step is None else f"step {step}: "
    if not isinstance(name, str):
        raise ScenarioError(f"{prefix}key must be a string; got {name!r}", step=step)

    upper = name.upper()
    if upper.startswith(CHAR_PREFIX):
        return _resolve_char_key(name, upper, prefix, step)
    canonical = upper[len(LV_KEY_PREFIX):] if upper.startswith(LV_KEY_PREFIX) else upper
    code = LV_KEYS.get(canonical)
    if code is None:
        expected = ", ".join(KEY_NAMES)
        raise ScenarioError(
            f"{prefix}unknown key {name!r}; expected one of {expected}",
            step=step,
        )
    return canonical, code


def _resolve_char_key(
    name: str, upper: str, prefix: str, step: int | None
) -> tuple[str, int]:
    match = _CHAR_RE.fullmatch(upper)
    if match is None:
        raise ScenarioError(
            f"{prefix}key must be CHAR_<code> with a printable ASCII code "
            f"{ASCII_PRINTABLE_MIN}..{ASCII_PRINTABLE_MAX}; got {name!r}",
            step=step,
        )
    code = int(match.group(1))
    if not ASCII_PRINTABLE_MIN <= code <= ASCII_PRINTABLE_MAX:
        raise ScenarioError(
            f"{prefix}key CHAR_<code> must be within printable ASCII "
            f"{ASCII_PRINTABLE_MIN}..{ASCII_PRINTABLE_MAX}; got {code}",
            step=step,
        )
    return f"{CHAR_PREFIX}{code}", code
