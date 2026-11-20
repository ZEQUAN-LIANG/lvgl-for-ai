#!/usr/bin/env python3
"""ESP32-C6 Arduino bring-up adapter for the PERF TAPE app.

This is a deliberately small, temporary adapter.  The official ESP32-C6
exporter/firmware shell is still ESP-IDF based; this path generates a
self-contained Arduino sketch so the board, display, LVGL 9.6 rotation and the
serial protocol can be exercised now.

It never writes into ``user/app`` or ``engine/lvgl``.  Sources are copied to
``chip-adapt/exports/esp32/perf_monitor_arduino/`` (git-ignored).  By default
only changed files are rewritten and the Arduino build cache is preserved, so
repeat builds are incremental; ``--force`` cleans and rebuilds everything.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Sequence

ADAPTER_DIR = Path(__file__).resolve().parent
REPO_ROOT = ADAPTER_DIR.parents[2]
DEFAULT_APP = "perf_monitor"
LVGL_DIR = REPO_ROOT / "engine" / "lvgl" / "9.6"
VENDOR_ZIP = (
    REPO_ROOT
    / "chip-adapt"
    / "vendor"
    / "esp32"
    / "demo"
    / "ESP32-C6-LCD-1.47-Demo.zip"
)
HOST_CLI = REPO_ROOT / "chip-adapt" / "esp32" / "host" / "host.py"


def app_dir(app: str) -> Path:
    return REPO_ROOT / "user" / "app" / app


def default_out(app: str) -> Path:
    return REPO_ROOT / "chip-adapt" / "exports" / "esp32" / f"{app}_arduino"


def required_app_files(app: str) -> tuple[str, ...]:
    """Sources every app must provide for this adapter to build.

    ``perf_protocol`` is specific to the PERF TAPE demo, so only the two
    per-app files are universal.
    """

    return (f"{app}.c", f"{app}.h")


TEMPLATES_DIR = ADAPTER_DIR / "templates"
DISPLAY_FILES = ("Display_ST7789.cpp", "Display_ST7789.h")
DISPLAY_PREFIX = "Arduino/examples/LVGL_Arduino/"
LVGL_ITEMS = (
    "lvgl.h",
    "lvgl_private.h",
    "lv_version.h",
    "library.properties",
    "LICENCE.txt",
    "src",
    "include",
)
BUILD_FLAGS = "-DLV_CONF_INCLUDE_SIMPLE -DARDUINO_LOOP_STACK_SIZE=16384"
DEFAULT_FQBN = "esp32:esp32:esp32c6:CDCOnBoot=cdc,PartitionScheme=huge_app"
SKETCH_NAME = "perf_c6"
MERGED_BIN = f"{SKETCH_NAME}.ino.merged.bin"


class AdapterError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_template(name: str) -> bytes:
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise AdapterError("template_missing", f"template not found: {path}")
    return path.read_bytes()


def patch_lvgl_include(text: str) -> str:
    """Generated font headers use the SDK include path; Arduino uses ``lvgl.h``."""

    return text.replace('"lvgl/lvgl.h"', '"lvgl.h"').replace(
        "<lvgl/lvgl.h>", "<lvgl.h>"
    )


def _app_sources(app: str, app_dir: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if not app_dir.is_dir():
        raise AdapterError("app_missing", f"app directory not found: {app_dir}")
    for path in sorted(app_dir.iterdir()):
        if not path.is_file() or path.suffix not in (".c", ".h"):
            continue
        data = path.read_bytes()
        if path.suffix == ".h":
            data = patch_lvgl_include(
                data.decode("utf-8-sig")
            ).encode("utf-8")
        files[path.name] = data
    if not files:
        raise AdapterError(
            "app_missing", f"no .c/.h sources found in {app_dir}"
        )
    missing = [name for name in required_app_files(app) if name not in files]
    if missing:
        raise AdapterError(
            "app_missing",
            f"required app files missing: {', '.join(missing)}",
        )
    return files


def _display_sources(vendor_zip: Path) -> dict[str, bytes]:
    if not vendor_zip.is_file():
        raise AdapterError(
            "vendor_missing",
            f"vendor demo zip not found: {vendor_zip}",
        )
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(vendor_zip) as archive:
        for name in DISPLAY_FILES:
            member = DISPLAY_PREFIX + name
            try:
                files[name] = archive.read(member)
            except KeyError as exc:
                raise AdapterError(
                    "vendor_missing",
                    f"{member} is missing from {vendor_zip}",
                ) from exc
    return files


def _copy_if_changed(source: Path, target: Path) -> bool:
    if target.is_file():
        if target.stat().st_size == source.stat().st_size and filecmp.cmp(
            source, target, shallow=False
        ):
            return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _copy_lvgl(lvgl_dir: Path, destination: Path, *, dry_run: bool) -> list[str]:
    if not lvgl_dir.is_dir():
        raise AdapterError("lvgl_missing", f"LVGL source not found: {lvgl_dir}")
    found: list[str] = []
    changed: list[str] = []
    for item in LVGL_ITEMS:
        source = lvgl_dir / item
        if not source.exists():
            continue
        target = destination / item
        found.append(str(target))
        if dry_run:
            changed.append(str(target))
            continue
        if source.is_dir():
            for child in source.rglob("*"):
                relative = child.relative_to(source)
                child_target = target / relative
                if child.is_dir():
                    child_target.mkdir(parents=True, exist_ok=True)
                    continue
                if _copy_if_changed(child, child_target):
                    changed.append(str(child_target))
        else:
            if _copy_if_changed(source, target):
                changed.append(str(target))
    if not found:
        raise AdapterError(
            "lvgl_missing", f"no LVGL library files found in {lvgl_dir}"
        )
    return changed


def _write_plan(
    out_dir: Path,
    files: dict[str, bytes],
    *,
    dry_run: bool,
) -> list[str]:
    written: list[str] = []
    for relative, data in sorted(files.items()):
        target = out_dir / relative
        if dry_run:
            written.append(str(target))
            continue
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(str(target))
    return written


def prepare_workspace(
    *,
    app: str = DEFAULT_APP,
    out_dir: Path | None = None,
    app_dir_override: Path | None = None,
    lvgl_dir: Path = LVGL_DIR,
    vendor_zip: Path = VENDOR_ZIP,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create the Arduino sketch and the bundled LVGL library."""

    resolved_app_dir = (
        app_dir_override if app_dir_override is not None else app_dir(app)
    )
    resolved_out = (
        Path(out_dir).resolve() if out_dir is not None else default_out(app)
    )
    out_dir = resolved_out
    sketch_dir = out_dir / SKETCH_NAME
    libraries_dir = out_dir / "libraries"

    if force and not dry_run:
        for relative in (SKETCH_NAME, Path("libraries") / "lvgl", "build"):
            target = out_dir / relative
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()

    files: dict[str, bytes] = {
        f"{SKETCH_NAME}/{SKETCH_NAME}.ino": _load_template(
            f"{SKETCH_NAME}.ino"
        ),
        f"{SKETCH_NAME}/ble_uart.h": _load_template("ble_uart.h"),
        f"{SKETCH_NAME}/ble_uart.cpp": _load_template("ble_uart.cpp"),
        f"{SKETCH_NAME}/lv_conf.h": _load_template("lv_conf.h"),
        f"{SKETCH_NAME}/app.h": _load_template("app.h"),
    }
    for name, data in _app_sources(app, resolved_app_dir).items():
        files[f"{SKETCH_NAME}/{name}"] = data
    for name, data in _display_sources(vendor_zip).items():
        files[f"{SKETCH_NAME}/{name}"] = data

    written_files = _write_plan(out_dir, files, dry_run=dry_run)
    if not dry_run:
        expected = {
            Path(relative).name
            for relative in files
            if relative.startswith(SKETCH_NAME + "/")
        }
        for path in sketch_dir.iterdir():
            if (
                path.is_file()
                and path.suffix in {".c", ".h", ".ino"}
                and path.name not in expected
            ):
                path.unlink()
    lvgl_files = _copy_lvgl(
        lvgl_dir, libraries_dir / "lvgl", dry_run=dry_run
    )
    return {
        "out_dir": str(out_dir),
        "sketch_dir": str(sketch_dir),
        "libraries_dir": str(libraries_dir),
        "files": written_files + lvgl_files,
        "dry_run": dry_run,
    }


