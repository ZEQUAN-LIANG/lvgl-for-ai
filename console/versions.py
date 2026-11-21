from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import paths

INDEX_SCHEMA = "lvgl-verify-loop-versions-v2"


class VersionsError(ValueError):
    pass


def _candidate_paths(repo_root: Path | None) -> Iterator[Path]:
    root = paths.REPO_ROOT if repo_root is None else Path(repo_root)
    yield root / "scripts" / "meta" / "versions.json"
    yield root / "versions.json"
    if root.resolve() != paths.REPO_ROOT.resolve():
        yield paths.REPO_ROOT / "scripts" / "meta" / "versions.json"
        yield paths.REPO_ROOT / "versions.json"


def index_path(repo_root: Path | None = None) -> Path:
    candidates = list(_candidate_paths(repo_root))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise VersionsError(
        "versions.json is missing; expected scripts/meta/versions.json in "
        f"{candidates[0].parent.parent}"
    )


def _validate(payload: Any, path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VersionsError(f"{path}: version index must be an object")
    if payload.get("schema") != INDEX_SCHEMA:
        raise VersionsError(f"{path}: schema must be {INDEX_SCHEMA!r}")
    entries = payload.get("versions")
    if not isinstance(entries, dict) or not entries:
        raise VersionsError(f"{path}: versions must be a non-empty object")
    default = payload.get("default")
    if not isinstance(default, str) or default not in entries:
        raise VersionsError(f"{path}: default must name a supported version")
    for name, entry in entries.items():
        if not isinstance(name, str) or not name:
            raise VersionsError(f"{path}: invalid version name {name!r}")
        if not isinstance(entry, dict):
            raise VersionsError(f"{path}: {name} must be an object")
        tag = entry.get("tag")
        if not isinstance(tag, str) or not tag:
            raise VersionsError(f"{path}: {name}.tag must be a string")
        for flag in ("intro", "sdk", "bundled", "legacy"):
            if flag in entry and not isinstance(entry[flag], bool):
                raise VersionsError(f"{path}: {name}.{flag} must be a boolean")
    return payload


def load(repo_root: Path | None = None) -> dict[str, Any]:
    path = index_path(repo_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionsError(f"cannot read {path}: {exc}") from exc
    return _validate(payload, path)


def supported(repo_root: Path | None = None) -> tuple[str, ...]:
    return tuple(load(repo_root)["versions"])


def default(repo_root: Path | None = None) -> str:
    return str(load(repo_root)["default"])


def _flagged(flag: str, repo_root: Path | None) -> tuple[str, ...]:
    entries = load(repo_root)["versions"]
    return tuple(
        name for name, entry in entries.items() if entry.get(flag) is True
    )


def intro(repo_root: Path | None = None) -> tuple[str, ...]:
    return _flagged("intro", repo_root)


def legacy(repo_root: Path | None = None) -> tuple[str, ...]:
    return _flagged("legacy", repo_root)


def bundled(repo_root: Path | None = None) -> tuple[str, ...]:
    return _flagged("bundled", repo_root)


def tags(repo_root: Path | None = None) -> dict[str, str]:
    entries = load(repo_root)["versions"]
    return {name: str(entry["tag"]) for name, entry in entries.items()}


def tag(version: str, repo_root: Path | None = None) -> str:
    tags_by_version = tags(repo_root)
    try:
        return tags_by_version[version]
    except KeyError:
        choices = ", ".join(tags_by_version)
        raise VersionsError(
            f"unsupported LVGL version {version!r}; supported: {choices}"
        ) from None


def is_supported(version: str, repo_root: Path | None = None) -> bool:
    return version in supported(repo_root)
