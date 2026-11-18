"""App trash lifecycle: soft delete, restore and permanent delete.

A delete moves the app directory and its scenarios under
``user/.trash/apps/<trash-id>/`` and writes ``meta.json``; restore moves them
back; purge removes the entry for good.  No shared registry is edited because
the next build rediscovers apps from ``user/app/<name>/app.json``.
"""

from __future__ import annotations

import json
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import common, discovery, policy, views
from .common import AppError


class InvalidTrashId(AppError):
    pass


def delete_app(repo_root: str | Path, name: str) -> dict[str, Any]:
    root = common.resolve_repo_root(repo_root)
    common._require_plain_name(name)
    if policy.is_protected_name(root, name):
        raise AppError(
            "protected_app",
            f'app "{name}" is the default app and cannot be deleted',
        )
    entries, issues = discovery.scan_apps(common._user_app(root))
    match = next((entry for entry in entries if entry.name == name), None)
    if match is None:
        if issues:
            issue = issues[0]
            raise AppError(
                "app_metadata_invalid",
                f"{common._relative(issue.path, root)}: {issue.message}",
            )
        raise AppError("unknown_app", f'app "{name}" is not discovered')

    scenarios = views.scenarios_for_app(root, name)
    app_dir = common._app_dir(root, name)
    if app_dir.is_symlink():
        raise AppError("unsafe_path", f"{app_dir} must not be a symlink")
    if app_dir.exists() and not app_dir.is_dir():
        raise AppError("app_conflict", f"{app_dir} is not a directory")
    app_present = app_dir.is_dir()
    if not app_present and not scenarios:
        raise AppError("unknown_app", f'app "{name}" has no files to delete')

    trash_root = common._trash_root(root)
    trash_root.mkdir(parents=True, exist_ok=True)
    trash_id = _new_trash_id(trash_root)
    trash_dir = trash_root / trash_id
    moved_app = False
    moved_scenarios: list[tuple[Path, Path]] = []
    try:
        trash_dir.mkdir()
        if app_present:
            common._move_path(app_dir, trash_dir / "app")
            moved_app = True
        if scenarios:
            (trash_dir / "scenarios").mkdir()
            for source in scenarios:
                target = trash_dir / "scenarios" / source.name
                common._move_path(source, target)
                moved_scenarios.append((source, target))
        meta = {
            "schema": common.TRASH_SCHEMA,
            "trash_id": trash_id,
            "name": name,
            "symbol": match.entry,
            "deleted_at": common._now_iso(),
            "scenarios": [path.name for path in scenarios],
            "app_present": moved_app,
        }
        common._write_json(trash_dir / "meta.json", meta)
    except BaseException as exc:
        warnings = _rollback_transaction(
            app_move_back=(trash_dir / "app", app_dir) if moved_app else None,
            moved_scenarios=moved_scenarios,
            app_first=False,
        )
        shutil.rmtree(trash_dir, ignore_errors=True)
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "app_io_error",
            f'删除应用 "{name}" 未完成：{exc}',
            detail={"rollback_warnings": warnings},
        ) from exc

    return {
        "ok": True,
        "action": "delete",
        "at": common._now_iso(),
        "name": name,
        "trash_id": trash_id,
        "trash_dir": common._relative(trash_dir, root),
        "app_dir": common._relative(app_dir, root),
        "app_moved": moved_app,
        "scenarios": [common._relative(path, root) for path in scenarios],
        "scenario_files": [path.name for path in scenarios],
        "app_c": common._relative(common._app_c(root), root),
        "registration_removed": False,
        "warnings": [],
        "build_required": True,
    }


def restore_app(repo_root: str | Path, trash_id: str) -> dict[str, Any]:
    root = common.resolve_repo_root(repo_root)
    trash_dir = _trash_dir(root, trash_id)
    meta = _read_trash_meta(trash_dir)
    name = common._require_plain_name(meta.get("name"))
    scenarios = _meta_scenarios(meta)
    app_dir = common._app_dir(root, name)
    targets = [common._scenario_path(root, basename) for basename in scenarios]
    conflicts = [path for path in [app_dir, *targets] if path.exists()]
    if conflicts:
        raise AppError(
            "restore_conflict",
            "restore target already exists",
            detail={
                "paths": [common._relative(path, root) for path in conflicts]
            },
        )
    app_src = trash_dir / "app"
    if app_src.is_symlink():
        raise AppError("unsafe_path", "trash app must not be a symlink")
    app_present = app_src.is_dir()
    if not app_present and not scenarios:
        raise AppError(
            "unknown_trash", f"trash entry {trash_id} has no application data"
        )

    moved_scenarios: list[tuple[Path, Path]] = []
    moved_app = False
    try:
        common._user_scenarios(root).mkdir(parents=True, exist_ok=True)
        for basename, target in zip(scenarios, targets):
            source = trash_dir / "scenarios" / basename
            if source.is_symlink():
                raise AppError(
                    "unsafe_path",
                    f"scenario {basename} must not be a symlink",
                )
            if not source.is_file():
                raise AppError("unknown_trash", f"missing scenario {basename}")
            common._move_path(source, target)
            moved_scenarios.append((source, target))
        if app_present:
            common._move_path(app_src, app_dir)
            moved_app = True
    except BaseException as exc:
        warnings = _rollback_transaction(
            app_move_back=(app_dir, app_src) if moved_app else None,
            moved_scenarios=moved_scenarios,
            app_first=True,
        )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "app_io_error",
            f'恢复应用 "{name}" 未完成：{exc}',
            detail={"rollback_warnings": warnings},
        ) from exc

    shutil.rmtree(trash_dir, ignore_errors=True)
    return {
        "ok": True,
        "action": "restore",
        "at": common._now_iso(),
        "trash_id": trash_id,
        "name": name,
        "app_dir": common._relative(app_dir, root),
        "app_restored": moved_app,
        "scenarios": [common._relative(path, root) for path in targets],
        "scenario_files": scenarios,
        "app_c": common._relative(common._app_c(root), root),
        "registered": moved_app,
        "build_required": True,
    }


