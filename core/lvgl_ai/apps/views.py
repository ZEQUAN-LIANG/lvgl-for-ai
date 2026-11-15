from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..scenario import scenario_index
from . import common, policy, registry
from .common import AppError


def list_apps(repo_root: str | Path) -> dict[str, Any]:
    root = common.resolve_repo_root(repo_root)
    app_c = common._app_c(root)
    index = scenario_index(root)
    if not app_c.is_file():
        return {
            "app_c_present": False,
            "apps": [],
            "orphans": _orphans(root, set(), index),
            "warnings": [f"未找到 {common._relative(app_c, root)}"],
        }

    text = app_c.read_text(encoding="utf-8-sig")
    try:
        entries = registry.parse_app_entries(text)
    except AppError as exc:
        return {
            "app_c_present": True,
            "apps": [],
            "orphans": _orphans(root, set(), index),
            "warnings": [exc.message],
        }
    apps: list[dict[str, Any]] = []
    warnings: list[str] = []
    for order, (name, symbol) in enumerate(entries):
        app_dir = common._app_dir(root, name)
        app_scenarios = [
            item for item in index
            if item.get("valid") and item.get("app") == name
        ]
        protected = policy.is_protected_name(name) or any(
            policy.is_protected_scenario(item["basename"])
            for item in app_scenarios
        )
        canonical = bool(common.APP_NAME_RE.fullmatch(name)) and symbol == f"{name}_create"
        files = _files_under(app_dir)
        modified_ns = common._max_mtime_ns([app_dir, *(
            root / item["path"] for item in app_scenarios
        )])
        app_warnings: list[str] = []
        if not app_dir.is_dir():
            app_warnings.append("目录不存在")
        if not app_scenarios:
            app_warnings.append("没有关联场景")
        if not canonical:
            app_warnings.append("注册符号不是 <name>_create，管理台不提供删除")
        if app_warnings:
            warnings.append(name + ": " + "；".join(app_warnings))
        apps.append({
            "name": name,
            "symbol": symbol,
            "registered": True,
            "order": order,
            "default": order == 0,
            "protected": protected,
            "deletable": bool(canonical and not protected),
            "app_dir": common._relative(app_dir, root),
            "app_dir_exists": app_dir.is_dir() and not app_dir.is_symlink(),
            "scenarios": [item["path"] for item in app_scenarios],
            "scenario_files": [item["basename"] for item in app_scenarios],
            "file_count": len(files),
            "size_bytes": sum(common._file_size(path) for path in files),
            "modified": common._iso_from_ns(modified_ns),
            "warnings": app_warnings,
        })

    return {
        "app_c_present": True,
        "apps": apps,
        "orphans": _orphans(
            root, {name for name, _ in entries}, index
        ),
        "warnings": warnings,
    }


