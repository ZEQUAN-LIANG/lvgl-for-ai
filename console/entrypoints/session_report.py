#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CONSOLE_ROOT = Path(__file__).resolve().parent.parent
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

import paths
from control import session_index
from control import session_schema
from control.anchors import (
    diff_rows,
    resolve_anchor,
    timeline_rows,
)
from control.evidence import DEFAULT_LOG_TAIL
from control.notes import human_notes
from control.recording import Recording, snapshot_label
from png_codec import (
    DEFAULT_CONTACT_COLUMNS,
    DEFAULT_CONTACT_TILE_HEIGHT,
    DEFAULT_CONTACT_TILE_WIDTH,
    PngError,
    Region,
    build_contact_sheet,
    compare_png,
    crop_png,
    read_pixel,
    read_png_header,
)

EXIT_OK = 0
EXIT_ERROR = 2
QUERY_COMMANDS = (
    "timeline",
    "diffs",
    "frames",
    "notes",
    "resolve",
    "context",
    "feedback",
)
VISUAL_COMMANDS = ("crop", "contact-sheet", "pixel", "compare")
DEFAULT_QUERY_LIMIT = 20
DEFAULT_DIFF_TOP = 5
DEFAULT_FRAME_LAST = 3
DEFAULT_WINDOW_MS = 200
DEFAULT_FEEDBACK_MAX = 8
LARGE_OFFSET_MS = 500


def _log_tail_lines(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "log tail must be a non-negative integer"
        ) from exc
    if number < 0:
        raise argparse.ArgumentTypeError(
            "log tail must be a non-negative integer"
        )
    return number


def _region(value: str) -> Region:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected X,Y,W,H")
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected X,Y,W,H as integers"
        ) from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("region width and height must be > 0")
    return Region(x, y, width, height)


def _coordinate(value: str) -> tuple[int, int]:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected X,Y")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected X,Y as integers") from exc


