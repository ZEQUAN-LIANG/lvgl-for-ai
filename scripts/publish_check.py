from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Sequence

_SCRIPTS_DIR = Path(__file__).resolve().parent
_CONSOLE_ROOT = _SCRIPTS_DIR.parent / "console"
for _path in (_SCRIPTS_DIR, _CONSOLE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import paths
from digest import sha256_file

REPO_ROOT = paths.REPO_ROOT
DIST_RELEASE = REPO_ROOT / "dist" / "release"
PACKAGE_DIR_NAME = "lvgl-verify-loop"
SKILL_DIR_NAME = "lvgl-verify-loop"
FULL_TEMPLATE = "lvgl-verify-loop-{version}-full-win64.zip"
FULL_SIFLI_TEMPLATE = (
    "lvgl-verify-loop-{version}-full-sifli-win64.zip"
)

GITHUB_REPO = "ZEQUAN-LIANG/lvgl-for-ai"
GITEE_REPO = "liang-zequan/lvgl-for-ai"
GITHUB_API = "https://api.github.com"
GITEE_API = "https://gitee.com/api/v5"
USER_AGENT = "lvgl-verify-loop-publish-check"

VERSION_FILES = (
    "console/paths.py",
    "scripts/meta/versions.json",
    "scripts/tests/tools/test_repo_contract.py",
    "scripts/tests/tools/test_contract_snapshot.py",
    "scripts/contract_snapshot.json",
    "README.md",
    "README.zh-CN.md",
    "CLAUDE.md",
)

STALE_CARRIERS = (
    "README.md",
    "README.zh-CN.md",
    "console/paths.py",
    "scripts/meta/versions.json",
    "scripts/contract_snapshot.json",
)

NARRATIVE_FILES = (
    "docs/RELEASE.md",
)

GENERATED_ALLOWLIST = (
    "user/app/perf_monitor/assets.json",
    "user/app/perf_monitor/perf_font_",
)

REQUIRED_ENTRIES = (
    "api-nav",
    "console",
    "engine",
    "user/app",
    "user/scenarios",
    "scripts",
    "bin/lvgl.cmd",
    "dist/lvgl",
    "build",
    "docs/licenses",
)

FORBIDDEN_ENTRIES = (
    "engine/lvgl",
    "engine/third_party",
    "lvgl-src",
    "smoke",
    "tests",
)


class CheckError(Exception):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def staged_zip(version: str, *, sifli: bool = False) -> Path:
    template = FULL_SIFLI_TEMPLATE if sifli else FULL_TEMPLATE
    return DIST_RELEASE / template.format(version=version)


def stage_version(version: str) -> dict[str, Any]:
    errors: list[str] = []
    matches: dict[str, list[str]] = {}
    for relative in VERSION_FILES:
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"{relative}: missing")
            continue
        found = [
            f"{relative}:{number}"
            for number, line in enumerate(read_text(path).splitlines(), 1)
            if version in line
        ]
        matches[relative] = found

    for required in (
        "console/paths.py",
        "scripts/meta/versions.json",
        "scripts/contract_snapshot.json",
        "README.md",
        "README.zh-CN.md",
    ):
        if not matches.get(required):
            errors.append(f"{required}: does not carry {version}")

    tool_version = paths.TOOL_VERSION
    if tool_version != version:
        errors.append(
            f"console/paths.py: TOOL_VERSION is {tool_version!r}, "
            f"expected {version!r}"
        )

    index_path = REPO_ROOT / "scripts" / "meta" / "versions.json"
    try:
        index = json.loads(read_text(index_path))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"scripts/meta/versions.json: {exc}")
        index = {}
    recorded = (index.get("tool") or {}).get("version")
    if recorded != version:
        errors.append(
            f"scripts/meta/versions.json: tool.version is {recorded!r}, "
            f"expected {version!r}"
        )

    snapshot_path = REPO_ROOT / "scripts" / "contract_snapshot.json"
    try:
        snapshot = json.loads(read_text(snapshot_path))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"scripts/contract_snapshot.json: {exc}")
        snapshot = {}
    snapshot_version = (
        snapshot.get("sections", {}).get("python", {}).get("paths", {})
    ).get("tool_version")
    if snapshot_version != version:
        errors.append(
            "scripts/contract_snapshot.json: paths.tool_version is "
            f"{snapshot_version!r}, expected {version!r}"
        )

    previous = _previous_version(version)
    warnings: list[str] = []
    if previous:
        for relative in _stray_references(previous):
            if relative in STALE_CARRIERS:
                errors.append(
                    f"{relative}: still references {previous}; "
                    "required carriers must describe only the current release"
                )
            elif relative not in NARRATIVE_FILES:
                warnings.append(f"{relative} references {previous}")

    return {
        "stage": "version",
        "version": version,
        "ok": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "matches": matches,
    }


