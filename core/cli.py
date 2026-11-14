#!/usr/bin/env python3
"""Thin CLI for the lvgl_ai control layer.

    python -I core/cli.py --lvgl 9.6 --record \
        --scenario user/scenarios/settings.json

Only argument mapping: parse flags, construct ``Runtime``, run
``play_scenario`` or stay idle, then translate the outcome into exit codes and
the optional ``--json`` summary. Protocol and evidence files live in
``lvgl_ai``; this file never speaks the wire protocol itself.

Exit codes: 0 = session finished ok; 1 = build, link or engine crash;
2 = harness error (bad flags, scenario, protocol, missing engine).

``--no-build`` skips the source build and uses the existing ``build/`` engine;
the default remains ``--build``. Build mode is automatic: an existing
``lvgl-src/<version>`` uses the source build, otherwise ``sdk/<version>`` is
used through the prebuilt path; ``--prebuilt`` / ``--source`` override that
choice. ``--app NAME`` selects
the user app variant by setting ``LVGL_AI_DEMO``; when ``--scenario`` is used and
the scenario declares ``app``, omitting the flag uses the scenario value.
A scenario's optional ``display`` object sets the engine width/height; an
explicit ``--app`` overrides only the app, not that scene's display.

``--json`` prints exactly one JSON object on stdout. The original fields
``session_id``, ``manifest_path``, ``app`` and ``error`` (``null`` on success)
are always present; ``session_dir``, ``status``, ``display``, ``frame_count``,
``requested_app``, ``effective_app``, ``snapshots``, ``marks`` and ``log_tail``
come from :func:`lvgl_ai.summarize_session` when the session evidence can be
read. A failed read leaves the original fields in place. Diagnostics stay on
stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ``python -I`` does not add the script directory to sys.path.
TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import (  # noqa: E402
    ToolError,
    Runtime,
    RuntimeCrash,
    ScenarioError,
    play_scenario,
    summarize_session,
)
from lvgl_ai.control.errors import dump_error, exit_code_for  # noqa: E402
from lvgl_ai.control.evidence import CLI_EVIDENCE_FIELDS  # noqa: E402
from lvgl_ai.control.input import TOKEN_PATTERN, is_token  # noqa: E402
from lvgl_ai.scenario import load_scenario  # noqa: E402

EXIT_OK = 0

IDLE_POLL_S = 0.1


def _app_token(value: str) -> str:
    if not is_token(value):
        raise argparse.ArgumentTypeError(f"app must match {TOKEN_PATTERN}")
    return value


def _load_scenario(
    path: Path | None,
) -> tuple[dict | None, Exception | None]:
    """Read ``lvgl-ai-scenario-v1`` once, before Runtime starts.

    The parsed document selects the app and supplies the already validated
    steps, so the file is not read twice. A failed read is remembered and
    re-raised after startup, so the session still records the harness error.
    """
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
        help="LVGL version, e.g. 9.6 (default: LVGL_AI_LVGL_VERSION or 9.6)",
    )
    parser.add_argument(
        "--app",
        type=_app_token,
        default=None,
        help=(
            "user app variant (forwarded as LVGL_AI_DEMO); with --scenario the "
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
            "rebuild lvgl_engine from user/app before launch (default: on); "
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
            "compile user/app against the prebuilt host SDK in sdk/<version> "
            "instead of CMake"
        ),
    )
    build_mode.add_argument(
        "--source",
        dest="build_mode",
        action="store_const",
        const="source",
        help=(
            "build from lvgl-src/<version> with CMake (default: auto; "
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
        "--json",
        action="store_true",
        help="print one JSON summary on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    scenario, scenario_error = _load_scenario(args.scenario)
    # Without --app the old code surfaced an unexpected read failure before
    # startup; with --app it skipped the pre-read and only failed inside
    # play_scenario. Keep both timings: only a ScenarioError (and any error
    # when --app is explicit) is delayed until after startup.
    if (
        scenario_error is not None
        and not isinstance(scenario_error, ScenarioError)
        and args.app is None
    ):
        raise scenario_error
    app = args.app if args.app is not None else (
        None if scenario is None else scenario.get("app")
    )
    runtime_kwargs = dict(
        lvgl=args.lvgl,
        build=args.build,
        record=args.record,
    )
    if args.build_mode is not None:
        runtime_kwargs["build_mode"] = args.build_mode
    if app is not None:
        runtime_kwargs["app"] = app
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
        # Ctrl+C is the documented stop path. Before startup completes there
        # is no session to finish, so that case is a harness error, not "ok".
        interrupted = True
    except Exception as exc:  # noqa: BLE001 - the CLI maps every failure layer
        error = exc
    finally:
        # Let Runtime finish the manifest with the real failure layer even
        # when the error came from scenario validation or the CLI loop.
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
    """Block until Ctrl+C or until the engine exits (crash/EOF).

    Sleeping keeps the main thread interruptible; polling ``is_running`` lets
    ``--idle`` return as soon as the engine exits.
    """
    while runtime.is_running:
        time.sleep(IDLE_POLL_S)


def _report(error: Exception | None, *, as_json: bool, runtime: Runtime) -> None:
    if error is not None:
        print(f"[cli] {error}", file=sys.stderr)
    if as_json:
        payload = {
            "session_id": runtime.session_id,
            "manifest_path": (
                None if runtime.manifest_path is None else str(runtime.manifest_path)
            ),
            "app": getattr(runtime, "app", None),
            "error": dump_error(error),
        }
        _add_evidence(payload, runtime)
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return
    if error is None and runtime.session_dir is not None:
        print(runtime.session_dir)


def _add_evidence(payload: dict, runtime: Runtime) -> None:
    """Add ``summarize_session`` fields; a failed read keeps what is known."""
    if runtime.session_dir is None:
        return
    payload["session_dir"] = str(Path(runtime.session_dir).resolve())
    try:
        summary = summarize_session(runtime.session_dir)
    except Exception:  # noqa: BLE001 - evidence is optional for the CLI
        return
    for field in CLI_EVIDENCE_FIELDS:
        payload[field] = summary[field]


if __name__ == "__main__":
    raise SystemExit(main())
