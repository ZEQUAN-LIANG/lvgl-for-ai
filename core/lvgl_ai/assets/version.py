"""Resolve the LVGL version that generated assets should target."""

from __future__ import annotations

import os
import re
from pathlib import Path

from lvgl_ai import paths

SUPPORTED_VERSIONS = ("8.3", "8.4", "9.1", "9.4", "9.5", "9.6")

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int]:
    """Parse ``"9.6"`` into ``(9, 6)``; reject anything else."""
    match = _VERSION_RE.fullmatch(text.strip())
    if not match:
        raise ValueError(f"invalid LVGL version: {text!r} (expected MAJOR.MINOR)")
    return int(match.group(1)), int(match.group(2))


def _supported(version: str) -> bool:
    try:
        parse_version(version)
    except ValueError:
        return False
    return version in SUPPORTED_VERSIONS


def available_versions(repo_root: Path) -> list[str]:
    """Return the supported version directories present in *repo_root*."""
    found: set[str] = set()
    for parent in (repo_root / "sdk", repo_root / "lvgl-src"):
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if child.is_dir() and _supported(child.name):
                found.add(child.name)
    return sorted(found, key=parse_version)


def resolve_lvgl_version(repo_root: Path, requested: str = "auto") -> str:
    """Resolve ``--lvgl``.

    Precedence for ``auto``: ``LVGL_AI_LVGL_VERSION`` > the highest supported
    directory under ``sdk/`` or ``lvgl-src/`` > ``paths.DEFAULT_LVGL_VERSION``.
    """
    if requested != "auto":
        if not _supported(requested):
            choices = ", ".join(SUPPORTED_VERSIONS)
            raise ValueError(
                f"unsupported --lvgl {requested!r}; choose one of {choices} or auto"
            )
        return requested

    env_version = os.environ.get("LVGL_AI_LVGL_VERSION")
    if env_version:
        if not _supported(env_version):
            choices = ", ".join(SUPPORTED_VERSIONS)
            raise ValueError(
                f"LVGL_AI_LVGL_VERSION={env_version!r} is unsupported; "
                f"choose one of {choices}"
            )
        return env_version

    present = available_versions(repo_root)
    if present:
        return max(present, key=parse_version)
    return paths.DEFAULT_LVGL_VERSION


def version_available(repo_root: Path, version: str) -> bool:
    """Whether *repo_root* has an SDK or source tree for *version*."""
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
