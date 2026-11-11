"""Session evidence summary built on top of :class:`Recording`.

``summarize_session`` is the single read-only summary entry point shared by
the session report tool and, later, the CLI JSON output. It never starts an
engine or the web server.

``manifest.json`` and ``engine.log`` are required evidence: a missing one is an
error. ``timeline.ndjson`` and ``frame_diffs.ndjson`` are optional because
``record=False`` sessions and crashed sessions may not have them; they report
as empty lists and set ``recorded`` to ``False`` instead of raising.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .recording import Recording
from .session_schema import FRAME_DIFFS_FILE, TIMELINE_FILE

_APP_LINE = re.compile(r"^\[app\]\s+app=(\S+)")
_SNAPSHOT_NUMBER_PREFIX = re.compile(r"^\d+_")


def summarize_session(
    session: str | Path, log_tail_lines: int = 20
) -> dict[str, Any]:
    """Return the stable evidence summary for one session directory.

    ``session`` is a session directory or its ``manifest.json``. The result
    contains only evidence; it never judges the picture.
    """
    recording = Recording(session)
    session_dir = recording.path.resolve()
    manifest = recording.manifest
    log_text = recording.log()

    timeline_path = session_dir / TIMELINE_FILE
    timeline_available = timeline_path.is_file()
    timeline = recording.timeline() if timeline_available else []

    diffs_path = session_dir / FRAME_DIFFS_FILE
    diffs_available = diffs_path.is_file()
    frame_diffs = recording.frame_diffs() if diffs_available else []

    return {
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
        "log_tail": _log_tail(log_text, log_tail_lines),
        "recorded": timeline_available or diffs_available,
        "error": manifest.get("error"),
    }


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
        snapshots.append({"label": _snapshot_label(file), "path": str(path)})
    return snapshots


def _snapshot_label(path: Path) -> str:
    return _SNAPSHOT_NUMBER_PREFIX.sub("", path.stem)


def _log_tail(log_text: str, log_tail_lines: int) -> list[str]:
    if log_tail_lines <= 0:
        return []
    return log_text.splitlines()[-log_tail_lines:]


__all__ = ["summarize_session"]
