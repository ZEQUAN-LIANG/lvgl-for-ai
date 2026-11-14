"""The release artifact contract shared by every bundle build.

Both ``release.py`` (one package) and ``release_all.py`` (two bundles) write
the same product shape:

* a deterministic ``<package>/...`` zip;
* ``<zip>.sha256`` with the coreutils ``<digest>  <name>`` line;
* ``<zip stem>.release.json`` with per-file hashes and SDK provenance.

Keeping the writers here means the two entry points cannot drift.  Staging,
engine builds and smoke checks stay in the entry points (or in ``release.py``)
until the shared orchestration layer is in place.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

from lvgl_ai.control.errors import BuildError
from lvgl_ai.digest import sha256_file

PACKAGE_DIR_NAME = "lvgl-verify-loop"
RELEASE_SCHEMA = "lvgl-ai-release-v1"
VERSION_SCHEMA = "lvgl-ai-version-v1"
BUNDLE_SCHEMA = "lvgl-verify-loop-release-v2"


def git_commit(repo_root: Path) -> str:
    """Return the current commit, or ``"unknown"`` outside a git checkout."""
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


def file_hashes(package: Path) -> dict[str, str]:
    """Hash every packaged file relative to the package root."""
    paths = sorted(
        (path for path in package.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(package).as_posix(),
    )
    return {
        path.relative_to(package).as_posix(): sha256_file(path)
        for path in paths
    }


def package_stats(package: Path) -> dict[str, int]:
    files = [path for path in package.rglob("*") if path.is_file()]
    return {
        "file_count": len(files),
        "unpacked_bytes": sum(path.stat().st_size for path in files),
    }


def write_checksum(zip_path: Path, digest: str | None = None) -> Path:
    """Write ``<zip>.sha256`` and return its path."""
    digest = digest or sha256_file(zip_path)
    path = zip_path.with_name(zip_path.name + ".sha256")
    path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def build_manifest(
    package: Path,
    zip_path: Path,
    *,
    tool_version: str,
    git_commit: str,
    lvgl_version: str,
    gcc_version: str,
    adapters: Iterable[str] = (),
    digest: str | None = None,
    sdk_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``lvgl-ai-release-v1`` payload for one package zip."""
    if sdk_manifest is None:
        manifest_path = package / "sdk" / lvgl_version / "manifest.json"
        sdk_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sdk_manifest_sha256 = sha256_file(
        package / "sdk" / lvgl_version / "manifest.json"
    )
    digest = digest or sha256_file(zip_path)
    stats = package_stats(package)
    return {
        "schema": RELEASE_SCHEMA,
        "tool_version": tool_version,
        "git_commit": git_commit,
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
        "gcc": {"version": gcc_version},
        "adapters": list(adapters),
        "package": {
            "root": PACKAGE_DIR_NAME,
            **stats,
            "archive_bytes": zip_path.stat().st_size,
        },
        "sha256": digest,
        "files": file_hashes(package),
    }


def write_manifest(
    package: Path,
    zip_path: Path,
    *,
    tool_version: str,
    git_commit: str,
    lvgl_version: str,
    gcc_version: str,
    adapters: Iterable[str] = (),
    digest: str | None = None,
    sdk_manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write ``<zip stem>.release.json`` and return ``(payload, path)``."""
    payload = build_manifest(
        package,
        zip_path,
        tool_version=tool_version,
        git_commit=git_commit,
        lvgl_version=lvgl_version,
        gcc_version=gcc_version,
        adapters=adapters,
        digest=digest,
        sdk_manifest=sdk_manifest,
    )
    path = zip_path.with_name(f"{zip_path.stem}.release.json")
    write_json(path, payload)
    return payload, path


def write_summary(out_dir: Path, payload: dict[str, Any]) -> Path:
    """Write the double-bundle ``release.json`` summary."""
    return write_json(out_dir / "release.json", payload)


def run_command(
    command: Iterable[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess[str]:
    """Run one release subprocess with captured UTF-8 output."""
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


def json_line(
    result: subprocess.CompletedProcess[str], *, label: str = "release smoke"
) -> dict[str, Any]:
    """Parse the single JSON line a CLI smoke command prints."""
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise BuildError(
            f"{label}: expected one JSON line, got {lines!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )
    try:
        payload = json.loads(lines[0])
    except ValueError as exc:
        raise BuildError(f"{label}: invalid JSON: {lines[0][:200]}") from exc
    if not isinstance(payload, dict):
        raise BuildError(f"{label}: JSON summary is not an object")
    return payload


def smoke_environment(workspace: Path) -> dict[str, str]:
    """Return a clean CLI environment rooted at ``workspace``."""
    env = os.environ.copy()
    env["LVGL_AI_SESSIONS_ROOT"] = str(workspace / "sessions")
    env.pop("LVGL_AI_LVGL_SRC", None)
    env.pop("LVGL_AI_DEMO", None)
    return env


def cli_command(
    package: Path, lvgl_version: str, *args: str
) -> list[str]:
    return [
        sys.executable,
        "-I", "-B",
        str(package / "core" / "cli.py"),
        "--lvgl", lvgl_version,
        *args,
    ]


def cmd_wrapper(package: Path, *args: str) -> list[str]:
    command = [str(package / "bin" / "lvgl.cmd"), *args]
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", *command]
    return command


def smoke_scenario(
    package: Path,
    lvgl_version: str,
    scenario: Path,
    workspace: Path,
    *,
    via_wrapper: bool = False,
    extra: Iterable[str] = (),
    markers: Iterable[str] = (),
    require_evidence: bool = False,
    label: str = "release smoke",
    timeout: float = 180.0,
    run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Run one packaged scenario and verify its status, evidence and markers."""
    common = (*extra, "--scenario", str(scenario), "--json")
    if via_wrapper:
        command = cmd_wrapper(package, "run", "--lvgl", lvgl_version, *common)
    else:
        command = cli_command(package, lvgl_version, *common)
    runner = run or run_command
    result = runner(
        command,
        cwd=workspace,
        env=smoke_environment(workspace),
        timeout=timeout,
    )
    if result.returncode != 0:
        raise BuildError(
            f"{label}: scenario failed; "
            f"stdout={result.stdout.strip()[:500]!r}; "
            f"stderr={result.stderr.strip()[:500]!r}"
        )
    payload = json_line(result, label=label)
    if payload.get("status") != "ok":
        raise BuildError(
            f"{label}: scenario finished with status={payload.get('status')!r}: "
            f"{payload.get('error')!r}"
        )
    session_dir = Path(str(payload.get("session_dir")))
    if require_evidence:
        for name in ("manifest.json", "timeline.ndjson", "engine.log", "build.log"):
            if not (session_dir / name).is_file():
                raise BuildError(f"{label}: session evidence missing {name}")
    marker_list = list(markers)
    if marker_list:
        log_path = session_dir / "engine.log"
        log = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.is_file()
            else ""
        )
        missing = [marker for marker in marker_list if marker not in log]
        if missing:
            raise BuildError(
                f"{label}: engine.log is missing {missing!r}; "
                f"log tail={log[-800:]!r}"
            )
    return payload
