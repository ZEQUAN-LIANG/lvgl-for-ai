#!/usr/bin/env python3
"""Read one finished session's evidence without starting an engine or the web.

Prints a human-readable summary by default and one line of JSON with
``--json``. The ``crop``, ``contact-sheet``, ``pixel``, and ``compare``
subcommands read snapshot or frame paths and write only an explicit output
file. Exit code 0 means the evidence was read; 2 means the input or output
could not be handled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ``python -I`` does not add the script directory to sys.path.
TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import paths, summarize_session  # noqa: E402
from lvgl_ai.png_codec import (  # noqa: E402
    DEFAULT_CONTACT_COLUMNS,
    DEFAULT_CONTACT_TILE_HEIGHT,
    DEFAULT_CONTACT_TILE_WIDTH,
    Region,
    build_contact_sheet,
    compare_png,
    crop_png,
    read_pixel,
)

EXIT_OK = 0
EXIT_ERROR = 2
DEFAULT_LOG_TAIL = 20
VISUAL_COMMANDS = ("crop", "contact-sheet", "pixel", "compare")


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
    stem = path.stem
    head, separator, tail = stem.partition("_")
    if separator and head.isdigit() and tail:
        return tail
    return stem


def _run_contact_sheet(argv: list[str]) -> int:
    args = _build_contact_sheet_parser().parse_args(argv)
    try:
        specs = [_split_input_spec(value) for value in args.input]
        items = [(label, path.read_bytes()) for label, path in specs]
        sheet = build_contact_sheet(
            items, columns=args.columns, tile_width=args.tile[0],
            tile_height=args.tile[1],
        )
        output = _write_output(
            args.out, sheet.to_png(), [path for _label, path in specs]
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
    return parser


def _write_output(path: str, data: bytes, inputs: list[Path]) -> Path:
    output = Path(path)
    resolved = output.resolve()
    for source in inputs:
        if resolved == source.resolve():
            raise ValueError(
                f"refusing to overwrite input file with output: {output}"
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
        source = Path(args.input)
        cropped, box, _image = crop_png(source.read_bytes(), args.region)
        output = _write_output(args.out, cropped, [source])
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
    return parser


def _run_pixel(argv: list[str]) -> int:
    args = _build_pixel_parser().parse_args(argv)
    x, y = args.at
    try:
        data = Path(args.input).read_bytes()
        red, green, blue = read_pixel(data, x, y)
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(
        f"pixel: {Path(args.input).resolve()} {x},{y} "
        f"rgb={red},{green},{blue}"
    )
    return EXIT_OK


def _build_compare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session_report.py compare",
        description=(
            "Compare two snapshots or sessions and optionally write a heatmap; "
            "a session resolves to its latest snapshot, else its last frame."
        ),
    )
    parser.add_argument(
        "left", metavar="LEFT", help="session directory, manifest.json, or PNG"
    )
    parser.add_argument(
        "right", metavar="RIGHT", help="session directory, manifest.json, or PNG"
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
    summary = summarize_session(session)
    if summary["snapshots"]:
        return (
            Path(summary["snapshots"][-1]["path"]).resolve(),
            session.resolve(),
        )
    if summary["frames"]:
        return Path(summary["frames"][-1]).resolve(), session.resolve()
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
            output = Path(args.out).resolve()
            for session in (left_session, right_session):
                if session is not None and _is_within(output, session):
                    raise ValueError(
                        "refusing to write heatmap inside session evidence: "
                        f"{args.out}"
                    )
            heatmap = _write_output(
                args.out, comparison.to_png(), [left, right]
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
            "Read one session's evidence without starting an engine or web."
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
        help="include the last N engine.log lines (default: 20)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one JSON summary on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in VISUAL_COMMANDS:
        if argv[0] == "contact-sheet":
            return _run_contact_sheet(argv[1:])
        if argv[0] == "crop":
            return _run_crop(argv[1:])
        if argv[0] == "pixel":
            return _run_pixel(argv[1:])
        if argv[0] == "compare":
            return _run_compare(argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.latest and args.session is not None:
        parser.error("SESSION and --latest are mutually exclusive")
    try:
        session = args.session
        if session is None or args.latest:
            session = latest_session()
        summary = summarize_session(
            session, log_tail_lines=args.log_tail
        )
    except (OSError, ValueError) as exc:
        print(f"[session-report] {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    else:
        print(format_summary(summary))
    return EXIT_OK


def latest_session(root: str | Path | None = None) -> Path:
    """Newest session directory with a manifest under ``root``."""
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


def format_summary(summary: dict) -> str:
    """Render the evidence summary for a human; paths stay absolute."""
    display = summary["display"]
    lines = [
        f"session: {summary['session_id']}",
        f"dir: {summary['session_dir']}",
        f"status: {summary['status']}",
        f"mode: {summary['mode'] if summary['mode'] is not None else 'unknown'}",
        (
            f"display: {display['width']}x{display['height']}"
            if display is not None
            else "display: unknown"
        ),
        f"frames: {summary['frame_count']}",
        f"recorded: {'yes' if summary['recorded'] else 'no'}",
        f"requested app: {_app(summary['requested_app'])}",
        f"effective app: {_app(summary['effective_app'])}",
    ]
    _append_entries(
        lines,
        "snapshots",
        [
            f"{snapshot['label']} {snapshot['path']}"
            for snapshot in summary["snapshots"]
        ],
    )
    _append_entries(lines, "frame paths", summary["frames"])
    _append_entries(
        lines, "marks", [_format_row(row) for row in summary["marks"]]
    )
    _append_entries(
        lines, "inputs", [_format_row(row) for row in summary["inputs"]]
    )
    _append_entries(
        lines,
        "frame diffs",
        [_format_row(row) for row in summary["frame_diffs"]],
    )
    _append_entries(lines, "log tail", summary["log_tail"])
    return "\n".join(lines)


def _app(value: str | None) -> str:
    return "未知" if value is None else value


def _append_entries(lines: list[str], title: str, entries: list[str]) -> None:
    lines.append(f"{title}:")
    if not entries:
        lines.append("  none")
        return
    lines.extend(f"  {entry}" for entry in entries)


def _format_row(row: dict) -> str:
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
