"""Derived name policy for the app management console.

This module contains no hand-maintained app registry.  Apps are discovered
from ``user/app/<name>/app.json`` (see :mod:`appmgr.discovery`); the only
protected app is the discovered default app, because ``app_create`` uses it
when ``LVGL_VERIFY_LOOP_DEMO`` is unset.  Create-time reservations are derived
from the current repository state: app directories, metadata aliases,
scenario-only names and the source files directly under ``user/app``.

Adding or deleting an app therefore never requires editing this module.
"""

from __future__ import annotations

from pathlib import Path

from scenario import ScenarioError, load_scenario
from . import common, discovery


def default_app_name(root: Path) -> str | None:
    """Return the discovered default app, if metadata is valid."""

    try:
        return discovery.default_app_name(common._user_app(root))
    except discovery.DiscoveryError:
        return None


def is_protected_name(root: Path, name: str) -> bool:
    """True only for the default app; protection is not a static list."""

    return name == default_app_name(root)


def is_reserved_create_name(root: Path, name: str) -> bool:
    """True when creating *name* must be rejected as reserved.

    The default app is always reserved.  Scenario-only names (a scenario with
    no ``app`` field) and aliases declared by app metadata are reserved too.
    Names with an existing create target keep the established create path
    (``app_exists``, ``app_conflict``, ``--force`` or plain creation); only
    identities with no other target fall through to ``name_reserved``.
    """

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
    """Scenario stems that do not declare an app are not app create targets."""

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
        names.update(entry.aliases)

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
