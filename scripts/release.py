from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable

_BOOTSTRAP_CONSOLE_ROOT = Path(__file__).resolve().parent.parent / "console"
if str(_BOOTSTRAP_CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_CONSOLE_ROOT))

import paths
import versions
from control.build_plan import BuildPlan
from control.errors import BuildError
from control.prebuilt import HostSdk, resolve_compiler
from digest import sha256_file

CONSOLE_ROOT = paths.CONSOLE_ROOT
REPO_ROOT = paths.REPO_ROOT
SCRIPTS_DIR = paths.SCRIPTS_DIR
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_sdk
import release_bundle

PACKAGE_DIR_NAME = release_bundle.PACKAGE_DIR_NAME
RELEASE_SCHEMA = release_bundle.RELEASE_SCHEMA
VERSION_SCHEMA = release_bundle.VERSION_SCHEMA
DEFAULT_LVGL = versions.default()
SMOKE_SCENARIO = Path("user") / "scenarios" / "intro.json"
RELEASE_INTRO_APP = "intro"
RELEASE_SCENARIOS = ("intro.json",)
RELEASE_APP_FILES = (
    "app.h",
    "app_registry_lookup.h",
    "lvgl_compat.h",
    "GUIDE.md",
)
RELEASE_APP_DIRS = (RELEASE_INTRO_APP,)
TOOL_RELEASE_EXCLUDE_FILES = (
    "README.md",
    "assets/vendor/README.md",
)
PACKAGE_TOOLS_FILES = (
    "lvgl.py",
    "new_app.py",
)
RELEASE_ENGINE_CACHE_DIR = Path("dist") / "release"
RELEASE_ENGINE_SCHEMA = "lvgl-verify-loop-release-engine-v1"
RELEASE_ENGINE_SOURCE_SUFFIXES = frozenset({".c", ".h", ".json", ".inc"})
RELEASE_VIEWER = "LVGL-AI-Viewer.exe"
RELEASE_VIEWER_PATH = Path("bin") / RELEASE_VIEWER
RELEASE_META_DIR = Path("scripts") / "meta"
RELEASE_LICENSE = Path("docs") / "licenses" / "LICENSE"
FORBIDDEN_TOP_LEVEL = {
    ".git",
    ".trash",
    "core",
    "chip-adapt",
    "sifli",
    "sifli-host",
    "smoke",
    "release",
    "lvgl",
    "patches",
    "sessions",
    "tests",
    "third_party",
    ".scratch",
}
FORBIDDEN_ANY_LEVEL = {"__pycache__"}
TOOL_EXCLUDE_DIRS = {"__pycache__", ".cache"}
ENGINE_EXCLUDE_DIRS = {"__pycache__", "lvgl", "third_party"}
APPS_EXCLUDE_DIRS = {".trash", "__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".dump"}

_run = release_bundle.run_command


def copy_tree(
    source: str | Path,
    target: str | Path,
    *,
    exclude_dirs: Iterable[str] = (),
    exclude_files: Iterable[str] = (),
    exclude_suffixes: Iterable[str] = (),
) -> None:
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


def write_version_file(
    package: Path,
    *,
    tool_version: str,
    lvgl_version: str,
    gcc_version: str,
    git_commit: str,
    adapters: list[str] | None = None,
    host_sdks: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": VERSION_SCHEMA,
        "tool_version": tool_version,
        "lvgl": {
            "host_default": lvgl_version,
            "host_sdk": list(host_sdks or [lvgl_version]),
        },
        "gcc": {"version": gcc_version, "source": "system"},
        "git_commit": git_commit,
        "adapters": list(adapters or []),
    }
    version_path = package / RELEASE_META_DIR / "VERSION.json"
    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def write_package_versions(
    package: Path, *, tool_version: str
) -> dict[str, Any]:
    path = package / RELEASE_META_DIR / "versions.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    index.pop("core", None)
    index["tool"] = {"version": tool_version, "platform": "win64"}
    path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return index


def check_hygiene(package: Path, repo_root: Path) -> None:
    package = package.resolve()
    for child in package.iterdir():
        if child.name in FORBIDDEN_TOP_LEVEL:
            raise BuildError(
                f"release hygiene: forbidden top-level entry {child.name!r}"
            )
        if child.is_file() and child.name != "SKILL.md":
            raise BuildError(
                "release hygiene: the package root may only contain SKILL.md, "
                f"found {child.name!r}"
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
    allowed_build_files = {paths.engine_filename()}
    for manifest_path in (package / "dist" / "lvgl").glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for field in ("runtime_dlls", "shared_runtime_dlls"):
            runtime_dlls = manifest.get(field, [])
            if isinstance(runtime_dlls, list):
                allowed_build_files.update(
                    name for name in runtime_dlls if isinstance(name, str)
                )
    if build_root.is_dir():
        for path in build_root.rglob("*"):
            if "sdk" in path.relative_to(build_root).parts:
                continue
            if path.is_file() and path.name not in allowed_build_files:
                raise BuildError(
                    "release hygiene: build intermediate entered the package: "
                    f"{path.relative_to(package)}"
                )
    paths_to_hide = {str(repo_root.resolve()), str(Path.home().resolve())}
    needles = set()
    for value in paths_to_hide:
        needles.add(value.encode("utf-8"))
        needles.add(value.replace("\\", "/").encode("utf-8"))
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise BuildError(
                f"release hygiene: cannot read {path}: {exc}"
            ) from exc
        for needle in needles:
            if needle and needle in data:
                raise BuildError(
                    "release hygiene: development absolute path "
                    f"{needle.decode('utf-8', 'replace')!r} in "
                    f"{path.relative_to(package)}"
                )


def tree_digest(root: Path, suffixes: frozenset[str]) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def release_engine_inputs_digest(
    *,
    version: str,
    engine_dir: Path,
    user_app_dir: Path,
    sdk_dir: Path,
    compiler_version: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(RELEASE_ENGINE_SCHEMA.encode("utf-8"))
    digest.update(b"\0")
    digest.update(version.encode("utf-8"))
    digest.update(b"\0")
    digest.update(
        tree_digest(engine_dir, RELEASE_ENGINE_SOURCE_SUFFIXES).encode("ascii")
    )
    digest.update(b"\0")
    digest.update(
        tree_digest(user_app_dir, RELEASE_ENGINE_SOURCE_SUFFIXES).encode(
            "ascii"
        )
    )
    digest.update(b"\0")
    digest.update(compiler_version.encode("utf-8"))
    digest.update(b"\0")
    manifest = sdk_dir / "manifest.json"
    if manifest.is_file():
        digest.update(manifest.read_bytes())
    return digest.hexdigest()


def _release_engine_cache_matches(
    cache_engine: Path,
    cache_meta: Path,
    digest: str,
) -> bool:
    if not cache_engine.is_file() or not cache_meta.is_file():
        return False
    try:
        meta = json.loads(cache_meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        meta.get("schema") == RELEASE_ENGINE_SCHEMA
        and meta.get("inputs_digest") == digest
        and meta.get("engine_bytes") == cache_engine.stat().st_size
        and meta.get("engine_sha256") == sha256_file(cache_engine)
    )


def _write_staged_app_registry(user_app_dir: Path) -> None:

    from appmgr import discovery

    try:
        discovery.write_registry(user_app_dir)
    except discovery.DiscoveryError as exc:
        raise BuildError(f"release: app discovery failed: {exc}") from exc


def ensure_release_engine(
    *,
    repo_root: Path,
    version: str,
    engine_dir: Path,
    user_app_dir: Path,
    sdk_dir: Path,
    build_dir: Path,
    compiler: str | None = None,
    compiler_version: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    compiler_path, resolved_version = resolve_compiler(
        override=compiler, version=compiler_version
    )
    digest = release_engine_inputs_digest(
        version=version,
        engine_dir=engine_dir,
        user_app_dir=user_app_dir,
        sdk_dir=sdk_dir,
        compiler_version=resolved_version,
    )
    cache_dir = (
        repo_root
        / RELEASE_ENGINE_CACHE_DIR
        / f"lvgl_{paths.version_token(version)}"
    )
    cache_engine = cache_dir / paths.engine_filename()
    cache_meta = cache_dir / "release-engine.json"
    engine = build_dir / paths.engine_filename()
    if not force and _release_engine_cache_matches(
        cache_engine, cache_meta, digest
    ):
        build_dir.mkdir(parents=True, exist_ok=True)
        if cache_engine.resolve() != engine.resolve():
            shutil.copy2(cache_engine, engine)
        sdk = HostSdk.load(sdk_dir, expected_version=version)
        for source in sdk.runtime_dll_paths:
            shutil.copy2(source, build_dir / source.name)
        _write_staged_app_registry(user_app_dir)
        return {
            "cache": str(cache_engine),
            "status": "reused",
            "digest": digest,
            "compiler": compiler_path,
            "compiler_version": resolved_version,
        }
    plan = BuildPlan(
        version,
        lvgl_src=repo_root / "engine" / "lvgl" / version,
        build_dir=build_dir,
        engine_dir=engine_dir,
        user_app_dir=user_app_dir,
        sdk_dir=sdk_dir,
        build_mode="prebuilt",
        compiler=compiler,
        compiler_version=compiler_version,
    )
    plan.execute(build=True)
    if not engine.is_file():
        raise BuildError(
            f"release: prebuilt engine was not produced: {engine}"
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    if cache_engine.resolve() != engine.resolve():
        shutil.copy2(engine, cache_engine)
    cache_meta.write_text(
        json.dumps(
            {
                "schema": RELEASE_ENGINE_SCHEMA,
                "version": version,
                "inputs_digest": digest,
                "engine_sha256": sha256_file(cache_engine),
                "engine_bytes": cache_engine.stat().st_size,
                "compiler": compiler_path,
                "compiler_version": resolved_version,
                "build_mode": "prebuilt",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "cache": str(cache_engine),
        "status": "built",
        "digest": digest,
        "compiler": compiler_path,
        "compiler_version": resolved_version,
    }


def _mark_release_default(apps_dir: Path) -> None:

    path = apps_dir / "app.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["default"] = RELEASE_INTRO_APP
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def stage_user_tree(repo_root: Path, package: Path) -> None:
    app_source = repo_root / "user" / "app"
    app_target = package / "user" / "app"
    app_target.mkdir(parents=True, exist_ok=True)
    for name in RELEASE_APP_FILES:
        source_file = app_source / name
        if not source_file.is_file():
            raise BuildError(f"release: user/app/{name} is missing")
        shutil.copy2(source_file, app_target / name)
    for name in RELEASE_APP_DIRS:
        source_dir = app_source / name
        if not source_dir.is_dir():
            raise BuildError(f"release: user/app/{name} is missing")
        copy_tree(
            source_dir,
            app_target / name,
            exclude_dirs=APPS_EXCLUDE_DIRS,
            exclude_suffixes=EXCLUDE_SUFFIXES,
        )
    intro_readme = app_target / RELEASE_INTRO_APP / "README.md"
    if intro_readme.is_file():
        intro_readme.unlink()
    _mark_release_default(app_target)
    release_app = SCRIPTS_DIR / "release_app.c"
    if not release_app.is_file():
        raise BuildError("release: scripts/release_app.c is missing")
    shutil.copy2(release_app, app_target / "app.c")
    scenario_target = package / "user" / "scenarios"
    scenario_target.mkdir(parents=True, exist_ok=True)
    for name in RELEASE_SCENARIOS:
        source_file = repo_root / "user" / "scenarios" / name
        if not source_file.is_file():
            raise BuildError(f"release: user/scenarios/{name} is missing")
        shutil.copy2(source_file, scenario_target / name)


def stage_package(
    *,
    repo_root: Path,
    package: Path,
    sdk_dir: Path,
    lvgl_version: str,
    tool_version: str,
    compiler: str | None = None,
    compiler_version: str | None = None,
    host_sdks: list[str] | None = None,
    force_build: bool = False,
) -> dict[str, Any]:
    package.mkdir(parents=True)
    skill_source = repo_root / "docs" / "skill" / "SKILL.md"
    if skill_source.is_file():
        shutil.copy2(skill_source, package / "SKILL.md")
    license_source = repo_root / "LICENSE"
    if license_source.is_file():
        license_target = package / RELEASE_LICENSE
        license_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_source, license_target)
    versions_source = repo_root / "scripts" / "meta" / "versions.json"
    if not versions_source.is_file():
        versions_source = repo_root / "versions.json"
    if not versions_source.is_file():
        raise BuildError("release: versions.json is missing")
    versions_target = package / RELEASE_META_DIR / "versions.json"
    versions_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(versions_source, versions_target)
    write_package_versions(package, tool_version=tool_version)
    copy_tree(
        repo_root / "console",
        package / "console",
        exclude_dirs=TOOL_EXCLUDE_DIRS,
        exclude_suffixes=EXCLUDE_SUFFIXES,
    )
    for name in TOOL_RELEASE_EXCLUDE_FILES:
        path = package / "console" / name
        if path.is_file():
            path.unlink()
    engine_target = package / "engine"
    copy_tree(
        repo_root / "engine",
        engine_target,
        exclude_dirs={"__pycache__", "lvgl", "third_party"},
        exclude_suffixes=EXCLUDE_SUFFIXES | {".c"},
    )
    main_source = repo_root / "engine" / "core" / "main.c"
    if not main_source.is_file():
        raise BuildError("release: engine/core/main.c is missing")
    main_target = engine_target / "core" / "main.c"
    main_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main_source, main_target)
    copy_tree(repo_root / "docs" / "skill" / "api-nav", package / "api-nav")
    tools_target = package / "scripts"
    tools_target.mkdir(parents=True, exist_ok=True)
    for name in PACKAGE_TOOLS_FILES:
        source_file = repo_root / "scripts" / name
        if not source_file.is_file():
            raise BuildError(f"release: scripts/{name} is missing")
        shutil.copy2(source_file, tools_target / name)
    stage_user_tree(repo_root, package)
    copy_tree(repo_root / "docs" / "licenses", package / "docs" / "licenses")
    bin_target = package / "bin"
    bin_target.mkdir(parents=True, exist_ok=True)
    wrapper = repo_root / "bin" / "lvgl.cmd"
    if not wrapper.is_file():
        raise BuildError("release: bin/lvgl.cmd is missing")
    shutil.copy2(wrapper, bin_target / "lvgl.cmd")
    viewer = repo_root / RELEASE_VIEWER_PATH
    if not viewer.is_file():
        raise BuildError(
            f"release: {RELEASE_VIEWER_PATH.as_posix()} is missing; "
            "run scripts/launchers/build.py first"
        )
    shutil.copy2(viewer, bin_target / RELEASE_VIEWER)
    sdk_target = package / "dist" / "lvgl" / lvgl_version
    shutil.copytree(sdk_dir, sdk_target)

    token = paths.version_token(lvgl_version)
    build_dir = package / "build" / f"lvgl_{token}"
    engine_result = ensure_release_engine(
        repo_root=repo_root,
        version=lvgl_version,
        engine_dir=repo_root / "engine",
        user_app_dir=package / "user" / "app",
        sdk_dir=sdk_target,
        build_dir=build_dir,
        compiler=compiler,
        compiler_version=compiler_version,
        force=force_build,
    )

    sdk_manifest = json.loads(
        (sdk_target / "manifest.json").read_text(encoding="utf-8")
    )
    version = write_version_file(
        package,
        tool_version=tool_version,
        lvgl_version=lvgl_version,
        gcc_version=str(sdk_manifest["compiler"]["version"]),
        git_commit=release_bundle.git_commit(repo_root),
        adapters=[],
        host_sdks=host_sdks,
    )
    return {
        "engine": engine_result,
        "sdk_manifest": sdk_manifest,
        "version": version,
    }


def purge_caches(package: Path) -> None:
    for path in sorted(package.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for path in package.rglob("*.pyc"):
        try:
            path.unlink()
        except OSError:
            pass


def clean_build_dir(package: Path, lvgl_version: str) -> Path:
    token = paths.version_token(lvgl_version)
    build_root = package / "build"
    target_dir = build_root / f"lvgl_{token}"
    engine = target_dir / paths.engine_filename()
    if not engine.is_file():
        raise BuildError(
            f"release: engine is missing before packaging: {engine}"
        )
    keep = [engine]
    sdk_manifest = package / "dist" / "lvgl" / lvgl_version / "manifest.json"
    if sdk_manifest.is_file():
        try:
            dlls = json.loads(sdk_manifest.read_text(encoding="utf-8")).get(
                "runtime_dlls", []
            )
        except (OSError, ValueError):
            dlls = []
        if isinstance(dlls, list):
            keep.extend(
                target_dir / name
                for name in dlls
                if isinstance(name, str) and (target_dir / name).is_file()
            )
    temporary = package / ".engine-keep"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    for path in keep:
        shutil.move(str(path), str(temporary / path.name))
    shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)
    for path in keep:
        shutil.move(str(temporary / path.name), str(target_dir / path.name))
    temporary.rmdir()
    return engine


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for path in sorted(
        root.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def share_sdk_payload(
    package: Path, versions: Iterable[str]
) -> dict[str, Any]:
    versions = list(versions)
    summary: dict[str, Any] = {
        "versions": versions,
        "shared_files": [],
        "saved_bytes": 0,
    }
    if len(versions) < 2:
        return summary
    sdk_root = package / "dist" / "lvgl"
    files_by_version: dict[str, dict[str, Path]] = {}
    for version in versions:
        root = sdk_root / version
        if not (root / "manifest.json").is_file():
            raise BuildError(f"release: SDK manifest is missing for {version}")
        files: dict[str, Path] = {}
        for sub in ("include", "lib"):
            base = root / sub
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    files[path.relative_to(root).as_posix()] = path
        files_by_version[version] = files

    common = sdk_root / "common"
    shared_rels: list[str] = []
    shared_libs: set[str] = set()
    shared_dlls: set[str] = set()
    shared_include = False
    for rel in sorted(
        set.intersection(*(set(files) for files in files_by_version.values()))
    ):
        first = files_by_version[versions[0]][rel]
        digest = sha256_file(first)
        if any(
            sha256_file(files_by_version[version][rel]) != digest
            for version in versions[1:]
        ):
            continue
        size = first.stat().st_size
        target = common / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first, target)
        for version in versions:
            files_by_version[version][rel].unlink()
        shared_rels.append(rel)
        summary["saved_bytes"] += size * (len(versions) - 1)
        if rel.startswith("include/"):
            shared_include = True
        elif rel.startswith("lib/") and "/" not in rel[len("lib/") :]:
            name = Path(rel).name
            if name.lower().endswith(".dll"):
                shared_dlls.add(name)
            else:
                shared_libs.add(name)

    if not shared_rels:
        shutil.rmtree(common, ignore_errors=True)
        return summary

    shared_lib_list = sorted(shared_libs)
    shared_dll_list = sorted(shared_dlls)
    for version in versions:
        root = sdk_root / version
        _prune_empty_dirs(root / "include")
        _prune_empty_dirs(root / "lib")
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        include_dirs = [
            rel
            for rel in manifest.get("include_dirs", [])
            if rel == "." or (root / rel).is_dir()
        ]
        manifest["include_dirs"] = include_dirs
        manifest["libs"] = [
            name
            for name in manifest.get("libs", [])
            if name not in shared_libs
        ]
        manifest["runtime_dlls"] = [
            name
            for name in manifest.get("runtime_dlls", [])
            if name not in shared_dlls
        ]
        manifest["shared_root"] = "common"
        if shared_include:
            manifest["shared_include_dirs"] = ["include"]
        if shared_lib_list:
            manifest["shared_libs"] = shared_lib_list
        if shared_dll_list:
            manifest["shared_runtime_dlls"] = shared_dll_list
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    summary["shared_files"] = shared_rels
    return summary


def strip_build_runtime_dlls(package: Path) -> None:
    build_root = package / "build"
    if not build_root.is_dir():
        return
    for path in build_root.glob("lvgl_*/*.dll"):
        if path.is_file():
            path.unlink()


_cli_command = release_bundle.cli_command
_smoke_env = release_bundle.smoke_environment


def _json_line(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return release_bundle.json_line(result, label="release smoke")


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


def _smoke_scenario(
    package: Path, lvgl_version: str, workspace: Path, *extra: str
) -> dict[str, Any]:
    return release_bundle.smoke_scenario(
        package,
        lvgl_version,
        package / SMOKE_SCENARIO,
        workspace,
        extra=extra,
        require_evidence=True,
        label="release smoke",
        timeout=300.0,
    )


_cmd_wrapper = release_bundle.cmd_wrapper


def _smoke_wrapper_run(
    package: Path, lvgl_version: str, workspace: Path
) -> dict[str, Any]:
    scenario = package / SMOKE_SCENARIO
    env = _smoke_env(workspace)
    result = _run(
        _cmd_wrapper(
            package,
            "run",
            "--lvgl",
            lvgl_version,
            "--no-build",
            "--scenario",
            str(scenario),
            "--json",
        ),
        cwd=workspace,
        env=env,
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


def _smoke_assets(package: Path, workspace: Path) -> dict[str, Any]:
    result = _run(
        _cmd_wrapper(package, "assets", "doctor", "--json"),
        cwd=workspace,
        env=_smoke_env(workspace),
    )
    if result.returncode != 0:
        raise BuildError(
            "release smoke: bin/lvgl.cmd assets doctor failed; "
            f"stdout={result.stdout.strip()[:500]!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )
    payload = _json_line(result)
    if not payload.get("ok"):
        raise BuildError(
            f"release smoke: assets doctor reported {payload.get('error')!r}"
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
        raise BuildError(
            "release smoke: serve check currently requires Windows"
        )
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
    with tempfile.TemporaryDirectory(prefix="lvgl-verify-loop-smoke-") as raw:
        workspace = Path(raw)
        no_build = _smoke_scenario(
            package, lvgl_version, workspace, "--no-build"
        )
        prebuilt = _smoke_scenario(
            package, lvgl_version, workspace, "--prebuilt"
        )
        build_log = Path(str(prebuilt["session_dir"])) / "build.log"
        if "# build mode: prebuilt" not in build_log.read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BuildError(
                "release smoke: prebuilt session build.log has no mode line"
            )
        wrapper = _smoke_wrapper_run(package, lvgl_version, workspace)
        assets = _smoke_assets(package, workspace)
        serve = _smoke_serve(package, workspace)
        return {
            "no_build_session": no_build.get("session_id"),
            "prebuilt_session": prebuilt.get("session_id"),
            "wrapper_session": wrapper.get("session_id"),
            "assets_doctor": assets,
            "serve_url": serve["url"],
        }


build_zip = release_bundle.build_zip


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
    host_sdks: list[str] | None = None,
    asset_name: str | None = None,
    force_build: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    out_dir = out_dir.resolve()
    sdk_dir = sdk_dir.resolve()
    if not (sdk_dir / "manifest.json").is_file():
        if not export_sdk_if_missing:
            raise BuildError(
                f"host SDK not found: {sdk_dir}; run scripts/export_sdk.py first"
            )
        export_sdk.export_sdk(
            version=lvgl_version,
            out_dir=sdk_dir,
            repo_root=repo_root,
            force=True,
        )
    with tempfile.TemporaryDirectory(
        prefix="lvgl-verify-loop-release-"
    ) as raw:
        staging_package = Path(raw) / PACKAGE_DIR_NAME
        staged = stage_package(
            repo_root=repo_root,
            package=staging_package,
            sdk_dir=sdk_dir,
            lvgl_version=lvgl_version,
            tool_version=tool_version,
            compiler=compiler,
            compiler_version=compiler_version,
            host_sdks=host_sdks,
            force_build=force_build,
        )
        if smoke:
            smoke_package(staging_package, lvgl_version)
        purge_caches(staging_package)
        clean_build_dir(staging_package, lvgl_version)
        check_hygiene(staging_package, repo_root)

        out_dir.mkdir(parents=True, exist_ok=True)
        package = out_dir / PACKAGE_DIR_NAME
        if package.exists():
            shutil.rmtree(package)
        shutil.move(str(staging_package), str(package))

        zip_path = out_dir / (
            asset_name
            or f"{PACKAGE_DIR_NAME}-{tool_version}-{lvgl_version}.zip"
        )
        zip_hash = release_bundle.build_zip(package, zip_path)
    sha_path = release_bundle.write_checksum(zip_path, zip_hash)
    _manifest, manifest_path = release_bundle.write_manifest(
        package,
        zip_path,
        tool_version=tool_version,
        git_commit=staged["version"]["git_commit"],
        lvgl_version=lvgl_version,
        gcc_version=str(staged["version"]["gcc"]["version"]),
        adapters=[],
        digest=zip_hash,
    )
    return {
        "package": str(package),
        "zip": str(zip_path),
        "sha256": zip_hash,
        "sha256_file": str(sha_path),
        "manifest": str(manifest_path),
        "engine": staged["engine"],
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
        help="output directory (default: <repo>/release)",
    )
    parser.add_argument(
        "--sdk",
        type=Path,
        default=None,
        help="existing host SDK directory (default: dist/lvgl/<lvgl>)",
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
        "--force-build",
        action="store_true",
        help="rebuild the prebuilt engine even when its inputs are unchanged",
    )
    parser.add_argument(
        "--asset-name",
        default=None,
        help="override the zip file name (default: <package>-<version>-<lvgl>.zip)",
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
    sdk_dir = args.sdk or (repo / "dist" / "lvgl" / args.lvgl)
    out_dir = args.out or (repo / "dist" / "release")
    try:
        summary = release(
            repo_root=repo,
            out_dir=out_dir,
            tool_version=args.version,
            lvgl_version=args.lvgl,
            sdk_dir=sdk_dir,
            export_sdk_if_missing=not args.no_export_sdk,
            smoke=not args.skip_smoke,
            asset_name=args.asset_name,
            force_build=args.force_build,
        )
    except BuildError as exc:
        print(f"[release] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    else:
        print(f"[release] package: {summary['package']}")
        print(f"[release] zip: {summary['zip']}")
        print(f"[release] sha256: {summary['sha256']}")
        print(f"[release] manifest: {summary['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
