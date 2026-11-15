from __future__ import annotations

import os
import re
from pathlib import Path

from lvgl_ai import versions

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int]:
    match = _VERSION_RE.fullmatch(text.strip())
    if not match:
        raise ValueError(f"invalid LVGL version: {text!r} (expected MAJOR.MINOR)")
    return int(match.group(1)), int(match.group(2))


def supported_versions(repo_root: Path | None = None) -> tuple[str, ...]:
    return tuple(sorted(versions.supported(repo_root), key=parse_version))


SUPPORTED_VERSIONS = supported_versions()


def _supported(version: str, repo_root: Path | None = None) -> bool:
    try:
        parse_version(version)
    except ValueError:
        return False
    return versions.is_supported(version, repo_root)


def available_versions(repo_root: Path) -> list[str]:
    found: set[str] = set()
    for parent in (repo_root / "sdk", repo_root / "lvgl-src"):
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if child.is_dir() and _supported(child.name, repo_root):
                found.add(child.name)
    return sorted(found, key=parse_version)


def resolve_lvgl_version(repo_root: Path, requested: str = "auto") -> str:
    """Resolve ``--lvgl``.

    Precedence for ``auto``: ``LVGL_AI_LVGL_VERSION`` > the highest supported
    directory under ``sdk/`` or ``lvgl-src/`` > the index default.
    """
    if requested != "auto":
        if not _supported(requested, repo_root):
            choices = ", ".join(supported_versions(repo_root))
            raise ValueError(
                f"unsupported --lvgl {requested!r}; choose one of {choices} or auto"
            )
        return requested

    env_version = os.environ.get("LVGL_AI_LVGL_VERSION")
    if env_version:
        if not _supported(env_version, repo_root):
            choices = ", ".join(supported_versions(repo_root))
            raise ValueError(
                f"LVGL_AI_LVGL_VERSION={env_version!r} is unsupported; "
                f"choose one of {choices}"
            )
        return env_version

    present = available_versions(repo_root)
    if present:
        return max(present, key=parse_version)
    return versions.default(repo_root)


def version_available(repo_root: Path, version: str) -> bool:
    return (repo_root / "sdk" / version).is_dir() or (
        repo_root / "lvgl-src" / version
    ).is_dir()


def major_minor(version: str) -> tuple[int, int]:
    return parse_version(version)


def target_label(version: str) -> str:
    major, _minor = parse_version(version)
    if major >= 9:
        return f"LVGL 9.x (generated for {version}; usable on 9.1-9.6)"
    return f"LVGL 8.x (generated for {version}; usable on 8.3-8.4)"
