#!/usr/bin/env python3
"""Create a user app variant through :mod:`lvgl_ai.apps`.

    python -I core/tools/new_app.py hello
    python -I core/tools/new_app.py hello --dry-run --json

The script never builds. C changes require a source build.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

# ``python -I`` does not add the script directory to sys.path.
TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import apps  # noqa: E402
from lvgl_ai.scenario import ScenarioError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="new_app.py",
        description=(
            "Create a user app variant, scenario, and apps[] registration."
        ),
    )
    parser.add_argument("name", help="app name: ^[a-z][a-z0-9_]{0,31}$")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="repository root (default: the tool's repository root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print planned changes without writing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite generated files and keep registration idempotent",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print exactly one JSON summary on stdout",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = apps.scaffold_app(
            apps.resolve_repo_root(args.repo_root),
            args.name,
            force=args.force,
            dry_run=args.dry_run,
        )
    except (apps.AppError, ScenarioError, OSError, ValueError) as exc:
        print(f"[new-app] error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        _print_human(result)
    return 0


def _print_human(result: dict[str, Any]) -> None:
    if not result["created"] and not result["updated"]:
        print("[new-app] up to date")
    prefix = "[new-app] would create" if result["dry_run"] else "[new-app] created"
    for path in result["created"]:
        print(f"{prefix} {path}")
    for path in result["updated"]:
        verb = "would update" if result["dry_run"] else "updated"
        print(f"[new-app] {verb} {path}")
    print("[new-app] build_required: true (new C code needs a source build)")
    for command in result["commands"]:
        print(f"[new-app] next: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
