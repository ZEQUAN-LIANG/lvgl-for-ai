#!/usr/bin/env python3
"""Build the distributable skill zip from this workspace.

One command produces the package directory, zip, ``.sha256`` and release
manifest.  The default package is host-only: tool layer, ``user/``, the
prebuilt host SDK, a prebuilt engine, ``bin/lvgl.cmd`` and ``SKILL.md``.  LVGL
source, third-party source, sessions, tests and chip adapter trees never enter
the package.

Smoke runs inside the staging directory from an unrelated working directory
before the zip is written: ``--no-build``, a prebuilt build, and the web
server.  ``--skip-smoke`` exists only for development.

Usage::

    python -I core/tools/release.py
    python -I core/tools/release.py --lvgl 9.6 --out dist --json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable

_BOOTSTRAP_TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402
from lvgl_ai.control.build_plan import BuildPlan  # noqa: E402
from lvgl_ai.control.errors import BuildError  # noqa: E402
from lvgl_ai.digest import sha256_file  # noqa: E402

TOOL_ROOT = paths.TOOL_ROOT
REPO_ROOT = paths.REPO_ROOT
TOOLS_DIR = TOOL_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import export_sdk  # noqa: E402

PACKAGE_DIR_NAME = "lvgl-ai-new"
RELEASE_SCHEMA = "lvgl-ai-release-v1"
VERSION_SCHEMA = "lvgl-ai-version-v1"
DEFAULT_LVGL = paths.DEFAULT_LVGL_VERSION
SMOKE_SCENARIO = Path("user") / "scenarios" / "settings.json"
FORBIDDEN_TOP_LEVEL = {
    ".git", "chip-adapt", "dist", "lvgl-src", "patches", "sessions",
    "tests", "third_party", ".scratch",
}
FORBIDDEN_ANY_LEVEL = {"__pycache__"}
CORE_EXCLUDE_DIRS = {"tests", "__pycache__", ".cache"}
USER_EXCLUDE_DIRS = {".trash", "__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".dump"}


def _run(command: Iterable[str], *, cwd: Path, env: dict[str, str] | None = None,
         timeout: float = 300.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def copy_tree(
    source: str | Path,
    target: str | Path,
    *,
    exclude_dirs: Iterable[str] = (),
    exclude_files: Iterable[str] = (),
    exclude_suffixes: Iterable[str] = (),
) -> None:
    """Copy ``source`` below ``target`` with name/suffix exclusions."""
    source_path = Path(source)
    target_path = Path(target)
    excluded_dirs = set(exclude_dirs)
    excluded_files = set(exclude_files)
    excluded_suffixes = set(exclude_suffixes)
    for path in sorted(source_path.rglob("*")):
        relative = path.relative_to(source_path)
        if any(part in excluded_dirs for part in relative.parts):
            continue
        if path.is_dir() or not path.is_file():
            continue
        if path.name in excluded_files or path.suffix in excluded_suffixes:
            continue
        destination = target_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    text = result.stdout.strip()
    return text if result.returncode == 0 and text else "unknown"


def write_version_file(
    package: Path,
    *,
    tool_version: str,
    lvgl_version: str,
    gcc_version: str,
    git_commit: str,
    adapters: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": VERSION_SCHEMA,
        "tool_version": tool_version,
        "lvgl": {
            "host_default": lvgl_version,
            "host_sdk": [lvgl_version],
        },
        "python": {
            "version": platform.python_version(),
            "source": "system",
        },
        "gcc": {"version": gcc_version, "source": "system"},
        "git_commit": git_commit,
        "adapters": list(adapters or []),
    }
    (package / "VERSION.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def check_hygiene(package: Path, repo_root: Path) -> None:
    """Reject forbidden trees, build intermediates and development paths."""
    package = package.resolve()
    for child in package.iterdir():
        if child.name in FORBIDDEN_TOP_LEVEL:
            raise BuildError(
                f"release hygiene: forbidden top-level entry {child.name!r}"
            )
    for path in package.rglob("*"):
        if path.name in FORBIDDEN_ANY_LEVEL:
            raise BuildError(
                f"release hygiene: cache directory entered the package: {path}"
            )
        if path.suffix in EXCLUDE_SUFFIXES:
            raise BuildError(
                f"release hygiene: excluded file entered the package: {path}"
            )
    build_root = package / "build"
    if build_root.is_dir():
        for path in build_root.rglob("*"):
            if path.is_file() and path.name != paths.engine_filename():
                raise BuildError(
                    "release hygiene: build intermediate entered the package: "
                    f"{path.relative_to(package)}"
                )
    paths_to_hide = {str(repo_root.resolve()), str(Path.home().resolve())}
    needles = set()
    for value in paths_to_hide:
        # Native and forward-slash spellings both appear in binaries.
        needles.add(value.encode("utf-8"))
        needles.add(value.replace("\\", "/").encode("utf-8"))
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise BuildError(f"release hygiene: cannot read {path}: {exc}") from exc
        for needle in needles:
            if needle and needle in data:
                raise BuildError(
                    "release hygiene: development absolute path "
                    f"{needle.decode('utf-8', 'replace')!r} in "
                    f"{path.relative_to(package)}"
                )


def stage_package(
    *,
    repo_root: Path,
    package: Path,
    sdk_dir: Path,
    lvgl_version: str,
    tool_version: str,
    compiler: str | None = None,
    compiler_version: str | None = None,
) -> dict[str, Any]:
    """Copy the allowlisted tree and build the package's engine."""
    package.mkdir(parents=True)
    for name in ("SKILL.md", "CONTEXT.md", "LICENSE"):
        source = repo_root / name
        if source.is_file():
            shutil.copy2(source, package / name)
    copy_tree(
        repo_root / "core", package / "core",
        exclude_dirs=CORE_EXCLUDE_DIRS,
        exclude_suffixes=EXCLUDE_SUFFIXES,
    )
    copy_tree(
        repo_root / "user", package / "user",
        exclude_dirs=USER_EXCLUDE_DIRS,
        exclude_suffixes=EXCLUDE_SUFFIXES,
    )
    copy_tree(repo_root / "licenses", package / "licenses")
    copy_tree(repo_root / "bin", package / "bin")
    if not (repo_root / "bin" / "lvgl.cmd").is_file():
        raise BuildError("release: bin/lvgl.cmd is missing")
    sdk_target = package / "sdk" / lvgl_version
    shutil.copytree(sdk_dir, sdk_target)

    token = paths.version_token(lvgl_version)
    build_dir = package / "build" / f"lvgl_{token}"
    plan = BuildPlan(
        lvgl_version,
        lvgl_src=repo_root / "lvgl-src" / lvgl_version,
        build_dir=build_dir,
        engine_dir=package / "core" / "engine",
        user_app_dir=package / "user" / "app",
        sdk_dir=sdk_target,
        build_mode="prebuilt",
        compiler=compiler,
        compiler_version=compiler_version,
    )
    plan.execute(build=True)
    engine = build_dir / paths.engine_filename()
    if not engine.is_file():
        raise BuildError(f"release: prebuilt engine was not produced: {engine}")

    sdk_manifest = json.loads(
        (sdk_target / "manifest.json").read_text(encoding="utf-8")
    )
    version = write_version_file(
        package,
        tool_version=tool_version,
        lvgl_version=lvgl_version,
        gcc_version=str(sdk_manifest["compiler"]["version"]),
        git_commit=_git_commit(repo_root),
        adapters=[],
    )
    return {
        "engine": engine,
        "sdk_manifest": sdk_manifest,
        "version": version,
    }


