"""Last-used flash paths and auto-fill suggestions.

The web UI should not make the user hunt for the exported project or the build
directory every time.  A small JSON file under ``host/.cache`` records the last
successful build/open, and a filesystem scan supplies a fallback on a fresh
checkout.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from serial_backend import list_ports
from timeutil import now_iso


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
            return payload if isinstance(payload, dict) else {}

    def update(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            payload = self.load()
            payload.update(fields)
            payload["updated_at"] = now_iso()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
            return payload

    def record_build(
        self,
        *,
        app: str,
        project_dir: str,
        build_dir: str,
    ) -> None:
        self.update(
            app=app,
            project_dir=project_dir,
            build_dir=build_dir,
        )

    def record_open(self, *, port: str, baud: int) -> None:
        self.update(port=port, baud=int(baud))


def _valid_build(path: str | Path | None) -> Path | None:
    if not path:
        return None
    candidate = Path(str(path))
    if (candidate / "sftool_param.json").is_file():
        return candidate.resolve()
    return None


def _scan_builds(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / "chip-adapt" / "sifli"
    builds: list[dict[str, Any]] = []
    if not root.is_dir():
        return builds
    for path in root.glob("*/project/build_*/sftool_param.json"):
        if not path.is_file():
            continue
        build_dir = path.parent
        project_dir = build_dir.parent
        app = project_dir.parent.name
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        builds.append(
            {
                "app": app,
                "project_dir": str(project_dir.resolve()),
                "build_dir": str(build_dir.resolve()),
                "mtime": mtime,
            }
        )
    builds.sort(key=lambda item: item["mtime"], reverse=True)
    return builds


def _app_from_project(project_dir: str | Path | None) -> str:
    if not project_dir:
        return ""
    parts = Path(str(project_dir)).parts
    for index in range(len(parts) - 2):
        if parts[index].lower() == "sifli" and parts[index + 2] == "project":
            return parts[index + 1]
    return ""


def _scan_apps(repo_root: Path) -> list[str]:
    apps: list[str] = []
    root = repo_root / "user" / "app"
    if not root.is_dir():
        return apps
    for path in root.iterdir():
        if not path.is_dir() or path.name.startswith("."):
            continue
        if path.name in ("__pycache__",):
            continue
        if any(path.glob("*.c")):
            apps.append(path.name)
    return sorted(apps)


def _pick_port(state_port: str, ports: list[dict[str, Any]]) -> str:
    names = [item["port"] for item in ports]
    if state_port and state_port in names:
        return state_port
    for item in ports:
        description = str(item.get("description") or "")
        if re.search(r"CH340|USB-SERIAL|CP210|FTDI|Silicon Labs", description, re.I):
            return str(item["port"])
    return names[0] if names else ""


def suggest(config: dict[str, Any], store: StateStore) -> dict[str, Any]:
    repo_root = Path(config["repo_root"])
    state = store.load()
    builds = _scan_builds(repo_root)
    apps = _scan_apps(repo_root)
    ports = list_ports()

    app = str(state.get("app") or config.get("app") or "")
    project_dir = str(state.get("project_dir") or config.get("project_dir") or "")
    build_dir = str(state.get("build_dir") or "")

    project_path = Path(project_dir) if project_dir else None
    if project_path is not None and not (
        (project_path / "SConstruct").is_file()
        or (project_path / "project" / "SConstruct").is_file()
    ):
        project_dir = ""
    if not _valid_build(build_dir) and builds:
        build_dir = builds[0]["build_dir"]
        project_dir = project_dir or builds[0]["project_dir"]
        app = app or builds[0]["app"]
    if not project_dir and build_dir:
        project_dir = str(Path(build_dir).parent)
    if not app and apps:
        app = apps[0]
    if not project_dir and app:
        candidate = repo_root / "chip-adapt" / "sifli" / app / "project"
        if candidate.is_dir():
            project_dir = str(candidate)

    # Do not let a stale app name leak onto an SDK example or another
    # project.  Only an exported chip-adapt/sifli/<app>/project keeps an app.
    project_app = _app_from_project(project_dir) or _app_from_project(build_dir)
    if project_app:
        app = project_app
    elif project_dir or build_dir:
        app = ""

    port = _pick_port(str(state.get("port") or ""), ports)
    baud = int(state.get("baud") or config.get("default_baud", 1_000_000))
    return {
        "app": app,
        "project_dir": project_dir,
        "build_dir": build_dir,
        "port": port,
        "baud": baud,
        "apps": apps,
        "builds": builds[:12],
        "ports": ports,
        "auto_reconnect": bool(config.get("auto_reconnect", True)),
        "state": state,
    }
