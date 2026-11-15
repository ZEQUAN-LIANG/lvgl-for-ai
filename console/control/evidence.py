"""The ``lvgl-verify-loop-session-index-v1`` query plan.

``session_index`` is the single read-only entry point shared by the session
report tool and the CLI JSON output. It returns counts, addresses and next
steps, not the full timeline: each raw file keeps its size and row count so a
reader can decide whether to open it. The index never starts an engine or the
web server and never judges the picture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import paths
from . import session_schema
from .anchors import diff_rows, read_rows, timeline_rows
from .recording import Recording, snapshot_label, tail_lines

INDEX_SCHEMA = "lvgl-verify-loop-session-index-v1"
_APP_LINE = re.compile(r"^\[app\]\s+app=(\S+)")

INDEX_FIELDS = (
    "schema",
    "session_id",
    "session_dir",
    "status",
    "mode",
    "display",
    "frame_count",
    "recorded",
    "record_changed_only",
    "requested_app",
    "effective_app",
    "truncated",
    "log_truncated",
    "build",
    "lvgl",
    "counts",
    "inputs",
    "raw_files",
    "timeline",
    "diffs",
    "frames",
    "marks",
    "snapshots",
    "clicks",
    "annotations",
    "whiteboards",
    "error",
    "log_tail",
    "next_reads",
)

DEFAULT_LOG_TAIL = 10
COMPACT_NOTE_CHARS = 100
NOTE_TEXT_CHARS = 200
INDEX_SNAPSHOT_ITEMS = 5


def session_index(
    session: str | Path,
    log_tail_lines: int = DEFAULT_LOG_TAIL,
    *,
    compact: bool = False,
) -> dict[str, Any]:
    recording = Recording.open(session)
    root = recording.path.resolve()
    manifest = recording.manifest
    log_text = recording.log()
    degraded = manifest.get("status") in ("crash", "harness_error")
    rows = timeline_rows(recording, tolerant=degraded)
    diffs = diff_rows(recording, tolerant=degraded)

    frames = _frame_rows(recording, root, rows)
    snapshots = _snapshots(root, rows, recording.snapshots)
    marks = [
        {
            "id": row.get("id"),
            "frame_no": row.get("frame_no"),
            "t_ms": row.get("t_ms"),
        }
        for row in rows
        if row.get("type") == "mark"
    ]
    clicks, drags = _clicks(root, rows)
    inputs = [row for row in rows if row.get("type") == "input"]
    waits = sum(1 for row in rows if row.get("type") == "wait")
    annotations = _annotations(root, compact)
    whiteboards = _whiteboards(root)
    end = _end_row(rows)
    last_frame = frames[-1] if frames else None

    values: dict[str, Any] = {
        "schema": INDEX_SCHEMA,
        "session_id": manifest["id"],
        "session_dir": str(root),
        "status": manifest["status"],
        "mode": manifest.get("mode"),
        "display": manifest.get("display"),
        "frame_count": manifest["frame_count"],
        "recorded": session_schema.session_is_recorded(manifest, root),
        "record_changed_only": bool(
            manifest.get("record_changed_only", False)
        ),
        "requested_app": manifest.get("app"),
        "effective_app": _effective_app(log_text),
        "truncated": bool(manifest.get("truncated", False)),
        "log_truncated": bool(manifest.get("log_truncated", False)),
        "build": manifest.get("build"),
        "lvgl": manifest.get("lvgl"),
        "counts": {
            "inputs": len(inputs),
            "waits": waits,
            "marks": len(marks),
            "snapshots": len(snapshots),
            "clicks": len(clicks),
            "drags": drags,
            "annotations": annotations["count"],
            "whiteboards": whiteboards["count"],
            "checks": _checks(manifest),
        },
        "inputs": {
            "hit_named": sum(
                1
                for row in inputs
                if isinstance(row.get("hit"), str) and row.get("hit")
            ),
            "hit_empty": sum(
                1
                for row in inputs
                if not isinstance(row.get("hit"), str) or not row.get("hit")
            ),
        },
        "raw_files": _raw_files(root, rows, diffs, degraded),
        "timeline": _timeline(frames, end),
        "diffs": _diffs(root, diffs, compact),
        "frames": {
            "count": len(frames),
            "dir": session_schema.FRAMES_DIR,
            "last": None if last_frame is None else last_frame["file"],
            "last_t_ms": None if last_frame is None else last_frame["t_ms"],
            "last_snapshot": snapshots[-1]["path"] if snapshots else None,
        },
        "marks": [] if compact else marks,
        "snapshots": _snapshots_view(snapshots, compact),
        "clicks": [] if compact else clicks,
        "annotations": annotations,
        "whiteboards": whiteboards,
        "error": manifest.get("error"),
        "log_tail": tail_lines(
            log_text,
            3 if compact else max(0, log_tail_lines),
        ),
    }
    values["next_reads"] = _next_reads(root, values, compact)
    return {field: values[field] for field in INDEX_FIELDS}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _frame_rows(
    recording: Recording, root: Path, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for view in recording.frame_views():
        file = view.get("file")
        frame_no = view.get("frame_no")
        if not isinstance(file, str) or not _is_int(frame_no):
            continue
        t_ms = view.get("t_ms")
        result.append(
            {
                "frame_no": frame_no,
                "t_ms": t_ms if _is_int(t_ms) else 0,
                "file": file,
                "path": str((root / file).resolve()),
            }
        )
    if result:
        return result
    for row in rows:
        if row.get("type") != "frame":
            continue
        file = row.get("file")
        frame_no = row.get("frame_no")
        t_ms = row.get("t_ms")
        if not isinstance(file, str) or not _is_int(frame_no):
            continue
        result.append(
            {
                "frame_no": frame_no,
                "t_ms": t_ms if _is_int(t_ms) else 0,
                "file": file,
                "path": str((root / file).resolve()),
            }
        )
    return result


def _evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if row.get("type") not in ("frame", "snapshot"):
            continue
        file = row.get("file")
        t_ms = row.get("t_ms")
        if not isinstance(file, str) or not _is_int(t_ms):
            continue
        result.append(
            {
                "row_index": index,
                "kind": row.get("type"),
                "frame_no": row.get("frame_no"),
                "t_ms": t_ms,
                "file": file,
            }
        )
    return result


def _last_at_or_before(
    evidence: list[dict[str, Any]], index: int
) -> dict[str, Any] | None:
    found = None
    for item in evidence:
        if item["row_index"] > index:
            break
        found = item
    return found


def _first_after(
    evidence: list[dict[str, Any]], index: int
) -> dict[str, Any] | None:
    for item in evidence:
        if item["row_index"] > index:
            return item
    return None


def _clicks(
    root: Path, rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    evidence = _evidence(rows)
    clicks: list[dict[str, Any]] = []
    drags = 0
    pending: dict[str, Any] | None = None
    for index, row in enumerate(rows):
        if row.get("type") != "input" or row.get("device") != "pointer":
            continue
        action = row.get("action")
        if action == "down":
            pending = {"index": index, "row": row, "moves": 0}
        elif action == "move" and pending is not None:
            pending["moves"] += 1
        elif action == "up":
            if pending is None:
                continue
            down = pending["row"]
            if pending["moves"]:
                drags += 1
            else:
                before = _last_at_or_before(evidence, pending["index"])
                after = _first_after(evidence, index)
                clicks.append(
                    {
                        "seq_down": down.get("seq"),
                        "seq_up": row.get("seq"),
                        "t_ms_down": down.get("t_ms"),
                        "t_ms_up": row.get("t_ms"),
                        "x": down.get("x"),
                        "y": down.get("y"),
                        "hit": down.get("hit"),
                        "hit_class": down.get("hit_class"),
                        "moves": 0,
                        "frame_before": (
                            None if before is None else before.get("frame_no")
                        ),
                        "t_ms_after": (
                            None if after is None else after.get("t_ms")
                        ),
                        "frame_after": (
                            None if after is None else after.get("frame_no")
                        ),
                    }
                )
            pending = None
    return clicks, drags


def _snapshots(
    root: Path, rows: list[dict[str, Any]], files: list[Path]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    referenced: set[Path] = set()
    for row in rows:
        if row.get("type") != "snapshot":
            continue
        file = row.get("file")
        if not isinstance(file, str):
            continue
        path = (root / file).resolve()
        referenced.add(path)
        items.append(
            {
                "label": row.get("label"),
                "frame_no": row.get("frame_no"),
                "t_ms": row.get("t_ms"),
                "path": file,
            }
        )
    for file in files:
        path = file.resolve()
        if path in referenced:
            continue
        items.append(
            {
                "label": snapshot_label(file),
                "frame_no": None,
                "t_ms": None,
                "path": path.relative_to(root).as_posix(),
            }
        )
    return items


def _snapshots_view(
    items: list[dict[str, Any]], compact: bool
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "count": len(items),
        "dir": session_schema.SNAPSHOTS_DIR,
        "last": items[-1]["path"] if items else None,
    }
    if not compact:
        view["items"] = items[-INDEX_SNAPSHOT_ITEMS:]
    return view


def _timeline(
    frames: list[dict[str, Any]], end: dict[str, Any] | None
) -> dict[str, Any]:
    first = frames[0] if frames else None
    last = frames[-1] if frames else None
    return {
        "first_frame_no": None if first is None else first["frame_no"],
        "last_frame_no": None if last is None else last["frame_no"],
        "first_t_ms": None if first is None else first["t_ms"],
        "last_frame_t_ms": None if last is None else last["t_ms"],
        "end": end,
    }


def _end_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("type") != "end":
            continue
        return {
            "t_ms": row.get("t_ms"),
            "frame_count": row.get("frame_count"),
            "truncated": bool(row.get("truncated", False)),
        }
    return None


def _checks(manifest: dict[str, Any]) -> dict[str, int]:
    checks = manifest.get("checks")
    if not isinstance(checks, list):
        return {"total": 0, "failed": 0}
    failed = sum(
        1
        for check in checks
        if isinstance(check, dict) and check.get("ok") is False
    )
    return {"total": len(checks), "failed": failed}


def _raw_files(
    root: Path,
    rows: list[dict[str, Any]],
    diffs: list[dict[str, Any]],
    tolerant: bool = False,
) -> dict[str, Any]:
    files: dict[str, Any] = {}
    entries = (
        (session_schema.TIMELINE_FILE, "timeline", len(rows)),
        (session_schema.FRAME_DIFFS_FILE, "frame_diffs", len(diffs)),
        (session_schema.MANIFEST_FILE, "manifest", None),
        (session_schema.ENGINE_LOG_FILE, "engine_log", None),
        (session_schema.BUILD_LOG_FILE, "build_log", None),
        (session_schema.REFERENCE_DIFFS_FILE, "reference_diffs", None),
    )
    for filename, key, count in entries:
        path = root / filename
        if not path.is_file():
            continue
        entry: dict[str, Any] = {
            "path": filename,
            "bytes": path.stat().st_size,
        }
        if count is not None:
            entry["rows"] = count
        elif key == "reference_diffs":
            entry["rows"] = len(read_rows(path, tolerant=tolerant))
        files[key] = entry
    return files


def _diffs(
    root: Path, rows: list[dict[str, Any]], compact: bool
) -> dict[str, Any]:
    changed = [row for row in rows if _positive(row.get("changed_px"))]
    threshold = 10
    for row in rows:
        value = row.get("threshold")
        if _is_int(value):
            threshold = value
            break
    top = sorted(
        rows,
        key=lambda row: (
            row.get("changed_px") if _is_int(row.get("changed_px")) else 0
        ),
        reverse=True,
    )[:3]
    result: dict[str, Any] = {
        "file": session_schema.FRAME_DIFFS_FILE,
        "rows": len(rows),
        "changed_rows": len(changed),
        "threshold": threshold,
        "max_changed_ratio": max(
            (
                row.get("changed_ratio")
                for row in changed
                if isinstance(row.get("changed_ratio"), (int, float))
            ),
            default=None,
        ),
    }
    if not compact:
        result["top"] = [
            {
                "frame_no": row.get("frame_no"),
                "t_ms": row.get("t_ms"),
                "bbox": row.get("bbox"),
                "changed_px": row.get("changed_px"),
                "changed_ratio": row.get("changed_ratio"),
                "image": _frame_file(row.get("frame_no")),
            }
            for row in top
            if _positive(row.get("changed_px"))
        ]
    return result


def _positive(value: Any) -> bool:
    return _is_int(value) and value > 0


def _frame_file(frame_no: Any) -> str | None:
    if not _is_int(frame_no):
        return None
    return f"{session_schema.FRAMES_DIR}/{frame_no:06d}.png"


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _abs_image(root: Path, relative: Any) -> str | None:
    if not isinstance(relative, str) or not relative:
        return None
    try:
        path = (root / relative).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return None
    return str(path) if path.is_file() else None


def _region_images(root: Path, regions: Any) -> list[str]:
    images: list[str] = []
    if not isinstance(regions, list):
        return images
    for region in regions:
        if not isinstance(region, dict):
            continue
        image = _abs_image(root, region.get("image"))
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


def _frame_images(root: Path, frames: list[Any]) -> list[str]:
    directory = root / session_schema.FRAMES_DIR
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


def _truncate(text: Any, limit: int) -> Any:
    if not isinstance(text, str):
        return text
    return text if len(text) <= limit else text[:limit]


def _annotations(root: Path, compact: bool) -> dict[str, Any]:
    path = root / session_schema.ANNOTATIONS_FILE
    if not path.is_file():
        return {"count": 0, "notes": []}
    data = _read_json_object(path)
    if data is None or not isinstance(data.get("notes"), list):
        return {"count": 0, "notes": [], "error": "annotations_unreadable"}
    limit = COMPACT_NOTE_CHARS if compact else NOTE_TEXT_CHARS
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
                images.extend(_region_images(root, anchor.get("regions")))
                boxes.extend(_region_boxes(anchor.get("regions"), frame_no))
                image = _abs_image(root, anchor.get("annotated"))
                if image is not None:
                    annotated.append(image)
                for region in anchor.get("regions") or []:
                    if not isinstance(region, dict):
                        continue
                    image = _abs_image(root, region.get("annotated"))
                    if image is not None:
                        annotated_regions.append(image)
        else:
            frame_no = note.get("frame_no")
            frames.append(frame_no)
            images.extend(_region_images(root, note.get("regions")))
            boxes.extend(_region_boxes(note.get("regions"), frame_no))
        anchored = list(dict.fromkeys(frames))
        item: dict[str, Any] = {
            "id": note.get("id"),
            "author": note.get("author"),
            "source": note.get("source"),
            "text": _truncate(note.get("text"), limit),
            "feedback_anchor": note.get("feedback_anchor"),
            "frame_start": note.get("frame_start", note.get("frame_no")),
            "frame_end": note.get("frame_end", note.get("frame_no")),
            "anchor_frames": anchored,
            "tags": note.get("tags")
            if isinstance(note.get("tags"), list)
            else [],
            "frame_images": _frame_images(root, anchored),
            "annotated": annotated,
            "annotated_regions": annotated_regions,
            "regions": boxes,
            "images": images,
        }
        if "transcribed_by" in note:
            item["transcribed_by"] = note.get("transcribed_by")
        if compact:
            for key in (
                "frame_images",
                "annotated",
                "annotated_regions",
                "images",
            ):
                item.pop(key, None)
        notes.append(item)
    return {"count": len(notes), "notes": notes}


def _whiteboards(root: Path) -> dict[str, Any]:
    path = root / session_schema.WHITEBOARDS_FILE
    if not path.is_file():
        return {"count": 0, "pending": 0, "items": []}
    data = _read_json_object(path)
    if data is None or not isinstance(data.get("whiteboards"), list):
        return {
            "count": 0,
            "pending": 0,
            "items": [],
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
                "scope": (
                    item.get("scope")
                    if isinstance(item.get("scope"), dict)
                    else {}
                ),
                "text": item.get("text"),
                "labels": [
                    label for label in labels or [] if isinstance(label, str)
                ]
                if isinstance(labels, list)
                else [],
                "image": _abs_image(root, item.get("image")),
                "confirmed": item.get("confirmed") is True,
            }
        )
    pending = sum(1 for item in items if not item["confirmed"])
    return {"count": len(items), "pending": pending, "items": items}


def _effective_app(log_text: str) -> str | None:
    found: str | None = None
    for line in log_text.splitlines():
        match = _APP_LINE.match(line)
        if match is not None:
            found = match.group(1)
    return found


def _session_command_path(root: Path) -> str:
    try:
        root.resolve().relative_to(paths.DEFAULT_SESSIONS_ROOT.resolve())
    except ValueError:
        return str(root)
    return f"user/sessions/{root.name}"


def _next_reads(
    root: Path, values: dict[str, Any], compact: bool
) -> list[dict[str, Any]]:
    session = _session_command_path(root)
    reads: list[dict[str, Any]] = []
    raw = values["raw_files"]
    annotations = values["annotations"]
    if annotations["count"]:
        reads.append(
            {
                "why": "human feedback is recorded in this session",
                "command": (
                    f"python -I console/entrypoints/session_report.py notes {session} "
                    "--resolve"
                ),
                "est_bytes": 1200,
            }
        )
    clicks = values["clicks"]
    if clicks:
        click = clicks[0]
        reads.append(
            {
                "why": "first click result frame",
                "command": (
                    f"python -I console/entrypoints/session_report.py resolve {session} "
                    f"--click {click['seq_down']}:{click['seq_up']}"
                ),
                "est_bytes": 400,
            }
        )
        reads.append(
            {
                "why": "bounded input, hit and diff join around that click",
                "command": (
                    f"python -I console/entrypoints/session_report.py context {session} "
                    f"--click {click['seq_down']}:{click['seq_up']}"
                ),
                "est_bytes": 3500,
            }
        )
    if values["diffs"]["changed_rows"] and "frame_diffs" in raw:
        reads.append(
            {
                "why": "largest changed regions",
                "command": (
                    f"python -I console/entrypoints/session_report.py diffs {session} --top 5"
                ),
                "est_bytes": 3000,
            }
        )
    if "timeline" in raw:
        reads.append(
            {
                "why": "bounded input / wait / mark rows",
                "command": (
                    f"python -I console/entrypoints/session_report.py timeline {session}"
                ),
                "est_bytes": 4000,
            }
        )
    return reads[:1] if compact else reads
