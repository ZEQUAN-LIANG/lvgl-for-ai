"""Read the LVGL version index that ships in ``meta/versions.json``.

The index is the only version manifest for the tool: supported membership,
the default version, and the intro / legacy / bundled flags all come from it.
Consumers that need a different shape (CLI tuples, tag maps, the release
build order) render it themselves; they must not carry a second copy.

``repo_root`` is optional for tests and for tools that operate on another
workspace.  When that workspace has no ``meta/versions.json`` (or the older
root ``versions.json``), the active package index is used as the fallback, so
a temporary directory that only contains ``sdk/<version>`` still resolves
against the installed tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from lvgl_ai import paths

INDEX_SCHEMA = "lvgl-verify-loop-versions-v1"


class VersionsError(ValueError):
    """The version index is missing or malformed."""


def _candidate_paths(repo_root: Path | None) -> Iterator[Path]:
    root = paths.REPO_ROOT if repo_root is None else Path(repo_root)
    yield root / "meta" / "versions.json"
    yield root / "versions.json"
    if root.resolve() != paths.REPO_ROOT.resolve():
        yield paths.REPO_ROOT / "meta" / "versions.json"
        yield paths.REPO_ROOT / "versions.json"


def index_path(repo_root: Path | None = None) -> Path:
    """Return the first existing version index for ``repo_root``."""
    candidates = list(_candidate_paths(repo_root))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise VersionsError(
        "versions.json is missing; expected meta/versions.json in "
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
    """Load and validate the version index."""
    path = index_path(repo_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionsError(f"cannot read {path}: {exc}") from exc
    return _validate(payload, path)


def supported(repo_root: Path | None = None) -> tuple[str, ...]:
    """Supported versions in index order."""
    return tuple(load(repo_root)["versions"])


def default(repo_root: Path | None = None) -> str:
    """The default host preview version."""
    return str(load(repo_root)["default"])


def _flagged(flag: str, repo_root: Path | None) -> tuple[str, ...]:
    entries = load(repo_root)["versions"]
    return tuple(
        name for name, entry in entries.items() if entry.get(flag) is True
    )


def intro(repo_root: Path | None = None) -> tuple[str, ...]:
    """Versions whose bundled app follows the intro harness."""
    return _flagged("intro", repo_root)


def legacy(repo_root: Path | None = None) -> tuple[str, ...]:
    """Versions whose bundled app follows the legacy harness."""
    return _flagged("legacy", repo_root)


def bundled(repo_root: Path | None = None) -> tuple[str, ...]:
    """Versions whose SDK and prebuilt engine ship in the full bundle."""
    return _flagged("bundled", repo_root)


def tags(repo_root: Path | None = None) -> dict[str, str]:
    """Map every supported version to its official LVGL release tag."""
    entries = load(repo_root)["versions"]
    return {name: str(entry["tag"]) for name, entry in entries.items()}


def tag(version: str, repo_root: Path | None = None) -> str:
    """Return the release tag for one supported version."""
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