def _tile_size(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected WxH")
    try:
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected WxH as integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("tile width and height must be > 0")
    return width, height


def _seq_pair(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected SEQ_DOWN:SEQ_UP")
    try:
        down, up = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected SEQ_DOWN:SEQ_UP as integers"
        ) from exc
    if down < 1 or up < 1:
        raise argparse.ArgumentTypeError("sequence numbers must be >= 1")
    return down, up


def _image_path(root: Path, relative: Any) -> str | None:
    if not isinstance(relative, str) or not relative:
        return None
    path = root / relative
    return str(path.resolve()) if path.is_file() else None


def _row_span(row: dict[str, Any]) -> tuple[int, int]:
    start = row.get("t_ms_start", row.get("t_ms"))
    end = row.get("t_ms_end", row.get("t_ms", start))
    if isinstance(start, bool) or not isinstance(start, int):
        start = 0
    if isinstance(end, bool) or not isinstance(end, int):
        end = start
    return start, max(start, end)


def _bounded(
    rows: list[dict[str, Any]], limit: int
) -> tuple[list[dict[str, Any]], int, bool]:
    total = len(rows)
    returned = rows[: max(0, limit)]
    return returned, total, total > len(returned)


def _emit(payload: dict[str, Any], args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    else:
        print(format_query(payload))
    return EXIT_OK


def _query_parser(name: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"session_report.py {name}", description=description
    )
    parser.add_argument("session", metavar="SESSION", help="session directory")
    parser.add_argument(
        "--json", action="store_true", help="print one JSON object on stdout"
    )
    return parser


def _build_timeline_parser() -> argparse.ArgumentParser:
    parser = _query_parser(
        "timeline",
        "Bounded input / wait / mark / snapshot rows; frame rows are excluded "
        "unless --type frame is given.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_QUERY_LIMIT,
        metavar="N",
        help=f"maximum rows (default: {DEFAULT_QUERY_LIMIT})",
    )
    parser.add_argument("--around-t", type=int, metavar="T_MS")
    parser.add_argument("--before-t", type=int, metavar="T_MS")
    parser.add_argument("--after-t", type=int, metavar="T_MS")
    parser.add_argument("--device")
    parser.add_argument("--type")
    parser.add_argument("--action")
    parser.add_argument("--hit")
    return parser


def _run_timeline(argv: list[str]) -> int:
    args = _build_timeline_parser().parse_args(argv)
    try:
        recording = Recording.open(args.session)
        rows = timeline_rows(recording)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    selected: list[dict[str, Any]] = []
    for row in rows:
        row_type = row.get("type")
        if args.type is not None:
            if row_type != args.type:
                continue
        elif row_type == "frame":
            continue
        if args.device is not None and row.get("device") != args.device:
            continue
        if args.action is not None and row.get("action") != args.action:
            continue
        if args.hit is not None and row.get("hit") != args.hit:
            continue
        start, end = _row_span(row)
        if args.before_t is not None and start > args.before_t:
            continue
        if args.after_t is not None and end < args.after_t:
            continue
        selected.append(row)
    if args.around_t is not None:
        selected.sort(key=lambda row: abs(_row_span(row)[0] - args.around_t))
        rows_out, total, truncated = _bounded(selected, args.limit)
        rows_out.sort(key=lambda row: _row_span(row)[0])
    else:
        rows_out, total, truncated = _bounded(selected, args.limit)
    return _emit(
        {
            "schema": "lvgl-verify-loop-timeline-query-v1",
            "session_dir": str(recording.path.resolve()),
            "total": total,
            "returned": len(rows_out),
            "truncated": truncated,
            "rows": rows_out,
        },
        args,
    )


def _build_diffs_parser() -> argparse.ArgumentParser:
    parser = _query_parser(
        "diffs", "Bounded changed regions with an absolute frame image."
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_DIFF_TOP,
        metavar="N",
        help=f"maximum rows (default: {DEFAULT_DIFF_TOP})",
    )
    parser.add_argument("--around-t", type=int, metavar="T_MS")
    parser.add_argument("--before-t", type=int, metavar="T_MS")
    parser.add_argument("--after-t", type=int, metavar="T_MS")
    parser.add_argument("--frame", type=int, metavar="N")
    parser.add_argument("--min-changed", type=int, default=0, metavar="N")
    parser.add_argument("--region", type=_region, metavar="X,Y,W,H")
    return parser


def _intersects(row: dict[str, Any], region: Region) -> bool:
    bbox = row.get("bbox")
    if not isinstance(bbox, dict):
        return False
    try:
        x = int(bbox["x"])
        y = int(bbox["y"])
        w = int(bbox["w"])
        h = int(bbox["h"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        x < region.x1
        and region.x < x + w
        and y < region.y1
        and region.y < y + h
    )


def _run_diffs(argv: list[str]) -> int:
    args = _build_diffs_parser().parse_args(argv)
    try:
        recording = Recording.open(args.session)
        rows = diff_rows(recording)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    root = recording.path.resolve()
    selected: list[dict[str, Any]] = []
    for row in rows:
        changed = row.get("changed_px")
        if not isinstance(changed, int) or isinstance(changed, bool):
            changed = 0
        if changed < args.min_changed:
            continue
        if args.frame is not None and row.get("frame_no") != args.frame:
            continue
        t_ms = row.get("t_ms")
        if args.after_t is not None and (
            not isinstance(t_ms, int) or t_ms < args.after_t
        ):
            continue
        if args.before_t is not None and (
            not isinstance(t_ms, int) or t_ms > args.before_t
        ):
            continue
        if args.region is not None and not _intersects(row, args.region):
            continue
        item = dict(row)
        item["image"] = _image_path(root, _frame_file(row.get("frame_no")))
        selected.append(item)
    if args.around_t is not None:
        selected.sort(
            key=lambda row: abs((row.get("t_ms") or 0) - args.around_t)
        )
    else:
        selected.sort(
            key=lambda row: (
                row.get("changed_px")
                if isinstance(row.get("changed_px"), int)
                else 0
            ),
            reverse=True,
        )
    rows_out, total, truncated = _bounded(selected, args.top)
    return _emit(
        {
            "schema": "lvgl-verify-loop-diffs-query-v1",
            "session_dir": str(root),
            "total": total,
            "returned": len(rows_out),
            "truncated": truncated,
            "rows": rows_out,
        },
        args,
    )


def _frame_file(frame_no: Any) -> str | None:
    if isinstance(frame_no, bool) or not isinstance(frame_no, int):
        return None
    return f"{session_schema.FRAMES_DIR}/{frame_no:06d}.png"


def _build_frames_parser() -> argparse.ArgumentParser:
    parser = _query_parser(
        "frames", "Bounded frame paths with t_ms and frame number."
    )
    parser.add_argument(
        "--last",
        type=int,
        default=DEFAULT_FRAME_LAST,
        metavar="N",
        help=f"maximum frames (default: {DEFAULT_FRAME_LAST})",
    )
    around = parser.add_mutually_exclusive_group()
    around.add_argument("--around-t", type=int, metavar="T_MS")
    around.add_argument("--around-frame", type=int, metavar="N")
    parser.add_argument(
        "--direction",
        choices=("before", "after", "nearest"),
        default="nearest",
    )
    return parser


def _run_frames(argv: list[str]) -> int:
    args = _build_frames_parser().parse_args(argv)
    try:
        recording = Recording.open(args.session)
        rows = timeline_rows(recording)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    root = recording.path.resolve()
    items: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") != "frame":
            continue
        frame_no = row.get("frame_no")
        file = row.get("file")
        if not isinstance(frame_no, int) or not isinstance(file, str):
            continue
        items.append(
            {
                "frame_no": frame_no,
                "t_ms": row.get("t_ms"),
                "image": str((root / file).resolve()),
            }
        )
    if not items:
        for path in recording.frames:
            items.append(
                {
                    "frame_no": int(path.stem)
                    if path.stem.isdigit()
                    else None,
                    "t_ms": None,
                    "image": str(path.resolve()),
                }
            )
    total = len(items)
    if args.around_t is not None:
        target = args.around_t
        if args.direction == "before":
            items = [item for item in items if (item["t_ms"] or 0) < target]
        elif args.direction == "after":
            items = [item for item in items if (item["t_ms"] or 0) > target]
        items.sort(key=lambda item: abs((item["t_ms"] or 0) - target))
        items = sorted(
            items[: max(0, args.last)], key=lambda item: item["t_ms"] or 0
        )
    elif args.around_frame is not None:
        target = args.around_frame
        if args.direction == "before":
            items = [
                item
                for item in items
                if item["frame_no"] is not None and item["frame_no"] < target
            ]
        elif args.direction == "after":
            items = [
                item
                for item in items
                if item["frame_no"] is not None and item["frame_no"] > target
            ]
        items.sort(key=lambda item: abs((item["frame_no"] or 0) - target))
        items = sorted(
            items[: max(0, args.last)], key=lambda item: item["frame_no"] or 0
        )
    else:
        items = items[-max(0, args.last) :]
    return _emit(
        {
            "schema": "lvgl-verify-loop-frames-query-v1",
            "session_dir": str(root),
            "total": total,
            "returned": len(items),
            "truncated": total > len(items),
            "rows": items,
        },
        args,
    )


def _document(root: Path) -> dict[str, Any]:
    path = root / session_schema.ANNOTATIONS_FILE
    if not path.is_file():
        return {"schema": session_schema.ANNOTATIONS_SCHEMA, "notes": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "schema": session_schema.ANNOTATIONS_SCHEMA,
            "notes": [],
            "error": "annotations_unreadable",
        }
    return (
        data
        if isinstance(data, dict)
        else {
            "schema": session_schema.ANNOTATIONS_SCHEMA,
            "notes": [],
            "error": "annotations_unreadable",
        }
    )


def _build_notes_parser() -> argparse.ArgumentParser:
    parser = _query_parser(
        "notes",
        "Human feedback notes, optionally resolved in another session.",
    )
    parser.add_argument("--author", default="human")
    parser.add_argument(
        "--resolve",
        nargs="?",
        const="",
        default=None,
        metavar="SESSION",
        help="resolve each anchor in SESSION (default: the same session)",
    )
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--limit", type=int, default=DEFAULT_QUERY_LIMIT)
    return parser


def _run_notes(argv: list[str]) -> int:
    args = _build_notes_parser().parse_args(argv)
    try:
        recording = Recording.open(args.session)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    root = recording.path.resolve()
    document = _document(root)
    notes = [
        note
        for note in document.get("notes") or []
        if isinstance(note, dict) and note.get("author") == args.author
    ]
    if args.latest:
        notes = notes[-1:]
    total = len(notes)
    notes = notes[: max(0, args.limit)]
    target = None
    if args.resolve is not None:
        try:
            target = Recording.open(args.resolve or args.session)
        except (OSError, ValueError) as exc:
            print(f"[session-report] {exc}", file=sys.stderr)
            return EXIT_ERROR
    items = [_note_item(recording, note, target) for note in notes]
    return _emit(
        {
            "schema": "lvgl-verify-loop-notes-query-v1",
            "session_dir": str(root),
            "total": total,
            "returned": len(items),
            "truncated": total > len(items),
            "notes": items,
        },
        args,
    )


def _note_item(
    recording: Recording,
    note: dict[str, Any],
    target: Recording | None,
) -> dict[str, Any]:
    root = recording.path.resolve()
    regions = []
    for region in note.get("regions") or []:
        if not isinstance(region, dict):
            continue
        item = {key: region.get(key) for key in ("x", "y", "w", "h")}
        item["image"] = _image_path(root, region.get("image"))
        regions.append(item)
    item = {
        "id": note.get("id"),
        "author": note.get("author"),
        "source": note.get("source"),
        "text": note.get("text"),
        "frame_no": note.get("frame_no"),
        "t_ms": note.get("t_ms"),
        "feedback_anchor": note.get("feedback_anchor"),
        "tags": note.get("tags") if isinstance(note.get("tags"), list) else [],
        "regions": regions,
    }
    anchor = note.get("feedback_anchor")
    if target is not None and isinstance(anchor, dict):
        item["resolved"] = resolve_anchor(target, anchor)
    return item


def _add_selector_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--note")
    group.add_argument("--click", type=_seq_pair, metavar="DOWN:UP")
    group.add_argument("--mark")
    group.add_argument("--input-seq", type=int)
    group.add_argument("--t-ms", type=int)
    group.add_argument("--frame", type=int)


def _build_resolve_parser() -> argparse.ArgumentParser:
    parser = _query_parser(
        "resolve",
        "Resolve one stable anchor to a frame or snapshot in row order.",
    )
    _add_selector_arguments(parser)
    parser.add_argument("--offset-ms", type=int, default=None)
    parser.add_argument("--at", choices=("event", "result"), default="result")
    return parser


def _run_resolve(argv: list[str]) -> int:
    args = _build_resolve_parser().parse_args(argv)
    try:
        recording = Recording.open(args.session)
        anchor, _note = _selector_anchor(args, recording)
        result = resolve_anchor(
            recording, anchor, at=args.at, offset_ms=args.offset_ms
        )
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    result["schema"] = "lvgl-verify-loop-resolve-v1"
    result["session_dir"] = str(recording.path.resolve())
    result["anchor"] = anchor
    return _emit(result, args)


def _selector_anchor(
    args: argparse.Namespace, recording: Recording
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if args.note is not None:
        note = _find_note(recording, args.note)
        anchor = note.get("feedback_anchor")
        if not isinstance(anchor, dict):
            raise ValueError(f"note {args.note} has no feedback_anchor")
        return anchor, note
    if args.click is not None:
        down, up = args.click
        return {"kind": "click", "seq_down": down, "seq_up": up}, None
    if args.mark is not None:
        return {"kind": "mark", "id": args.mark}, None
    if args.input_seq is not None:
        return {"kind": "input", "seq": args.input_seq}, None
    if args.t_ms is not None:
        return {"kind": "t_ms", "t_ms": args.t_ms}, None
    return {"kind": "frame", "frame_no": args.frame}, None


def _find_note(recording: Recording, note_id: str) -> dict[str, Any]:
    root = recording.path.resolve()
    for note in _document(root).get("notes") or []:
        if isinstance(note, dict) and note.get("id") == note_id:
            return note
    for child in sorted(
        root.parent.iterdir(), key=lambda path: path.name, reverse=True
    ):
        if child == root or not child.is_dir():
            continue
        if not (child / session_schema.MANIFEST_FILE).is_file():
            continue
        for note in _document(child).get("notes") or []:
            if isinstance(note, dict) and note.get("id") == note_id:
                return note
    raise ValueError(f"unknown note id: {note_id}")


def _build_context_parser() -> argparse.ArgumentParser:
    parser = _query_parser(
        "context",
        "One bounded input + hit + before/after frame + diff + note join.",
    )
    _add_selector_arguments(parser)
    parser.add_argument(
        "--window-ms", type=int, default=DEFAULT_WINDOW_MS, metavar="MS"
    )
    return parser


def _run_context(argv: list[str]) -> int:
    args = _build_context_parser().parse_args(argv)
    try:
        recording = Recording.open(args.session)
        anchor, note = _selector_anchor(args, recording)
        resolved = resolve_anchor(recording, anchor)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    root = recording.path.resolve()
    rows = timeline_rows(recording)
    diffs = diff_rows(recording)
    target_ms = resolved.get("resolved_t_ms")
    if target_ms is None:
        window_start = window_end = 0
    else:
        window_start = target_ms - max(0, args.window_ms)
        window_end = target_ms + max(0, args.window_ms)
    inputs = [
        row
        for row in rows
        if row.get("type") == "input"
        and window_start <= (row.get("t_ms") or 0) <= window_end
    ][:DEFAULT_QUERY_LIMIT]
    before = None
    after = None
    for row in rows:
        if row.get("type") != "frame":
            continue
        t_ms = row.get("t_ms")
        if not isinstance(t_ms, int):
            continue
        item = {
            "frame_no": row.get("frame_no"),
            "t_ms": t_ms,
            "image": _image_path(root, row.get("file")),
        }
        if t_ms <= window_start:
            before = item
        elif after is None and t_ms >= window_end:
            after = item
    window_diffs = []
    for row in diffs:
        t_ms = row.get("t_ms")
        if not isinstance(t_ms, int) or not (
            window_start <= t_ms <= window_end
        ):
            continue
        item = dict(row)
        item["image"] = _image_path(root, _frame_file(row.get("frame_no")))
        window_diffs.append(item)
    window_diffs = window_diffs[:10]
    notes = (
        [note]
        if note is not None
        else [
            item
            for item in _all_notes(root)
            if window_start <= (item.get("t_ms") or 0) <= window_end
        ][:5]
    )
    return _emit(
        {
            "schema": "lvgl-verify-loop-context-v1",
            "session_dir": str(root),
            "anchor": anchor,
            "resolved": resolved,
            "window": {
                "t_ms_start": window_start,
                "t_ms_end": window_end,
                "window_ms": max(0, args.window_ms),
            },
            "inputs": inputs,
            "frames": {"before": before, "after": after},
            "diffs": window_diffs,
            "notes": notes,
        },
        args,
    )


def _all_notes(root: Path) -> list[dict[str, Any]]:
    document = _document(root)
    return [
        note for note in document.get("notes") or [] if isinstance(note, dict)
    ]


def _build_feedback_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py feedback",
        description=(
            "Compare human feedback notes from one session against a new "
            "session. Outputs located / pixel_diff evidence, never a verdict."
        ),
    )
    parser.add_argument(
        "session",
        nargs="?",
        metavar="NOTES_SESSION",
        help="session holding the notes (default: newest other session)",
    )
    parser.add_argument(
        "--previous",
        required=True,
        metavar="NEW_SESSION",
        help="new session to locate the notes in",
    )
    parser.add_argument(
        "--max", type=int, default=DEFAULT_FEEDBACK_MAX, metavar="N"
    )
    parser.add_argument("--json", action="store_true")
    return parser


def _run_feedback(argv: list[str]) -> int:
    args = _build_feedback_parser().parse_args(argv)
    try:
        target = Recording.open(args.previous)
        source_path = args.session or _notes_session(
            target.path.resolve().parent, target.path.resolve().name
        )
        source = Recording.open(source_path)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    payload = _feedback_payload(source, target, max(0, args.max))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return EXIT_OK
    print(
        "[feedback] "
        f"{payload['located']}/{payload['total']} located | "
        f"{payload['notes_with_pixel_change']} note(s) with pixel change | "
        f"{payload['unmapped']} unmapped"
    )
    for item in payload["items"]:
        print(
            f"  {item['note_id']}: "
            + (
                f"frame {item.get('new_frame')} {item.get('relation')}"
                if item["located"]
                else "unmapped"
            )
        )
    return EXIT_OK


def _notes_session(root: Path, target: str) -> str:
    candidates = []
    for child in root.iterdir():
        if child.name == target or not child.is_dir():
            continue
        if not (child / session_schema.MANIFEST_FILE).is_file():
            continue
        try:
            recording = Recording.open(child)
        except (OSError, ValueError):
            continue
        if human_notes(recording):
            candidates.append(child)
    if not candidates:
        raise ValueError("no other session with human notes was found")
    return str(max(candidates, key=lambda path: path.name))


def _feedback_payload(
    source: Recording, target: Recording, maximum: int
) -> dict[str, Any]:
    notes = human_notes(source)[-maximum:] if maximum else []
    old_manifest = source.manifest
    new_manifest = target.manifest
    scenario_changed = _changed(
        old_manifest.get("scenario"), new_manifest.get("scenario")
    )
    source_changed = _changed(
        old_manifest.get("source_digest"), new_manifest.get("source_digest")
    )
    source_unknown = not isinstance(
        old_manifest.get("source_digest"), dict
    ) or not isinstance(new_manifest.get("source_digest"), dict)
    display_changed = _field_changed(
        old_manifest.get("display"), new_manifest.get("display")
    )
    app_changed = _field_changed(
        old_manifest.get("app"), new_manifest.get("app")
    )
    lvgl_changed = _field_changed(
        old_manifest.get("lvgl"), new_manifest.get("lvgl")
    )
    threshold = _threshold(target)
    items: list[dict[str, Any]] = []
    located = 0
    changed_notes = 0
    for note in notes:
        anchor = note.get("feedback_anchor")
        resolved = (
            resolve_anchor(target, anchor)
            if isinstance(anchor, dict)
            else {
                "resolved": False,
                "status": "missing",
                "frame_no": None,
                "resolved_t_ms": None,
                "image": None,
                "image_kind": None,
                "relation": "exact",
                "delta_ms": None,
            }
        )
        item: dict[str, Any] = {
            "note_id": note.get("id"),
            "text": note.get("text"),
            "feedback_anchor": anchor,
            "located": bool(resolved.get("resolved")),
            "new_frame": resolved.get("frame_no"),
            "new_t_ms": resolved.get("resolved_t_ms"),
            "new_image": resolved.get("image"),
            "image_kind": resolved.get("image_kind"),
            "relation": resolved.get("relation"),
            "delta_ms": resolved.get("delta_ms"),
            "pixel_diff": None,
            "anchor_unreliable_reasons": [],
        }
        reasons: list[str] = item["anchor_unreliable_reasons"]
        if not isinstance(anchor, dict):
            reasons.append("anchor_missing")
        status = resolved.get("status")
        if status in ("fallback", "ambiguous"):
            reasons.append(status)
        if (
            item["delta_ms"] is not None
            and abs(item["delta_ms"]) > LARGE_OFFSET_MS
        ):
            reasons.append("large_offset")
        if app_changed is True:
            reasons.append("app_changed")
        if source_unknown:
            reasons.append("source_unknown")
        if item["located"]:
            located += 1
            if not scenario_changed:
                pixel_diff = _pixel_diff(
                    source, target, note, anchor, resolved, threshold, reasons
                )
                item["pixel_diff"] = pixel_diff
                if pixel_diff and pixel_diff.get("changed_px", 0) > 0:
                    changed_notes += 1
        items.append(item)
    return {
        "schema": "lvgl-verify-loop-feedback-v1",
        "context": {
            "scenario_changed": scenario_changed,
            "source_changed": source_changed,
            "display_changed": display_changed,
            "app_changed": app_changed,
            "lvgl_changed": lvgl_changed,
            "source_unknown": source_unknown,
        },
        "total": len(items),
        "located": located,
        "unmapped": len(items) - located,
        "notes_with_pixel_change": changed_notes,
        "items": items,
    }


def _changed(old: Any, new: Any) -> bool | str:
    if not isinstance(old, dict) or not isinstance(new, dict):
        return "unknown"
    return old.get("sha256") != new.get("sha256")


def _field_changed(old: Any, new: Any) -> bool | str:
    if old is None or new is None:
        return "unknown"
    return old != new


def _threshold(recording: Recording) -> int:
    for row in diff_rows(recording):
        value = row.get("threshold")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 10


def _note_region(
    note: dict[str, Any], anchor: dict[str, Any]
) -> dict[str, Any] | None:
    regions = note.get("regions")
    if not isinstance(regions, list) or not regions:
        for item in note.get("anchors") or []:
            if isinstance(item, dict) and item.get("regions"):
                regions = item["regions"]
                break
    if not isinstance(regions, list) or not regions:
        return None
    region = regions[0]
    return region if isinstance(region, dict) else None


def _old_image(
    source: Recording, note: dict[str, Any], anchor: dict[str, Any]
) -> tuple[bytes | None, dict[str, Any] | None]:
    region = _note_region(note, anchor)
    if region is None:
        return None, None
    image = region.get("image")
    if isinstance(image, str):
        path = source.path / image
        if path.is_file():
            try:
                return path.read_bytes(), region
            except OSError:
                pass
    resolved = resolve_anchor(source, anchor)
    image_path = resolved.get("image")
    if isinstance(image_path, str):
        try:
            data = Path(image_path).read_bytes()
        except OSError:
            return None, region
        cropped = _crop_bytes(data, region)
        return cropped, region
    return None, region


def _crop_bytes(data: bytes, region: dict[str, Any]) -> bytes | None:
    try:
        cropped, _box, _image = crop_png(
            data,
            Region(
                int(region["x"]),
                int(region["y"]),
                int(region["w"]),
                int(region["h"]),
            ),
        )
    except (PngError, KeyError, TypeError, ValueError):
        return None
    return cropped


def _pixel_diff(
    source: Recording,
    target: Recording,
    note: dict[str, Any],
    anchor: dict[str, Any],
    resolved: dict[str, Any],
    threshold: int,
    reasons: list[str],
) -> dict[str, Any] | None:
    old_data, region = _old_image(source, note, anchor)
    if region is None:
        return None
    if old_data is None:
        reasons.append("old_image_missing")
        return None
    new_image = resolved.get("image")
    if not isinstance(new_image, str):
        return None
    try:
        new_source = Path(new_image).read_bytes()
    except OSError:
        return None
    new_data = _crop_bytes(new_source, region)
    if new_data is None:
        reasons.append("out_of_bounds")
        return None
    try:
        old_header = read_png_header(old_data)
        new_header = read_png_header(new_data)
    except PngError:
        reasons.append("size_changed")
        return None
    if (old_header.width, old_header.height) != (
        new_header.width,
        new_header.height,
    ):
        reasons.append("size_changed")
        return None
    comparison = compare_png(old_data, new_data)
    return {
        "region": {
            "x": region.get("x"),
            "y": region.get("y"),
            "w": region.get("w"),
            "h": region.get("h"),
        },
        "changed_px": comparison.changed_px,
        "changed_ratio": comparison.changed_ratio,
        "max_delta": comparison.max_delta,
        "threshold": threshold,
    }


def _build_contact_sheet_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py contact-sheet",
        description=(
            "Combine snapshots or frames into one labeled thumbnail sheet."
        ),
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="[LABEL=]PATH",
        help="snapshot or frame PNG; repeat in the wanted tile order",
    )
    parser.add_argument(
        "--out", required=True, metavar="OUT", help="explicit output PNG path"
    )
    parser.add_argument(
        "--session",
        metavar="SESSION",
        help="resolve relative --input paths against this session",
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=DEFAULT_CONTACT_COLUMNS,
        metavar="N",
        help=f"tiles per row (default: {DEFAULT_CONTACT_COLUMNS})",
    )
    parser.add_argument(
        "--tile",
        type=_tile_size,
        default=(
            DEFAULT_CONTACT_TILE_WIDTH,
            DEFAULT_CONTACT_TILE_HEIGHT,
        ),
        metavar="WxH",
        help=(
            "tile size in pixels "
            f"(default: {DEFAULT_CONTACT_TILE_WIDTH}x"
            f"{DEFAULT_CONTACT_TILE_HEIGHT})"
        ),
    )
    return parser


def _split_input_spec(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator:
        path = Path(value)
        return _derived_label(path), path
    if not label:
        raise ValueError(f"input label is empty: {value}")
    if not raw_path:
        raise ValueError(f"input path is empty: {value}")
    return label, Path(raw_path)


def _derived_label(path: Path) -> str:
    return snapshot_label(path)


def _run_contact_sheet(argv: list[str]) -> int:
    args = _build_contact_sheet_parser().parse_args(argv)
    try:
        specs = [
            (label, _media_path(str(path), args.session))
            for label, path in (
                _split_input_spec(value) for value in args.input
            )
        ]
        items = [(label, path.read_bytes()) for label, path in specs]
        sheet = build_contact_sheet(
            items,
            columns=args.columns,
            tile_width=args.tile[0],
            tile_height=args.tile[1],
        )
        sources = [path for _label, path in specs]
        output = _write_output(
            args.out,
            sheet.to_png(),
            sources,
            tuple(_session_for_png(path.resolve()) for path in sources),
        )
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"contact-sheet: {output}")
    print(f"tiles: {len(sheet.tiles)}")
    print(f"columns: {sheet.columns}")
    print(f"rows: {sheet.rows}")
    print("labels:")
    for tile in sheet.tiles:
        print(f"  {tile.label}")
    return EXIT_OK


def _build_crop_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py crop",
        description="Crop one snapshot or frame into an explicit output PNG.",
    )
    parser.add_argument("input", metavar="INPUT", help="snapshot or frame PNG")
    parser.add_argument(
        "--region",
        required=True,
        type=_region,
        metavar="X,Y,W,H",
        help="crop rectangle in display pixels",
    )
    parser.add_argument(
        "--out", required=True, metavar="OUT", help="explicit output PNG path"
    )
    parser.add_argument(
        "--session",
        metavar="SESSION",
        help="resolve a relative input against this session",
    )
    return parser


def _media_path(value: str, session: str | None) -> Path:
    path = Path(value)
    if not path.is_absolute() and session is not None and not path.is_file():
        return Path(session) / path
    return path


def _write_output(
    path: str,
    data: bytes,
    inputs: list[Path],
    sessions: tuple[Path | None, ...] = (),
) -> Path:
    output = Path(path)
    resolved = output.resolve()
    for source in inputs:
        if resolved == source.resolve():
            raise ValueError(
                f"refusing to overwrite input file with output: {output}"
            )
    for session in sessions:
        if session is not None and _is_within(resolved, session):
            raise ValueError(
                f"refusing to write output inside session evidence: {path}"
            )
    if not output.parent.is_dir():
        raise FileNotFoundError(
            f"output directory does not exist: {output.parent}"
        )
    output.write_bytes(data)
    return resolved


def _run_crop(argv: list[str]) -> int:
    args = _build_crop_parser().parse_args(argv)
    try:
        source = _media_path(args.input, args.session)
        cropped, box, _image = crop_png(source.read_bytes(), args.region)
        output = _write_output(
            args.out,
            cropped,
            [source],
            (_session_for_png(source.resolve()),),
        )
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"crop: {output} {box.x},{box.y},{box.w},{box.h}")
    return EXIT_OK


