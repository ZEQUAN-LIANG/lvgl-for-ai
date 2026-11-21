from __future__ import annotations

from pathlib import Path

from scenario import ScenarioError, load_scenario
from . import common, discovery


def default_app_name(root: Path) -> str | None:

    try:
        return discovery.default_app_name(common._user_app(root))
    except discovery.DiscoveryError:
        return None


def is_protected_name(root: Path, name: str) -> bool:

    return name == default_app_name(root)


def is_reserved_create_name(root: Path, name: str) -> bool:

    if is_protected_name(root, name):
        return True
    if name in _scenario_only_names(root):
        return True
    names, targets = _reserved_state(root)
    if name not in names or name in targets:
        return False
    if common._app_dir(root, name).exists():
        return False
    if common._scenario_path(root, f"{name}.json").exists():
        return False
    return True


def _scenario_only_names(root: Path) -> frozenset[str]:

    scenarios_dir = common._user_scenarios(root)
    if not scenarios_dir.is_dir():
        return frozenset()
    result: set[str] = set()
    for path in sorted(scenarios_dir.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        stem = path.stem
        if not common.NAME_RE.fullmatch(stem):
            continue
        try:
            document = load_scenario(path)
        except (OSError, ValueError, ScenarioError):
            continue
        app = document.get("app")
        if not isinstance(app, str) or not app:
            result.add(stem)
    return frozenset(result)


def _reserved_state(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    names: set[str] = set()
    targets: set[str] = set()

    user_app = common._user_app(root)
    if user_app.is_dir():
        for child in user_app.iterdir():
            if child.is_dir() and common.NAME_RE.fullmatch(child.name):
                names.add(child.name)
                targets.add(child.name)
            elif (
                child.is_file()
                and child.suffix in (".c", ".h")
                and common.NAME_RE.fullmatch(child.stem)
            ):
                names.add(child.stem)

    entries, _issues = discovery.scan_apps(user_app)
    for entry in entries:
        names.add(entry.name)
        targets.add(entry.name)

    scenarios_dir = common._user_scenarios(root)
    if scenarios_dir.is_dir():
        for path in sorted(scenarios_dir.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                continue
            stem = path.stem
            if common.NAME_RE.fullmatch(stem):
                names.add(stem)
                targets.add(stem)
            try:
                document = load_scenario(path)
            except (OSError, ValueError, ScenarioError):
                continue
            for key in ("app", "name"):
                value = document.get(key)
                if isinstance(value, str) and common.NAME_RE.fullmatch(value):
                    names.add(value)
                    targets.add(value)
    return frozenset(names), frozenset(targets)
