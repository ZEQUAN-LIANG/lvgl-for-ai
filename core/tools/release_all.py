#!/usr/bin/env python3
"""Build the 0.2.0 multi-version release assets.

This orchestrator builds one core package (9.6 + embedded Python), one pack
for every other supported LVGL version, and the SiFli tools asset.  It is a
local release driver: uploads are still a manual step, and every asset gets a
sha256 file plus a release manifest entry.

Usage::

    python -I core/tools/release_all.py --out release
    python -I core/tools/release_all.py --out release --skip-smoke
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
from lvgl_ai.digest import sha256_file  # noqa: E402

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import export_sdk  # noqa: E402
import pack  # noqa: E402
import release as release_tool  # noqa: E402

VERSIONS = ("9.6", "9.5", "9.4", "9.1", "8.4", "8.3")
INTRO_VERSIONS = frozenset(("9.6", "9.5", "9.4"))
LEGACY_VERSIONS = frozenset(("9.1", "8.4", "8.3"))
CORE_ASSET = "lvgl-verify-loop-{version}-core-win64.zip"
SIFLI_ASSET = "lvgl-verify-loop-{version}-sifli-tools-win64.zip"


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None,
         timeout: float = 300.0) -> subprocess.CompletedProcess[str]:
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


def _stage_intro_app(repo: Path, target: Path) -> None:
    source = repo / "user" / "app"
    target.mkdir(parents=True)
    for name in ("app.h", "lvgl_compat.h"):
        shutil.copy2(source / name, target / name)
    shutil.copytree(source / "intro", target / "intro")
    shutil.copy2(repo / "core" / "tools" / "release_app.c", target / "app.c")


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
    repo: Path,
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
                sys.executable, "-I", "-B",
                str(repo / "core" / "cli.py"),
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
        log = (session / "engine.log").read_text(encoding="utf-8", errors="replace")
        missing = [marker for marker in markers if marker not in log]
        if missing:
            raise BuildError(
                f"{version} smoke log is missing {missing!r}; "
                f"log tail={log[-800:]!r}"
            )
        return {
            "version": version,
            "session_id": payload.get("session_id"),
            "session_dir": str(session),
            "frame_count": payload.get("frame_count"),
            "markers": list(markers),
        }


def _build_version_asset(
    repo: Path,
    version: str,
    *,
    tool_version: str,
    out_dir: Path,
) -> dict[str, Any]:
    sdk_dir = repo / "sdk" / version
    if not (sdk_dir / "manifest.json").is_file():
        export_sdk.export_sdk(
            version=version,
            out_dir=sdk_dir,
            repo_root=repo,
            force=True,
        )
    intro = version in INTRO_VERSIONS
    with tempfile.TemporaryDirectory(prefix=f"lvgl-{version}-app-") as raw:
        app_dir = Path(raw) / "app"
        if intro:
            _stage_intro_app(repo, app_dir)
        else:
            app_dir = repo / "user" / "app"
        build_dir = repo / "build" / f"lvgl_{paths.version_token(version)}"
        engine = _build_engine(
            repo, version, user_app_dir=app_dir, build_dir=build_dir
        )
        scenario = (
            repo / "user" / "scenarios" / "intro.json"
            if intro
            else repo / "user" / "scenarios" / "settings.json"
        )
        markers = (
            ("[intro] step=1", "[intro] step=4", "[intro] evidence ready")
            if intro
            else ("[app] demo_button clicked",)
        )
        smoke = _smoke(repo, version, scenario, markers=markers)
        manifest = pack.build_pack(
            repo_root=repo,
            version=version,
            tool_version=tool_version,
            engine=engine,
            sdk_dir=sdk_dir,
            out_dir=out_dir,
            legacy=not intro,
            smoke_scenario=None if intro else scenario,
        )
    manifest["smoke"] = smoke
    manifest["intro"] = intro
    manifest["legacy"] = not intro
    return manifest


def _update_index(repo: Path, manifests: list[dict[str, Any]], tool_version: str) -> None:
    path = repo / "versions.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    index["core"] = {"version": tool_version, "platform": "win64"}
    by_version = {item["lvgl"]: item for item in manifests}
    for version, entry in index["versions"].items():
        if version == "9.6":
            continue
        item = by_version.get(version)
        if item is None:
            continue
        entry["sdk"] = True
        entry["legacy"] = bool(item.get("legacy"))
        pack_entry = entry.setdefault("pack", {})
        pack_entry["sha256"] = item["sha256"]
    path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _ensure_launchers(repo: Path) -> None:
    """Build the untracked double-click launchers before staging the core."""
    viewer = repo / "LVGL-AI-Viewer.exe"
    host = repo / "chip-adapt" / "sifli" / "tools" / "SiFli-Host.exe"
    if viewer.is_file() and host.is_file():
        return
    result = _run(
        [sys.executable, "-I", str(repo / "core" / "tools" / "launchers" / "build.py")],
        cwd=repo,
        timeout=180.0,
    )
    if result.returncode != 0:
        raise BuildError(
            "release_all: cannot build the Windows launchers; "
            f"stdout={result.stdout.strip()[:500]!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )


def _build_core(
    repo: Path,
    out_dir: Path,
    tool_version: str,
    *,
    smoke: bool,
) -> dict[str, Any]:
    python_dir = repo / "runtime" / "python"
    if not python_dir.is_dir():
        raise BuildError(
            "release_all: runtime/python is missing; stage the Python 3.11 "
            "embeddable runtime first"
        )
    return release_tool.release(
        repo_root=repo,
        out_dir=out_dir,
        tool_version=tool_version,
        lvgl_version="9.6",
        sdk_dir=repo / "sdk" / "9.6",
        export_sdk_if_missing=True,
        smoke=smoke,
        python_dir=python_dir,
        host_sdks=list(VERSIONS),
        asset_name=CORE_ASSET.format(version=tool_version),
    )


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _build_sifli_tools(repo: Path, out_dir: Path, tool_version: str) -> dict[str, Any]:
    """Package only the self-developed SiFli layer and its run dependencies."""
    with tempfile.TemporaryDirectory(prefix="lvgl-sifli-tools-") as raw:
        root = Path(raw) / release_tool.PACKAGE_DIR_NAME
        root.mkdir(parents=True)

        sifli = repo / "chip-adapt" / "sifli"
        if not (sifli / "export.py").is_file():
            raise BuildError("release_all: chip-adapt/sifli/export.py is missing")
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
                _copy_file(source, root / "chip-adapt" / "sifli" / name)
        for name in ("host", "templates"):
            source = sifli / name
            if source.is_dir():
                shutil.copytree(
                    source,
                    root / "chip-adapt" / "sifli" / name,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", "logs", ".cache", "config.json",
                        "tests",
                    ),
                )
        tools = sifli / "tools"
        if tools.is_dir():
            shutil.copytree(tools, root / "chip-adapt" / "sifli" / "tools")

        for name in ("README.md", "docs"):
            source = repo / "chip-adapt" / name
            if source.is_dir():
                shutil.copytree(source, root / "chip-adapt" / name)
            elif source.is_file():
                _copy_file(source, root / "chip-adapt" / name)

        vendor_readme = repo / "chip-adapt" / "vendor" / "README.md"
        if vendor_readme.is_file():
            _copy_file(vendor_readme, root / "chip-adapt" / "vendor" / "README.md")

        example_target = (
            root / "chip-adapt" / "examples" / "export" / "sift_watch"
        )
        with tempfile.TemporaryDirectory(prefix="lvgl-sifli-example-") as raw:
            generated = Path(raw) / "sift_watch"
            result = _run(
                [
                    sys.executable, "-I", "-B",
                    str(sifli / "export.py"),
                    "sift_watch",
                    "--output", str(generated),
                    "--force",
                ],
                cwd=repo,
                timeout=180.0,
            )
            if result.returncode == 0 and (generated / "export.json").is_file():
                shutil.copytree(generated, example_target)
        if not example_target.is_dir():
            example = repo / "chip-adapt" / "examples" / "export" / "sift_watch"
            if example.is_dir():
                shutil.copytree(example, example_target)
        sift_app = repo / "user" / "app" / "sift_watch"
        if sift_app.is_dir():
            shutil.copytree(
                sift_app,
                root / "user" / "app" / "sift_watch",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

        _copy_file(repo / "LICENSE", root / "LICENSE")
        if (repo / "licenses").is_dir():
            shutil.copytree(repo / "licenses", root / "licenses")

        (root / "SIFLI.md").write_text(_sifli_readme(), encoding="utf-8")
        (root / "bin").mkdir(parents=True, exist_ok=True)
        (root / "bin" / "sifli.cmd").write_text(
            _sifli_cmd(), encoding="utf-8"
        )

        zip_path = out_dir / SIFLI_ASSET.format(version=tool_version)
        digest = release_tool.build_zip(root, zip_path)
        sha_path = zip_path.with_name(zip_path.name + ".sha256")
        sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
        return {
            "asset": zip_path.name,
            "zip": str(zip_path),
            "sha256": digest,
            "sha256_file": str(sha_path),
            "bytes": zip_path.stat().st_size,
        }


def _sifli_readme() -> str:
    return "\n".join(
        (
            "# SiFli tools",
            "",
            "This asset adds the self-developed SiFli export/host layer to the",
            "LVGL Verify Loop core package. Extract the core zip and this zip",
            "into the same parent directory; both use the `lvgl-verify-loop/`",
            "top-level folder, so they merge. It adds `chip-adapt/`,",
            "`user/app/sift_watch/`, `bin/sifli.cmd` and this file.",
            "",
            "It does **not** include the SiFli SDK, ARM toolchain, sftool,",
            "serial driver or firmware. Install those from the official sources",
            "described in `chip-adapt/vendor/README.md` before build/flash.",
            "",
            "```bat",
            "bin\\sifli.cmd",
            "```",
            "",
            "The default demo app is `sift_watch`; an exported copy is under",
            "`chip-adapt/examples/export/sift_watch/`.  Re-export or dry-run it",
            "without an SDK:",
            "",
            "```bat",
            "runtime\\python\\python.exe -I chip-adapt\\sifli\\export.py sift_watch --dry-run --force",
            "```",
            "",
            "There is no firmware in this asset; build output stays in the",
            "user's workspace.",
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


def _write_upload_checklist(
    out_dir: Path,
    tool_version: str,
    core: dict[str, Any],
    packs: list[dict[str, Any]],
    sifli: dict[str, Any],
) -> Path:
    assets = [(Path(core["zip"]).name, core["sha256"])]
    assets.extend((Path(item["zip"]).name, item["sha256"]) for item in packs)
    assets.append((Path(sifli["zip"]).name, sifli["sha256"]))
    lines = [
        f"# {tool_version} upload checklist",
        "",
        f"Tag: `v{tool_version}`",
        "",
        "Upload the zips and matching `.sha256` files to the same Release on Gitee and GitHub.",
        "`versions.json` already contains the Gitee/GitHub pack URLs for this tag.",
        "",
        "| Asset | sha256 |",
        "| --- | --- |",
    ]
    for name, digest in assets:
        lines.append(f"| `{name}` | `{digest}` |")
    lines += [
        "",
        "## Usage",
        "",
        f"1. Download `lvgl-verify-loop-{tool_version}-core-win64.zip` and extract `lvgl-verify-loop/`.",
        "2. Double-click `LVGL-AI-Viewer.exe`, or run `bin\\lvgl.cmd run --scenario user\\scenarios\\intro.json`.",
        "3. For 9.5 / 9.4 / 9.1 / 8.4 / 8.3, run the version directly; the first run asks before downloading its pack.",
        "4. For SiFli, extract the `sifli-tools` zip into the same parent directory as core and run `bin\\sifli.cmd`.",
        "",
        "## Post-upload checks",
        "",
        f"- The Gitee and GitHub `v{tool_version}` releases contain every zip.",
        "- Each `versions.json` sha256 matches the uploaded file.",
        "- Extract core into an empty directory and run `bin\\lvgl.cmd run --lvgl 9.4 --yes ...`; it must download and run.",
        "- After extracting `sifli-tools`, `runtime\\python\\python.exe -I chip-adapt\\sifli\\export.py sift_watch --dry-run --force` returns ok.",
        "",
    ]
    path = out_dir / "UPLOAD.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def release_all(
    *,
    repo_root: Path,
    out_dir: Path,
    tool_version: str,
    smoke: bool = True,
    only: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    out = out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    _ensure_launchers(repo)
    versions = [version for version in VERSIONS if only is None or version in only]
    if "9.6" not in versions:
        raise BuildError("release_all: 9.6 is required for the core package")

    manifests: list[dict[str, Any]] = []
    for version in versions:
        if version == "9.6":
            continue
        print(f"[release_all] building {version} pack", file=sys.stderr)
        manifests.append(
            _build_version_asset(
                repo, version, tool_version=tool_version, out_dir=out
            )
        )

    _update_index(repo, manifests, tool_version)
    print("[release_all] building core", file=sys.stderr)
    core = _build_core(repo, out, tool_version, smoke=smoke)
    print("[release_all] building sifli-tools", file=sys.stderr)
    sifli = _build_sifli_tools(repo, out, tool_version)

    summary = {
        "schema": "lvgl-verify-loop-release-all-v1",
        "tool_version": tool_version,
        "platform": "win64",
        "core": core,
        "packs": manifests,
        "sifli": sifli,
    }
    summary["manifest"] = str(
        out / f"lvgl-verify-loop-{tool_version}-release-all.json"
    )
    summary["upload_checklist"] = str(
        _write_upload_checklist(out, tool_version, core, manifests, sifli)
    )
    Path(summary["manifest"]).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release_all.py",
        description="Build the multi-version release assets.",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--version", default=paths.TOOL_VERSION)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--only", nargs="+", choices=VERSIONS, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = paths.REPO_ROOT
    out = args.out or (repo / "release")
    try:
        summary = release_all(
            repo_root=repo,
            out_dir=out,
            tool_version=args.version,
            smoke=not args.skip_smoke,
            only=tuple(args.only) if args.only else None,
        )
    except (BuildError, OSError) as exc:
        print(f"[release_all] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"[release_all] core: {summary['core']['zip']}")
        for item in summary["packs"]:
            print(f"[release_all] pack {item['lvgl']}: {item['zip']}")
        print(f"[release_all] sifli: {summary['sifli']['zip']}")
        print(f"[release_all] manifest: {summary['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
