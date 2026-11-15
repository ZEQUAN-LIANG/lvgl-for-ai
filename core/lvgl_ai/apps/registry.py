"""``user/app/app.c`` parsing and registration text.

Registration is pure text manipulation: the web layer and the scaffolder both
call :func:`register_app` / :func:`unregister_app` so there is one definition
of the include block and the ``apps[]`` table.
"""

from __future__ import annotations

import re
from typing import Any

from .common import AppError

VERSION_GATE_RE = re.compile(
    r"^\s*#if\s+LVGL_VERSION_MAJOR\s*==\s*9\s*&&\s*"
    r"LVGL_VERSION_MINOR\s*>=\s*6\s*$"
)
APPS_OPEN_RE = re.compile(
    r"^\s*static\s+const\s+app_entry_t\s+apps\[\]\s*=\s*\{"
)
ENTRY_RE = re.compile(
    r'^\s*\{\s*"([^"]+)"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\s*,?\s*$'
)
INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$')


def parse_app_entries(text: str) -> list[tuple[str, str]]:
    lines = _normalized_lines(text)
    open_index = _apps_open_index(lines)
    close_index = _apps_close_index(lines, open_index)
    entries: list[tuple[str, str]] = []
    for line in lines[open_index + 1:close_index]:
        match = ENTRY_RE.match(line)
        if match:
            entries.append((match.group(1), match.group(2)))
    return entries


def find_include(text: str, name: str) -> str | None:
    for line in _normalized_lines(text):
        parsed = INCLUDE_RE.match(line)
        if parsed and parsed.group(1).split("/", 1)[0] == name:
            return line.strip()
    return None


def register_app(text: str, name: str) -> tuple[str, bool]:
    lines = _normalized_lines(text)
    first_before = _first_registered_name(text)
    include_line = f'#include "{name}/{name}.h"'
    changed = False

    if include_line not in (line.strip() for line in lines):
        lines, include_changed = _insert_include(lines, include_line)
        changed = changed or include_changed

    open_index = _apps_open_index(lines)
    close_index = _apps_close_index(lines, open_index)
    lines, entry_changed = _insert_entry(lines, name, open_index, close_index)
    changed = changed or entry_changed

    if not changed:
        return text, False

    new_text = "\n".join(lines)
    if text.endswith(("\n", "\r")):
        new_text += "\n"
    _verify_registration(new_text, name, first_before)
    return new_text, True


def unregister_app(
    text: str, name: str, *, missing_ok: bool = False
) -> tuple[str, dict[str, Any]]:
    lines = _normalized_lines(text)
    first_before = _first_registered_name(text)
    open_index = _apps_open_index(lines)
    close_index = _apps_close_index(lines, open_index)
    entries: list[tuple[str, str, int]] = []
    for index in range(open_index + 1, close_index):
        match = ENTRY_RE.match(lines[index])
        if match:
            entries.append((match.group(1), match.group(2), index))

    name_rows = [entry for entry in entries if entry[0] == name]
    if len(name_rows) > 1:
        raise AppError(
            "app_conflict", f'app "{name}" is registered more than once'
        )

    include_indices: list[int] = []
    for index, line in enumerate(lines):
        match = INCLUDE_RE.match(line)
        if match and match.group(1).split("/", 1)[0] == name:
            include_indices.append(index)

    if not name_rows and not include_indices:
        if missing_ok:
            return text, {
                "symbol": None,
                "includes": [],
                "warnings": [f'app "{name}" was not registered'],
                "changed": False,
            }
        raise AppError("unknown_app", f'app "{name}" is not registered')

    warnings: list[str] = []
    if not name_rows:
        warnings.append(f'app "{name}" had includes but no apps[] row')
    if not include_indices:
        warnings.append(f'app "{name}" had an apps[] row but no include')
    if len(include_indices) > 1:
        warnings.append(f'app "{name}" had multiple includes')

    removed_includes = [lines[index] for index in include_indices]
    remove_indices = set(include_indices)
    if name_rows:
        remove_indices.add(name_rows[0][2])
    for index in sorted(remove_indices, reverse=True):
        del lines[index]

    new_text = "\n".join(lines)
    if text.endswith(("\n", "\r")):
        new_text += "\n"
    _verify_unregistered(new_text, name, first_before)
    return new_text, {
        "symbol": name_rows[0][1] if name_rows else None,
        "includes": removed_includes,
        "warnings": warnings,
        "changed": True,
    }


