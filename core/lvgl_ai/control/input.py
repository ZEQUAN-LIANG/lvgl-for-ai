"""Input vocabulary: devices, actions, tokens, integer ranges and key parsing.

This module is the single vocabulary source shared by ``play_scenario``
(``lvgl-ai-scenario-v1``), ``Runtime`` and the CLI:

- :data:`DEVICE_ACTIONS` lists the pointer/key/encoder actions;
- :data:`TOKEN_PATTERN` defines the ``[A-Za-z0-9_-]+`` token syntax and
  :func:`is_token` enforces it with the 64-character cap;
- :data:`INT16_MIN` / :data:`INT16_MAX` define the encoder range;
- :func:`resolve_key` (re-exported from :mod:`~lvgl_ai.control.keys`) defines the
  ``LV_KEY_*`` aliases and ``CHAR_<code>`` text tokens;
- :func:`text_problem` enforces the printable ASCII range of a ``text`` step.

The ``*_problem`` functions return the shared diagnostic text (or ``None``);
callers prepend their own context (``step N:``) and raise their own error type.
The ``require_*`` helpers raise ``ValueError`` with the Runtime wording.

``lvgl-ai-input-v1`` is the compact, replayable form of a scripted gesture::

    {"at_ms": 0, "device": "pointer", "action": "down", "x": 10, "y": 20}
    {"at_ms": 16, "device": "key", "action": "press", "key": "ENTER"}
    {"at_ms": 32, "device": "encoder", "action": "turn", "diff": -1}

``at_ms`` is the offset from the start of the ``rt.input(...)`` call. Events
are stably sorted by ``at_ms`` before dispatch, so equal timestamps keep the
caller's order. Key names are resolved against LVGL 9.6's ``LV_KEY_*`` set or
the printable ASCII ``CHAR_<code>`` text tokens; unknown names raise
:class:`ScenarioError` with the event index before any command is sent.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .errors import ScenarioError
# Re-exported: callers import the whole input vocabulary from this module.
from .keys import (
    ASCII_PRINTABLE_MAX,
    ASCII_PRINTABLE_MIN,
    char_key,
    resolve_key,
)
from .session_schema import (
    MAX_DISPLAY_DIMENSION,
    display_problem as _shared_display_problem,
    dimension_problem as _shared_dimension_problem,
)

POINTER_ACTIONS = ("down", "move", "up")
KEY_ACTIONS = ("press", "release")
ENCODER_ACTIONS = ("turn",)
DEVICE_ACTIONS = {
    "pointer": POINTER_ACTIONS,
    "key": KEY_ACTIONS,
    "encoder": ENCODER_ACTIONS,
}

TOKEN_PATTERN = "[A-Za-z0-9_-]+"
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
INT16_MIN = -32768
INT16_MAX = 32767
_COMMON_FIELDS = {"at_ms", "device", "action"}
_DEVICE_FIELDS = {
    "pointer": _COMMON_FIELDS | {"x", "y"},
    "key": _COMMON_FIELDS | {"key"},
    "encoder": _COMMON_FIELDS | {"diff"},
}


# ---- vocabulary checks ------------------------------------------------


def is_token(value: Any) -> bool:
    """True when ``value`` matches the shared token syntax and length cap."""
    return isinstance(value, str) and _TOKEN_RE.fullmatch(value) is not None


def token_problem(value: Any, name: str) -> str | None:
    """Return the shared token diagnostic, or ``None`` when it is valid."""
    if is_token(value):
        return None
    return f"{name} must match {TOKEN_PATTERN}"


def integer_problem(
    value: Any,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> str | None:
    """Return the shared integer diagnostic, or ``None`` when it is valid."""
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{name} must be an integer"
    if minimum is not None and value < minimum:
        return f"{name} must be >= {minimum}; got {value}"
    if maximum is not None and value > maximum:
        return f"{name} must be <= {maximum}; got {value}"
    return None


def dimension_problem(value: Any, name: str) -> str | None:
    """Return the display-dimension diagnostic, or ``None`` when valid."""
    return _shared_dimension_problem(
        value, name, maximum=MAX_DISPLAY_DIMENSION
    )


def display_problem(value: Any) -> str | None:
    """Return the scenario ``display`` object diagnostic, or ``None``."""
    return _shared_display_problem(
        value,
        label="display",
        maximum=MAX_DISPLAY_DIMENSION,
        reject_unknown=True,
    )


def text_problem(value: Any) -> str | None:
    """Return the ``text`` step diagnostic, or ``None`` when valid."""
    if not isinstance(value, str):
        return "value must be a string"
    if not value:
        return "value must not be empty"
    for char in value:
        if not ASCII_PRINTABLE_MIN <= ord(char) <= ASCII_PRINTABLE_MAX:
            return (
                "value must contain only printable ASCII characters "
                f"({ASCII_PRINTABLE_MIN}..{ASCII_PRINTABLE_MAX}); got {char!r}"
            )
    return None


def point_problem(value: Any, name: str) -> str | None:
    """Return the shared ``[x, y]`` diagnostic, or ``None`` when it is valid."""
    valid = (
        isinstance(value, list)
        and len(value) == 2
        and all(
            not isinstance(item, bool) and isinstance(item, int)
            for item in value
        )
        and all(item >= 0 for item in value)
    )
    if valid:
        return None
    return f"{name} must be [x, y] with non-negative integers"


def step_action_problem(
    device: str, action: Any, *, quoted: bool = False
) -> str | None:
    """Diagnostic for a scenario/input-event action in dotted naming."""
    actions = DEVICE_ACTIONS[device]
    if action in actions:
        return None
    if quoted:
        return f"{device}.action must be {actions[0]!r}; got {action!r}"
    return f"{device}.action must be one of {list(actions)}; got {action!r}"


def runtime_action_problem(device: str, action: Any) -> str | None:
    """Diagnostic for a ``Runtime`` method action in plain naming."""
    actions = DEVICE_ACTIONS[device]
    if action in actions:
        return None
    return f"{device} action must be {_or_list(actions)}; got {action!r}"


def _or_list(actions: tuple[str, ...]) -> str:
    if len(actions) == 1:
        return actions[0]
    return ", ".join(actions[:-1]) + " or " + actions[-1]


# ---- Runtime-facing helpers -------------------------------------------


def require_action(device: str, action: Any) -> str:
    """Validate a Runtime action, raising ``ValueError`` with today's text."""
    problem = runtime_action_problem(device, action)
    if problem is not None:
        raise ValueError(problem)
    return action


