"""Canonical locations for the tool, user files and session evidence.

The development checkout keeps the tool under ``<repo>/core``; a flat checkout
with the tool code at the repository root is also supported. Resolve from
``__file__`` so imports work from any working directory.

Build output lives beside the tool root, not inside it: ``build/`` belongs to
:data:`REPO_ROOT`. Third-party license texts live in ``licenses/``.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
TOOL_ROOT = PACKAGE_DIR.parent


def _repo_root_for(tool_root: Path) -> Path:
    """Resolve the workspace root for all supported layouts.

    Flat development checkout: the tool code and ``user/`` share ``<repo>``.
    Tool subdirectory: ``<workspace>/<tool>`` -> the parent directory, which
    owns ``user/``.
    """
    if (tool_root / "user").is_dir():
        return tool_root
    return tool_root.parent


REPO_ROOT = _repo_root_for(TOOL_ROOT)

ENGINE_DIR = TOOL_ROOT / "engine"
BUILD_ROOT = REPO_ROOT / "build"
LVGL_SRC_ROOT = REPO_ROOT / "lvgl-src"
SDK_ROOT = REPO_ROOT / "sdk"
THIRD_PARTY_ROOT = REPO_ROOT / "third_party"
ZLIB_SRC_ROOT = THIRD_PARTY_ROOT / "zlib"
LIBPNG_SRC_ROOT = THIRD_PARTY_ROOT / "libpng"
USER_DIR = REPO_ROOT / "user"
USER_APP_DIR = USER_DIR / "app"
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


def sdk_dir_for(version: str) -> Path:
    """Directory of the exported host SDK for ``version``.

    ``sdk/<version>`` is the prebuilt counterpart of ``lvgl-src/<version>``.
    A release package ships the same layout, so the prebuilt build path works
    without the LVGL source tree.
    """
    if not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        raise ValueError(f"invalid host SDK version: {version!r}")
    return SDK_ROOT / version


def user_app_dir_from_env() -> Path:
    override = os.environ.get("LVGL_AI_USER_APP_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return USER_APP_DIR


def zlib_src() -> Path:
    override = os.environ.get("LVGL_AI_ZLIB_SRC")
    if override:
        return Path(override).expanduser().resolve()
    return ZLIB_SRC_ROOT


def libpng_src() -> Path:
    override = os.environ.get("LVGL_AI_LIBPNG_SRC")
    if override:
        return Path(override).expanduser().resolve()
    return LIBPNG_SRC_ROOT


def sessions_root_from_env() -> Path:
    override = os.environ.get("LVGL_AI_SESSIONS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_SESSIONS_ROOT


def build_dir_for(
    version: str, user_app_dir: str | Path | None = None
) -> Path:
    """Return the build directory for ``version`` and one user app directory.

    Every non-alphanumeric run becomes ``_`` so local patched trees get a
    distinct directory: ``9.6`` -> ``build/lvgl_9_6`` and ``9.6-patched`` ->
    ``build/lvgl_9_6_patched``. Labels that normalize to the same token share
    a directory, so keep version labels distinct.

    The default ``user/app`` keeps the version-only directory for ``--no-build``
    compatibility. Any other source tree gets its own directory so an exported
    project and the workspace app never share a CMake cache or engine binary.
    """
    token = version_token(version)
    if user_app_dir is None:
        return BUILD_ROOT / f"lvgl_{token}"
    app_dir = Path(user_app_dir).expanduser().resolve()
    if app_dir == USER_APP_DIR.resolve():
        return BUILD_ROOT / f"lvgl_{token}"
    digest = hashlib.sha256(str(app_dir).encode("utf-8")).hexdigest()[:8]
    label_source = app_dir.parent.parent.name or app_dir.name
    label = re.sub(r"[^0-9A-Za-z]+", "_", label_source).strip("_")[:24] or "app"
    return BUILD_ROOT / f"lvgl_{token}_export_{label}_{digest}"


def version_token(version: str) -> str:
    """Filesystem-safe token for a version label (``9.6`` -> ``9_6``)."""
    token = re.sub(r"[^0-9A-Za-z]+", "_", version).strip("_")
    if not token:
        raise ValueError(f"invalid LVGL version: {version!r}")
    return token


def engine_filename() -> str:
    return "lvgl_engine.exe" if os.name == "nt" else "lvgl_engine"
