"""Session evidence summary built on top of :class:`Recording`.

``summarize_session`` is the single read-only summary entry point shared by
the session report tool and the CLI JSON output. It never starts an engine or
the web server. ``SUMMARY_FIELDS`` and ``CLI_EVIDENCE_FIELDS`` are the one
source for both entry points' field lists.

``manifest.json`` and ``engine.log`` are required evidence: a missing one is an
error. A session whose manifest describes recording must also have both
``timeline.ndjson`` and ``frame_diffs.ndjson``, matching
:meth:`Recording.open`. ``record=False`` and crashed sessions without those
files report as empty lists and ``recorded=False`` instead of raising.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .recording import (
    Recording,
    manifest_is_recorded,
    snapshot_label,
    tail_lines,
)
from .session_schema import FRAME_DIFFS_FILE, TIMELINE_FILE

_APP_LINE = re.compile(r"^\[app\]\s+app=(\S+)")

# Every key returned by ``summarize_session`` in order. ``frames`` carries the
# absolute frame PNG paths needed by the visual evidence commands; it is part
# of the summary contract even though the CLI JSON keeps the shorter ticket 02
# field list.
SUMMARY_FIELDS = (
    "session_id",
    "session_dir",
    "status",
    "mode",
    "display",
    "frame_count",
    "record_changed_only",
    "requested_app",
    "effective_app",
    "snapshots",
    "frames",
    "marks",
    "inputs",
    "frame_diffs",
    "log_tail",
    "recorded",
    "error",
)

# Fields the CLI adds to its four original JSON fields. Kept next to
# ``SUMMARY_FIELDS`` so the two entry points cannot drift.
CLI_EVIDENCE_FIELDS = (
    "session_dir",
    "status",
    "display",
    "frame_count",
    "requested_app",
    "effective_app",
    "snapshots",
    "marks",
    "log_tail",
)


def summarize_session(
    session: str | Path, log_tail_lines: int = 20
) -> dict[str, Any]:
    """Return the stable evidence summary for one session directory.

    ``session`` is a session directory or its ``manifest.json``. The result
    contains only evidence; it never judges the picture.
    """
    recording = Recording.open(session)
    session_dir = recording.path.resolve()
    manifest = recording.manifest
    log_text = recording.log()

    timeline_available = (session_dir / TIMELINE_FILE).is_file()
    timeline = recording.timeline() if timeline_available else []
    diffs_available = (session_dir / FRAME_DIFFS_FILE).is_file()
    frame_diffs = recording.frame_diffs() if diffs_available else []

    values = {
        "session_id": manifest["id"],
        "session_dir": str(session_dir),
        "status": manifest["status"],
        "mode": manifest.get("mode"),
        "display": manifest.get("display"),
        "frame_count": manifest["frame_count"],
        "record_changed_only": bool(manifest.get("record_changed_only", False)),
        "requested_app": manifest.get("app"),
        "effective_app": _effective_app(log_text),
        "snapshots": _snapshots(session_dir, timeline, recording.snapshots),
        "frames": [str(path.resolve()) for path in recording.frames],
        "marks": [dict(row) for row in timeline if row["type"] == "mark"],
        "inputs": [dict(row) for row in timeline if row["type"] == "input"],
        "frame_diffs": [dict(row) for row in frame_diffs],
        "log_tail": tail_lines(log_text, log_tail_lines),
        "recorded": manifest_is_recorded(manifest),
        "error": manifest.get("error"),
    }
    return {field: values[field] for field in SUMMARY_FIELDS}


def _effective_app(log_text: str) -> str | None:
    """The last ``[app] app=NAME`` line, or ``None`` when the log has none."""
    found: str | None = None
    for line in log_text.splitlines():
        match = _APP_LINE.match(line)
        if match is not None:
            found = match.group(1)
    return found


def _snapshots(
    session_dir: Path,
    timeline: list[dict[str, Any]],
    files: list[Path],
) -> list[dict[str, Any]]:
    """Snapshot label plus absolute path, from timeline rows and stray PNGs."""
    snapshots: list[dict[str, Any]] = []
    referenced: set[Path] = set()
    for row in timeline:
        if row["type"] != "snapshot":
            continue
        relative = row.get("file")
        if not isinstance(relative, str):
            continue
        path = (session_dir / relative).resolve()
        referenced.add(path)
        snapshots.append({"label": row.get("label"), "path": str(path)})
    for file in files:
        path = file.resolve()
        if path in referenced:
            continue
        snapshots.append({"label": snapshot_label(file), "path": str(path)})
    return snapshots


__all__ = ["CLI_EVIDENCE_FIELDS", "SUMMARY_FIELDS", "summarize_session"]
