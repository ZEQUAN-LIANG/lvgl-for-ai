#!/usr/bin/env python3
"""Unified entry for the distributable skill package.

``bin/lvgl.cmd`` calls this file from any working directory.  It only maps a
subcommand to the existing entry point; there is no second CLI:

- ``run``    -> ``core/cli.py`` (build and play a scenario)
- ``report`` -> ``core/session_report.py`` (read finished evidence)
- ``serve``  -> ``core/web.py`` (viewer and live bridge)
- ``assets`` -> ``core/assets.py`` (fonts/images to LVGL C arrays)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

COMMANDS = {
    "run": ("cli", "build and play a scenario, then print the session summary"),
    "report": ("session_report", "read a finished session's evidence"),
    "serve": ("web", "serve the viewer and live bridge on 127.0.0.1:8765"),
    "assets": ("assets", "generate LVGL C arrays from fonts and images"),
}


def _usage() -> str:
    lines = [
        "usage: lvgl <command> [options]",
        "",
        "commands:",
    ]
    for name, (_module, help_text) in COMMANDS.items():
        lines.append(f"  {name:<8} {help_text}")
    lines.append("")
    lines.append("Each command forwards to the same tool entry point:")
    lines.append("  lvgl run --scenario user/scenarios/settings.json --json")
    lines.append("  lvgl report --latest --log-tail 5")
    lines.append("  lvgl serve --port 8765")
    lines.append("  lvgl assets font --app myapp --font C:\\Windows\\Fonts\\Deng.ttf --size 16")
    lines.append("  lvgl assets image --app myapp --input logo.png --cf ARGB8888")
    lines.append("  lvgl assets doctor --json")
    return "\n".join(lines)


def _packaged_bundle() -> bool:
    """Return true when this is the release package with embedded Python."""
    version_path = Path(__file__).resolve().parent.parent.parent / "VERSION.json"
    try:
        payload = json.loads(version_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    python = payload.get("python") if isinstance(payload, dict) else None
    return isinstance(python, dict) and python.get("source") == "bundled"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(_usage(), file=sys.stderr)
        return 2
    if args[0] in ("-h", "--help"):
        print(_usage())
        return 0
    command = args.pop(0)
    entry = COMMANDS.get(command)
    if entry is None:
        print(f"[lvgl] unknown command: {command}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    if command == "run" and _packaged_bundle():
        build_flags = {"--build", "--no-build", "--prebuilt", "--source"}
        if not any(arg in build_flags for arg in args):
            # The release package ships a prebuilt engine but no compiler.
            # A bare ``run`` means "play the existing engine"; an explicit
            # build flag still rebuilds.
            args.append("--no-build")
    module_name = entry[0]
    module = __import__(module_name)
    return int(module.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
