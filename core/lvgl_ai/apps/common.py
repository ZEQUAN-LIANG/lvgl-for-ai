"""Shared primitives for the app domain package.

Path resolution, name validation, atomic file helpers and the domain error
live here so registry, scaffold, trash and views share one definition.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .. import paths

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
APP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SCENARIO_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$")
TRASH_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")
C_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)

TRASH_SCHEMA = "lvgl-ai-app-trash-v1"
TRASH_ROOT_REL = "user/.trash/apps"


class AppError(Exception):
    """Domain error carrying a code, message and detail.

    HTTP status is intentionally not part of the domain error: the web
    adapter maps ``code`` to a status. ``status`` stays in the signature only
    because the committed contract snapshot freezes it; it is accepted and
    ignored so older callers keep constructing the same object.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


class AppCChanged(AppError):
    """app.c changed or disappeared after it was read for a write."""


def resolve_repo_root(value: str | Path | None = None) -> Path:
    root = paths.REPO_ROOT if value is None else value
    return Path(root).expanduser().resolve()


def _user_app(root: Path) -> Path:
    return root / "user" / "app"


def _user_scenarios(root: Path) -> Path:
    return root / "user" / "scenarios"


def _trash_root(root: Path) -> Path:
    return root / "user" / ".trash" / "apps"


def _app_c(root: Path) -> Path:
    return _user_app(root) / "app.c"


def _app_dir(root: Path, name: str) -> Path:
    return _user_app(root) / name


def _scenario_path(root: Path, basename: str) -> Path:
    return _user_scenarios(root) / basename


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _iso_from_ns(value: int) -> str | None:
    if value <= 0:
        return None
    return datetime.fromtimestamp(value / 1e9, tz=timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _tool_command(root: Path, script: str) -> str:
    tool = paths.TOOL_ROOT / script
    return f"python -I {_relative(tool, root)}"


def _require_plain_name(name: Any, *, create: bool = False) -> str:
    if not isinstance(name, str):
        raise AppError("invalid_name", "name must be a string")
    pattern = NAME_RE if create else APP_NAME_RE
    if not pattern.fullmatch(name) or Path(name).name != name:
        raise AppError(
            "invalid_name",
            "name must match ^[a-z][a-z0-9_]{0,31}$"
            if create else "name must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        )
    if create and name in WINDOWS_DEVICE_NAMES:
        raise AppError("invalid_name", f'name "{name}" is a Windows device name')
    return name


# ---------------------------------------------------------------------------
# filesystem helpers


def _read_source(path: Path) -> tuple[bytes, str, bool, str]:
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in text else "\n"
    return data, text, bom, eol


def _encode_source(text: str, bom: bool, eol: str) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if eol != "\n":
        normalized = normalized.replace("\n", eol)
    prefix = b"\xef\xbb\xbf" if bom else b""
    return prefix + normalized.encode("utf-8")


def _ensure_unchanged(path: Path, expected: bytes) -> None:
    """Abort when *path* no longer matches the bytes read at transaction start."""
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise AppCChanged(
            "app_conflict",
            "app.c changed on disk; retry the operation",
        ) from exc
    if hashlib.sha256(current).digest() != hashlib.sha256(expected).digest():
        raise AppCChanged(
            "app_conflict",
            "app.c changed on disk; retry the operation",
        )


def _replace_bytes(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _move_path(source: Path, destination: Path) -> None:
    if destination.exists():
        raise AppError(
            "app_conflict", f"destination already exists: {destination}"
        )
    shutil.move(str(source), str(destination))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _replace_bytes(path, data)


def _stat_info(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"size": None, "modified": None, "modified_ns": 0}
    return {
        "size": stat.st_size if path.is_file() else None,
        "modified": _iso_from_ns(stat.st_mtime_ns),
        "modified_ns": stat.st_mtime_ns,
    }


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _max_mtime_ns(paths: Iterable[Path]) -> int:
    values = []
    for path in paths:
        try:
            values.append(path.stat().st_mtime_ns)
        except OSError:
            continue
    return max(values, default=0)


def _tree_stats(path: Path) -> tuple[int, int]:
    file_count = 0
    size_bytes = 0
    try:
        for item in path.rglob("*"):
            if item.is_file() and not item.is_symlink():
                file_count += 1
                try:
                    size_bytes += item.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return file_count, size_bytes