def _previous_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or not parts[2].isdigit():
        return ""
    return f"{parts[0]}.{parts[1]}.{int(parts[2]) - 1}"


def _stray_references(needle: str) -> list[str]:
    tracked: list[str] = []
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "grep", "-l", "-F", needle],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    for line in result.stdout.splitlines():
        relative = line.strip().replace("\\", "/")
        if not relative:
            continue
        if relative.startswith(GENERATED_ALLOWLIST):
            continue
        if relative.startswith((".claude/worktrees/", "chip-adapt/exports/")):
            continue
        if relative.startswith("chip-adapt/vendor/"):
            continue
        tracked.append(relative)
    return sorted(set(tracked))


def _read_zip_entry(archive: zipfile.ZipFile, name: str) -> str | None:
    try:
        return archive.read(name).decode("utf-8", "replace")
    except KeyError:
        return None


def stage_package(version: str) -> dict[str, Any]:
    errors: list[str] = []
    packages: list[dict[str, Any]] = []
    for sifli in (False, True):
        zip_path = staged_zip(version, sifli=sifli)
        entry: dict[str, Any] = {
            "zip": str(zip_path),
            "name": zip_path.name,
            "sifli": sifli,
        }
        if not zip_path.is_file():
            errors.append(f"{zip_path.name}: missing; run release_all.py")
            packages.append(entry)
            continue
        entry["sha256"] = sha256_file(zip_path)
        entry["bytes"] = zip_path.stat().st_size
        checksum = zip_path.with_name(zip_path.name + ".sha256")
        if not checksum.is_file():
            errors.append(f"{checksum.name}: missing")
        else:
            recorded = read_text(checksum).split()[0].strip()
            if recorded != entry["sha256"]:
                errors.append(
                    f"{checksum.name}: records {recorded[:12]}, "
                    f"zip is {entry['sha256'][:12]}"
                )
            entry["sha256_file"] = str(checksum)
        problems = _inspect_package(zip_path, version)
        entry["errors"] = problems
        errors.extend(problems)
        packages.append(entry)
    return {
        "stage": "package",
        "version": version,
        "ok": not errors,
        "errors": errors,
        "packages": packages,
    }


def _inspect_package(zip_path: Path, version: str) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        prefix = PACKAGE_DIR_NAME + "/"
        if not any(name == prefix + "SKILL.md" for name in names):
            errors.append(f"{zip_path.name}: SKILL.md is missing")
        root_files = sorted(
            name[len(prefix) :]
            for name in names
            if name.startswith(prefix)
            and "/" not in name[len(prefix) :]
            and name != prefix
        )
        if root_files != ["SKILL.md"]:
            errors.append(
                f"{zip_path.name}: root files must be ['SKILL.md'], "
                f"got {root_files}"
            )
        entries = {
            name[len(prefix) :] for name in names if name.startswith(prefix)
        }
        for relative in REQUIRED_ENTRIES:
            if not any(
                entry == relative or entry.startswith(relative + "/")
                for entry in entries
            ):
                errors.append(f"{zip_path.name}: missing {relative}")
        for relative in FORBIDDEN_ENTRIES:
            if any(
                entry == relative or entry.startswith(relative + "/")
                for entry in entries
            ):
                errors.append(f"{zip_path.name}: unexpected {relative}")

        version_text = _read_zip_entry(
            archive, prefix + "scripts/meta/VERSION.json"
        )
        if version_text is None:
            errors.append(f"{zip_path.name}: scripts/meta/VERSION.json missing")
        else:
            try:
                payload = json.loads(version_text)
            except json.JSONDecodeError as exc:
                errors.append(
                    f"{zip_path.name}: VERSION.json is not JSON: {exc}"
                )
            else:
                packaged = payload.get("tool_version")
                if packaged != version:
                    errors.append(
                        f"{zip_path.name}: VERSION.json tool_version is "
                        f"{packaged!r}, expected {version!r}"
                    )
                errors.extend(
                    _check_packaged_commit(zip_path, payload.get("git_commit"))
                )
    return errors


def _check_packaged_commit(zip_path: Path, packaged: Any) -> list[str]:
    tagged = _tagged_commit()
    if not tagged or not isinstance(packaged, str):
        return []
    if tagged.startswith(packaged) or packaged.startswith(tagged):
        return []
    return [
        f"{zip_path.name}: VERSION.json records commit {packaged[:8]}, "
        f"but the version tag points at {tagged[:8]}; the package was built "
        "before the release commit, so commit first and rebuild"
    ]


