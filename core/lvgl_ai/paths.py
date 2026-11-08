"""Canonical locations for the tool, user files and session evidence.

The development checkout keeps the tool under ``<repo>/core``; a flat checkout
with the tool code at the repository root is also supported. Resolve from
``__file__`` so imports work from any working directory.

Build output lives beside the tool root, not inside it: ``build/`` belongs to
:data:`REPO_ROOT`. Third-party license texts live in ``licenses/``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
TOOL_ROOT = PACKAGE_DIR.parent


def _repo_root_for(tool_root: Path) -> Path:
    """Resolve the workspace root for all supported layouts.

    Flat development checkout: the tool code and ``user/`` share ``<repo>``.
    Legacy development checkout: ``<repo>/.scratch/lvgl-ai-new`` -> ``<repo>``.
    Tool subdirectory: ``<workspace>/<tool>`` -> the parent directory, which
    owns ``user/``.
    """
    if (tool_root / "user").is_dir():
        return tool_root
    parent = tool_root.parent
    if parent.name == ".scratch":
        return parent.parent
    return parent


REPO_ROOT = _repo_root_for(TOOL_ROOT)

ENGINE_DIR = TOOL_ROOT / "engine"
BUILD_ROOT = REPO_ROOT / "build"
LVGL_SRC_ROOT = REPO_ROOT / "lvgl-src"
USER_DIR = REPO_ROOT / "user"
USER_APP_DIR = USER_DIR / "app"
USER_ASSET_DIR = USER_DIR / "asset"
USER_SCENARIOS_DIR = USER_DIR / "scenarios"
DEFAULT_SESSIONS_ROOT = REPO_ROOT / "sessions"

DEFAULT_LVGL_VERSION = "9.6"
TOOL_VERSION = "0.1.0"


def lvgl_version_from_env() -> str:
    return os.environ.get("LVGL_AI_LVGL_VERSION") or DEFAULT_LVGL_VERSION


def lvgl_src_for(version: str) -> Path:
    override = os.environ.get("LVGL_AI_LVGL_SRC")
    if override:
        return Path(override).expanduser().resolve()
    return LVGL_SRC_ROOT / version


def sessions_root_from_env() -> Path:
    override = os.environ.get("LVGL_AI_SESSIONS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_SESSIONS_ROOT


def build_dir_for(version: str) -> Path:
    """Return the build directory for ``version``.

    Every non-alphanumeric run becomes ``_`` so local patched trees get a
    distinct directory: ``9.6`` -> ``build/lvgl_9_6`` and ``9.6-patched`` ->
    ``build/lvgl_9_6_patched``. Labels that normalize to the same token share
    a directory, so keep version labels distinct.
    """
    return BUILD_ROOT / f"lvgl_{_version_token(version)}"


def _version_token(version: str) -> str:
    token = re.sub(r"[^0-9A-Za-z]+", "_", version).strip("_")
    if not token:
        raise ValueError(f"invalid LVGL version: {version!r}")
    return token


def engine_filename() -> str:
    return "lvgl_engine.exe" if os.name == "nt" else "lvgl_engine"
