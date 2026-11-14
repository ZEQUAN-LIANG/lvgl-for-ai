#!/usr/bin/env python3
"""Build the two default release bundles.

The default release contains exactly two zips:

- ``full``: one package with all six LVGL versions and their prebuilt engines.
- ``full-sifli``: the same package plus the self-developed SiFli tools.

There are no per-version packs, no release notes and no upload scripts in the
release directory.  Tokens are never part of this build.  Files that are
identical in every host SDK (the FreeType DLL, its import library and the
shared zlib/libpng/FreeType headers) are stored once under ``sdk/common``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_BOOTSTRAP_TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402
from lvgl_ai.control.build_plan import BuildPlan  # noqa: E402
from lvgl_ai.control.errors import BuildError  # noqa: E402

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import export_sdk  # noqa: E402
import release as release_tool  # noqa: E402

VERSIONS = ("9.6", "9.5", "9.4", "9.1", "8.4", "8.3")
INTRO_VERSIONS = frozenset(("9.6", "9.5", "9.4"))
LEGACY_VERSIONS = frozenset(("9.1", "8.4", "8.3"))
FULL_ASSET = "lvgl-verify-loop-{version}-full-win64.zip"
FULL_SIFLI_ASSET = "lvgl-verify-loop-{version}-full-sifli-win64.zip"


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _json_line(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise BuildError(
            f"expected one JSON line, got {lines!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )
    payload = json.loads(lines[0])
    if not isinstance(payload, dict):
        raise BuildError("JSON summary is not an object")
    return payload


def _ensure_launchers(repo: Path) -> None:
    viewer = repo / release_tool.RELEASE_VIEWER_PATH
    host = repo / "chip-adapt" / "sifli" / "tools" / "SiFli-Host.exe"
    if viewer.is_file() and host.is_file():
        return
    result = _run(
        [
            sys.executable,
            "-I",
            str(repo / "core" / "tools" / "launchers" / "build.py"),
        ],
        cwd=repo,
        timeout=180.0,
    )
    if result.returncode != 0:
        raise BuildError(
            "cannot build the Windows launchers; "
            f"stdout={result.stdout.strip()[:500]!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )


def _ensure_sdk(repo: Path, version: str) -> Path:
    sdk = repo / "sdk" / version
    if not (sdk / "manifest.json").is_file():
        export_sdk.export_sdk(
            version=version,
            out_dir=sdk,
            repo_root=repo,
            force=True,
        )
    return sdk


def _stage_intro_app(repo: Path, target: Path) -> None:
    source = repo / "user" / "app"
    target.mkdir(parents=True)
    for name in ("app.h", "lvgl_compat.h"):
        shutil.copy2(source / name, target / name)
    shutil.copytree(source / "intro", target / "intro")
    shutil.copy2(repo / "core" / "tools" / "release_app.c", target / "app.c")


def _stage_legacy_app(repo: Path, target: Path) -> None:
    source = repo / "user" / "app"
    target.mkdir(parents=True)
    for name in ("app.c", "app.h", "lvgl_compat.h"):
        shutil.copy2(source / name, target / name)
    for name in ("demo", "asset_probe"):
        shutil.copytree(source / name, target / name)


def _build_engine(
    repo: Path,
    version: str,
    *,
    user_app_dir: Path,
    build_dir: Path,
) -> Path:
    plan = BuildPlan(
        version,
        lvgl_src=repo / "lvgl-src" / version,
        build_dir=build_dir,
        engine_dir=repo / "core" / "engine",
        user_app_dir=user_app_dir,
        sdk_dir=repo / "sdk" / version,
        build_mode="prebuilt",
    )
    plan.execute(build=True)
    engine = build_dir / paths.engine_filename()
    if not engine.is_file():
        raise BuildError(f"engine was not produced: {engine}")
    return engine


def _smoke(
    package: Path,
    version: str,
    scenario: Path,
    *,
    markers: tuple[str, ...],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"lvgl-release-{version}-") as raw:
        workspace = Path(raw)
        env = os.environ.copy()
        env["LVGL_AI_SESSIONS_ROOT"] = str(workspace / "sessions")
        env.pop("LVGL_AI_LVGL_SRC", None)
        env.pop("LVGL_AI_DEMO", None)
        result = _run(
            [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/c",
                str(package / "bin" / "lvgl.cmd"),
                "run",
                "--lvgl", version,
                "--no-build",
                "--scenario", str(scenario),
                "--json",
            ],
            cwd=workspace,
            env=env,
            timeout=180.0,
        )
        if result.returncode != 0:
            raise BuildError(
                f"{version} smoke failed: stdout={result.stdout.strip()[:500]!r}; "
                f"stderr={result.stderr.strip()[:500]!r}"
            )
        payload = _json_line(result)
        if payload.get("status") != "ok":
            raise BuildError(
                f"{version} smoke status={payload.get('status')!r}: "
                f"{payload.get('error')!r}"
            )
        session = Path(str(payload["session_dir"]))
        log = (session / "engine.log").read_text(
            encoding="utf-8", errors="replace"
        )
        missing = [marker for marker in markers if marker not in log]
        if missing:
            raise BuildError(
                f"{version} smoke log is missing {missing!r}; "
                f"log tail={log[-800:]!r}"
            )
        return {
            "version": version,
            "session_id": payload.get("session_id"),
            "frame_count": payload.get("frame_count"),
            "markers": list(markers),
        }


def _update_versions(repo: Path, tool_version: str) -> None:
    path = repo / "versions.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    index["core"] = {"version": tool_version, "platform": "win64"}
    for version, entry in index["versions"].items():
        entry["sdk"] = True
        entry["bundled"] = True
        entry["legacy"] = version in LEGACY_VERSIONS
        entry.pop("pack", None)
    path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _copy_engine(package: Path, repo: Path, version: str) -> None:
    build_dir = repo / "build" / f"lvgl_{paths.version_token(version)}"
    engine = build_dir / paths.engine_filename()
    if not engine.is_file():
        raise BuildError(f"engine is missing: {engine}")
    target = package / "build" / build_dir.name
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(engine, target / engine.name)
    manifest = json.loads(
        (repo / "sdk" / version / "manifest.json").read_text(encoding="utf-8")
    )
    for name in manifest.get("runtime_dlls", []):
        source = repo / "sdk" / version / "lib" / name
        if source.is_file():
            shutil.copy2(source, target / name)
    release_tool.clean_build_dir(package, version)


def _stage_full_package(
    repo: Path,
    package: Path,
    *,
    tool_version: str,
    smoke: bool,
) -> dict[str, Any]:
    for version in VERSIONS:
        _ensure_sdk(repo, version)
    # Engines for 9.5/9.4 are intro-only; legacy engines keep the demo harness.
    for version in ("9.5", "9.4"):
        with tempfile.TemporaryDirectory(prefix=f"lvgl-{version}-app-") as raw:
            app_dir = Path(raw) / "app"
            _stage_intro_app(repo, app_dir)
            _build_engine(
                repo,
                version,
                user_app_dir=app_dir,
                build_dir=repo / "build" / f"lvgl_{paths.version_token(version)}",
            )
    for version in ("9.1", "8.4", "8.3"):
        with tempfile.TemporaryDirectory(prefix=f"lvgl-{version}-app-") as raw:
            app_dir = Path(raw) / "app"
            _stage_legacy_app(repo, app_dir)
            _build_engine(
                repo,
                version,
                user_app_dir=app_dir,
                build_dir=repo / "build" / f"lvgl_{paths.version_token(version)}",
            )

    staged = release_tool.stage_package(
        repo_root=repo,
        package=package,
        sdk_dir=repo / "sdk" / "9.6",
        lvgl_version="9.6",
        tool_version=tool_version,
        python_dir=repo / "runtime" / "python",
        host_sdks=list(VERSIONS),
    )
    for version in VERSIONS:
        if version == "9.6":
            continue
        shutil.copytree(
            repo / "sdk" / version,
            package / "sdk" / version,
        )
        _copy_engine(package, repo, version)
    release_tool.clean_build_dir(package, "9.6")

    for version in LEGACY_VERSIONS:
        smoke_dir = package / "smoke" / version
        smoke_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            repo / "user" / "scenarios" / "settings.json",
            smoke_dir / "legacy_smoke.json",
        )

    shared = release_tool.share_sdk_payload(package, VERSIONS)
    release_tool.strip_build_runtime_dlls(package)

    smoke_report: list[dict[str, Any]] = []
    if smoke:
        for version in VERSIONS:
            if version in INTRO_VERSIONS:
                scenario = package / "user" / "scenarios" / "intro.json"
                markers = (
                    "[intro] step=1",
                    "[intro] step=4",
                    "[intro] evidence ready",
                )
            else:
                scenario = package / "smoke" / version / "legacy_smoke.json"
                markers = ("[app] demo_button clicked",)
            smoke_report.append(
                _smoke(package, version, scenario, markers=markers)
            )

    release_tool.purge_caches(package)
    release_tool.check_hygiene(package, repo)
    return {"engine": staged["engine"], "smoke": smoke_report, "shared": shared}


def _overlay_sifli(package: Path, repo: Path, tool_version: str) -> None:
    sifli = repo / "chip-adapt" / "sifli"
    for name in (
        "README.md",
        "adapter.json",
        "asset_plan.py",
        "bootstrap.ps1",
        "export.py",
        "layout.py",
    ):
        source = sifli / name
        if source.is_file():
            target = package / "chip-adapt" / "sifli" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for name in ("host", "templates", "tools"):
        source = sifli / name
        if source.is_dir():
            shutil.copytree(
                source,
                package / "chip-adapt" / "sifli" / name,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "logs", ".cache", "config.json",
                    "tests",
                ),
            )
    for name in ("README.md", "docs"):
        source = repo / "chip-adapt" / name
        if source.is_dir():
            shutil.copytree(
                source, package / "chip-adapt" / name, dirs_exist_ok=True
            )
        elif source.is_file():
            target = package / "chip-adapt" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    vendor_readme = repo / "chip-adapt" / "vendor" / "README.md"
    if vendor_readme.is_file():
        target = package / "chip-adapt" / "vendor" / "README.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vendor_readme, target)

    sift_app = repo / "user" / "app" / "sift_watch"
    if sift_app.is_dir():
        shutil.copytree(
            sift_app,
            package / "user" / "app" / "sift_watch",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    example_target = package / "chip-adapt" / "examples" / "export" / "sift_watch"
    with tempfile.TemporaryDirectory(prefix="lvgl-sifli-example-") as raw:
        generated = Path(raw) / "sift_watch"
        result = _run(
            [
                sys.executable,
                "-I",
                "-B",
                str(sifli / "export.py"),
                "sift_watch",
                "--output", str(generated),
                "--force",
            ],
            cwd=repo,
            timeout=180.0,
        )
        if result.returncode == 0 and (generated / "export.json").is_file():
            shutil.copytree(generated, example_target, dirs_exist_ok=True)

    docs = package / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "SIFLI.md").write_text(_sifli_readme(tool_version), encoding="utf-8")
    (package / "bin" / "sifli.cmd").write_text(_sifli_cmd(), encoding="utf-8")


def _sifli_readme(tool_version: str) -> str:
    return "\n".join(
        (
            "# SiFli tools",
            "",
            "This is the full package plus the self-developed SiFli export/host",
            "layer. The default demo is `sift_watch`.",
            "",
            "```bat",
            "bin\\sifli.cmd",
            "runtime\\python\\python.exe -I chip-adapt\\sifli\\export.py sift_watch --dry-run --force",
            "```",
            "",
            "It does not include the SiFli SDK, ARM toolchain, sftool, serial",
            "driver or firmware. Install those from the official sources described",
            "in `chip-adapt/vendor/README.md` before building or flashing.",
            "",
            f"Release {tool_version}.",
            "",
        )
    )


def _sifli_cmd() -> str:
    return "\n".join(
        (
            "@echo off",
            "setlocal",
            'set "LVGL_AI_ROOT=%~dp0.."',
            'if exist "%LVGL_AI_ROOT%\\runtime\\python\\python.exe" (',
            '  set "LVGL_AI_PY=%LVGL_AI_ROOT%\\runtime\\python\\python.exe"',
            ") else (",
            '  set "LVGL_AI_PY=python"',
            ")",
            '"%LVGL_AI_PY%" -I -B "%LVGL_AI_ROOT%\\chip-adapt\\sifli\\host\\server.py" --open %*',
            "exit /b %ERRORLEVEL%",
            "",
        )
    )


def _clean_output(out: Path) -> None:
    """Keep only the two bundles this script produces."""
    if not out.is_dir():
        return
    for path in out.iterdir():
        if path.name == "lvgl-verify-loop":
            shutil.rmtree(path, ignore_errors=True)
        elif path.name.startswith("lvgl-verify-loop-"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        elif path.name in {"UPLOAD.md", "RELEASE_NOTES.md", "release.json"}:
            path.unlink(missing_ok=True)


def build_release(
    *,
    repo_root: Path,
    out_dir: Path,
    tool_version: str,
    smoke: bool = True,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    out = out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    _clean_output(out)
    _ensure_launchers(repo)
    _update_versions(repo, tool_version)

    with tempfile.TemporaryDirectory(prefix="lvgl-release-full-") as raw:
        root = Path(raw)
        package = root / release_tool.PACKAGE_DIR_NAME
        staged = _stage_full_package(
            repo, package, tool_version=tool_version, smoke=smoke
        )
        full_zip = out / FULL_ASSET.format(version=tool_version)
        full_sha = release_tool.build_zip(package, full_zip)

        sifli_package = root / "sifli" / release_tool.PACKAGE_DIR_NAME
        shutil.copytree(package, sifli_package)
        _overlay_sifli(sifli_package, repo, tool_version)
        sifli_zip = out / FULL_SIFLI_ASSET.format(version=tool_version)
        sifli_sha = release_tool.build_zip(sifli_package, sifli_zip)

    return {
        "schema": "lvgl-verify-loop-release-v2",
        "tool_version": tool_version,
        "versions": list(VERSIONS),
        "full": {
            "zip": str(full_zip),
            "sha256": full_sha,
            "bytes": full_zip.stat().st_size,
        },
        "full_sifli": {
            "zip": str(sifli_zip),
            "sha256": sifli_sha,
            "bytes": sifli_zip.stat().st_size,
        },
        "smoke": staged["smoke"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release_all.py",
        description="Build the full LVGL bundle and the full+SiFli bundle.",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--version", default=paths.TOOL_VERSION)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = paths.REPO_ROOT
    out = args.out or (repo / "release")
    try:
        summary = build_release(
            repo_root=repo,
            out_dir=out,
            tool_version=args.version,
            smoke=not args.skip_smoke,
        )
    except (BuildError, OSError) as exc:
        print(f"[release_all] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"[release_all] full:       {summary['full']['zip']}")
        print(f"[release_all] full+sifli: {summary['full_sifli']['zip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
