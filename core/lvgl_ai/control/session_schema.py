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

from pathlib import Path
from typing import Any

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
FRAMES_DIR = "frames"
SNAPSHOTS_DIR = "snapshots"
# Transient raw preview for the web live stream; never an evidence artifact.
PREVIEW_FILE = "live.rgba"

# Full write-side field order. The manifest JSON keeps this order.
MANIFEST_FIELDS = (
    "schema",
    "id",
    "status",
    "app",
    "record_changed_only",
    "mode",
    "input",
    "build",
    "lvgl",
    "lvgl_src",
    "adapter",
    "tool_version",
    "frame_count",
    "truncated",
    "log_truncated",
    "checks",
    "error",
    "artifacts",
)
# ``app`` and ``record_changed_only`` were added after the first sessions, so
# they stay optional and old sessions keep opening.
MANIFEST_OPTIONAL_FIELDS = ("app", "record_changed_only")
MANIFEST_REQUIRED_FIELDS = tuple(
    field for field in MANIFEST_FIELDS if field not in MANIFEST_OPTIONAL_FIELDS
)
TIMELINE_ROW_TYPES = frozenset({"frame", "input", "wait", "mark", "snapshot", "end"})

# Optional evidence file -> manifest artifacts key, in listing order.
ARTIFACT_FILES = (
    (BUILD_LOG_FILE, "build_log"),
    (ENGINE_LOG_FILE, "engine_log"),
    (TIMELINE_FILE, "timeline"),
    (FRAME_DIFFS_FILE, "frame_diffs"),
    (REFERENCE_DIFFS_FILE, "reference_diffs"),
    (ANNOTATIONS_FILE, "annotations"),
)


def build_manifest(**values: Any) -> dict[str, Any]:
    """Stamp the manifest schema and order ``values`` by :data:`MANIFEST_FIELDS`.

    The field set is strict in both directions: a missing or unexpected value
    is a programming error in the writer, not a silently malformed manifest.
    """
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
    """Validate a manifest read from ``path`` with the shared schema.

    Raises ``ValueError`` with the same messages the reader always used; old
    sessions stay readable because only :data:`MANIFEST_REQUIRED_FIELDS` are
    mandatory.
    """
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(
            f"{path}: schema must be {MANIFEST_SCHEMA!r}, "
            f"got {data.get('schema')!r}"
        )
    missing = [field for field in MANIFEST_REQUIRED_FIELDS if field not in data]
    if missing:
        raise ValueError(f"{path}: missing manifest fields: {', '.join(missing)}")
    status = data["status"]
    if status not in SESSION_STATUSES:
        allowed = ", ".join(sorted(SESSION_STATUSES))
        raise ValueError(f"{path}: status must be one of {allowed}; got {status!r}")
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


def list_pngs(directory: Path) -> list[Path]:
    """Every PNG directly under ``directory``, sorted by file name."""
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.png") if path.is_file())


def _require_int(data: dict[str, Any], field: str, path: Path) -> None:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path}: {field} must be a non-negative integer")
