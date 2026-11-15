"""Session evidence layout and manifest schema, shared by writer and reader.

A session is one directory under the sessions root. The engine writes the
frame PNGs, ``timeline.ndjson`` and ``frame_diffs.ndjson``; the Python control
layer writes ``manifest.json`` and ``build.log`` and keeps ``engine.log``.
:class:`~lvgl_ai.control.session.SessionStore` builds the manifest from the
constants and helpers here, and :class:`~lvgl_ai.control.recording.Recording`
validates it with the same definition, so the write side and the read side
cannot drift.
"""

from __future__ import annotations

import datetime as _dt
import re
import secrets
from pathlib import Path
from typing import Any, Mapping

from .errors import SESSION_STATUSES

MANIFEST_SCHEMA = "lvgl-ai-session-v1"
TIMELINE_SCHEMA = "lvgl-ai-timeline-v1"
FRAME_DIFFS_SCHEMA = "lvgl-ai-frame-diffs-v1"
ANNOTATIONS_SCHEMA = "lvgl-ai-annotations-v1"

MANIFEST_FILE = "manifest.json"
BUILD_LOG_FILE = "build.log"
ENGINE_LOG_FILE = "engine.log"
TIMELINE_FILE = "timeline.ndjson"
FRAME_DIFFS_FILE = "frame_diffs.ndjson"
REFERENCE_DIFFS_FILE = "reference_diffs.ndjson"
ANNOTATIONS_FILE = "annotations.json"
WHITEBOARDS_FILE = "whiteboards.json"
FRAMES_DIR = "frames"
SNAPSHOTS_DIR = "snapshots"
REGIONS_DIR = "regions"
WHITEBOARDS_DIR = "whiteboards"
WHITEBOARDS_SCHEMA = "lvgl-ai-whiteboards-v1"
PREVIEW_FILE = "live.rgba"

# Full write-side field order. The manifest JSON keeps this order.
MANIFEST_FIELDS = (
    "schema",
    "id",
    "status",
    "app",
    "scenario",
    "source_digest",
    "record_changed_only",
    "mode",
    "input",
    "build",
    "lvgl",
    "lvgl_src",
    "adapter",
    "display",
    "tool_version",
    "frame_count",
    "truncated",
    "log_truncated",
    "checks",
    "error",
    "artifacts",
)
MANIFEST_OPTIONAL_FIELDS = ("app", "display", "record_changed_only")
MANIFEST_REQUIRED_FIELDS = tuple(
    field for field in MANIFEST_FIELDS if field not in MANIFEST_OPTIONAL_FIELDS
)
TIMELINE_ROW_TYPES = frozenset(
    {"frame", "input", "wait", "mark", "snapshot", "end"}
)

MAX_DISPLAY_DIMENSION = 4096

SESSION_ID_PATTERN = r"\d{8}-\d{6}-[0-9a-f]{4}"
SESSION_ID_RE = re.compile(r"^" + SESSION_ID_PATTERN + r"\Z")


