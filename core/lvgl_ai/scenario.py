"""Scenario: a small gesture script translated into ``Runtime`` calls.

A scenario file is a JSON object with the ``lvgl-ai-scenario-v1`` schema::

    {
      "schema": "lvgl-ai-scenario-v1",
      "name": "settings",
      "app": "coffee",
      "display": {"width": 800, "height": 600},
      "steps": [
        {"type": "click_at", "x": 112, "y": 324},
        {"type": "wait", "ms": 64},
        {"type": "mark", "id": "after_click"},
        {"type": "snapshot", "label": "after_click"},
        {"type": "drag", "from": [112, 324], "to": [240, 324], "steps": 4}
      ]
    }

``app`` is optional and selects the user app variant (matching
``[A-Za-z0-9_-]+``). The CLI forwards it as ``LVGL_AI_DEMO`` before starting the
engine and the session manifest records it; omit it to use the user code
default.

``display`` is optional and declares the LVGL screen size. ``width`` and
``height`` are integers in ``1..4096``; omit the object to use the engine
default (800x600). The size is passed to the engine at startup, so changing it
does not require a rebuild.

Step types (the schema is intentionally this small):

``click_at``
    ``x``, ``y``; optional ``hold_ms`` (default 64). Expands to
    ``pointer down`` / ``wait(hold_ms)`` / ``pointer up`` so the press has a
    visible frame.
``drag``
    ``from`` and ``to`` (``[x, y]``); optional ``steps`` (default 8, 1..1000).
    Expands to ``pointer down(from)`` / ``pointer move`` x ``steps``
    (linearly interpolated, the last move lands on ``to``) / ``pointer up(to)``
    / ``snapshot("drag_end")``.
``key``
    ``action`` (``press`` / ``release``) and an LVGL ``LV_KEY_*`` name in
    ``key`` (case-insensitive, optional ``LV_KEY_`` prefix).
``encoder``
    ``action`` (``turn``) and a signed ``diff`` within -32768..32767; positive
    turns move focus forward.
``wait``
    exactly one of ``ms`` or ``frames``.
``mark``
    ``id`` matching ``[A-Za-z0-9_-]+``.
``snapshot``
    ``label`` matching ``[A-Za-z0-9_-]+``.

All steps are validated before the first command is sent, so a typo in the
last step cannot leave a half-played gesture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .control.errors import ScenarioError
from .control.input import (
    INT16_MAX,
    INT16_MIN,
    TOKEN_PATTERN,
    display_problem,
    integer_problem,
    is_token,
    point_problem,
    resolve_key,
    step_action_problem,
    token_problem,
)

SCENARIO_SCHEMA = "lvgl-ai-scenario-v1"
STEP_TYPES = ("click_at", "drag", "encoder", "key", "mark", "snapshot", "wait")
DEFAULT_CLICK_HOLD_MS = 64
DEFAULT_DRAG_STEPS = 8
MAX_DRAG_STEPS = 1000
DRAG_SNAPSHOT_LABEL = "drag_end"

_FILE_FIELDS = {"schema", "name", "app", "display", "steps"}
_STEP_FIELDS = {
    "click_at": {"type", "x", "y", "hold_ms"},
    "drag": {"type", "from", "to", "steps"},
    "encoder": {"type", "action", "diff"},
    "key": {"type", "action", "key"},
    "mark": {"type", "id"},
    "snapshot": {"type", "label"},
    "wait": {"type", "ms", "frames"},
}


def load_scenario(path: str | Path) -> dict[str, Any]:
    """Read and validate a scenario file, returning the normalized document.

    Defaults are applied (``hold_ms``, ``steps``) so callers can see the exact
    commands a ``play_scenario`` call will send. Raises
    :class:`ScenarioError` when the file is missing, is not JSON, or does not
    match the schema.
    """
    scenario_path = Path(path)
    try:
        text = scenario_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScenarioError(f"cannot read scenario {scenario_path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScenarioError(
            f"scenario {scenario_path}: invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise ScenarioError(f"scenario {scenario_path}: expected a JSON object")

    unknown = sorted(set(data) - _FILE_FIELDS)
    if unknown:
        raise ScenarioError(
            f"scenario {scenario_path}: unexpected field(s) {', '.join(unknown)}"
        )
    if data.get("schema") != SCENARIO_SCHEMA:
        raise ScenarioError(
            f"scenario {scenario_path}: schema must be {SCENARIO_SCHEMA!r}, "
            f"got {data.get('schema')!r}"
        )
    name = data.get("name")
    if name is not None and (not isinstance(name, str) or not name):
        raise ScenarioError(
            f"scenario {scenario_path}: name must be a non-empty string"
        )
    app = data.get("app")
    if app is not None and not is_token(app):
        raise ScenarioError(
            f"scenario {scenario_path}: app must match {TOKEN_PATTERN}"
        )
    display = data.get("display")
    if display is not None:
        problem = display_problem(display)
        if problem is not None:
            raise ScenarioError(f"scenario {scenario_path}: {problem}")
    if "steps" not in data:
        raise ScenarioError(f"scenario {scenario_path}: steps is required")

    document: dict[str, Any] = {"schema": SCENARIO_SCHEMA}
    if name is not None:
        document["name"] = name
    if app is not None:
        document["app"] = app
    if display is not None:
        document["display"] = {
            "width": display["width"],
            "height": display["height"],
        }
    document["steps"] = normalize_steps(data["steps"])
    return document


def scenario_index(
    root: str | Path,
    *,
    scenarios_dir: str | Path | None = None,
    include_symlinks: bool = False,
) -> list[dict[str, Any]]:
    """Return one entry per ``*.json`` scenario file, sorted by filename.

    ``root`` is the base for the relative ``path`` field; the scanned directory
    defaults to ``root/user/scenarios`` and can be overridden with
    ``scenarios_dir`` (the web app manager keeps its scenarios outside the
    repository root). Invalid scenarios keep their error text and do not block
    the other entries.

    Symlinked scenario files are skipped by default (the app views and trash
    must not follow links). The web app picker and its display lookup pass
    ``include_symlinks=True`` to keep following them.
    """
    root_path = Path(root).expanduser().resolve()
    directory = (
        Path(scenarios_dir).expanduser().resolve()
        if scenarios_dir is not None
        else root_path / "user" / "scenarios"
    )
    result: list[dict[str, Any]] = []
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.json")):
        if not include_symlinks and path.is_symlink():
            continue
        if not path.is_file():
            continue
        entry: dict[str, Any] = {
            "path": _relative(path, root_path),
            "basename": path.name,
            "app": None,
            "name": None,
            "display": None,
            "valid": False,
            "error": None,
        }
        try:
            document = load_scenario(path)
        except (OSError, ValueError, ScenarioError) as exc:
            entry["error"] = str(exc)
        else:
            app = document.get("app")
            entry["app"] = app if isinstance(app, str) else None
            entry["name"] = document.get("name")
            entry["display"] = document.get("display")
            entry["valid"] = True
        result.append(entry)
    return result


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_steps(steps: Any) -> list[dict[str, Any]]:
    """Validate a list of steps and apply per-type defaults."""
    if not isinstance(steps, list):
        raise ScenarioError("scenario.steps must be a list")
    if not steps:
        raise ScenarioError("scenario.steps must not be empty")
    return [_normalize_step(index, step) for index, step in enumerate(steps)]


def play_scenario(rt: Any, path_or_steps: str | Path | Sequence[dict]) -> list[dict]:
    """Execute a scenario against a started Runtime (or a test double).

    ``path_or_steps`` is either a path to a ``lvgl-ai-scenario-v1`` file or the
    step list itself. The whole script is validated before any command is
    sent. Returns the replies of every Runtime command in execution order.
    """
    try:
        steps = _steps_from(path_or_steps)
        replies: list[dict] = []
        for step in steps:
            replies.extend(_play_step(rt, step))
        return replies
    except ScenarioError as exc:
        # A caller-owned loop (the CLI) relies on Runtime.stop() writing the
        # manifest; remember the failure so it lands as harness_error.
        record = getattr(rt, "record_error", None)
        if record is not None:
            record(exc)
        raise


def _steps_from(path_or_steps: Any) -> list[dict[str, Any]]:
    if isinstance(path_or_steps, (str, Path)):
        return load_scenario(path_or_steps)["steps"]
    if isinstance(path_or_steps, list):
        return normalize_steps(path_or_steps)
    raise ScenarioError("play_scenario needs a scenario path or a list of steps")


def _play_step(rt: Any, step: dict[str, Any]) -> list[dict]:
    kind = step["type"]
    if kind == "click_at":
        x = step["x"]
        y = step["y"]
        return [
            rt.pointer("down", x, y),
            rt.wait(ms=step["hold_ms"]),
            rt.pointer("up", x, y),
        ]
    if kind == "drag":
        start = step["from"]
        end = step["to"]
        replies = [rt.pointer("down", start[0], start[1])]
        for x, y in _interpolate(start, end, step["steps"]):
            replies.append(rt.pointer("move", x, y))
        replies.append(rt.pointer("up", end[0], end[1]))
        replies.append(rt.snapshot(DRAG_SNAPSHOT_LABEL))
        return replies
    if kind == "wait":
        if "ms" in step:
            return [rt.wait(ms=step["ms"])]
        return [rt.wait(frames=step["frames"])]
    if kind == "key":
        return [rt.key(step["action"], step["key"])]
    if kind == "encoder":
        return [rt.encoder(step["action"], step["diff"])]
    if kind == "mark":
        return [rt.mark(step["id"])]
    if kind == "snapshot":
        return [rt.snapshot(step["label"])]
    raise ScenarioError(f"unsupported step type {kind!r}")


def _interpolate(
    start: Sequence[int], end: Sequence[int], count: int
) -> list[tuple[int, int]]:
    """``count`` points from just after ``start`` through exactly ``end``."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return [
        (start[0] + dx * index // count, start[1] + dy * index // count)
        for index in range(1, count + 1)
    ]