def _orphans(
    root: Path,
    registered: set[str],
    index: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    user_app = common._user_app(root)
    if user_app.is_dir():
        for path in sorted(user_app.iterdir()):
            if (
                path.is_dir()
                and not path.is_symlink()
                and path.name not in registered
                and not policy.is_protected_name(path.name)
            ):
                result.append({
                    "kind": "directory",
                    "name": path.name,
                    "path": common._relative(path, root),
                    "modified": common._iso_from_ns(
                        common._max_mtime_ns([path])
                    ),
                })
    for item in index:
        app = item.get("app")
        if (
            item.get("valid")
            and isinstance(app, str)
            and app not in registered
            and not policy.is_protected_name(app)
            and not policy.is_protected_scenario(item["basename"])
        ):
            result.append({
                "kind": "scenario",
                "name": app,
                "path": item["path"],
                "modified": common._iso_from_ns(
                    common._max_mtime_ns([root / item["path"]])
                ),
            })
    return result


def app_tree(
    repo_root: str | Path,
    name: str,
    *,
    max_entries: int = 400,
    max_depth: int = 6,
) -> dict[str, Any]:
    root = common.resolve_repo_root(repo_root)
    common._require_plain_name(name)
    max_entries = max(1, min(int(max_entries), 2000))
    max_depth = max(1, min(int(max_depth), 20))
    app_dir = common._app_dir(root, name)
    app_c = common._app_c(root)
    text = app_c.read_text(encoding="utf-8-sig") if app_c.is_file() else ""
    try:
        entries = registry.parse_app_entries(text) if text else []
    except AppError:
        entries = []
    match = next(((index, symbol) for index, (entry_name, symbol) in enumerate(entries)
                  if entry_name == name), None)
    registered = match is not None
    symbol = match[1] if match else None
    order = match[0] if match else None
    include = registry.find_include(text, name)

    state = {"count": 0, "truncated": False}

    def node(path: Path, depth: int) -> dict[str, Any]:
        rel = common._relative(path, root)
        info = common._stat_info(path)
        if path.is_symlink():
            return {
                "name": path.name,
                "path": rel,
                "type": "link",
                "size": None,
                "modified": info["modified"],
                "children": [],
            }
        if path.is_dir():
            children: list[dict[str, Any]] = []
            if depth < max_depth:
                for child in sorted(
                    path.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                ):
                    if state["count"] >= max_entries:
                        state["truncated"] = True
                        break
                    state["count"] += 1
                    children.append(node(child, depth + 1))
            elif any(path.iterdir()):
                state["truncated"] = True
            return {
                "name": path.name,
                "path": rel,
                "type": "dir",
                "size": None,
                "modified": info["modified"],
                "children": children,
            }
        return {
            "name": path.name,
            "path": rel,
            "type": "file",
            "size": info["size"],
            "modified": info["modified"],
            "children": [],
        }

    tree = node(app_dir, 0) if app_dir.is_dir() and not app_dir.is_symlink() else None
    app_c_node = node(app_c, 0) if app_c.is_file() else None
    scenarios = []
    for item in scenarios_for_app(root, name):
        scenarios.append(node(item, 0))
    return {
        "name": name,
        "registered": registered,
        "symbol": symbol,
        "order": order,
        "default": order == 0,
        "protected": policy.is_protected_name(name),
        "include": include,
        "app_c": app_c_node,
        "app_dir": common._relative(app_dir, root),
        "app_dir_exists": app_dir.is_dir() and not app_dir.is_symlink(),
        "tree": tree,
        "scenarios": scenarios,
        "truncated": state["truncated"],
        "max_entries": max_entries,
        "max_depth": max_depth,
    }


def recent_apps(repo_root: str | Path, *, limit: int = 8) -> list[dict[str, Any]]:
    root = common.resolve_repo_root(repo_root)
    limit = max(1, min(int(limit), 100))
    items: list[dict[str, Any]] = []

    def add(path: Path, kind: str) -> None:
        if not path.is_file() or path.is_symlink():
            return
        info = common._stat_info(path)
        items.append({
            "path": common._relative(path, root),
            "kind": kind,
            "size": info["size"],
            "modified": info["modified"],
            "modified_ns": info["modified_ns"],
        })

    app_c = common._app_c(root)
    if app_c.is_file():
        add(app_c, "registration")
    user_app = common._user_app(root)
    if user_app.is_dir():
        for path in user_app.rglob("*"):
            if path == app_c or path.is_symlink() or not path.is_file():
                continue
            if any(part in ("__pycache__",) for part in path.parts):
                continue
            add(path, "app")
    scenarios_dir = common._user_scenarios(root)
    if scenarios_dir.is_dir():
        for path in scenarios_dir.glob("*.json"):
            add(path, "scenario")
    trash_root = common._trash_root(root)
    if trash_root.is_dir():
        for path in trash_root.glob("*/meta.json"):
            add(path, "trash")
    items.sort(key=lambda item: (-item["modified_ns"], item["path"]))
    for item in items:
        item.pop("modified_ns", None)
    return items[:limit]


def scenarios_for_app(root: Path, name: str) -> list[Path]:
    return [
        root / item["path"]
        for item in scenario_index(root)
        if item.get("valid") and item.get("app") == name
    ]


def _files_under(path: Path) -> list[Path]:
    if not path.is_dir() or path.is_symlink():
        return []
    result: list[Path] = []
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            result.append(item)
    return result
