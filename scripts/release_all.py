"""Build the two default release bundles.

The default release contains exactly two zips:

- ``full``: one package with all six LVGL versions and their prebuilt engines.
- ``full-sifli``: the same package plus the self-developed SiFli tools.

There are no per-version packs, no release notes and no upload scripts in the
release directory.  Tokens are never part of this build.  Files that are
identical in every host SDK (the FreeType DLL, its import library and the
shared zlib/libpng/FreeType headers) are stored once under ``dist/lvgl/common``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

_BOOTSTRAP_CONSOLE_ROOT = Path(__file__).resolve().parent.parent / "console"
if str(_BOOTSTRAP_CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_CONSOLE_ROOT))

import paths
import versions
from control.errors import BuildError

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import export_sdk
import release as release_tool
import release_bundle

FULL_ASSET = "lvgl-verify-loop-{version}-full-win64.zip"
FULL_SIFLI_ASSET = "lvgl-verify-loop-{version}-full-sifli-win64.zip"


def version_plan(repo_root: Path) -> dict[str, Any]:
    return {
        "supported": versions.supported(repo_root),
        "default": versions.default(repo_root),
        "intro": versions.intro(repo_root),
        "legacy": versions.legacy(repo_root),
        "bundled": versions.bundled(repo_root),
    }


LAUNCHER_SUFFIXES = frozenset({".c", ".rc", ".ico", ".py"})


def _ensure_launchers(repo: Path, *, force: bool = False) -> dict[str, Any]:
    exe = repo / release_tool.RELEASE_VIEWER_PATH
    cache_meta = repo / release_tool.RELEASE_ENGINE_CACHE_DIR / "launcher.json"
    digest = release_tool.tree_digest(
        repo / "scripts" / "launchers", LAUNCHER_SUFFIXES
    )
    if not force and exe.is_file() and cache_meta.is_file():
        try:
            meta = json.loads(cache_meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if meta.get("inputs_digest") == digest and meta.get(
            "exe_sha256"
        ) == release_tool.sha256_file(exe):
            return {"status": "reused", "digest": digest}
    result = release_bundle.run_command(
        [
            sys.executable,
            "-I",
            str(repo / "scripts" / "launchers" / "build.py"),
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
    cache_meta.parent.mkdir(parents=True, exist_ok=True)
    cache_meta.write_text(
        json.dumps(
            {
                "schema": "lvgl-verify-loop-release-launcher-v2",
                "inputs_digest": digest,
                "exe_sha256": release_tool.sha256_file(exe),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"status": "built", "digest": digest}


def _ensure_sdk(repo: Path, version: str) -> Path:
    sdk = repo / "dist" / "lvgl" / version
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
    shutil.copy2(repo / "scripts" / "release_app.c", target / "app.c")


def _stage_legacy_app(repo: Path, target: Path) -> None:
    source = repo / "user" / "app"
    target.mkdir(parents=True)
    for name in ("app.c", "app.h", "lvgl_compat.h"):
        shutil.copy2(source / name, target / name)
    for name in ("demo", "asset_probe"):
        shutil.copytree(source / name, target / name)


def _release_build_dir(repo: Path, version: str) -> Path:
    return (
        repo
        / release_tool.RELEASE_ENGINE_CACHE_DIR
        / f"lvgl_{paths.version_token(version)}"
    )


def _build_engine(
    repo: Path,
    version: str,
    *,
    user_app_dir: Path,
    force: bool,
) -> dict[str, Any]:
    return release_tool.ensure_release_engine(
        repo_root=repo,
        version=version,
        engine_dir=repo / "engine",
        user_app_dir=user_app_dir,
        sdk_dir=repo / "dist" / "lvgl" / version,
        build_dir=_release_build_dir(repo, version),
        force=force,
    )


def _smoke(
    package: Path,
    version: str,
    scenario: Path,
    *,
    markers: tuple[str, ...],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"lvgl-release-{version}-") as raw:
        payload = release_bundle.smoke_scenario(
            package,
            version,
            scenario,
            Path(raw),
            via_wrapper=True,
            extra=("--no-build",),
            markers=markers,
            label=version,
            timeout=180.0,
        )
        return {
            "version": version,
            "session_id": payload.get("session_id"),
            "frame_count": payload.get("frame_count"),
            "markers": list(markers),
        }


def _copy_engine(package: Path, repo: Path, version: str) -> None:
    build_dir = _release_build_dir(repo, version)
    engine = build_dir / paths.engine_filename()
    if not engine.is_file():
        raise BuildError(f"engine is missing: {engine}")
    target = package / "build" / build_dir.name
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(engine, target / engine.name)
    manifest = json.loads(
        (repo / "dist" / "lvgl" / version / "manifest.json").read_text(encoding="utf-8")
    )
    for name in manifest.get("runtime_dlls", []):
        source = repo / "dist" / "lvgl" / version / "lib" / name
        if source.is_file():
            shutil.copy2(source, target / name)
    release_tool.clean_build_dir(package, version)


def _stage_full_package(
    repo: Path,
    package: Path,
    *,
    tool_version: str,
    smoke: bool,
    force_build: bool,
    plan: dict[str, Any],
) -> dict[str, Any]:
    supported = tuple(plan["supported"])
    base_version = str(plan["default"])
    legacy_versions = set(plan["legacy"])
    engines: dict[str, dict[str, Any]] = {}
    for version in supported:
        _ensure_sdk(repo, version)
    for version in supported:
        if version == base_version:
            continue
        with tempfile.TemporaryDirectory(prefix=f"lvgl-{version}-app-") as raw:
            app_dir = Path(raw) / "app"
            if version in legacy_versions:
                _stage_legacy_app(repo, app_dir)
            else:
                _stage_intro_app(repo, app_dir)
            engines[version] = _build_engine(
                repo,
                version,
                user_app_dir=app_dir,
                force=force_build,
            )

    staged = release_tool.stage_package(
        repo_root=repo,
        package=package,
        sdk_dir=repo / "dist" / "lvgl" / base_version,
        lvgl_version=base_version,
        tool_version=tool_version,
        host_sdks=list(supported),
        force_build=force_build,
    )
    engines[base_version] = staged["engine"]
    for version in supported:
        if version == base_version:
            continue
        shutil.copytree(
            repo / "dist" / "lvgl" / version,
            package / "dist" / "lvgl" / version,
        )
        _copy_engine(package, repo, version)
    release_tool.clean_build_dir(package, base_version)

    shared = release_tool.share_sdk_payload(package, supported)
    release_tool.strip_build_runtime_dlls(package)

    if smoke:
        with tempfile.TemporaryDirectory(prefix="lvgl-release-smoke-") as raw:
            smoke_root = Path(raw)
            for version in supported:
                if version in legacy_versions:
                    scenario = smoke_root / f"legacy_{version}.json"
                    shutil.copy2(
                        repo / "user" / "scenarios" / "settings.json",
                        scenario,
                    )
                    markers = ("[app] demo_button clicked",)
                else:
                    scenario = package / "user" / "scenarios" / "intro.json"
                    markers = (
                        "[app] app=intro",
                        "[intro] ui created",
                    )
                _smoke(package, version, scenario, markers=markers)

    release_tool.purge_caches(package)
    release_tool.check_hygiene(package, repo)
    return {
        "engine": staged["engine"],
        "shared": shared,
        "engines": engines,
        "sdk_manifest": staged["sdk_manifest"],
        "version": staged["version"],
    }


SIFLI_TOP_FILES = (
    ".cppcheck-suppressions",
    "README.md",
    "adapter.json",
    "asset_plan.py",
    "export.py",
    "layout.py",
    "run_tests.py",
)
SIFLI_TOP_DIRS = ("templates", "tests")
HOST_IGNORE = (
    "__pycache__",
    "*.pyc",
    "logs",
    ".cache",
    "config.json",
)


def _overlay_sifli(package: Path, repo: Path, tool_version: str) -> None:
    chip = repo / "chip-adapt"
    sifli = chip / "sifli"
    host = sifli / "host"
    target_root = package / "chip-adapt"
    target_root.mkdir(parents=True, exist_ok=True)
    chip_readme = chip / "README.md"
    if chip_readme.is_file():
        shutil.copy2(chip_readme, target_root / "README.md")
    for name in SIFLI_TOP_FILES:
        source = sifli / name
        if source.is_file():
            target = target_root / "sifli" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for name in SIFLI_TOP_DIRS:
        source = sifli / name
        if source.is_dir():
            shutil.copytree(
                source,
                target_root / "sifli" / name,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
    docs = chip / "docs"
    if docs.is_dir():
        shutil.copytree(
            docs,
            target_root / "docs",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    if host.is_dir():
        shutil.copytree(
            host,
            target_root / "sifli" / "host",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*HOST_IGNORE),
        )
    vendor_readme = chip / "vendor" / "README.md"
    if vendor_readme.is_file():
        target = target_root / "vendor" / "README.md"
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

    example_target = target_root / "exports" / "sift_watch"
    with tempfile.TemporaryDirectory(prefix="lvgl-sifli-example-") as raw:
        generated = Path(raw) / "sift_watch"
        result = release_bundle.run_command(
            [
                sys.executable,
                "-I",
                "-B",
                str(sifli / "export.py"),
                "sift_watch",
                "--output",
                str(generated),
                "--force",
            ],
            cwd=repo,
            timeout=180.0,
        )
        if result.returncode == 0 and (generated / "export.json").is_file():
            shutil.copytree(generated, example_target, dirs_exist_ok=True)

    (package / "bin" / "sifli.cmd").write_text(_sifli_cmd(), encoding="utf-8")
    host_exe = sifli / "tools" / "SiFli-Host.exe"
    if host_exe.is_file():
        target = target_root / "sifli" / "tools" / "SiFli-Host.exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(host_exe, target)


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
            "python -I chip-adapt\\sifli\\export.py sift_watch --dry-run --force",
            "```",
            "",
            "Python 3.9+ must be on PATH; the package does not bundle a runtime.",
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
            'set "LVGL_VERIFY_LOOP_ROOT=%~dp0.."',
            'set "LVGL_VERIFY_LOOP_PY="',
            "where python >nul 2>nul",
            'if not errorlevel 1 set "LVGL_VERIFY_LOOP_PY=python"',
            "if not defined LVGL_VERIFY_LOOP_PY (",
            "  where py >nul 2>nul",
            '  if not errorlevel 1 set "LVGL_VERIFY_LOOP_PY=py -3"',
            ")",
            "if not defined LVGL_VERIFY_LOOP_PY (",
            "  echo [sifli] Python 3.9+ was not found on PATH. 1>&2",
            "  exit /b 2",
            ")",
            '%LVGL_VERIFY_LOOP_PY% -I -B "%LVGL_VERIFY_LOOP_ROOT%\\chip-adapt\\sifli\\host\\server.py" --open %*',
            "exit /b %ERRORLEVEL%",
        )
    )


def _clean_output(out: Path) -> None:
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
    force_build: bool = False,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    out = out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    _clean_output(out)
    launcher = _ensure_launchers(repo, force=force_build)
    plan = version_plan(repo)

    with tempfile.TemporaryDirectory(prefix="lvgl-release-full-") as raw:
        root = Path(raw)
        package = root / release_tool.PACKAGE_DIR_NAME
        staged = _stage_full_package(
            repo,
            package,
            tool_version=tool_version,
            smoke=smoke,
            force_build=force_build,
            plan=plan,
        )
        base_version = str(plan["default"])
        full_zip = out / FULL_ASSET.format(version=tool_version)
        full_sha = release_bundle.build_zip(package, full_zip)
        full_sha_path = release_bundle.write_checksum(full_zip, full_sha)
        _full_manifest, full_manifest_path = release_bundle.write_manifest(
            package,
            full_zip,
            tool_version=tool_version,
            git_commit=staged["version"]["git_commit"],
            lvgl_version=base_version,
            gcc_version=str(staged["version"]["gcc"]["version"]),
            adapters=[],
            digest=full_sha,
        )

        sifli_package = root / "chip-adapt" / "sifli" / release_bundle.PACKAGE_DIR_NAME
        shutil.copytree(package, sifli_package)
        _overlay_sifli(sifli_package, repo, tool_version)
        sifli_zip = out / FULL_SIFLI_ASSET.format(version=tool_version)
        sifli_sha = release_bundle.build_zip(sifli_package, sifli_zip)
        sifli_sha_path = release_bundle.write_checksum(sifli_zip, sifli_sha)
        _sifli_manifest, sifli_manifest_path = release_bundle.write_manifest(
            sifli_package,
            sifli_zip,
            tool_version=tool_version,
            git_commit=staged["version"]["git_commit"],
            lvgl_version=base_version,
            gcc_version=str(staged["version"]["gcc"]["version"]),
            adapters=[],
            digest=sifli_sha,
        )

    summary = {
        "schema": release_bundle.BUNDLE_SCHEMA,
        "tool_version": tool_version,
        "versions": list(plan["supported"]),
        "full": {
            "zip": str(full_zip),
            "sha256": full_sha,
            "bytes": full_zip.stat().st_size,
            "sha256_file": str(full_sha_path),
            "manifest": str(full_manifest_path),
        },
        "full_sifli": {
            "zip": str(sifli_zip),
            "sha256": sifli_sha,
            "bytes": sifli_zip.stat().st_size,
            "sha256_file": str(sifli_sha_path),
            "manifest": str(sifli_manifest_path),
        },
        "engines": staged["engines"],
        "launcher": launcher,
    }
    release_bundle.write_summary(out, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release_all.py",
        description="Build the full LVGL bundle and the full+SiFli bundle.",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--version", default=paths.TOOL_VERSION)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument(
        "--force-build",
        action="store_true",
        help="rebuild engines and the launcher even when their inputs are unchanged",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = paths.REPO_ROOT
    out = args.out or (repo / "dist" / "release")
    try:
        summary = build_release(
            repo_root=repo,
            out_dir=out,
            tool_version=args.version,
            smoke=not args.skip_smoke,
            force_build=args.force_build,
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
