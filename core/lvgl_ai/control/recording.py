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
import re
from pathlib import Path
from typing import Any

_SNAPSHOT_NUMBER_PREFIX = re.compile(r"^\d+_")


def snapshot_label(path: Path) -> str:
    return _SNAPSHOT_NUMBER_PREFIX.sub("", path.stem)


def tail_lines(text: str, n: int) -> list[str]:
    if n <= 0:
        return []
    return text.splitlines()[-n:]


from . import session_schema
from .documents import DocumentStore

ANNOTATIONS_FILE = session_schema.ANNOTATIONS_FILE
ANNOTATIONS_SCHEMA = session_schema.ANNOTATIONS_SCHEMA
BUILD_LOG_FILE = session_schema.BUILD_LOG_FILE
ENGINE_LOG_FILE = session_schema.ENGINE_LOG_FILE
FRAME_DIFFS_FILE = session_schema.FRAME_DIFFS_FILE
FRAME_DIFFS_SCHEMA = session_schema.FRAME_DIFFS_SCHEMA
FRAMES_DIR = session_schema.FRAMES_DIR
MANIFEST_FILE = session_schema.MANIFEST_FILE
MANIFEST_REQUIRED_FIELDS = session_schema.MANIFEST_REQUIRED_FIELDS
MANIFEST_SCHEMA = session_schema.MANIFEST_SCHEMA
REFERENCE_DIFFS_FILE = session_schema.REFERENCE_DIFFS_FILE
SNAPSHOTS_DIR = session_schema.SNAPSHOTS_DIR
TIMELINE_FILE = session_schema.TIMELINE_FILE
TIMELINE_ROW_TYPES = session_schema.TIMELINE_ROW_TYPES
TIMELINE_SCHEMA = session_schema.TIMELINE_SCHEMA
_list_pngs = session_schema.list_pngs
_validate_manifest = session_schema.validate_manifest
manifest_is_recorded = session_schema.manifest_describes_recording


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
        if raw.is_file() and raw.name == session_schema.MANIFEST_FILE:
            raw = raw.parent
        self.path = raw
        self._timeline_rows: list[dict[str, Any]] | None = None

    @classmethod
    def open(cls, path: str | Path) -> Recording:
        recording = cls(path)
        recording._validate_session()
        return recording

    def _validate_session(self) -> None:
        if not self.path.is_dir():
            raise FileNotFoundError(
                f"session directory not found: {self.path}"
            )
        manifest = self.manifest
        self._require_file(self.path / session_schema.ENGINE_LOG_FILE)

        if session_schema.manifest_describes_recording(manifest):
            self._require_file(self.path / session_schema.TIMELINE_FILE)
            self._require_file(self.path / session_schema.FRAME_DIFFS_FILE)

    @staticmethod
    def _require_file(path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(
                f"required session file is missing: {path}"
            )

    @property
    def manifest(self) -> dict[str, Any]:
        path = self.path / session_schema.MANIFEST_FILE
        return session_schema.validate_manifest(_read_json_object(path), path)

    @property
    def recorded(self) -> bool:
        return session_schema.session_is_recorded(self.manifest, self.path)

    def timeline(self) -> list[dict[str, Any]]:
        rows = _read_ndjson(
            self.path / session_schema.TIMELINE_FILE,
            session_schema.TIMELINE_SCHEMA,
            session_schema.TIMELINE_ROW_TYPES,
        )
        self._timeline_rows = rows
        return rows

    def frame_diffs(self) -> list[dict[str, Any]]:
        return _read_ndjson(
            self.path / session_schema.FRAME_DIFFS_FILE,
            session_schema.FRAME_DIFFS_SCHEMA,
        )

    def reference_diffs(self) -> list[dict[str, Any]] | None:
        path = self.path / session_schema.REFERENCE_DIFFS_FILE
        if not path.is_file():
            return None
        return _read_ndjson(path, session_schema.FRAME_DIFFS_SCHEMA)

    @property
    def frames(self) -> list[Path]:
        return session_schema.list_pngs(self.path / session_schema.FRAMES_DIR)

    @property
    def snapshots(self) -> list[Path]:
        return session_schema.list_pngs(
            self.path / session_schema.SNAPSHOTS_DIR
        )

    def frame_views(self) -> list[dict[str, Any]]:
        by_file = _rows_by_file(self._shared_timeline_rows(), "frame")
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

    def snapshot_views(self) -> list[dict[str, Any]]:
        by_file = _rows_by_file(self._shared_timeline_rows(), "snapshot")
        views: list[dict[str, Any]] = []
        for path in self.snapshots:
            relative = path.relative_to(self.path).as_posix()
            row = by_file.get(relative, {})
            label = row.get("label")
            label_text = (
                label if isinstance(label, str) and label else path.stem
            )
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
        frames = self.frames
        if not frames:
            return None
        latest = frames[-1]
        relative = latest.relative_to(self.path).as_posix()
        stem = latest.stem
        return {
            "file": relative,
            "frame_no": int(stem) if stem.isdigit() else None,
            "t_ms": _latest_frame_t_ms(
                self.path / session_schema.TIMELINE_FILE, relative
            ),
        }

    def _shared_timeline_rows(self) -> list[dict[str, Any]]:
        if self._timeline_rows is None:
            try:
                self._timeline_rows = self.timeline()
            except (FileNotFoundError, ValueError):
                self._timeline_rows = []
        return self._timeline_rows

    def log(self) -> str:
        return _read_text(self.path / session_schema.ENGINE_LOG_FILE)

    def log_tail(self, n: int = 40) -> list[str]:
        return tail_lines(self.log(), n)

    def build_log(self) -> str:
        return _read_text(self.path / session_schema.BUILD_LOG_FILE)

    @property
    def annotations_store(self) -> DocumentStore:
        return DocumentStore(
            self.path,
            filename=session_schema.ANNOTATIONS_FILE,
            schema=session_schema.ANNOTATIONS_SCHEMA,
            collection="notes",
            unreadable_code="annotations_unreadable",
            write_code="annotations_write_error",
        )

    @property
    def annotations(self) -> dict[str, Any]:
        return self.annotations_store.read()

    @annotations.setter
    def annotations(self, value: Any) -> None:
        if not self.path.is_dir():
            raise FileNotFoundError(
                f"session directory not found: {self.path}"
            )
        self.annotations_store.write(value)

    @property
    def whiteboards_store(self) -> DocumentStore:
        return DocumentStore(
            self.path,
            filename=session_schema.WHITEBOARDS_FILE,
            schema=session_schema.WHITEBOARDS_SCHEMA,
            collection="whiteboards",
            unreadable_code="whiteboards_unreadable",
            write_code="whiteboards_write_error",
            keep_extra_fields=False,
        )

    @property
    def whiteboards(self) -> dict[str, Any]:
        return self.whiteboards_store.read()

    @whiteboards.setter
    def whiteboards(self, value: Any) -> None:
        if not self.path.is_dir():
            raise FileNotFoundError(
                f"session directory not found: {self.path}"
            )
        self.whiteboards_store.write(value)


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