def permanently_delete(
    repo_root: str | Path,
    trash_id: str,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    if confirm is not True:
        raise AppError(
            "confirmation_required",
            "permanent deletion requires confirm=true",
        )
    root = common.resolve_repo_root(repo_root)
    trash_dir = _trash_dir(root, trash_id)
    name = None
    try:
        meta = _read_trash_meta(trash_dir)
        value = meta.get("name")
        name = value if isinstance(value, str) else None
    except AppError:
        pass
    file_count, size_bytes = common._tree_stats(trash_dir)
    try:
        shutil.rmtree(trash_dir)
    except OSError as exc:
        raise AppError("app_io_error", f"永久删除未完成：{exc}") from exc
    return {
        "ok": True,
        "action": "purge",
        "at": common._now_iso(),
        "trash_id": trash_id,
        "name": name,
        "path": common._relative(trash_dir, root),
        "file_count": file_count,
        "size_bytes": size_bytes,
    }


def list_trash(repo_root: str | Path) -> list[dict[str, Any]]:
    root = common.resolve_repo_root(repo_root)
    trash_root = common._trash_root(root)
    if not trash_root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(trash_root.iterdir(), reverse=True):
        if (
            not path.is_dir()
            or path.is_symlink()
            or not common.TRASH_ID_RE.fullmatch(path.name)
        ):
            continue
        entry: dict[str, Any] = {
            "trash_id": path.name,
            "name": None,
            "deleted_at": None,
            "app_path": common._relative(path / "app", root),
            "app_present": (path / "app").is_dir(),
            "scenario_files": [],
            "scenario_paths": [],
            "valid": False,
            "error": None,
        }
        try:
            meta = _read_trash_meta(path)
            name = common._require_plain_name(meta.get("name"))
            scenarios = _meta_scenarios(meta)
        except AppError as exc:
            entry["error"] = exc.message
        else:
            entry.update(
                {
                    "name": name,
                    "deleted_at": meta.get("deleted_at"),
                    "scenario_files": scenarios,
                    "scenario_paths": [
                        common._relative(path / "scenarios" / basename, root)
                        for basename in scenarios
                    ],
                    "valid": True,
                }
            )
        result.append(entry)
    return result


def _rollback_transaction(
    *,
    app_move_back: tuple[Path, Path] | None,
    moved_scenarios: list[tuple[Path, Path]],
    app_first: bool,
) -> list[str]:
    warnings: list[str] = []

    def undo_app() -> None:
        if app_move_back is None:
            return
        source, target = app_move_back
        try:
            common._move_path(source, target)
        except OSError as exc:
            warnings.append(str(exc))

    def undo_scenarios() -> None:
        for source, target in reversed(moved_scenarios):
            try:
                common._move_path(target, source)
            except OSError as exc:
                warnings.append(str(exc))

    if app_first:
        undo_app()
        undo_scenarios()
    else:
        undo_scenarios()
        undo_app()
    return warnings


def _new_trash_id(trash_root: Path) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for _ in range(20):
        candidate = f"{stamp}-{secrets.token_hex(4)}"
        if not (trash_root / candidate).exists():
            return candidate
    raise AppError("app_conflict", "cannot allocate a trash id")


def _trash_dir(root: Path, trash_id: Any) -> Path:
    if not isinstance(trash_id, str) or not common.TRASH_ID_RE.fullmatch(
        trash_id
    ):
        raise InvalidTrashId("invalid_trash", "invalid trash id")
    trash_root = common._trash_root(root)
    raw = trash_root / trash_id
    if raw.is_symlink():
        raise AppError("unsafe_path", "trash entry must not be a symlink")
    resolved = raw.resolve()
    try:
        resolved.relative_to(trash_root.resolve())
    except ValueError as exc:
        raise AppError(
            "unsafe_path", "trash entry escapes the trash root"
        ) from exc
    if resolved.parent != trash_root.resolve() or not resolved.is_dir():
        raise AppError("unknown_trash", f"unknown trash entry: {trash_id}")
    return resolved


def _read_trash_meta(trash_dir: Path) -> dict[str, Any]:
    path = trash_dir / "meta.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AppError(
            "invalid_trash", f"cannot read trash metadata: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise AppError("invalid_trash", "trash metadata must be an object")
    if payload.get("schema") != common.TRASH_SCHEMA:
        raise AppError("invalid_trash", "unsupported trash metadata")
    return payload


def _meta_scenarios(meta: dict[str, Any]) -> list[str]:
    values = meta.get("scenarios")
    if values is None:
        return []
    if not isinstance(values, list):
        raise AppError("invalid_trash", "scenarios must be a list")
    result: list[str] = []
    for value in values:
        if (
            not isinstance(value, str)
            or not common.SCENARIO_FILE_RE.fullmatch(value)
            or Path(value).name != value
        ):
            raise AppError("invalid_trash", "invalid scenario basename")
        if value in result:
            raise AppError("invalid_trash", "duplicate scenario basename")
        result.append(value)
    return result
