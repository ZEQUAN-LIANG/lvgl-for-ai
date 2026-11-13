"""Build the Windows double-click launchers and their icons."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

LAUNCHERS_DIR = Path(__file__).resolve().parent
CORE_ROOT = LAUNCHERS_DIR.parent.parent
for _path in (CORE_ROOT, LAUNCHERS_DIR):
    _text = str(_path)
    if _text not in sys.path:
        sys.path.insert(0, _text)

import icons  # noqa: E402
from lvgl_ai.paths import REPO_ROOT  # noqa: E402

BUILD_DIR = REPO_ROOT / "build" / "launchers"

LAUNCHERS = (
    {
        "name": "lvgl-ai-viewer",
        "title": "LVGL AI Viewer",
        "target": r"core\web.pyw",
        "cwd": ".",
        "args": (),
        "output": REPO_ROOT / "LVGL-AI-Viewer.exe",
    },
    {
        "name": "sifli-host",
        "title": "SiFli Host",
        "target": r"..\host\server.py",
        "cwd": r"..\host",
        "args": ("--open",),
        "output": REPO_ROOT / "chip-adapt" / "sifli" / "tools" / "SiFli-Host.exe",
    },
)


class BuildError(Exception):
    pass


def _wide_literal(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'L"{escaped}"'


def _write_config(entry: dict) -> Path:
    config_dir = BUILD_DIR / entry["name"]
    config_dir.mkdir(parents=True, exist_ok=True)
    args = " ".join(entry["args"])
    args_literal = _wide_literal(f" {args}") if args else 'L""'
    lines = (
        f"#define LAUNCHER_TITLE {_wide_literal(entry['title'])}",
        f"#define LAUNCHER_TARGET {_wide_literal(entry['target'])}",
        f"#define LAUNCHER_CWD {_wide_literal(entry['cwd'])}",
        f"#define LAUNCHER_ARGS {args_literal}",
    )
    (config_dir / "config.h").write_text("\n".join(lines) + "\n", encoding="ascii")
    return config_dir


def _toolchain() -> tuple:
    gcc = shutil.which("gcc")
    if gcc is None:
        raise BuildError("gcc was not found in PATH; install MinGW-w64 and retry")
    windres = Path(gcc).with_name("windres.exe")
    if not windres.is_file():
        found = shutil.which("windres")
        if found is None:
            raise BuildError("windres.exe was not found next to gcc or in PATH")
        windres = Path(found)
    return Path(gcc), windres


def _build(entry: dict, gcc: Path, windres: Path) -> None:
    config_dir = _write_config(entry)
    resource = BUILD_DIR / f"{entry['name']}.res.o"
    temp_dir = BUILD_DIR / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(temp_dir)
    env["TEMP"] = str(temp_dir)
    env["TMPDIR"] = str(temp_dir)
    subprocess.run(
        [
            str(windres),
            "--use-temp-file",
            "-O",
            "coff",
            "-i",
            f"{entry['name']}.rc",
            "-o",
            str(resource),
        ],
        cwd=LAUNCHERS_DIR,
        env=env,
        check=True,
    )
    output = Path(entry["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(gcc),
            "-Os",
            "-s",
            "-Wall",
            "-Wextra",
            "-mwindows",
            "-I",
            str(config_dir),
            "-o",
            str(output),
            str(LAUNCHERS_DIR / "launcher.c"),
            str(resource),
        ],
        cwd=LAUNCHERS_DIR,
        env=env,
        check=True,
    )


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Windows launcher executables.")
    parser.parse_args(argv)
    if os.name != "nt":
        print("[launchers] error: the launchers can only be built on Windows", file=sys.stderr)
        return 1
    try:
        for path in icons.write_all(icons.ICON_DIR):
            print(f"[launchers] wrote {path}")
        gcc, windres = _toolchain()
        for entry in LAUNCHERS:
            _build(entry, gcc, windres)
            print(f"[launchers] wrote {entry['output']}")
    except (BuildError, subprocess.CalledProcessError) as exc:
        print(f"[launchers] error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
