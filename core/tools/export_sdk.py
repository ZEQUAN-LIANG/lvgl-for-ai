#!/usr/bin/env python3
"""Export a prebuilt host SDK for one LVGL version.

The SDK holds the five static libraries the engine and user apps need
(LVGL, adapter, engine, libpng, zlib), the public LVGL and PNG headers,
``lv_conf.h`` and a manifest (``lvgl-ai-host-sdk-v1``) with the compiler,
defines, include order, link order and hashes.  A package with ``sdk/<ver>``
can build ``user/app`` without ``lvgl-src`` or CMake.

Usage::

    python -I core/tools/export_sdk.py --version 9.6 --out sdk/9.6

The build is a Release configuration built by the existing CMake engine
project.  The executable and the exported ``libengine.a`` come from the same
``engine_core`` object library.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Sequence

_BOOTSTRAP_TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402
from lvgl_ai.control.build import (  # noqa: E402
    BuildResult,
    build_failure,
    format_build_log,
    missing_build_tools,
    run_capture,
)
from lvgl_ai.control.errors import BuildError  # noqa: E402
from lvgl_ai.control.prebuilt import REQUIRED_LIBS, SDK_SCHEMA  # noqa: E402
from lvgl_ai.digest import sha256_file  # noqa: E402

SOURCE_SCHEMA = "lvgl-ai-lvgl-source-v1"

DEFINES = ["LV_CONF_INCLUDE_SIMPLE", "LV_KCONFIG_IGNORE", "LV_LVGL_H_INCLUDE_SIMPLE"]
CFLAGS = ["-std=gnu11", "-O2", "-Wall", "-Wextra"]
LINK_FLAGS = ["-lgdi32", "-luser32", "-static-libgcc"]

EXPORT_TIMEOUT_S = 900.0


def _platform_tag() -> str:
    bits = struct.calcsize("P") * 8
    if sys.platform == "win32":
        return f"win{bits}"
    if sys.platform.startswith("linux"):
        return f"linux{bits}"
    return f"{sys.platform}{bits}"


def _compiler_id(version_text: str) -> str:
    return "mingw-w64-gcc" if "mingw" in version_text.lower() else "gcc"


def _latest_compiler_version(compiler: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except OSError as exc:
        raise BuildError(f"cannot run C compiler {compiler}: {exc}") from exc
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", text)
    if result.returncode != 0 or match is None:
        raise BuildError(
            f"cannot read the C compiler version from {compiler}: "
            f"{text.strip()[:200]}"
        )
    return match.group(1), _compiler_id(text)


def _run(command: Sequence[str], phase: str) -> str:
    result: BuildResult = run_capture(
        command,
        timeout=EXPORT_TIMEOUT_S,
        env=os.environ.copy(),
    )
    log_text = format_build_log(result, phase)
    if result.returncode != 0:
        raise build_failure(result, log_text)
    return log_text


def _read_source_tag(source_dir: Path) -> str:
    stamp = source_dir / ".lvgl-ai-source.json"
    try:
        payload = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    if isinstance(payload, dict) and payload.get("schema") == SOURCE_SCHEMA:
        tag = payload.get("tag")
        if isinstance(tag, str):
            return tag
    return "unknown"


def _copy_headers(source: Path, out: Path) -> list[str]:
    """Copy public LVGL, zlib and libpng headers; return include order."""
    include_dir = out / "include"
    include_dir.mkdir(parents=True, exist_ok=True)

    public = source / "include" / "lvgl"
    if not public.is_dir():
        raise BuildError(
            f"LVGL source does not use the 9.6 include/lvgl layout: {source}. "
            "This ticket exports LVGL 9.6 host SDKs only."
        )
    shutil.copytree(public, include_dir / "lvgl")
    include_dirs = [".", "include", "include/lvgl"]

    zlib_src = paths.zlib_src()
    for path in sorted(zlib_src.glob("*.h")):
        shutil.copy2(path, include_dir / path.name)

    libpng_src = paths.libpng_src()
    for name in ("png.h", "pngconf.h"):
        path = libpng_src / name
        if not path.is_file():
            raise BuildError(f"libpng header not found: {path}")
        shutil.copy2(path, include_dir / name)
    generated = libpng_src / "scripts" / "pnglibconf.h.prebuilt"
    if not generated.is_file():
        raise BuildError(f"libpng prebuilt config not found: {generated}")
    shutil.copy2(generated, include_dir / "pnglibconf.h")
    return include_dirs


def export_sdk(
    *,
    version: str,
    out_dir: Path,
    source_dir: Path | None = None,
    repo_root: Path | None = None,
    force: bool = False,
    compiler: str | None = None,
) -> dict:
    """Build one host SDK and write its manifest; return the manifest."""
    repo = (repo_root or paths.REPO_ROOT).resolve()
    source = (
        Path(source_dir).expanduser().resolve()
        if source_dir is not None
        else paths.lvgl_src_for(version)
    )
    if not source.is_dir():
        raise BuildError(
            f"LVGL source not found: {source}. Run: "
            f"python -I core/tools/fetch_lvgl.py --version {version} --repo-root ."
        )
    missing = missing_build_tools()
    if missing:
        raise BuildError(
            "build tools not found on PATH: " + ", ".join(missing),
            command=["cmake"],
        )
    bundled = paths.REPO_ROOT / "runtime" / "mingw64" / "bin" / (
        "gcc.exe" if os.name == "nt" else "gcc"
    )
    chosen = (
        compiler
        or (str(bundled) if bundled.is_file() else None)
        or os.environ.get("LVGL_AI_GCC")
        or shutil.which("gcc")
    )
    if not chosen:
        raise BuildError(
            "C compiler not found: expected runtime/mingw64, LVGL_AI_GCC, "
            "or gcc on PATH"
        )
    compiler_version, compiler_id = _latest_compiler_version(chosen)

    out = Path(out_dir).expanduser().resolve()
    if out.exists():
        if not force:
            raise BuildError(
                f"host SDK directory already exists: {out}; pass --force to rebuild"
            )
        shutil.rmtree(out)
    out.mkdir(parents=True)
    lib_dir = out / "lib"
    lib_dir.mkdir()

    token = paths.version_token(version)
    build_dir = repo / "build" / f"sdk_{token}"
    configure = [
        "cmake",
        "-S", str(paths.ENGINE_DIR),
        "-B", str(build_dir),
        "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG",
        "-DCMAKE_C_COMPILER=" + chosen,
        f"-DLVGL_AI_LVGL_SRC={source}",
        f"-DLVGL_AI_LVGL_VERSION={version}",
        f"-DLVGL_AI_LVGL_SRC_LABEL=prebuilt-{version}",
        f"-DLVGL_AI_FILE_PREFIX_MAP={repo}",
        f"-DLVGL_AI_LVGL_SRC_PREFIX_MAP={source}",
        f"-DLVGL_AI_USER_APP_DIR={repo / 'user' / 'app'}",
        f"-DLVGL_AI_ZLIB_SRC={paths.zlib_src()}",
        f"-DLVGL_AI_LIBPNG_SRC={paths.libpng_src()}",
        f"-DLVGL_AI_SDK_LIBS_DIR={lib_dir}",
    ]
    _run(configure, "configure")
    _run(
        ["cmake", "--build", str(build_dir), "--target", "lvgl_ai_sdk"],
        "build",
    )

    missing_libs = [name for name in REQUIRED_LIBS if not (lib_dir / name).is_file()]
    if missing_libs:
        raise BuildError(
            "SDK export did not produce " + ", ".join(missing_libs)
        )

    include_dirs = _copy_headers(source, out)
    lv_conf = paths.ENGINE_DIR / "lv_conf.h"
    shutil.copy2(lv_conf, out / "lv_conf.h")

    manifest = {
        "schema": SDK_SCHEMA,
        "lvgl_version": version,
        "lvgl_tag": _read_source_tag(source),
        "platform": _platform_tag(),
        "tool_version": paths.TOOL_VERSION,
        "compiler": {
            "id": compiler_id,
            "version": compiler_version,
        },
        "defines": list(DEFINES),
        "cflags": list(CFLAGS),
        "include_dirs": include_dirs,
        "libs": list(REQUIRED_LIBS),
        "link_flags": list(LINK_FLAGS),
        "source_label": f"prebuilt-{version}",
        "lv_conf_sha256": sha256_file(out / "lv_conf.h"),
        "sha256": {
            name: sha256_file(lib_dir / name) for name in REQUIRED_LIBS
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "sdk": str(out),
        "manifest": str(manifest_path),
        "lvgl_version": version,
        "compiler": manifest["compiler"],
        "libs": list(REQUIRED_LIBS),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_sdk.py",
        description=(
            "Export a prebuilt host SDK (libraries, headers, lv_conf.h and "
            "manifest) for one LVGL version."
        ),
    )
    parser.add_argument(
        "--version",
        default=None,
        help="LVGL version (default: LVGL_AI_LVGL_VERSION or 9.6)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="SDK output directory (default: <repo>/sdk/<version>)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="LVGL source tree (default: lvgl-src/<version>)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="workspace root (default: detected from the tool location)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing SDK directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one JSON summary on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    version = args.version or paths.lvgl_version_from_env()
    repo = (args.repo_root or paths.REPO_ROOT).resolve()
    out = args.out or (repo / "sdk" / version)
    try:
        summary = export_sdk(
            version=version,
            out_dir=out,
            source_dir=args.source,
            repo_root=repo,
            force=args.force,
        )
    except BuildError as exc:
        print(f"[sdk] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    else:
        print(f"[sdk] exported LVGL {version} host SDK -> {summary['sdk']}")
        print(f"[sdk] manifest: {summary['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