def _normalized_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _insert_include(lines: list[str], include_line: str) -> tuple[list[str], bool]:
    for index, line in enumerate(lines):
        if not VERSION_GATE_RE.match(line):
            continue
        last_include = None
        cursor = index + 1
        while cursor < len(lines):
            stripped = lines[cursor].strip()
            if stripped.startswith("#include "):
                last_include = cursor
                cursor += 1
            elif stripped == "":
                cursor += 1
            else:
                break
        if last_include is not None:
            lines.insert(last_include + 1, include_line)
            return lines, True
    raise AppError(
        "app_registry_invalid",
        "app.c: cannot find the 9.6 include block; expected "
        "#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6 "
        "followed by #include lines",
    )


def _apps_open_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if APPS_OPEN_RE.match(line):
            return index
    raise AppError(
        "app_registry_invalid",
        "app.c: cannot find static const app_entry_t apps[] = {",
    )


def _apps_close_index(lines: list[str], open_index: int) -> int:
    for index in range(open_index + 1, len(lines)):
        if lines[index].strip() == "};":
            return index
    raise AppError(
        "app_registry_invalid", "app.c: cannot find the end of apps[]"
    )


def _insert_entry(
    lines: list[str], name: str, open_index: int, close_index: int
) -> tuple[list[str], bool]:
    symbol = f"{name}_create"
    entries: list[tuple[str, str, int]] = []
    for index in range(open_index + 1, close_index):
        match = ENTRY_RE.match(lines[index])
        if match:
            entries.append((match.group(1), match.group(2), index))

    name_matches = [entry for entry in entries if entry[0] == name]
    if len(name_matches) > 1:
        raise AppError(
            "app_conflict", f'app "{name}" is registered more than once'
        )
    symbol_matches = [entry for entry in entries if entry[1] == symbol]
    if len(symbol_matches) > 1:
        raise AppError(
            "app_conflict", f"symbol {symbol} is registered more than once"
        )

    for entry_name, entry_symbol, _ in entries:
        if entry_name == name:
            if entry_symbol == symbol:
                return lines, False
            raise AppError(
                "app_conflict",
                f'app "{name}" is already registered to {entry_symbol}',
            )
        if entry_symbol == symbol:
            raise AppError(
                "app_conflict",
                f'symbol {symbol} is already registered as "{entry_name}"',
            )

    if entries:
        last_index = entries[-1][2]
        last_line = lines[last_index]
        indent = last_line[:len(last_line) - len(last_line.lstrip())]
        if not last_line.rstrip().endswith(","):
            lines[last_index] = last_line.rstrip() + ","
    else:
        indent = "    "

    lines.insert(close_index, f'{indent}{{"{name}", {symbol}}},')
    return lines, True


def _first_registered_name(text: str) -> str | None:
    try:
        entries = parse_app_entries(text)
    except AppError:
        return None
    return entries[0][0] if entries else None


def _verify_registration(
    text: str, name: str, first_before: str | None
) -> None:
    lines = _normalized_lines(text)
    include_line = f'#include "{name}/{name}.h"'
    if sum(1 for line in lines if line.strip() == include_line) != 1:
        raise AppError(
            "app_registry_invalid", "app.c: expected exactly one new include"
        )

    entries = parse_app_entries(text)
    if sum(1 for entry_name, _ in entries if entry_name == name) != 1:
        raise AppError(
            "app_registry_invalid",
            "app.c: expected exactly one new apps[] row",
        )
    _verify_first_entry(entries, first_before)


def _verify_unregistered(
    text: str, name: str, first_before: str | None
) -> None:
    lines = _normalized_lines(text)
    prefix = f'#include "{name}/'
    if any(line.strip().startswith(prefix) for line in lines):
        raise AppError(
            "app_registry_invalid",
            f"app.c: include for {name} was not removed",
        )
    entries = parse_app_entries(text)
    if any(entry_name == name for entry_name, _ in entries):
        raise AppError(
            "app_registry_invalid",
            f"app.c: apps[] row for {name} was not removed",
        )
    _verify_first_entry(entries, first_before)


def _verify_first_entry(
    entries: list[tuple[str, str]], first_before: str | None
) -> None:
    if first_before is None:
        return
    if not entries or entries[0][0] != first_before:
        raise AppError(
            "app_registry_invalid",
            f"app.c: {first_before} must stay the first apps[] entry",
        )
