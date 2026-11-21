from __future__ import annotations

import sys
from pathlib import Path

CONSOLE_ROOT = Path(__file__).resolve().parent.parent / "console"
ENTRYPOINTS_DIR = CONSOLE_ROOT / "entrypoints"
for _path in (ENTRYPOINTS_DIR, CONSOLE_ROOT):
    _text = str(_path)
    if _text not in sys.path:
        sys.path.insert(0, _text)

import paths

COMMANDS = {
    "run": (
        "cli",
        "build and play a scenario, then print the session summary",
    ),
    "report": ("session_report", "read a finished session's evidence"),
    "serve": ("serve", "serve the viewer and live bridge on 127.0.0.1:8765"),
    "assets": (
        "assets_tool",
        "generate LVGL C arrays from fonts and images",
    ),
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
    lines.append(
        "  lvgl assets font --app myapp --font C:\\Windows\\Fonts\\Deng.ttf --size 16"
    )
    lines.append(
        "  lvgl assets image --app myapp --input logo.png --cf ARGB8888"
    )
    lines.append("  lvgl assets doctor --json")
    return "\n".join(lines)


def _packaged_bundle() -> bool:
    if not (paths.REPO_ROOT / "SKILL.md").is_file():
        return False
    version = paths.default_lvgl_version()
    engine = paths.build_dir_for(version) / paths.engine_filename()
    return engine.is_file()


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
            args.append("--no-build")
    module_name = entry[0]
    module = __import__(module_name)
    return int(module.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