def _normalize_step(index: int, step: Any) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise ScenarioError(f"step {index}: step must be an object", step=index)
    kind = step.get("type")
    if kind not in _STEP_FIELDS:
        raise ScenarioError(
            f"step {index}: type must be one of {', '.join(STEP_TYPES)}; "
            f"got {kind!r}",
            step=index,
        )

    unknown = sorted(set(step) - _STEP_FIELDS[kind])
    if unknown:
        raise ScenarioError(
            f"step {index}: unexpected field(s) {', '.join(unknown)} for {kind}",
            step=index,
        )

    if kind == "click_at":
        normalized: dict[str, Any] = {
            "type": kind,
            "x": _integer(index, step, "x"),
            "y": _integer(index, step, "y"),
            "hold_ms": _integer(index, step, "hold_ms", default=DEFAULT_CLICK_HOLD_MS),
        }
    elif kind == "drag":
        normalized = {
            "type": kind,
            "from": _point(index, step, "from"),
            "to": _point(index, step, "to"),
            "steps": _integer(
                index,
                step,
                "steps",
                default=DEFAULT_DRAG_STEPS,
                minimum=1,
                maximum=MAX_DRAG_STEPS,
            ),
        }
    elif kind == "wait":
        has_ms = "ms" in step
        has_frames = "frames" in step
        if has_ms == has_frames:
            raise ScenarioError(
                f"step {index}: wait needs exactly one of ms or frames",
                step=index,
            )
        if has_ms:
            normalized = {"type": kind, "ms": _integer(index, step, "ms")}
        else:
            normalized = {"type": kind, "frames": _integer(index, step, "frames")}
    elif kind == "key":
        action = step.get("action")
        _action(index, "key", action)
        key = step.get("key")
        _problem(index, token_problem(key, "key.key"))
        canonical, _ = resolve_key(key, step=index)
        normalized = {"type": kind, "action": action, "key": canonical}
    elif kind == "encoder":
        action = step.get("action")
        _action(index, "encoder", action)
        normalized = {
            "type": kind,
            "action": action,
            "diff": _integer(
                index,
                step,
                "diff",
                minimum=INT16_MIN,
                maximum=INT16_MAX,
            ),
        }
    elif kind == "mark":
        normalized = {"type": kind, "id": _token(index, step, "id")}
    else:
        normalized = {"type": kind, "label": _token(index, step, "label")}
    return normalized


def _integer(
    index: int,
    step: dict[str, Any],
    name: str,
    *,
    default: int | None = None,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if name not in step:
        if default is not None:
            return default
        raise ScenarioError(f"step {index}: {name} is required", step=index)
    value = step[name]
    _problem(index, integer_problem(value, name, minimum=minimum, maximum=maximum))
    return value


def _point(index: int, step: dict[str, Any], name: str) -> list[int]:
    value = step.get(name)
    _problem(index, point_problem(value, name))
    return [value[0], value[1]]


def _token(index: int, step: dict[str, Any], name: str) -> str:
    value = step.get(name)
    _problem(index, token_problem(value, name))
    return value


def _action(index: int, device: str, action: Any) -> None:
    _problem(index, step_action_problem(device, action))


def _problem(index: int, problem: str | None) -> None:
    if problem is not None:
        raise ScenarioError(f"step {index}: {problem}", step=index)
