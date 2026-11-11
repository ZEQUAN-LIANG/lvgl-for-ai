"""Recording: a read-only view of one session's evidence.

``Recording.open(path)`` reads an existing session and never starts an engine.
Frames, timeline rows and frame diffs are plain files written by the engine;
the manifest and build log are written by
:class:`~lvgl_ai.control.session.SessionStore`. The file layout and the manifest
schema come from :mod:`~lvgl_ai.control.session_schema`, shared with the writer.

Only ``annotations`` is writable: humans and AI agents add notes to a session
without touching the evidence the engine produced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The schema, file names and validation are shared with SessionStore, the
# write side. Re-exported here so existing imports keep working.
from .session_schema import (
    ANNOTATIONS_FILE,
    ANNOTATIONS_SCHEMA,
    BUILD_LOG_FILE,
    ENGINE_LOG_FILE,
    FRAME_DIFFS_FILE,
    FRAME_DIFFS_SCHEMA,
    FRAMES_DIR,
    MANIFEST_FILE,
    MANIFEST_REQUIRED_FIELDS,
    MANIFEST_SCHEMA,
    REFERENCE_DIFFS_FILE,
    SNAPSHOTS_DIR,
    TIMELINE_FILE,
    TIMELINE_ROW_TYPES,
    TIMELINE_SCHEMA,
    list_pngs as _list_pngs,
    validate_manifest as _validate_manifest,
)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required session file is missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


class Recording:
    """Evidence view for ``sessions/<id>/``.

    Required files are ``manifest.json`` and ``engine.log``. When the manifest
    describes a recorded session (``frame_count > 0`` or the artifacts list
    ``timeline`` / ``frame_diffs``), those two files are required as well.
    ``build.log`` and ``annotations.json`` are optional; a missing annotations
    file reads as an empty ``lvgl-ai-annotations-v1`` document.
    """

    def __init__(self, path: str | Path) -> None:
        raw = Path(path)
        if raw.is_file() and raw.name == "manifest.json":
            raw = raw.parent
        self.path = raw

    @classmethod
    def open(cls, path: str | Path) -> Recording:
        """Open a session directory (or its manifest.json) without an engine."""
        recording = cls(path)
        recording._validate_session()
        return recording

    # ---- session validation -------------------------------------------

    def _validate_session(self) -> None:
        if not self.path.is_dir():
            raise FileNotFoundError(f"session directory not found: {self.path}")
        manifest = self.manifest
        self._require_file(self.path / ENGINE_LOG_FILE)

        artifacts = manifest["artifacts"]
        recorded = manifest["frame_count"] > 0 or any(
            key in artifacts for key in ("timeline", "frame_diffs")
        )
        if recorded:
            self._require_file(self.path / TIMELINE_FILE)
            self._require_file(self.path / FRAME_DIFFS_FILE)

    @staticmethod
    def _require_file(path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"required session file is missing: {path}")

    # ---- evidence ------------------------------------------------------

    @property
    def manifest(self) -> dict[str, Any]:
        """The session manifest, re-read on every access."""
        path = self.path / MANIFEST_FILE
        return _validate_manifest(_read_json_object(path), path)

    def timeline(self) -> list[dict[str, Any]]:
        """Parsed ``timeline.ndjson`` rows."""
        return _read_ndjson(
            self.path / TIMELINE_FILE, TIMELINE_SCHEMA, TIMELINE_ROW_TYPES
        )

    def frame_diffs(self) -> list[dict[str, Any]]:
        """Parsed ``frame_diffs.ndjson`` rows."""
        return _read_ndjson(self.path / FRAME_DIFFS_FILE, FRAME_DIFFS_SCHEMA)

    def reference_diffs(self) -> list[dict[str, Any]] | None:
        """Parsed ``reference_diffs.ndjson``, or None when no reference was used."""
        path = self.path / REFERENCE_DIFFS_FILE
        if not path.is_file():
            return None
        return _read_ndjson(path, FRAME_DIFFS_SCHEMA)

    @property
    def frames(self) -> list[Path]:
        """Every full-frame PNG, sorted by frame number."""
        return _list_pngs(self.path / FRAMES_DIR)

    @property
    def snapshots(self) -> list[Path]:
        """Every named snapshot PNG, sorted by snapshot number."""
        return _list_pngs(self.path / SNAPSHOTS_DIR)

    def frame_views(
        self, timeline: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Retained frames as ``file``, ``frame_no`` and ``t_ms`` entries.

        ``timeline`` lets a caller reuse rows it already parsed; without it the
        full timeline is read. A missing or corrupt timeline degrades to file
        numbers and ``t_ms = 0``. Entries carry no URLs.
        """
        by_file = _rows_by_file(self._timeline_rows(timeline), "frame")
        views: list[dict[str, Any]] = []
        for index, path in enumerate(self.frames, start=1):
            relative = path.relative_to(self.path).as_posix()
            row = by_file.get(relative, {})
            frame_no = row.get("frame_no")
            if not _is_int(frame_no):
                frame_no = _frame_no_from_name(path, index)
            t_ms = row.get("t_ms")
            views.append(
                {
                    "file": relative,
                    "frame_no": frame_no,
                    "t_ms": t_ms if _is_int(t_ms) else 0,
                }
            )
        return views

    def snapshot_views(
        self, timeline: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Snapshots as ``file``, ``frame_no``, ``t_ms`` and ``label`` entries.

        The label falls back to the file stem when the timeline has no row or
        no label. Entries carry no URLs.
        """
        by_file = _rows_by_file(self._timeline_rows(timeline), "snapshot")
        views: list[dict[str, Any]] = []
        for path in self.snapshots:
            relative = path.relative_to(self.path).as_posix()
            row = by_file.get(relative, {})
            label = row.get("label")
            label_text = label if isinstance(label, str) and label else path.stem
            views.append(
                {
                    "file": relative,
                    "frame_no": row.get("frame_no"),
                    "t_ms": row.get("t_ms"),
                    "label": label_text,
                }
            )
        return views

    def latest_frame(self) -> dict[str, Any] | None:
        """The newest retained frame, or ``None`` when the session has none.

        ``t_ms`` comes from a bounded tail read of ``timeline.ndjson``; the
        frame number comes from the file name, like the live status reports it.
        """
        frames = self.frames
        if not frames:
            return None
        latest = frames[-1]
        relative = latest.relative_to(self.path).as_posix()
        stem = latest.stem
        return {
            "file": relative,
            "frame_no": int(stem) if stem.isdigit() else None,
            "t_ms": _latest_frame_t_ms(self.path / TIMELINE_FILE, relative),
        }

    def _timeline_rows(
        self, timeline: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if timeline is not None:
            return timeline
        try:
            return self.timeline()
        except (FileNotFoundError, ValueError):
            return []

    def log(self) -> str:
        """Full ``engine.log`` text (stdout and stderr)."""
        return _read_text(self.path / ENGINE_LOG_FILE)

    def log_tail(self, n: int = 40) -> list[str]:
        """Last ``n`` lines of ``engine.log``; ``n <= 0`` returns ``[]``."""
        if n <= 0:
            return []
        return self.log().splitlines()[-n:]

    def build_log(self) -> str:
        """Full ``build.log`` text."""
        return _read_text(self.path / BUILD_LOG_FILE)

    # ---- annotations (writable) ---------------------------------------

    @property
    def annotations(self) -> dict[str, Any]:
        path = self.path / ANNOTATIONS_FILE
        if not path.is_file():
            return {"schema": ANNOTATIONS_SCHEMA, "notes": []}
        data = _read_json_object(path)
        return _validate_annotations(data, path)

    @annotations.setter
    def annotations(self, value: Any) -> None:
        if not self.path.is_dir():
            raise FileNotFoundError(f"session directory not found: {self.path}")
        data = _validate_annotations(value, self.path / ANNOTATIONS_FILE)
        path = self.path / ANNOTATIONS_FILE
        tmp = path.with_name(f"{ANNOTATIONS_FILE}.tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)


def _validate_annotations(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path}: annotations must be a JSON object")
    schema = value.get("schema", ANNOTATIONS_SCHEMA)
    if schema != ANNOTATIONS_SCHEMA:
        raise ValueError(
            f"{path}: schema must be {ANNOTATIONS_SCHEMA!r}, got {schema!r}"
        )
    notes = value.get("notes")
    if not isinstance(notes, list):
        raise ValueError(f"{path}: notes must be a list")
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise ValueError(f"{path}: notes[{index}] must be a JSON object")
    data = dict(value)
    data["schema"] = ANNOTATIONS_SCHEMA
    data["notes"] = notes
    return data


_TIMELINE_TAIL_BYTES = 262144


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _frame_no_from_name(path: Path, fallback: int) -> int:
    stem = path.stem
    return int(stem) if stem.isdigit() else fallback


def _rows_by_file(
    rows: list[dict[str, Any]], row_type: str
) -> dict[str, dict[str, Any]]:
    return {
        row["file"]: row
        for row in rows
        if row.get("type") == row_type and isinstance(row.get("file"), str)
    }


def _latest_frame_t_ms(path: Path, frame_file: str) -> int | None:
    """Read the newest matching frame row from the tail of timeline.ndjson.

    Live sessions are polled every few seconds; reading the whole timeline on
    each poll would grow with the recording. Async recording writes frame rows
    as soon as a raw frame is queued, so the newest published PNG can trail the
    file end by the encoder backlog; 256 KiB covers max_frames and input rows
    for the supported display sizes.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            chunk = min(size, _TIMELINE_TAIL_BYTES)
            handle.seek(size - chunk)
            data = handle.read()
    except OSError:
        return None
    for line in reversed(data.splitlines()):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if row.get("type") == "frame" and row.get("file") == frame_file:
            t_ms = row.get("t_ms")
            if _is_int(t_ms):
                return t_ms
            return None
    return None


def _read_ndjson(
    path: Path,
    schema: str,
    allowed_types: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"required session file is missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{path}:{line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        if row.get("schema") != schema:
            raise ValueError(
                f"{path}:{line_number}: schema must be {schema!r}, "
                f"got {row.get('schema')!r}"
            )
        if allowed_types is not None and row.get("type") not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            raise ValueError(
                f"{path}:{line_number}: type must be one of {allowed}; "
                f"got {row.get('type')!r}"
            )
        rows.append(row)
    return rows


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required session file is missing: {path}")
    return path.read_text(encoding="utf-8", errors="replace")