def purge_caches(package: Path) -> None:
    """Remove bytecode caches created by running the staged package."""
    for path in sorted(package.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for path in package.rglob("*.pyc"):
        try:
            path.unlink()
        except OSError:
            pass


def clean_build_dir(package: Path, lvgl_version: str) -> Path:
    """Keep only the engine under ``build/lvgl_<token>/``.

    Object caches, CMake leftovers and the prebuilt marker are build
    intermediates and must not enter the package.
    """
    token = paths.version_token(lvgl_version)
    build_root = package / "build"
    target_dir = build_root / f"lvgl_{token}"
    engine = target_dir / paths.engine_filename()
    if not engine.is_file():
        raise BuildError(f"release: engine is missing before packaging: {engine}")
    temporary = package / ".engine.tmp"
    os.replace(engine, temporary)
    shutil.rmtree(build_root)
    target_dir.mkdir(parents=True)
    os.replace(temporary, engine)
    return engine


def _cli_command(package: Path, lvgl_version: str, *args: str) -> list[str]:
    return [
        sys.executable,
        "-I", "-B",
        str(package / "core" / "cli.py"),
        "--lvgl", lvgl_version,
        *args,
    ]


def _smoke_env(workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LVGL_AI_SESSIONS_ROOT"] = str(workspace / "sessions")
    env.pop("LVGL_AI_LVGL_SRC", None)
    env.pop("LVGL_AI_DEMO", None)
    return env


def _json_line(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise BuildError(
            "release smoke: expected one JSON line, got "
            f"{lines!r}; stderr={result.stderr.strip()[:500]!r}"
        )
    try:
        payload = json.loads(lines[0])
    except ValueError as exc:
        raise BuildError(f"release smoke: invalid JSON: {lines[0][:200]}") from exc
    if not isinstance(payload, dict):
        raise BuildError("release smoke: JSON summary is not an object")
    return payload


def _smoke_run(
    package: Path, lvgl_version: str, workspace: Path, *args: str
) -> dict[str, Any]:
    result = _run(
        _cli_command(package, lvgl_version, *args),
        cwd=workspace,
        env=_smoke_env(workspace),
    )
    if result.returncode != 0:
        raise BuildError(
            f"release smoke failed: {' '.join(args)}; "
            f"stdout={result.stdout.strip()[:500]!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )
    return _json_line(result)


def _smoke_scenario(package: Path, lvgl_version: str, workspace: Path, *extra: str) -> dict[str, Any]:
    scenario = package / SMOKE_SCENARIO
    payload = _smoke_run(
        package,
        lvgl_version,
        workspace,
        *extra,
        "--scenario", str(scenario),
        "--json",
    )
    if payload.get("status") != "ok":
        raise BuildError(
            "release smoke: scenario finished with "
            f"status={payload.get('status')!r}: {payload.get('error')!r}"
        )
    session_dir = Path(str(payload.get("session_dir")))
    for name in ("manifest.json", "timeline.ndjson", "engine.log", "build.log"):
        if not (session_dir / name).is_file():
            raise BuildError(f"release smoke: session evidence missing {name}")
    return payload


def _cmd_wrapper(package: Path, *args: str) -> list[str]:
    command = [str(package / "bin" / "lvgl.cmd"), *args]
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", *command]
    return command


def _smoke_wrapper_run(
    package: Path, lvgl_version: str, workspace: Path
) -> dict[str, Any]:
    scenario = package / SMOKE_SCENARIO
    result = _run(
        _cmd_wrapper(
            package,
            "run",
            "--lvgl", lvgl_version,
            "--no-build",
            "--scenario", str(scenario),
            "--json",
        ),
        cwd=workspace,
        env=_smoke_env(workspace),
    )
    if result.returncode != 0:
        raise BuildError(
            "release smoke: bin/lvgl.cmd run failed; "
            f"stdout={result.stdout.strip()[:500]!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )
    payload = _json_line(result)
    if payload.get("status") != "ok":
        raise BuildError(
            "release smoke: bin/lvgl.cmd run returned "
            f"status={payload.get('status')!r}"
        )
    return payload


def _kill_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _smoke_serve(package: Path, workspace: Path) -> dict[str, Any]:
    if os.name != "nt":
        raise BuildError("release smoke: serve check currently requires Windows")
    env = _smoke_env(workspace)
    process = subprocess.Popen(
        _cmd_wrapper(package, "serve", "--host", "127.0.0.1", "--port", "0"),
        cwd=str(workspace),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    watchdog = threading.Timer(30.0, _kill_tree, args=(process,))
    watchdog.start()
    try:
        assert process.stdout is not None
        url = None
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                break
            match = re.search(r"\[web\] serving (http://\S+)", line)
            if match:
                url = match.group(1)
                break
        if url is None:
            stderr = "" if process.stderr is None else process.stderr.read()
            raise BuildError(
                "release smoke: web server did not print a URL; "
                f"stderr={stderr.strip()[:500]!r}"
            )
        with urllib.request.urlopen(url, timeout=10) as response:
            status = response.status
            body = response.read(200)
        if status != 200 or not body:
            raise BuildError(f"release smoke: GET {url} returned {status}")
        return {"url": url, "status": status}
    finally:
        watchdog.cancel()
        _kill_tree(process)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def smoke_package(package: Path, lvgl_version: str) -> dict[str, Any]:
    """Run the package from an unrelated working directory."""
    with tempfile.TemporaryDirectory(prefix="lvgl-ai-smoke-") as raw:
        workspace = Path(raw)
        no_build = _smoke_scenario(package, lvgl_version, workspace, "--no-build")
        prebuilt = _smoke_scenario(package, lvgl_version, workspace, "--prebuilt")
        build_log = Path(str(prebuilt["session_dir"])) / "build.log"
        if "# build mode: prebuilt" not in build_log.read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BuildError(
                "release smoke: prebuilt session build.log has no mode line"
            )
        wrapper = _smoke_wrapper_run(package, lvgl_version, workspace)
        serve = _smoke_serve(package, workspace)
        return {
            "no_build_session": no_build.get("session_id"),
            "prebuilt_session": prebuilt.get("session_id"),
            "wrapper_session": wrapper.get("session_id"),
            "serve_url": serve["url"],
        }


def build_zip(package: Path, zip_path: Path) -> str:
    """Write a deterministic zip; return its sha256."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in package.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(package).as_posix(),
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(package).as_posix()
            info = zipfile.ZipInfo(
                f"{PACKAGE_DIR_NAME}/{relative}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())
    return sha256_file(zip_path)


def _file_hashes(package: Path) -> dict[str, str]:
    paths = sorted(
        (path for path in package.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(package).as_posix(),
    )
    return {
        path.relative_to(package).as_posix(): sha256_file(path)
        for path in paths
    }


def release(
    *,
    repo_root: Path,
    out_dir: Path,
    tool_version: str,
    lvgl_version: str,
    sdk_dir: Path,
    export_sdk_if_missing: bool = True,
    smoke: bool = True,
    compiler: str | None = None,
    compiler_version: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    out_dir = out_dir.resolve()
    sdk_dir = sdk_dir.resolve()
    if not (sdk_dir / "manifest.json").is_file():
        if not export_sdk_if_missing:
            raise BuildError(
                f"host SDK not found: {sdk_dir}; run core/tools/export_sdk.py first"
            )
        export_sdk.export_sdk(
            version=lvgl_version,
            out_dir=sdk_dir,
            repo_root=repo_root,
            force=True,
        )
    with tempfile.TemporaryDirectory(prefix="lvgl-ai-release-") as raw:
        staging = Path(raw)
        package = staging / PACKAGE_DIR_NAME
        staged = stage_package(
            repo_root=repo_root,
            package=package,
            sdk_dir=sdk_dir,
            lvgl_version=lvgl_version,
            tool_version=tool_version,
            compiler=compiler,
            compiler_version=compiler_version,
        )
        smoke_report = (
            smoke_package(package, lvgl_version) if smoke else None
        )
        purge_caches(package)
        clean_build_dir(package, lvgl_version)
        check_hygiene(package, repo_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        zip_path = out_dir / f"lvgl-ai-{tool_version}-{lvgl_version}.zip"
        zip_hash = build_zip(package, zip_path)
        hashes = _file_hashes(package)
        files = sorted(package.rglob("*"))
        file_count = sum(1 for path in files if path.is_file())
        unpacked = sum(
            path.stat().st_size for path in files if path.is_file()
        )
        sdk_manifest_sha256 = sha256_file(
            package / "sdk" / lvgl_version / "manifest.json"
        )
    sha_path = zip_path.with_name(zip_path.name + ".sha256")
    sha_path.write_text(f"{zip_hash}  {zip_path.name}\n", encoding="utf-8")
    sdk_manifest = staged["sdk_manifest"]
    manifest = {
        "schema": RELEASE_SCHEMA,
        "tool_version": tool_version,
        "git_commit": staged["version"]["git_commit"],
        "lvgl_version": lvgl_version,
        "sdk": {
            "schema": sdk_manifest.get("schema"),
            "lvgl_version": sdk_manifest.get("lvgl_version"),
            "lvgl_tag": sdk_manifest.get("lvgl_tag"),
            "manifest_sha256": sdk_manifest_sha256,
            "compiler": sdk_manifest.get("compiler"),
            "libs": sdk_manifest.get("libs"),
            "sha256": sdk_manifest.get("sha256"),
        },
        "python": {"version": platform.python_version()},
        "gcc": {"version": staged["version"]["gcc"]["version"]},
        "adapters": [],
        "package": {
            "root": PACKAGE_DIR_NAME,
            "file_count": file_count,
            "unpacked_bytes": unpacked,
            "archive_bytes": zip_path.stat().st_size,
        },
        "sha256": zip_hash,
        "files": hashes,
        "smoke": smoke_report,
    }
    manifest_path = out_dir / f"lvgl-ai-{tool_version}-{lvgl_version}.release.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "zip": str(zip_path),
        "sha256": zip_hash,
        "sha256_file": str(sha_path),
        "manifest": str(manifest_path),
        "smoke": smoke_report,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release.py",
        description=(
            "Build the distributable skill zip, .sha256 and release manifest."
        ),
    )
    parser.add_argument(
        "--version",
        default=paths.TOOL_VERSION,
        help=f"tool version (default: {paths.TOOL_VERSION})",
    )
    parser.add_argument(
        "--lvgl",
        default=DEFAULT_LVGL,
        help=f"host SDK version (default: {DEFAULT_LVGL})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: <repo>/dist)",
    )
    parser.add_argument(
        "--sdk",
        type=Path,
        default=None,
        help="existing host SDK directory (default: sdk/<lvgl>)",
    )
    parser.add_argument(
        "--no-export-sdk",
        action="store_true",
        help="fail instead of exporting the host SDK when it is missing",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="skip the staging-directory smoke (development only)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="workspace root (default: detected from the tool location)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one JSON summary on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = (args.repo_root or REPO_ROOT).resolve()
    sdk_dir = args.sdk or (repo / "sdk" / args.lvgl)
    out_dir = args.out or (repo / "dist")
    try:
        summary = release(
            repo_root=repo,
            out_dir=out_dir,
            tool_version=args.version,
            lvgl_version=args.lvgl,
            sdk_dir=sdk_dir,
            export_sdk_if_missing=not args.no_export_sdk,
            smoke=not args.skip_smoke,
        )
    except BuildError as exc:
        print(f"[release] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    else:
        print(f"[release] zip: {summary['zip']}")
        print(f"[release] sha256: {summary['sha256']}")
        print(f"[release] manifest: {summary['manifest']}")
        if summary["smoke"]:
            print(
                "[release] smoke: "
                f"no-build={summary['smoke']['no_build_session']} "
                f"prebuilt={summary['smoke']['prebuilt_session']} "
                f"serve={summary['smoke']['serve_url']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