def _tagged_commit() -> str:
    tag = f"v{paths.TOOL_VERSION}^{{commit}}"
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", tag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""
    text = result.stdout.strip()
    return text if result.returncode == 0 else ""


def _backup_root() -> Path:
    base = os.environ.get("TEMP") or os.environ.get("TMP")
    if not base:
        base = str(Path.home() / "AppData" / "Local" / "Temp")
    return Path(base) / "lvgl-verify-loop-skill-backup"


def stage_install(
    version: str, *, keep_backup: bool = False
) -> dict[str, Any]:
    errors: list[str] = []
    skill_root = _skill_root()
    zip_path = staged_zip(version)
    if not zip_path.is_file():
        raise CheckError(f"{zip_path} is missing; run release_all.py first")
    if skill_root is None:
        raise CheckError(
            "cannot resolve the skill install directory; set USERPROFILE"
        )

    target = skill_root / SKILL_DIR_NAME
    backup: Path | None = None
    if target.is_dir():
        root = _backup_root()
        root.mkdir(parents=True, exist_ok=True)
        backup = root / f"{SKILL_DIR_NAME}-{time.strftime('%Y%m%d-%H%M%S')}"
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        shutil.move(str(target), str(backup))
    skill_root.mkdir(parents=True, exist_ok=True)

    installed: dict[str, Any] = {"skill_dir": str(target)}
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(skill_root)
        if not (target / "SKILL.md").is_file():
            raise CheckError(
                f"{zip_path.name}: SKILL.md was not extracted to {target}"
            )
        installed["backup"] = str(backup) if backup else None
        installed.update(_run_skill_flow(target, version))
    except (CheckError, OSError, zipfile.BadZipFile) as exc:
        errors.append(str(exc))
        if backup is not None:
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(backup), str(target))
            installed["restored"] = str(backup)
            backup = None
    if backup is not None and not keep_backup:
        shutil.rmtree(backup, ignore_errors=True)
        installed["backup"] = None
    if keep_backup and backup is not None:
        installed["backup"] = str(backup)
    return {
        "stage": "install",
        "version": version,
        "ok": not errors,
        "errors": errors,
        "install": installed,
    }


def _skill_root() -> Path | None:
    profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if not profile:
        return None
    return Path(profile) / ".claude" / "skills"


def _run(
    args: Sequence[str], *, cwd: Path, timeout: float
) -> dict[str, Any]:
    command = [sys.executable, "-I", "-B", *args]
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CheckError(
            f"timed out after {timeout:.0f}s: {' '.join(command)}"
        ) from exc
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _run_skill_flow(target: Path, version: str) -> dict[str, Any]:
    report: dict[str, Any] = {"steps": []}
    scenario = _first_scenario(target)
    run = _run(
        [
            "console/entrypoints/cli.py",
            "--scenario",
            scenario,
            "--json",
        ],
        cwd=target,
        timeout=900.0,
    )
    report["steps"].append(_step("run", run))
    if run["returncode"] != 0:
        raise CheckError(
            f"package run failed: {run['stderr'][-500:]}"
        )
    index = _session_index(run)
    report["session"] = index

    session_dir = index.get("session_dir")
    if not session_dir:
        raise CheckError("run --json did not report session_dir")
    session = Path(session_dir)
    for relative in ("manifest.json", "timeline.ndjson", "frames"):
        if not (session / relative).exists():
            raise CheckError(f"session is missing {relative}")
    manifest = json.loads(read_text(session / "manifest.json"))
    if manifest.get("status") != "ok":
        raise CheckError(
            f"session status is {manifest.get('status')!r}, expected 'ok'"
        )
    if manifest.get("tool_version") != version:
        raise CheckError(
            f"session tool_version is {manifest.get('tool_version')!r}, "
            f"expected {version!r}"
        )
    report["timeline_frames"] = sum(
        1 for _ in (session / "timeline.ndjson").open(encoding="utf-8")
    )

    for name, args, timeout in (
        (
            "report",
            [
                "console/entrypoints/session_report.py",
                "--latest",
                "--log-tail",
                "3",
            ],
            300.0,
        ),
        (
            "assets",
            ["console/entrypoints/assets_tool.py", "doctor", "--json"],
            300.0,
        ),
    ):
        outcome = _run(args, cwd=target, timeout=timeout)
        report["steps"].append(_step(name, outcome))
        if outcome["returncode"] != 0:
            raise CheckError(
                f"package {name} failed: {outcome['stderr'][-500:]}"
            )
    return report


