from __future__ import annotations

import re
from typing import Any

from .errors import ScenarioError

LV_KEY_PREFIX = "LV_KEY_"
CHAR_PREFIX = "CHAR_"
ASCII_PRINTABLE_MIN = 32
ASCII_PRINTABLE_MAX = 126

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
    return f"{CHAR_PREFIX}{ord(char)}"


def resolve_key(name: Any, *, step: int | None = None) -> tuple[str, int]:
    prefix = "" if step is None else f"step {step}: "
    if not isinstance(name, str):
        raise ScenarioError(
            f"{prefix}key must be a string; got {name!r}", step=step
        )

    upper = name.upper()
    if upper.startswith(CHAR_PREFIX):
        return _resolve_char_key(name, upper, prefix, step)
    canonical = (
        upper[len(LV_KEY_PREFIX) :]
        if upper.startswith(LV_KEY_PREFIX)
        else upper
    )
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
