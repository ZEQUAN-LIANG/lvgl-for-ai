#!/usr/bin/env python3
"""Write one human feedback note from the chat window.

The tool only records what the human said and where it applies; it never
decides whether the note is fixed. ``add`` is the v1 entry point: ``author``
must be ``human`` and ``transcribed_by`` may be ``ai``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import paths
from lvgl_ai.control.anchors import derive_anchor, resolve_anchor
from lvgl_ai.control.notes import (
    AUTHORS,
    SOURCES,
    TRANSCRIBERS,
    AnnotationError,
    add_note,
)
from lvgl_ai.control.recording import Recording
from lvgl_ai.png_codec import Region

EXIT_OK = 0
EXIT_ERROR = 2


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


def _build_add_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feedback.py add",
        description=(
            "Append one human note with a stable feedback anchor."
        ),
    )
    parser.add_argument("--session", required=True, metavar="SESSION")
    parser.add_argument("--author", choices=AUTHORS, default="human")
    parser.add_argument("--source", choices=SOURCES, default="chat")
    parser.add_argument("--transcribed-by", choices=TRANSCRIBERS)
    parser.add_argument("--text", required=True)
    parser.add_argument("--offset-ms", type=int, default=0)
    parser.add_argument("--region", action="append", type=_region, default=[])
    parser.add_argument("--json", action="store_true")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--click", type=_seq_pair, metavar="DOWN:UP")
    selector.add_argument("--mark", metavar="ID")
    selector.add_argument("--input-seq", type=int)
    selector.add_argument("--t-ms", type=int)
    selector.add_argument("--frame", type=int)
    return parser


def _session_path(value: str) -> Path:
    root = paths.sessions_root_from_env().resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = candidate.resolve()
        if not candidate.is_dir():
            candidate = (root / value).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"session must stay inside the sessions root: {root}"
        ) from exc
    return candidate


def _anchor(args: argparse.Namespace, recording: Recording) -> dict:
    if args.click is not None:
        down, up = args.click
        anchor = {"kind": "click", "seq_down": down, "seq_up": up}
        if args.offset_ms:
            anchor["offset_ms"] = args.offset_ms
        return anchor
    if args.mark is not None:
        anchor = {"kind": "mark", "id": args.mark}
        if args.offset_ms:
            anchor["offset_ms"] = args.offset_ms
        return anchor
    if args.input_seq is not None:
        anchor = {"kind": "input", "seq": args.input_seq}
        if args.offset_ms:
            anchor["offset_ms"] = args.offset_ms
        return anchor
    if args.t_ms is not None:
        return {"kind": "t_ms", "t_ms": args.t_ms}
    return derive_anchor(recording, frame_no=args.frame)


def _frame_t_ms(recording: Recording, frame_no: int) -> int | None:
    try:
        rows = recording.timeline()
    except (OSError, ValueError):
        return None
    for row in rows:
        if row.get("type") == "frame" and row.get("frame_no") == frame_no:
            value = row.get("t_ms")
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def _run_add(argv: list[str]) -> int:
    args = _build_add_parser().parse_args(argv)
    try:
        session = _session_path(args.session)
        recording = Recording.open(session)
        anchor = _anchor(args, recording)
        resolved = resolve_anchor(recording, anchor)
        regions = [
            {"x": region.x, "y": region.y, "w": region.w, "h": region.h}
            for region in args.region
        ]
        frame_no = resolved.get("frame_no")
        t_ms = resolved.get("resolved_t_ms")
        if args.frame is not None:
            frame_no = args.frame
            t_ms = _frame_t_ms(recording, args.frame) or t_ms
        if not isinstance(frame_no, int) or isinstance(frame_no, bool):
            frame_no = 0 if not regions else None
        payload = {
            "frame_no": frame_no if frame_no is not None else 0,
            "t_ms": t_ms if isinstance(t_ms, int) else 0,
            "regions": regions,
            "tags": [],
            "text": args.text,
            "feedback_anchor": anchor,
        }
        document, saved = add_note(
            recording,
            payload,
            source=args.source,
            author=args.author,
            transcribed_by=args.transcribed_by,
        )
    except (OSError, ValueError) as exc:
        print(f"[feedback] {exc}", file=sys.stderr)
        return EXIT_ERROR
    images = [
        region.get("image")
        for region in saved.get("regions") or []
        if isinstance(region, dict) and region.get("image")
    ]
    output = {
        "note_id": saved.get("id"),
        "feedback_anchor": saved.get("feedback_anchor"),
        "resolved": resolved,
        "region_images": images,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False), flush=True)
        return EXIT_OK
    print(f"note: {output['note_id']}")
    print(
        "anchor: "
        + json.dumps(output["feedback_anchor"], ensure_ascii=False)
    )
    print(
        "resolved: "
        f"frame={resolved.get('frame_no')} "
        f"t_ms={resolved.get('resolved_t_ms')} "
        f"kind={resolved.get('image_kind')} "
        f"status={resolved.get('status')}"
    )
    for image in images:
        print(f"region image: {session / image}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "add":
        try:
            return _run_add(argv[1:])
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    parser = argparse.ArgumentParser(
        prog="feedback.py",
        description="Write human feedback notes into a session.",
        epilog="commands: add",
    )
    parser.parse_args(argv)
    parser.print_help()
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
