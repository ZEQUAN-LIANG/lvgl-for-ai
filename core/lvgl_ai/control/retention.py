"""Best-effort retention for session directories.

Every session is one directory under the sessions root. The tool keeps the
newest :data:`DEFAULT_SESSION_LIMIT` sessions and never keeps a
``build_error`` session. Cleanup runs right after a new session directory is
reserved, so evidence from the current run is never touched.

Directories whose name does not match the session id format, or whose
``manifest.json`` is missing or unreadable, are left alone: they may belong to
another live Runtime, an interrupted run, or the user.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import session_schema

DEFAULT_SESSION_LIMIT = 10
SESSION_DIR_RE = session_schema.SESSION_ID_RE
DISCARDED_STATUSES = frozenset({"build_error"})


def prune_sessions(
    root: str | Path,
    *,
    limit: int | None = DEFAULT_SESSION_LIMIT,
    keep: str | Path | None = None,
) -> list[Path]:
    if limit is None or limit < 0:
        return []
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    keep_path = None if keep is None else Path(keep).resolve()

    sessions: list[tuple[Path, str]] = []
    for child in root_path.iterdir():
        if not child.is_dir() or not session_schema.is_session_id(child.name):
            continue
        status = _manifest_status(child)
        if status is None:
            continue
        sessions.append((child, status))
    sessions.sort(key=lambda item: item[0].name, reverse=True)

    removed: list[Path] = []
    survivors: list[Path] = []
    if (
        keep_path is not None
        and keep_path.parent == root_path.resolve()
        and keep_path.is_dir()
    ):
        survivors.append(keep_path)
    for path, status in sessions:
        if _same_path(path, keep_path):
            continue
        if status in DISCARDED_STATUSES:
            if _remove(path):
                removed.append(path)
            continue
        survivors.append(path)

    for path in survivors[limit:]:
        if _same_path(path, keep_path):
            continue
        if _remove(path):
            removed.append(path)
    return removed


def _manifest_status(path: Path) -> str | None:
    try:
        data = json.loads(
            (path / session_schema.MANIFEST_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    status = data.get("status")
    return status if isinstance(status, str) else None


def _same_path(path: Path, other: Path | None) -> bool:
    return other is not None and path.resolve() == other


def _remove(path: Path) -> bool:
    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return True
