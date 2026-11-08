"""LVGL key names accepted by ``Runtime.key`` and ``lvgl-ai-input-v1``.

The table mirrors ``lv_key_t`` in LVGL 9.6's public header
``include/lvgl/core/lv_group.h``. Names are case-insensitive and may carry the
``LV_KEY_`` prefix; the canonical name (without prefix, uppercase) is what the
timeline records. LVGL 9.6 defines no ``LV_KEY_INSERT``, so ``INSERT`` is an
unknown key.

Version-specific tables for 8.x / 9.5 / 9.4 / 9.1 belong to tickets 08/09.
"""

from __future__ import annotations

from typing import Any

from .errors import ScenarioError

LV_KEY_PREFIX = "LV_KEY_"

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
    canonical = upper[len(LV_KEY_PREFIX):] if upper.startswith(LV_KEY_PREFIX) else upper
    code = LV_KEYS.get(canonical)
    if code is None:
        expected = ", ".join(KEY_NAMES)
        raise ScenarioError(
            f"{prefix}unknown key {name!r}; expected one of {expected}",
            step=step,
        )
    return canonical, code