def arduino_cli_path(explicit: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("ARDUINO_CLI"):
        candidates.append(os.environ["ARDUINO_CLI"])
    found = shutil.which("arduino-cli")
    if found:
        candidates.append(found)
    candidates.extend(
        [
            r"C:\Program Files\Arduino CLI\arduino-cli.exe",
            r"C:\Program Files (x86)\Arduino CLI\arduino-cli.exe",
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return str(path)
    raise AdapterError(
        "arduino_cli_missing",
        "arduino-cli not found; install it or set ARDUINO_CLI",
    )


def build_command(
    *,
    arduino_cli: str,
    out_dir: Path,
    fqbn: str,
) -> list[str]:
    return [
        arduino_cli,
        "compile",
        "--fqbn",
        fqbn,
        "--libraries",
        str(out_dir / "libraries"),
        "--build-path",
        str(out_dir / "build"),
        "--build-property",
        f"compiler.c.extra_flags={BUILD_FLAGS}",
        "--build-property",
        f"compiler.cpp.extra_flags={BUILD_FLAGS}",
        str(out_dir / SKETCH_NAME),
    ]


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdapterError("command_failed", str(exc)) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AdapterError(
            "command_failed",
            detail[-2000:] or f"command failed: {' '.join(command)}",
        )
    return completed


def build_workspace(
    *,
    out_dir: Path,
    arduino_cli: str | None = None,
    fqbn: str = DEFAULT_FQBN,
    dry_run: bool = False,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    cli = arduino_cli
    if not cli:
        cli = "arduino-cli" if dry_run else arduino_cli_path()
    command = build_command(
        arduino_cli=cli,
        out_dir=out_dir,
        fqbn=fqbn,
    )
    if dry_run:
        return {"out_dir": str(out_dir), "command": command, "dry_run": True}
    completed = _run(command)
    merged = out_dir / "build" / MERGED_BIN
    if not merged.is_file():
        raise AdapterError(
            "build_output_missing", f"build did not produce {merged}"
        )
    output = (completed.stdout + completed.stderr).strip()
    return {
        "out_dir": str(out_dir),
        "command": command,
        "merged_bin": str(merged),
        "output_tail": output[-1000:],
        "dry_run": False,
    }


def flash_command(
    *,
    merged_bin: Path,
    port: str,
    host_url: str,
) -> list[str]:
    return [
        sys.executable,
        "-I",
        str(HOST_CLI),
        "flash",
        "--url",
        host_url,
        "--file",
        str(merged_bin),
        "--address",
        "0x0",
        "--port",
        port,
        "--json",
    ]


def _last_json_line(text: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return None


def _flash_ok(payload: dict[str, Any]) -> bool:
    """Host flash jobs report status/result, not a top-level ok."""

    result = payload.get("result")
    if isinstance(result, dict) and "ok" in result:
        return result.get("ok") is True
    return payload.get("ok") is True or payload.get("status") == "ok"


def flash_workspace(
    *,
    out_dir: Path,
    port: str,
    host_url: str = "http://127.0.0.1:8767",
    dry_run: bool = False,
) -> dict[str, Any]:
    merged = out_dir.resolve() / "build" / MERGED_BIN
    if not dry_run and not merged.is_file():
        raise AdapterError("image_missing", f"firmware not built: {merged}")
    command = flash_command(
        merged_bin=merged, port=port, host_url=host_url
    )
    if dry_run:
        return {"command": command, "dry_run": True}
    completed = _run(command, timeout=300)
    payload = _last_json_line(completed.stdout)
    if payload is None or not _flash_ok(payload):
        raise AdapterError(
            "flash_failed",
            (completed.stdout or completed.stderr).strip()[-2000:],
        )
    return {"job": payload, "command": command, "dry_run": False}


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--app",
        default=DEFAULT_APP,
        help=(
            "app directory under user/app to export "
            f"(default: {DEFAULT_APP})"
        ),
    )
    parser.add_argument(
        "--out",
        default="",
        help="output directory (default: exports/esp32/<app>_arduino)",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--arduino-cli", default="")
    parser.add_argument("--fqbn", default=DEFAULT_FQBN)


def _print(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    if payload.get("files"):
        print(f"workspace: {payload['out_dir']}")
        print(f"files: {len(payload['files'])}")
    if payload.get("command"):
        print("command:", " ".join(payload["command"]))
    if payload.get("merged_bin"):
        print(f"firmware: {payload['merged_bin']}")
    job = payload.get("job")
    if isinstance(job, dict):
        print(f"flash: {job.get('status')} ({job.get('id')})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser("export", help="generate the Arduino sketch")
    _add_common(export_parser)

    build_parser = sub.add_parser("build", help="export (unless --no-export) and compile")
    _add_common(build_parser)
    build_parser.add_argument("--no-export", action="store_true")

    flash_parser = sub.add_parser("flash", help="flash the built merged image through the host")
    _add_common(flash_parser)
    flash_parser.add_argument("--port", required=True)
    flash_parser.add_argument(
        "--host-url", default="http://127.0.0.1:8767"
    )

    all_parser = sub.add_parser("all", help="export, build and flash")
    _add_common(all_parser)
    all_parser.add_argument("--port", required=True)
    all_parser.add_argument(
        "--host-url", default="http://127.0.0.1:8767"
    )

    args = parser.parse_args(argv)
    app = args.app
    out_dir = (
        Path(args.out).expanduser()
        if args.out
        else default_out(app)
    )

    try:
        if args.command == "export":
            payload = prepare_workspace(
                app=app,
                out_dir=out_dir,
                force=args.force,
                dry_run=args.dry_run,
            )
            payload.update({"ok": True, "action": "export"})
            _print(payload, as_json=args.json)
            return 0

        if args.command == "build":
            if not args.no_export:
                prepare_workspace(
                    app=app,
                    out_dir=out_dir,
                    force=args.force,
                    dry_run=args.dry_run,
                )
            payload = build_workspace(
                out_dir=out_dir,
                arduino_cli=args.arduino_cli or None,
                fqbn=args.fqbn,
                dry_run=args.dry_run,
            )
            payload.update({"ok": True, "action": "build"})
            _print(payload, as_json=args.json)
            return 0

        if args.command == "flash":
            payload = flash_workspace(
                out_dir=out_dir,
                port=args.port,
                host_url=args.host_url,
                dry_run=args.dry_run,
            )
            payload.update({"ok": True, "action": "flash"})
            _print(payload, as_json=args.json)
            return 0

        if args.command == "all":
            export_payload = prepare_workspace(
                app=app,
                out_dir=out_dir,
                force=args.force,
                dry_run=args.dry_run,
            )
            build_payload = build_workspace(
                out_dir=out_dir,
                arduino_cli=args.arduino_cli or None,
                fqbn=args.fqbn,
                dry_run=args.dry_run,
            )
            flash_payload = flash_workspace(
                out_dir=out_dir,
                port=args.port,
                host_url=args.host_url,
                dry_run=args.dry_run,
            )
            payload = {
                "ok": True,
                "action": "all",
                "export": export_payload,
                "build": build_payload,
                "flash": flash_payload,
            }
            _print(payload, as_json=args.json)
            return 0
    except AdapterError as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": exc.code, "message": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