def _step(name: str, outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "ok": outcome["returncode"] == 0,
        "command": outcome["command"],
        "stderr_tail": outcome["stderr"][-800:],
    }


def _first_scenario(target: Path) -> str:
    preferred = target / "user" / "scenarios" / "intro.json"
    if preferred.is_file():
        return "user/scenarios/intro.json"
    scenarios = sorted(
        (target / "user" / "scenarios").glob("*.json")
    )
    if not scenarios:
        raise CheckError("the package has no scenarios")
    return scenarios[0].relative_to(target).as_posix()


def _session_index(run: dict[str, Any]) -> dict[str, Any]:
    lines = [line for line in run["stdout"].splitlines() if line.strip()]
    if not lines:
        raise CheckError("run --json printed nothing on stdout")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise CheckError(f"cannot parse run --json output: {exc}") from exc


def _request(
    url: str, *, headers: dict[str, str], timeout: float = 60.0
) -> Any:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        raise CheckError(f"GET {url.split('?', 1)[0]} failed: {exc}") from exc


def _gitee_asset_names(payload: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(payload, dict):
        return names
    for key in ("assets", "attach_files"):
        for item in payload.get(key) or []:
            if isinstance(item, dict) and item.get("name"):
                names.add(str(item["name"]))
    return names


def stage_remote(version: str) -> dict[str, Any]:
    errors: list[str] = []
    tag = f"v{version}"
    releases: dict[str, Any] = {}

    gitee_token = os.environ.get("GITEE_TOKEN", "").strip()
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not gitee_token:
        errors.append("GITEE_TOKEN is not set")
    else:
        url = (
            f"{GITEE_API}/repos/{GITEE_REPO}/releases/tags/{tag}"
            f"?access_token={urllib.parse.quote(gitee_token)}"
        )
        try:
            payload = _request(url, headers={"User-Agent": USER_AGENT})
            releases["gitee"] = {
                "url": f"https://gitee.com/{GITEE_REPO}/releases/tag/{tag}",
                "assets": sorted(_gitee_asset_names(payload)),
            }
        except CheckError as exc:
            errors.append(f"gitee: {exc}")

    if not github_token:
        errors.append("GITHUB_TOKEN is not set")
    else:
        url = f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/tags/{tag}"
        headers = {
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            payload = _request(url, headers=headers)
            releases["github"] = {
                "url": (payload or {}).get("html_url"),
                "assets": sorted(
                    item.get("name", "")
                    for item in (payload or {}).get("assets") or []
                ),
            }
        except CheckError as exc:
            errors.append(f"github: {exc}")

    expected = sorted(
        [staged_zip(version).name, staged_zip(version, sifli=True).name]
        + [
            staged_zip(version).name + ".sha256",
            staged_zip(version, sifli=True).name + ".sha256",
            "release.json",
        ]
    )
    for provider, record in releases.items():
        missing = [name for name in expected if name not in record["assets"]]
        if missing:
            errors.append(f"{provider}: missing assets {missing}")

    local: dict[str, str] = {}
    for sifli in (False, True):
        zip_path = staged_zip(version, sifli=sifli)
        if zip_path.is_file():
            local[zip_path.name] = sha256_file(zip_path)

    return {
        "stage": "remote",
        "version": version,
        "tag": tag,
        "ok": not errors,
        "errors": errors,
        "expected_assets": expected,
        "releases": releases,
        "local_sha256": local,
    }


STAGES = ("version", "package", "install", "remote")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish_check.py",
        description=(
            "Check the release pipeline: version consistency, package "
            "contents, a real skill install and the published assets."
        ),
    )
    parser.add_argument("--stage", choices=STAGES, default=None)
    parser.add_argument("--version", default=paths.TOOL_VERSION)
    parser.add_argument("--keep-backup", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    version = args.version
    stages = (args.stage,) if args.stage else STAGES
    reports: list[dict[str, Any]] = []
    try:
        for stage in stages:
            if stage == "version":
                reports.append(stage_version(version))
            elif stage == "package":
                reports.append(stage_package(version))
            elif stage == "install":
                reports.append(
                    stage_install(version, keep_backup=args.keep_backup)
                )
            else:
                reports.append(stage_remote(version))
    except CheckError as exc:
        payload = {
            "version": version,
            "ok": False,
            "errors": [str(exc)],
            "reports": reports,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"[publish] {exc}", file=sys.stderr)
        return 1

    ok = all(report["ok"] for report in reports)
    summary = {"version": version, "ok": ok, "reports": reports}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        for report in reports:
            state = "ok" if report["ok"] else "FAILED"
            print(f"[{state}] {report['stage']}")
            for error in report["errors"]:
                print(f"  {error}")
        print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
