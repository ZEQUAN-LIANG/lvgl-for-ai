#!/usr/bin/env python3
"""Read one finished session's evidence without starting an engine or the web.

Prints a human-readable summary by default and one line of JSON with
``--json``. Exit code 0 means the evidence was read; 2 means the session or a
required file could not be read.
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

EXIT_OK = 0
EXIT_ERROR = 2
DEFAULT_LOG_TAIL = 20


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
