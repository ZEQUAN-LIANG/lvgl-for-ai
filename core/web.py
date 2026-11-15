#!/usr/bin/env python3
"""Thin launcher for the LVGL session viewer.

    python -I core/web.py

Serves replay and the live bridge at the fixed default address
``http://127.0.0.1:8765/``. The HTTP/UI layer lives in ``lvgl_ai.web``;
this file only parses flags and starts the server. It works from any working
directory and does not require a browser to be present.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ``python -I`` does not add the script directory to sys.path.
TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai.control.input import TOKEN_PATTERN, is_token
from lvgl_ai.web import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    serve,
)


def _app_token(value: str) -> str:
    if not is_token(value):
        raise argparse.ArgumentTypeError(f"app must match {TOKEN_PATTERN}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web.py",
        description=(
            "Serve the session viewer and live bridge. Default address: "
            f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/"
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"bind address (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port; 0 picks a free port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=None,
        help="session directory (default: LVGL_AI_SESSIONS_ROOT or <repo>/sessions)",
    )
    parser.add_argument(
        "--lvgl",
        default=None,
        help="LVGL version for live sessions (default: LVGL_AI_LVGL_VERSION or 9.6)",
    )
    parser.add_argument(
        "--build",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "rebuild lvgl_engine for live sessions (default: on); --no-build "
            "uses an existing build/ engine"
        ),
    )
    parser.add_argument(
        "--app",
        type=_app_token,
        default=None,
        help=(
            "app to preselect and test-preview on page load; the browser URL "
            "gets ?app=NAME"
        ),
    )
    parser.add_argument(
        "--manage",
        action="store_true",
        help=(
            "open the app management dialog on page load; the browser URL "
            "gets ?manage=1"
        ),
    )
    parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="open the page in a browser after startup (default: off)",
    )
    parser.add_argument(
        "--exit-on-close",
        action="store_true",
        help=(
            "exit after the last tracked browser page closes "
            "(default: off; core/web.pyw enables it)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        serve(
            host=args.host,
            port=args.port,
            sessions_root=args.sessions_root,
            lvgl=args.lvgl,
            build=args.build,
            open_browser=args.open_browser,
            exit_on_close=args.exit_on_close,
            app=args.app,
            manage=args.manage,
        )
    except OSError as exc:
        print(
            f"[web] cannot listen on {args.host}:{args.port}: {exc}",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