def require_token(value: Any, name: str) -> str:
    problem = token_problem(value, name)
    if problem is not None:
        raise ValueError(problem)
    return value


def require_integer(
    value: Any,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    problem = integer_problem(value, name, minimum=minimum, maximum=maximum)
    if problem is not None:
        raise ValueError(problem)
    return value


def require_non_negative_int(value: Any, name: str) -> int:
    return require_integer(value, name, minimum=0)


def require_display_pair(
    width: Any, height: Any
) -> tuple[int, int] | None:
    """Validate Runtime width/height; ``None`` means the engine default."""
    if width is None and height is None:
        return None
    if width is None or height is None:
        raise ValueError("width and height must be provided together")
    for value, name in ((width, "width"), (height, "height")):
        problem = dimension_problem(value, name)
        if problem is not None:
            raise ValueError(problem)
    return width, height


def require_int16(value: Any, name: str) -> int:
    """Validate the encoder range; Runtime keeps its ``within`` wording."""
    problem = integer_problem(value, name)
    if problem is not None:
        raise ValueError(problem)
    if not INT16_MIN <= value <= INT16_MAX:
        raise ValueError(
            f"{name} must be within {INT16_MIN}..{INT16_MAX}; got {value}"
        )
    return value


# ---- lvgl-ai-input-v1 --------------------------------------------------


def normalize_input_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and stably sort a ``lvgl-ai-input-v1`` list.

    Raises :class:`ScenarioError` with ``step`` set to the offending index.
    ``at_ms`` is an offset relative to the start of the input call.
    """
    if isinstance(events, (str, bytes)) or not isinstance(events, Iterable):
        raise ScenarioError("input events must be a list of objects")

    ordered: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        ordered.append(_normalize_event(index, event))
    ordered.sort(key=lambda event: event["at_ms"])
    return ordered


def _normalize_event(index: int, event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ScenarioError(f"step {index}: event must be an object", step=index)

    device = event.get("device")
    if device not in _DEVICE_FIELDS:
        raise ScenarioError(
            f"step {index}: device must be one of pointer, key, encoder; got {device!r}",
            step=index,
        )

    allowed = _DEVICE_FIELDS[device]
    unknown = sorted(set(event) - allowed)
    if unknown:
        raise ScenarioError(
            f"step {index}: unexpected field(s) {', '.join(unknown)} for {device}",
            step=index,
        )

    at_ms = _event_integer(index, event, "at_ms", minimum=0)
    action = event.get("action")
    normalized: dict[str, Any] = {"at_ms": at_ms, "device": device, "action": action}

    if device == "pointer":
        _event_action(index, device, action)
        normalized["x"] = _event_integer(index, event, "x", minimum=0)
        normalized["y"] = _event_integer(index, event, "y", minimum=0)
    elif device == "key":
        _event_action(index, device, action)
        key = event.get("key")
        problem = token_problem(key, "key.key")
        if problem is not None:
            raise ScenarioError(f"step {index}: {problem}", step=index)
        canonical, _ = resolve_key(key, step=index)
        normalized["key"] = canonical
    else:
        _event_action(index, device, action, quoted=True)
        normalized["diff"] = _event_integer(
            index,
            event,
            "diff",
            minimum=INT16_MIN,
            maximum=INT16_MAX,
        )
    return normalized


def _event_integer(
    index: int,
    event: dict[str, Any],
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = event.get(name)
    problem = integer_problem(value, name, minimum=minimum, maximum=maximum)
    if problem is not None:
        raise ScenarioError(f"step {index}: {problem}", step=index)
    return value


def _event_action(
    index: int, device: str, action: Any, *, quoted: bool = False
) -> None:
    problem = step_action_problem(device, action, quoted=quoted)
    if problem is not None:
        raise ScenarioError(f"step {index}: {problem}", step=index)