def new_session_id(now: _dt.datetime | None = None) -> str:
    stamp = (now or _dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def is_session_id(value: Any) -> bool:
    return (
        isinstance(value, str) and SESSION_ID_RE.fullmatch(value) is not None
    )


# Optional evidence file -> manifest artifacts key, in listing order.
ARTIFACT_FILES = (
    (BUILD_LOG_FILE, "build_log"),
    (ENGINE_LOG_FILE, "engine_log"),
    (TIMELINE_FILE, "timeline"),
    (FRAME_DIFFS_FILE, "frame_diffs"),
    (REFERENCE_DIFFS_FILE, "reference_diffs"),
    (ANNOTATIONS_FILE, "annotations"),
)


def dimension_problem(
    value: Any,
    name: str,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{name} must be an integer"
    if value < minimum:
        return f"{name} must be >= {minimum}; got {value}"
    if maximum is not None and value > maximum:
        return f"{name} must be <= {maximum}; got {value}"
    return None


def display_problem(
    value: Any,
    *,
    label: str = "display",
    allow_none: bool = False,
    maximum: int | None = None,
    reject_unknown: bool = False,
) -> str | None:
    if value is None:
        if allow_none:
            return None
        return f"{label} must be an object with width and height"
    if not isinstance(value, dict):
        return f"{label} must be an object with width and height"
    if reject_unknown:
        unknown = sorted(set(value) - {"width", "height"})
        if unknown:
            return f"{label} has unexpected field(s) {', '.join(unknown)}"
    for name in ("width", "height"):
        if name not in value:
            return f"{label}.{name} is required"
        problem = dimension_problem(
            value[name], f"{label}.{name}", maximum=maximum
        )
        if problem is not None:
            return problem
    return None


def validate_display(
    value: Any,
    *,
    path: Path | None = None,
    label: str = "display",
    allow_none: bool = False,
    maximum: int | None = None,
    reject_unknown: bool = False,
) -> dict[str, int] | None:
    problem = display_problem(
        value,
        label=label,
        allow_none=allow_none,
        maximum=maximum,
        reject_unknown=reject_unknown,
    )
    if problem is not None:
        prefix = "" if path is None else f"{path}: "
        raise ValueError(prefix + problem)
    if value is None:
        return None
    return {"width": value["width"], "height": value["height"]}


def build_manifest(**values: Any) -> dict[str, Any]:
    missing = [field for field in MANIFEST_FIELDS[1:] if field not in values]
    unexpected = sorted(set(values) - set(MANIFEST_FIELDS[1:]))
    if missing or unexpected:
        problems = []
        if missing:
            problems.append("missing " + ", ".join(missing))
        if unexpected:
            problems.append("unexpected " + ", ".join(unexpected))
        raise ValueError("manifest fields: " + "; ".join(problems))
    payload: dict[str, Any] = {"schema": MANIFEST_SCHEMA}
    for field in MANIFEST_FIELDS[1:]:
        payload[field] = values[field]
    return payload


def validate_manifest(data: dict[str, Any], path: Path) -> dict[str, Any]:
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(
            f"{path}: schema must be {MANIFEST_SCHEMA!r}, "
            f"got {data.get('schema')!r}"
        )
    missing = [
        field for field in MANIFEST_REQUIRED_FIELDS if field not in data
    ]
    if missing:
        raise ValueError(
            f"{path}: missing manifest fields: {', '.join(missing)}"
        )
    status = data["status"]
    if status not in SESSION_STATUSES:
        allowed = ", ".join(sorted(SESSION_STATUSES))
        raise ValueError(
            f"{path}: status must be one of {allowed}; got {status!r}"
        )
    validate_display(data.get("display"), path=path, allow_none=True)
    _validate_optional_object(
        data.get("scenario"),
        path=path,
        label="scenario",
        fields=("path", "sha256"),
    )
    _validate_optional_object(
        data.get("source_digest"),
        path=path,
        label="source_digest",
        fields=("dir", "sha256", "files"),
    )
    _require_int(data, "frame_count", path)
    if not isinstance(data["checks"], list):
        raise ValueError(f"{path}: checks must be a list")
    if not isinstance(data["artifacts"], dict):
        raise ValueError(f"{path}: artifacts must be an object")
    error = data["error"]
    if error is not None:
        if not isinstance(error, dict) or not all(
            key in error for key in ("code", "message", "detail")
        ):
            raise ValueError(
                f"{path}: error must be null or {{code, message, detail}}"
            )
    return data


def manifest_describes_recording(manifest: Mapping[str, Any]) -> bool:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return False
    return manifest.get("frame_count", 0) > 0 or any(
        key in artifacts for key in ("timeline", "frame_diffs")
    )


def session_is_recorded(
    manifest: Mapping[str, Any], session_dir: str | Path
) -> bool:
    if not manifest_describes_recording(manifest):
        return False
    root = Path(session_dir)
    return (root / TIMELINE_FILE).is_file() and (
        root / FRAME_DIFFS_FILE
    ).is_file()


def list_pngs(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.png") if path.is_file())


def _validate_optional_object(
    value: Any,
    *,
    path: Path,
    label: str,
    fields: tuple[str, ...],
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"{path}: {label} must be null or an object")
    missing = [field for field in fields if field not in value]
    if missing:
        raise ValueError(f"{path}: {label} is missing {', '.join(missing)}")


def _require_int(data: dict[str, Any], field: str, path: Path) -> None:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path}: {field} must be a non-negative integer")
