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

import json
import re
from pathlib import Path
from typing import Any

from . import session_schema
from .recording import (
    Recording,
    manifest_is_recorded,
    snapshot_label,
    tail_lines,
)

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
    "annotations",
    "whiteboards",
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
    "annotations",
    "whiteboards",
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

    timeline_available = (
        session_dir / session_schema.TIMELINE_FILE
    ).is_file()
    timeline = recording.timeline() if timeline_available else []
    diffs_available = (
        session_dir / session_schema.FRAME_DIFFS_FILE
    ).is_file()
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
        "annotations": _annotations_summary(session_dir),
        "whiteboards": _whiteboards_summary(session_dir),
        "marks": [dict(row) for row in timeline if row["type"] == "mark"],
        "inputs": [dict(row) for row in timeline if row["type"] == "input"],
        "frame_diffs": [dict(row) for row in frame_diffs],
        "log_tail": tail_lines(log_text, log_tail_lines),
        "recorded": manifest_is_recorded(manifest),
        "error": manifest.get("error"),
    }
    return {field: values[field] for field in SUMMARY_FIELDS}


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _abs_image(session_dir: Path, relative: Any) -> str | None:
    """Absolute path of one evidence image, or None when it escapes the session."""
    if not isinstance(relative, str) or not relative:
        return None
    try:
        path = (session_dir / relative).resolve()
        path.relative_to(session_dir.resolve())
    except (OSError, ValueError):
        return None
    return str(path) if path.is_file() else None


def _region_images(session_dir: Path, regions: Any) -> list[str]:
    images: list[str] = []
    if not isinstance(regions, list):
        return images
    for region in regions:
        if not isinstance(region, dict):
            continue
        image = _abs_image(session_dir, region.get("image"))
        if image is not None:
            images.append(image)
    return images


def _region_boxes(regions: Any, frame_no: Any) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    if not isinstance(regions, list):
        return boxes
    for region in regions:
        if not isinstance(region, dict):
            continue
        boxes.append(
            {
                "frame_no": frame_no,
                "x": region.get("x"),
                "y": region.get("y"),
                "w": region.get("w"),
                "h": region.get("h"),
                "image": region.get("image"),
                "annotated": region.get("annotated"),
            }
        )
    return boxes


def _frame_images(session_dir: Path, frames: list[Any]) -> list[str]:
    """Whole-frame PNG paths; an agent crops the boxes itself."""
    directory = session_dir / session_schema.FRAMES_DIR
    if not directory.is_dir():
        return []
    by_number: dict[int, str] = {}
    for path in directory.glob("*.png"):
        if path.stem.isdigit():
            by_number[int(path.stem)] = str(path.resolve())
    images: list[str] = []
    for frame_no in frames:
        if isinstance(frame_no, int) and frame_no in by_number:
            images.append(by_number[frame_no])
    return images


def _annotations_summary(session_dir: Path) -> dict[str, Any]:
    """Notes as an index an agent can read before opening the crop PNGs."""
    path = session_dir / session_schema.ANNOTATIONS_FILE
    if not path.is_file():
        return {"count": 0, "notes": []}
    data = _read_json_object(path)
    if data is None or not isinstance(data.get("notes"), list):
        return {
            "count": 0, "notes": [], "error": "annotations_unreadable"
        }
    notes: list[dict[str, Any]] = []
    for note in data["notes"]:
        if not isinstance(note, dict):
            continue
        frames: list[Any] = []
        images: list[str] = []
        annotated: list[str] = []
        annotated_regions: list[str] = []
        boxes: list[dict[str, Any]] = []
        anchors = note.get("anchors")
        if isinstance(anchors, list) and anchors:
            for anchor in anchors:
                if not isinstance(anchor, dict):
                    continue
                frame_no = anchor.get("frame_no")
                frames.append(frame_no)
                images.extend(_region_images(session_dir, anchor.get("regions")))
                boxes.extend(_region_boxes(anchor.get("regions"), frame_no))
                image = _abs_image(session_dir, anchor.get("annotated"))
                if image is not None:
                    annotated.append(image)
                for region in anchor.get("regions") or []:
                    if not isinstance(region, dict):
                        continue
                    image = _abs_image(session_dir, region.get("annotated"))
                    if image is not None:
                        annotated_regions.append(image)
        else:
            frame_no = note.get("frame_no")
            frames.append(frame_no)
            images.extend(_region_images(session_dir, note.get("regions")))
            boxes.extend(_region_boxes(note.get("regions"), frame_no))
        anchored = list(dict.fromkeys(frames))
        notes.append(
            {
                "id": note.get("id"),
                "frame_start": note.get("frame_start", note.get("frame_no")),
                "frame_end": note.get("frame_end", note.get("frame_no")),
                "anchor_frames": anchored,
                "text": note.get("text"),
                "tags": note.get("tags") if isinstance(note.get("tags"), list) else [],
                "frame_images": _frame_images(session_dir, anchored),
                "annotated": annotated,
                "annotated_regions": annotated_regions,
                "regions": boxes,
                "images": images,
            }
        )
    return {"count": len(notes), "notes": notes}


def _whiteboards_summary(session_dir: Path) -> dict[str, Any]:
    """Whiteboards with the text and labels an agent can execute against."""
    path = session_dir / session_schema.WHITEBOARDS_FILE
    if not path.is_file():
        return {"count": 0, "pending": 0, "items": []}
    data = _read_json_object(path)
    if data is None or not isinstance(data.get("whiteboards"), list):
        return {
            "count": 0, "pending": 0, "items": [],
            "error": "whiteboards_unreadable",
        }
    items: list[dict[str, Any]] = []
    for item in data["whiteboards"]:
        if not isinstance(item, dict):
            continue
        labels = item.get("labels")
        items.append(
            {
                "id": item.get("id"),
                "scope": item.get("scope") if isinstance(item.get("scope"), dict) else {},
                "text": item.get("text"),
                "labels": [
                    label for label in labels or [] if isinstance(label, str)
                ] if isinstance(labels, list) else [],
                "image": _abs_image(session_dir, item.get("image")),
                "confirmed": item.get("confirmed") is True,
            }
        )
    pending = sum(1 for item in items if not item["confirmed"])
    return {"count": len(items), "pending": pending, "items": items}


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
