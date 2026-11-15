"""Name policy: deletion protection and derived create-time reservations.

Deletion protection is an explicit management-console policy for the built-in
apps and scenarios; it is not the build layer's app discovery. When a built-in
app or scenario is added, renamed or removed, update ``PROTECTED_APPS`` /
``PROTECTED_SCENARIOS`` here.

Create-time reservations are derived from the current repository state:
``apps[]`` rows, app directories, scenarios and ``app.c`` string literals, so
adding or deleting a user app never leaves a stale static list behind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from scenario import ScenarioError, load_scenario
from . import common, registry
from .common import AppError

PROTECTED_APPS = frozenset(
    {
        "coffee",
        "xiaohongshu",
        "xhs",
        "spectrum",
        "demo",
        "app",
        "settings",
    }
)
PROTECTED_LOWER = frozenset(name.lower() for name in PROTECTED_APPS)
PROTECTED_SCENARIOS = frozenset(
    {
        "coffee.json",
        "xiaohongshu.json",
        "spectrum.json",
        "settings.json",
    }
)


def is_protected_name(name: str) -> bool:
    return name.lower() in PROTECTED_LOWER


def is_protected_scenario(basename: str) -> bool:
    return basename in PROTECTED_SCENARIOS


def is_reserved_create_name(root: Path, name: str) -> bool:
    """True when creating *name* must be rejected as reserved.

    Deletion-protected identities are always reserved. Derived identities
    with an existing create target (app directory, ``<name>.json`` scenario,
    a scenario declaration or an ``apps[]`` row) keep the established create
    path (``app_exists``, ``app_conflict``, ``--force`` or plain creation);
    only identities with no other target, such as an ``app.c`` alias, fall
    through to ``name_reserved``.
    """
    if is_protected_name(name):
        return True
    names, targets = _reserved_state(root)
    if name not in names or name in targets:
        return False
    if common._app_dir(root, name).exists():
        return False
    if common._scenario_path(root, f"{name}.json").exists():
        return False
    return True


def _reserved_state(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    names: set[str] = set()
    targets: set[str] = set()
    app_c = common._app_c(root)
    text = ""
    if app_c.is_file():
        try:
            text = app_c.read_text(encoding="utf-8-sig")
        except OSError:
            text = ""
    if text:
        try:
            entries = registry.parse_app_entries(text)
        except AppError:
            entries = []
        for entry_name, _symbol in entries:
            names.add(entry_name)
            targets.add(entry_name)
        names.update(
            literal
            for literal in _c_string_literals(text)
            if common.NAME_RE.fullmatch(literal)
        )

    user_app = common._user_app(root)
    if user_app.is_dir():
        for child in user_app.iterdir():
            if child.is_dir() and common.NAME_RE.fullmatch(child.name):
                names.add(child.name)
                targets.add(child.name)

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


def _c_string_literals(text: str) -> Iterator[str]:
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            index += 1
            value: list[str] = []
            while index < length:
                current = text[index]
                if current == "\\" and index + 1 < length:
                    value.append(text[index : index + 2])
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                value.append(current)
                index += 1
            yield "".join(value)
        elif char == "'":
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "'":
                    index += 1
                    break
                index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
        else:
            index += 1