def _build_pixel_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py pixel",
        description="Read one pixel's RGB value from a snapshot or frame.",
    )
    parser.add_argument("input", metavar="INPUT", help="snapshot or frame PNG")
    parser.add_argument(
        "--at",
        required=True,
        type=_coordinate,
        metavar="X,Y",
        help="pixel coordinate in display pixels",
    )
    parser.add_argument(
        "--session",
        metavar="SESSION",
        help="resolve a relative input against this session",
    )
    return parser


def _run_pixel(argv: list[str]) -> int:
    args = _build_pixel_parser().parse_args(argv)
    x, y = args.at
    try:
        source = _media_path(args.input, args.session)
        data = source.read_bytes()
        red, green, blue = read_pixel(data, x, y)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"pixel: {source.resolve()} {x},{y} rgb={red},{green},{blue}")
    return EXIT_OK


def _build_compare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py compare",
        description=(
            "Compare two snapshots or sessions and optionally write a heatmap. "
            "A session resolves to its last snapshot, or its last frame when "
            "there is no snapshot."
        ),
    )
    parser.add_argument(
        "left", metavar="LEFT", help="session directory, manifest.json, or PNG"
    )
    parser.add_argument(
        "right",
        metavar="RIGHT",
        help="session directory, manifest.json, or PNG",
    )
    parser.add_argument(
        "--out",
        metavar="OUT",
        help=(
            "explicit output path for the optional heatmap PNG; "
            "must be outside session evidence"
        ),
    )
    parser.add_argument(
        "--json", action="store_true", help="print one JSON result on stdout"
    )
    return parser


