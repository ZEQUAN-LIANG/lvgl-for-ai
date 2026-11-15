"""CMake/Ninja configure + build, with GCC diagnostics parsing.

The tool never decides whether a UI is correct; it only reports which layer
failed. Build output is kept verbatim in ``build.log``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .. import paths
from .errors import BuildError, LinkError

BUILD_TOOL_NAMES = ("cmake", "ninja", "gcc")
GCC_DIAG_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?:(?P<column>\d+):)?\s*"
    r"(?P<severity>fatal error|error|warning|note):\s*(?P<message>.*)$"
)
_LINK_MARKERS = (
    "undefined reference to",
    "multiple definition of",
    "ld returned",
    "collect2: error",
)
_UNRESOLVED_RE = re.compile(r"undefined reference to [`'\"]([^`'\"]+)[`'\"]")
_SEVERITY_RANK = {"fatal error": 0, "error": 1, "warning": 2, "note": 3}


@dataclass(frozen=True)
class BuildResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float

    @property
    def output(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


def configure_command(
    engine_dir: Path,
    build_dir: Path,
    *,
    lvgl_src: Path,
    lvgl_version: str,
    user_app_dir: Path,
    ccache: bool,
    zlib_src: Path | None = None,
    libpng_src: Path | None = None,
) -> list[str]:
    zlib_path = zlib_src if zlib_src is not None else paths.zlib_src()
    libpng_path = libpng_src if libpng_src is not None else paths.libpng_src()
    command = [
        "cmake",
        "-S",
        str(engine_dir),
        "-B",
        str(build_dir),
        "-G",
        "Ninja",
        "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
        "-DCMAKE_C_COMPILER=gcc",
        f"-DLVGL_AI_LVGL_SRC={lvgl_src}",
        f"-DLVGL_AI_LVGL_VERSION={lvgl_version}",
        f"-DLVGL_AI_USER_APP_DIR={user_app_dir}",
        f"-DLVGL_AI_ZLIB_SRC={zlib_path}",
        f"-DLVGL_AI_LIBPNG_SRC={libpng_path}",
    ]
    if ccache:
        command.append("-DCMAKE_C_COMPILER_LAUNCHER=ccache")
    return command


def build_command(build_dir: Path) -> list[str]:
    return ["cmake", "--build", str(build_dir), "--target", "lvgl_engine"]


def run_capture(
    command: Sequence[str],
    *,
    timeout: float | None,
    env: Mapping[str, str] | None = None,
) -> BuildResult:
    start = time.perf_counter()
    # cmake/ninja are console programs; when the web runs under pythonw this
    # stops each incremental build from flashing a console window.
    flags: dict[str, object] = {}
    if os.name == "nt":
        flags["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        **flags,
    )
    return BuildResult(
        command=list(command),
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        duration_ms=(time.perf_counter() - start) * 1000.0,
    )


def format_build_log(result: BuildResult, phase: str) -> str:
    return "\n".join(
        [
            f"# phase: {phase}",
            "# command: " + " ".join(str(part) for part in result.command),
            f"# exit_code: {result.returncode}",
            f"# duration_ms: {result.duration_ms:.1f}",
            "# --- stdout ---",
            result.stdout.rstrip(),
            "# --- stderr ---",
            result.stderr.rstrip(),
            "",
        ]
    )


def parse_diagnostics(text: str) -> tuple[list[dict], list[str], list[str]]:
    diagnostics: list[dict] = []
    link_lines: list[str] = []
    unresolved: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        match = GCC_DIAG_RE.match(line.strip())
        if match:
            column = match.group("column")
            diagnostics.append(
                {
                    "file": match.group("file"),
                    "line": int(match.group("line")),
                    "column": int(column) if column else None,
                    "severity": match.group("severity"),
                    "message": match.group("message"),
                    "raw": line,
                }
            )
            continue
        lowered = line.lower()
        if any(marker in lowered for marker in _LINK_MARKERS):
            link_lines.append(line)
            for symbol in _UNRESOLVED_RE.findall(line):
                if symbol not in unresolved:
                    unresolved.append(symbol)
    diagnostics.sort(key=lambda item: _SEVERITY_RANK.get(item["severity"], 9))
    return diagnostics, link_lines, unresolved


def build_failure(
    result: BuildResult, log_text: str
) -> BuildError | LinkError:
    diagnostics, link_lines, unresolved = parse_diagnostics(result.output)
    compiler_errors = [
        item
        for item in diagnostics
        if item["severity"] in ("fatal error", "error")
    ]
    if link_lines and not compiler_errors:
        return LinkError(
            "link failed: "
            + (link_lines[0].strip() or "unknown linker error"),
            unresolved_symbols=unresolved,
            log_text=log_text,
            command=result.command,
        )
    first = (
        compiler_errors[0]
        if compiler_errors
        else (diagnostics[0] if diagnostics else None)
    )
    if first is not None:
        message = (
            f"build failed: {first['file']}:{first['line']}"
            f"{':' + str(first['column']) if first['column'] else ''}: {first['message']}"
        )
    else:
        lines = [
            line.strip()
            for line in (result.stderr or result.stdout).splitlines()
            if line.strip()
        ]
        message = f"build failed: {lines[-1] if lines else 'see build.log'}"
    return BuildError(
        message,
        diagnostics=diagnostics,
        log_text=log_text,
        command=result.command,
    )


def needs_configure(
    build_dir: Path,
    *,
    lvgl_src: Path,
    lvgl_version: str,
    user_app_dir: Path,
    engine_dir: Path | None = None,
    zlib_src: Path | None = None,
    libpng_src: Path | None = None,
) -> bool:
    cache_path = build_dir / "CMakeCache.txt"
    # A failed configure can leave CMakeCache.txt without build.ninja; always
    # reconfigure in that case instead of letting ninja fail on a missing file.
    if not cache_path.is_file() or not (build_dir / "build.ninja").is_file():
        return True
    expected = {
        "LVGL_AI_LVGL_SRC": lvgl_src,
        "LVGL_AI_LVGL_VERSION": lvgl_version,
        "LVGL_AI_USER_APP_DIR": user_app_dir,
        "LVGL_AI_ZLIB_SRC": zlib_src
        if zlib_src is not None
        else paths.zlib_src(),
        "LVGL_AI_LIBPNG_SRC": (
            libpng_src if libpng_src is not None else paths.libpng_src()
        ),
        # Moving the checkout leaves the LVGL_AI_* values unchanged, but the
        # generated build files still embed the old engine directory.
        "CMAKE_HOME_DIRECTORY": paths.ENGINE_DIR
        if engine_dir is None
        else engine_dir,
    }
    cached = _read_cache(cache_path)
    for name, value in expected.items():
        entry = cached.get(name)
        if entry is None:
            return True
        if not _same_value(entry, value):
            return True
    return False


def _read_cache(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator:
            continue
        values[name.split(":", 1)[0]] = value
    return values


def _same_value(cached: str, expected: str | Path) -> bool:
    if isinstance(expected, Path):
        left = Path(cached)
        right = expected
        try:
            return os.path.normcase(str(left.resolve())) == os.path.normcase(
                str(right.resolve())
            )
        except OSError:
            return os.path.normcase(str(left)) == os.path.normcase(str(right))
    return cached == str(expected)


def ccache_available() -> bool:
    return shutil.which("ccache") is not None


def missing_build_tools() -> list[str]:
    return [name for name in BUILD_TOOL_NAMES if shutil.which(name) is None]


def build_environment_message(
    *,
    lvgl_src: Path,
    lvgl_version: str,
    missing_tools: Sequence[str],
    png_sources: Sequence[Path] = (),
) -> str:
    if not lvgl_src.is_dir():
        return (
            f"LVGL source not found: {lvgl_src}. Source builds need "
            f"lvgl-src/{lvgl_version} (or LVGL_AI_LVGL_SRC). Place an official "
            f"LVGL {lvgl_version} tree there; tools/fetch_lvgl.py can download "
            f"supported versions. If a build/ engine already exists, use "
            f"build=False / --no-build."
        )
    missing_png = [str(path) for path in png_sources if not path.is_dir()]
    if missing_png:
        return (
            "PNG encoder source not found: "
            + ", ".join(missing_png)
            + ". Run: python -I core/tools/fetch_png.py --repo-root ."
        )
    tools = ", ".join(missing_tools)
    return (
        f"build tools not found on PATH: {tools}. Source builds need "
        "CMake >= 3.20, Ninja and GCC (MinGW-w64). Install them and reopen "
        "the shell. If a build/ engine already exists, use build=False / "
        "--no-build."
    )
