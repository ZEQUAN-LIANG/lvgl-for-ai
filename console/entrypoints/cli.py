#!/usr/bin/env python3
"""Thin CLI for the control layer.

    python -I console/entrypoints/cli.py --lvgl 9.6 --record \
        --scenario user/scenarios/settings.json

Only argument mapping: parse flags, construct ``Runtime``, run
``play_scenario`` or stay idle, then translate the outcome into exit codes and
the optional ``--json`` session index. Protocol and evidence files live in
``control``; this file never speaks the wire protocol itself.

Exit codes: 0 = session finished ok; 1 = build, link or engine crash;
2 = harness error (bad flags, scenario, protocol, missing engine).

``--no-build`` skips the source build and uses the existing ``build/`` engine;
the default remains ``--build``. Build mode is automatic: an existing
``engine/lvgl/<version>`` uses the source build, otherwise ``dist/lvgl/<version>`` is
used through the prebuilt path; ``--prebuilt`` / ``--source`` override that
choice. ``--app NAME`` selects
the user app variant by setting ``LVGL_VERIFY_LOOP_DEMO``; when ``--scenario`` is used and
the scenario declares ``app``, omitting the flag uses the scenario value.
A scenario's optional ``display`` object sets the engine width/height; an
explicit ``--app`` overrides only the app, not that scene's display. A
scenario's optional ``lvgl`` field selects the version when ``--lvgl`` is
omitted; explicit ``--lvgl`` wins, then the scenario field, then
``LVGL_VERIFY_LOOP_LVGL_VERSION``, then the default 9.6.

``--json`` prints exactly one JSON object on stdout. When the session evidence
is readable it is the same ``lvgl-verify-loop-session-index-v1`` document as
``session_report.py --json``; otherwise a failed read keeps the original
``session_id`` / ``manifest_path`` / ``app`` / ``error`` envelope. Diagnostics
stay on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ``python -I`` does not add the script directory to sys.path.
CONSOLE_ROOT = Path(__file__).resolve().parent.parent
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

from control import (
    ToolError,
    Runtime,
    RuntimeCrash,
    ScenarioError,
    session_index,
)
from scenario import play_scenario
import paths
from control.errors import dump_error, exit_code_for
from control.input import TOKEN_PATTERN, is_token
from scenario import load_scenario

SCRIPTS_DIR = paths.SCRIPTS_DIR
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import install_version
except ModuleNotFoundError:  # packaged skill ships no maintenance scripts
    install_version = None

EXIT_OK = 0

IDLE_POLL_S = 0.1


def _app_token(value: str) -> str:
    if not is_token(value):
        raise argparse.ArgumentTypeError(f"app must match {TOKEN_PATTERN}")
    return value


def _load_scenario(
    path: Path | None,
) -> tuple[dict | None, Exception | None]:
    if path is None:
        return None, None
    try:
        return load_scenario(path), None
    except Exception as exc:  # noqa: BLE001 - mirrored by main's delay rule
        return None, exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description=(
            "Run a headless LVGL session and optionally play a scenario."
        ),
    )
    parser.add_argument(
        "--lvgl",
        default=None,
        help=(
            "LVGL version, e.g. 9.6 (default: scenario lvgl, "
            "LVGL_VERIFY_LOOP_LVGL_VERSION, or 9.6)"
        ),
    )
    parser.add_argument(
        "--app",
        type=_app_token,
        default=None,
        help=(
            "user app variant (forwarded as LVGL_VERIFY_LOOP_DEMO); with --scenario the "
            "scenario's app is used when this flag is omitted"
        ),
    )
    parser.add_argument(
        "--record",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="record frames and evidence files (default: on)",
    )
    parser.add_argument(
        "--build",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "rebuild lvgl_engine from apps before launch (default: on); "
            "--no-build uses an existing build/ engine"
        ),
    )
    build_mode = parser.add_mutually_exclusive_group()
    build_mode.add_argument(
        "--prebuilt",
        dest="build_mode",
        action="store_const",
        const="prebuilt",
        help=(
            "compile apps against the prebuilt host SDK in dist/lvgl/<version> "
            "instead of CMake"
        ),
    )
    build_mode.add_argument(
        "--source",
        dest="build_mode",
        action="store_const",
        const="source",
        help=(
            "build from engine/lvgl/<version> with CMake (default: auto; "
            "prebuilt is used when the source tree is missing)"
        ),
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--scenario",
        type=Path,
        default=None,
        help="scenario JSON file to play after startup",
    )
    action.add_argument(
        "--idle",
        action="store_true",
        help="keep the session running until Ctrl+C",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="download a missing LVGL version pack without prompting",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="never download a missing LVGL version pack",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the session index as JSON on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    scenario, scenario_error = _load_scenario(args.scenario)
    if (
        scenario_error is not None
        and not isinstance(scenario_error, ScenarioError)
        and args.app is None
    ):
        raise scenario_error
    app = (
        args.app
        if args.app is not None
        else (None if scenario is None else scenario.get("app"))
    )
    lvgl = (
        args.lvgl
        if args.lvgl is not None
        else (None if scenario is None else scenario.get("lvgl"))
    )
    effective_lvgl = lvgl or paths.lvgl_version_from_env()
    if install_version is not None:
        try:
            install_version.ensure_pack_for_version(
                paths.REPO_ROOT,
                effective_lvgl,
                interactive=bool(sys.stdin and sys.stdin.isatty()),
                yes=args.yes,
                offline=args.offline,
            )
        except install_version.InstallError as exc:
            print(f"[cli] {exc}", file=sys.stderr)
            return 2
    runtime_kwargs = dict(
        lvgl=lvgl,
        build=args.build,
        record=args.record,
    )
    if args.build_mode is not None:
        runtime_kwargs["build_mode"] = args.build_mode
    if app is not None:
        runtime_kwargs["app"] = app
    if args.scenario is not None:
        runtime_kwargs["scenario"] = args.scenario
    runtime_kwargs["record_changed_only"] = True
    display = None if scenario is None else scenario.get("display")
    if display is not None:
        runtime_kwargs["width"] = display["width"]
        runtime_kwargs["height"] = display["height"]
    runtime = Runtime(**runtime_kwargs)
    error: Exception | None = None
    started = False
    interrupted = False
    try:
        runtime.start()
        started = True
        if args.scenario is not None:
            if scenario_error is not None:
                raise scenario_error
            play_scenario(runtime, scenario["steps"])
        elif args.idle:
            print(
                f"[cli] session {runtime.session_id} is idle; "
                "press Ctrl+C to stop",
                file=sys.stderr,
            )
            _wait_for_interrupt(runtime)
            if runtime.exit_code not in (None, 0):
                raise RuntimeCrash(
                    f"engine exited with {runtime.exit_code}",
                    exit_code=runtime.exit_code,
                    log_tail=runtime.log_tail(),
                    log_path=runtime.engine_log_path,
                )
    except KeyboardInterrupt:
        interrupted = True
    except Exception as exc:  # noqa: BLE001 - the CLI maps every failure layer
        error = exc
    finally:
        if error is not None and runtime.session_dir is not None:
            runtime.record_error(error)
        try:
            runtime.stop()
        except Exception as exc:  # noqa: BLE001 - keep the original failure
            if error is None:
                error = exc

    if interrupted and not started:
        error = ToolError("interrupted before the session started")
    _report(error, as_json=args.json, runtime=runtime)
    return EXIT_OK if error is None else exit_code_for(error)


def _wait_for_interrupt(runtime: Runtime) -> None:
    while runtime.is_running:
        time.sleep(IDLE_POLL_S)


def _report(
    error: Exception | None, *, as_json: bool, runtime: Runtime
) -> None:
    if error is not None:
        print(f"[cli] {error}", file=sys.stderr)
    if as_json:
        payload = _index_payload(runtime)
        if payload is None:
            payload = {
                "session_id": runtime.session_id,
                "manifest_path": (
                    None
                    if runtime.manifest_path is None
                    else str(runtime.manifest_path)
                ),
                "app": getattr(runtime, "app", None),
                "error": dump_error(error),
            }
        print(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        return
    if error is None and runtime.session_dir is not None:
        print(runtime.session_dir)


def _index_payload(runtime: Runtime) -> dict | None:
    if runtime.session_dir is None:
        return None
    try:
        return session_index(runtime.session_dir)
    except Exception:  # noqa: BLE001 - evidence is optional for the CLI
        return None


if __name__ == "__main__":
    raise SystemExit(main())