def _resolve_compare_image(value: str) -> tuple[Path, Path | None]:
    path = Path(value)
    if path.is_dir():
        session = path
    elif path.is_file() and path.name == "manifest.json":
        session = path.parent
    elif path.is_file():
        resolved = path.resolve()
        return resolved, _session_for_png(resolved)
    else:
        raise FileNotFoundError(f"compare input not found: {path}")
    recording = Recording.open(session)
    snapshots = recording.snapshot_views()
    if snapshots:
        return (
            (recording.path / snapshots[-1]["file"]).resolve(),
            recording.path.resolve(),
        )
    latest = recording.latest_frame()
    if latest is not None:
        return (
            (recording.path / latest["file"]).resolve(),
            recording.path.resolve(),
        )
    raise ValueError(f"session has no snapshots or frames: {path}")


def _session_for_png(path: Path) -> Path | None:
    for candidate in (path.parent, path.parent.parent):
        if (candidate / "manifest.json").is_file():
            return candidate.resolve()
    return None


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _run_compare(argv: list[str]) -> int:
    args = _build_compare_parser().parse_args(argv)
    try:
        left, left_session = _resolve_compare_image(args.left)
        right, right_session = _resolve_compare_image(args.right)
        comparison = compare_png(
            left.read_bytes(),
            right.read_bytes(),
            heatmap=args.out is not None,
        )
        heatmap = None
        if args.out is not None:
            heatmap = _write_output(
                args.out,
                comparison.to_png(),
                [left, right],
                (left_session, right_session),
            )
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    payload = {
        "left": str(left),
        "right": str(right),
        "width": comparison.width,
        "height": comparison.height,
        "bbox": (
            None if comparison.bbox is None else comparison.bbox.as_dict()
        ),
        "changed_px": comparison.changed_px,
        "changed_ratio": comparison.changed_ratio,
        "max_delta": comparison.max_delta,
        "heatmap": None if heatmap is None else str(heatmap),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return EXIT_OK
    if comparison.bbox is None:
        bbox = "none"
    else:
        bbox = (
            f"{comparison.bbox.x},{comparison.bbox.y},"
            f"{comparison.bbox.w},{comparison.bbox.h}"
        )
    lines = [
        f"compare: {comparison.width}x{comparison.height}",
        f"left: {left}",
        f"right: {right}",
        f"bbox: {bbox}",
        f"changed_px: {comparison.changed_px}",
        f"changed_ratio: {comparison.changed_ratio:.9f}",
        f"max_delta: {comparison.max_delta:.9f}",
        f"heatmap: {payload['heatmap'] or 'none'}",
    ]
    print("\n".join(lines))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py",
        description=(
            "Read one session's evidence without starting an engine or web. "
            "The default output is the session index; query subcommands are "
            "bounded and every command accepts --json."
        ),
        epilog=(
            "queries: timeline, diffs, frames, notes, resolve, context, "
            "feedback; visual: crop, contact-sheet, pixel, compare"
        ),
    )
    parser.add_argument(
        "session",
        nargs="?",
        metavar="SESSION",
        help="session directory or manifest.json",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="use the newest session under the sessions root (default)",
    )
    parser.add_argument(
        "--log-tail",
        type=_log_tail_lines,
        default=DEFAULT_LOG_TAIL,
        metavar="N",
        help=f"include the last N engine.log lines (default: {DEFAULT_LOG_TAIL})",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="shrink snapshots, note text and the log tail",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the session index as one JSON object",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in QUERY_COMMANDS:
        name = argv[0]
        try:
            if name == "timeline":
                return _run_timeline(argv[1:])
            if name == "diffs":
                return _run_diffs(argv[1:])
            if name == "frames":
                return _run_frames(argv[1:])
            if name == "notes":
                return _run_notes(argv[1:])
            if name == "resolve":
                return _run_resolve(argv[1:])
            if name == "context":
                return _run_context(argv[1:])
            return _run_feedback(argv[1:])
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    if argv and argv[0] in VISUAL_COMMANDS:
        try:
            if argv[0] == "contact-sheet":
                return _run_contact_sheet(argv[1:])
            if argv[0] == "crop":
                return _run_crop(argv[1:])
            if argv[0] == "pixel":
                return _run_pixel(argv[1:])
            return _run_compare(argv[1:])
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.latest and args.session is not None:
        parser.error("SESSION and --latest are mutually exclusive")
    try:
        session = args.session
        if session is None or args.latest:
            session = latest_session()
        summary = session_index(
            session,
            log_tail_lines=args.log_tail,
            compact=args.compact,
        )
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(
            json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
    else:
        print(format_index(summary))
    return EXIT_OK


def latest_session(root: str | Path | None = None) -> Path:
    root_path = paths.sessions_root_from_env() if root is None else Path(root)
    if not root_path.is_dir():
        raise FileNotFoundError(f"sessions root not found: {root_path}")
    sessions = [
        child
        for child in root_path.iterdir()
        if child.is_dir() and (child / "manifest.json").is_file()
    ]
    if not sessions:
        raise FileNotFoundError(f"no sessions found under: {root_path}")
    return max(sessions, key=lambda path: path.name)


def format_index(index: dict[str, Any]) -> str:
    display = index["display"]
    counts = index["counts"]
    timeline = index["timeline"]
    diffs = index["diffs"]
    lines = [
        f"session: {index['session_id']}",
        f"dir: {index['session_dir']}",
        f"status: {index['status']}",
        f"mode: {index['mode'] if index['mode'] is not None else 'unknown'}",
        (
            f"display: {display['width']}x{display['height']}"
            if display is not None
            else "display: unknown"
        ),
        f"frames: {index['frame_count']}",
        (
            f"recorded: {'yes' if index['recorded'] else 'no'}"
            f" changed_only: {'yes' if index['record_changed_only'] else 'no'}"
        ),
        f"requested app: {_app_or_unknown(index['requested_app'])}",
        f"effective app: {_app_or_unknown(index['effective_app'])}",
        (
            "timeline: "
            f"frame {timeline['first_frame_no']}..{timeline['last_frame_no']} "
            f"t_ms {timeline['first_t_ms']}..{timeline['last_frame_t_ms']}"
        ),
        (
            "end: "
            + (
                "missing"
                if timeline["end"] is None
                else f"t_ms={timeline['end']['t_ms']} "
                f"frames={timeline['end']['frame_count']} "
                f"truncated={'true' if timeline['end']['truncated'] else 'false'}"
            )
        ),
        (
            "diffs: "
            f"rows={diffs['rows']} changed={diffs['changed_rows']} "
            f"threshold={diffs['threshold']} "
            f"max_ratio={diffs['max_changed_ratio']}"
        ),
        (
            f"inputs: {counts['inputs']} waits: {counts['waits']} "
            f"marks: {counts['marks']} snapshots: {counts['snapshots']}"
        ),
        (
            f"clicks: {counts['clicks']} drags: {counts['drags']} "
            f"notes: {counts['annotations']} "
            f"whiteboards: {counts['whiteboards']}"
        ),
        (
            "checks: "
            f"{counts['checks']['total']} total "
            f"{counts['checks']['failed']} not_ok"
        ),
        (
            f"truncated: {'yes' if index['truncated'] else 'no'} "
            f"log_truncated: {'yes' if index['log_truncated'] else 'no'}"
        ),
        "raw files:",
    ]
    for key, value in index["raw_files"].items():
        rows = f" {value['rows']} rows" if "rows" in value else ""
        lines.append(f"  {key}: {value['bytes']} B{rows} {value['path']}")
    if index["clicks"]:
        lines.append("clicks:")
        for click in index["clicks"]:
            lines.append(
                f"  {click['seq_down']}:{click['seq_up']} "
                f"t_ms={click['t_ms_down']} "
                f"frame={click['frame_before']}->{click['frame_after']} "
                f"hit={click['hit']}"
            )
    lines.append("snapshots:")
    snapshot_items = index["snapshots"]
    lines.append(
        f"  {snapshot_items['count']} in {snapshot_items['dir']}"
        + (
            " (none)"
            if snapshot_items["last"] is None
            else f"; last={snapshot_items['last']}"
        )
    )
    items = snapshot_items.get("items") or []
    for snapshot in items[-5:]:
        lines.append(f"  {snapshot['label']} {snapshot['path']}")
    if snapshot_items["count"] > len(items[-5:]):
        lines.append(f"  ... {snapshot_items['count'] - len(items[-5:])} more")
    lines.append("marks:")
    if not index["marks"]:
        lines.append("  none")
    else:
        lines.append(
            "  " + ", ".join(str(mark["id"]) for mark in index["marks"])
        )
    notes = index["annotations"]["notes"]
    lines.append(f"notes: {index['annotations']['count']}")
    for note in notes[:5]:
        lines.append(
            f"  {note['id']} {note.get('author')}/{note.get('source')}: "
            f"{note.get('text')}"
        )
    lines.append("next reads:")
    if not index["next_reads"]:
        lines.append("  none")
    for read in index["next_reads"]:
        lines.append(
            f"  - {read['why']}: {read['command']} (~{read['est_bytes']} B)"
        )
    lines.append("log tail:")
    if not index["log_tail"]:
        lines.append("  none")
    else:
        lines.extend(f"  {line}" for line in index["log_tail"])
    return "\n".join(lines)


def format_query(payload: dict[str, Any]) -> str:
    schema = payload.get("schema", "")
    if schema == "lvgl-verify-loop-timeline-query-v1":
        lines = [f"timeline: {payload['returned']}/{payload['total']} rows"]
        for row in payload["rows"]:
            lines.append("  " + _format_row(row))
        return "\n".join(lines)
    if schema == "lvgl-verify-loop-diffs-query-v1":
        lines = [f"diffs: {payload['returned']}/{payload['total']} rows"]
        for row in payload["rows"]:
            lines.append("  " + _format_row(row))
        return "\n".join(lines)
    if schema == "lvgl-verify-loop-frames-query-v1":
        lines = [f"frames: {payload['returned']}"]
        for row in payload["rows"]:
            lines.append("  " + _format_row(row))
        return "\n".join(lines)
    if schema == "lvgl-verify-loop-notes-query-v1":
        lines = [f"notes: {payload['returned']}/{payload['total']}"]
        for note in payload["notes"]:
            lines.append(
                f"  {note['id']} {note.get('author')}/{note.get('source')}: "
                f"{note.get('text')}"
            )
            if "resolved" in note:
                lines.append("    resolved: " + _format_row(note["resolved"]))
        return "\n".join(lines)
    if schema == "lvgl-verify-loop-resolve-v1":
        return "\n".join(
            [
                f"resolved: {'yes' if payload['resolved'] else 'no'}",
                f"status: {payload['status']}",
                f"relation: {payload['relation']}",
                f"requested_t_ms: {payload['requested_t_ms']}",
                f"resolved_t_ms: {payload['resolved_t_ms']}",
                f"delta_ms: {payload['delta_ms']}",
                f"frame_no: {payload['frame_no']}",
                f"image_kind: {payload['image_kind']}",
                f"image: {payload['image']}",
                f"basis: {payload['basis']}",
                f"candidates: {json.dumps(payload['candidates'])}",
            ]
        )
    if schema == "lvgl-verify-loop-context-v1":
        lines = [
            "resolved: " + _format_row(payload["resolved"]),
            "window: " + _format_row(payload["window"]),
            f"inputs: {len(payload['inputs'])}",
            f"frames: before={payload['frames']['before']} "
            f"after={payload['frames']['after']}",
            f"diffs: {len(payload['diffs'])}",
            f"notes: {len(payload['notes'])}",
        ]
        return "\n".join(lines)
    if schema == "lvgl-verify-loop-feedback-v1":
        return "\n".join(
            [
                f"feedback: {payload['located']}/{payload['total']} located",
                "context: " + json.dumps(payload["context"]),
                "notes with pixel change: "
                f"{payload['notes_with_pixel_change']}",
            ]
        )
    return json.dumps(payload, ensure_ascii=False)


def _app_or_unknown(value: str | None) -> str:
    return "未知" if value is None else value


def _format_row(row: dict[str, Any]) -> str:
    return " ".join(
        f"{key}={_format_value(value)}"
        for key, value in row.items()
        if key != "schema"
    )


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
