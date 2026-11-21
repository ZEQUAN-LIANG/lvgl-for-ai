from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CONSOLE_ROOT = PACKAGE_DIR
REPO_ROOT = CONSOLE_ROOT.parent

ENGINE_DIR = REPO_ROOT / "engine"
BUILD_ROOT = REPO_ROOT / "build"
DIST_ROOT = REPO_ROOT / "dist"
LVGL_SRC_ROOT = REPO_ROOT / "engine" / "lvgl"
SDK_ROOT = DIST_ROOT / "lvgl"
THIRD_PARTY_ROOT = REPO_ROOT / "engine" / "third_party"
ZLIB_SRC_ROOT = THIRD_PARTY_ROOT / "zlib"
LIBPNG_SRC_ROOT = THIRD_PARTY_ROOT / "libpng"
APPS_DIR = REPO_ROOT / "user" / "app"
SCENARIOS_DIR = REPO_ROOT / "user" / "scenarios"
API_NAV_DIR = REPO_ROOT / "docs" / "skill" / "api-nav"
SCRIPTS_DIR = REPO_ROOT / "scripts"
TRASH_ROOT = REPO_ROOT / "user" / ".trash"
DEFAULT_SESSIONS_ROOT = REPO_ROOT / "user" / "sessions"

DEFAULT_LVGL_VERSION = "9.6"
TOOL_VERSION = "0.2.3"


def metadata_dir() -> Path:
    meta = REPO_ROOT / "scripts" / "meta"
    return meta if meta.is_dir() else REPO_ROOT


def metadata_file(name: str) -> Path:
    return metadata_dir() / name


def shared_sdk_lib_dir() -> Path | None:
    candidate = SDK_ROOT / "common" / "lib"
    return candidate if candidate.is_dir() else None


def default_lvgl_version() -> str:
    import versions

    try:
        return versions.default()
    except versions.VersionsError:
        return DEFAULT_LVGL_VERSION


def lvgl_version_from_env() -> str:
    return (
        os.environ.get("LVGL_VERIFY_LOOP_LVGL_VERSION")
        or default_lvgl_version()
    )


def lvgl_src_for(version: str) -> Path:
    override = os.environ.get("LVGL_VERIFY_LOOP_LVGL_SRC")
    if override:
        return Path(override).expanduser().resolve()
    return LVGL_SRC_ROOT / version


def sdk_dir_for(version: str) -> Path:
    if not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        raise ValueError(f"invalid host SDK version: {version!r}")
    return SDK_ROOT / version


def apps_dir_from_env() -> Path:
    override = os.environ.get("LVGL_VERIFY_LOOP_APPS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return APPS_DIR


def zlib_src() -> Path:
    override = os.environ.get("LVGL_VERIFY_LOOP_ZLIB_SRC")
    if override:
        return Path(override).expanduser().resolve()
    return ZLIB_SRC_ROOT


def libpng_src() -> Path:
    override = os.environ.get("LVGL_VERIFY_LOOP_LIBPNG_SRC")
    if override:
        return Path(override).expanduser().resolve()
    return LIBPNG_SRC_ROOT


def sessions_root_from_env() -> Path:
    override = os.environ.get("LVGL_VERIFY_LOOP_SESSIONS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_SESSIONS_ROOT


def build_root_from_env() -> Path:
    override = os.environ.get("LVGL_VERIFY_LOOP_BUILD_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return BUILD_ROOT


def entrypoint_path(name: str) -> Path:
    return CONSOLE_ROOT / "entrypoints" / name


def entrypoint_command(name: str) -> str:
    relative = entrypoint_path(name).relative_to(REPO_ROOT).as_posix()
    return f"python -I {relative}"


def build_dir_for(
    version: str,
    user_app_dir: str | Path | None = None,
    *,
    build_root: str | Path | None = None,
) -> Path:
    token = version_token(version)
    root = (
        BUILD_ROOT
        if build_root is None
        else Path(build_root).expanduser().resolve()
    )
    if user_app_dir is None:
        return root / f"lvgl_{token}"
    app_dir = Path(user_app_dir).expanduser().resolve()
    if app_dir == APPS_DIR.resolve():
        return root / f"lvgl_{token}"
    digest = hashlib.sha256(str(app_dir).encode("utf-8")).hexdigest()[:8]
    try:
        relative = app_dir.relative_to(APPS_DIR.resolve())
        label_source = relative.parts[0] if relative.parts else app_dir.name
    except ValueError:
        label_source = app_dir.parent.parent.name or app_dir.name
    label = (
        re.sub(r"[^0-9A-Za-z]+", "_", label_source).strip("_")[:24] or "app"
    )
    return root / f"lvgl_{token}_export_{label}_{digest}"


def version_token(version: str) -> str:
    token = re.sub(r"[^0-9A-Za-z]+", "_", version).strip("_")
    if not token:
        raise ValueError(f"invalid LVGL version: {version!r}")
    return token


def engine_filename() -> str:
    return "lvgl_engine.exe" if os.name == "nt" else "lvgl_engine"
