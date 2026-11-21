from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from scenario import ScenarioError, load_scenario
from . import common, discovery, policy
from .common import AppError

HEADER_TEMPLATE = """\
#ifndef {{GUARD}}
#define {{GUARD}}

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
void {{NAME}}_create(void);
#endif

#endif
"""

SOURCE_TEMPLATE = """\
#include "{{NAME}}.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

#include "app.h"

#include <stdio.h>

static void {{NAME}}_click_cb(lv_event_t * event)
{
    lv_obj_t * status = lv_event_get_user_data(event);
    lv_label_set_text(status, "clicked");
    printf("[{{NAME}}] clicked\\n");
}

void {{NAME}}_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    app_set_name("{{NAME}}");
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101318), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    lv_obj_t * title = lv_label_create(screen);
    lv_label_set_text(title, "{{TITLE}}");
    lv_obj_set_style_text_font(title, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(title, lv_color_hex(0xE6E8EB), 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 24);
    app_obj_set_name(title, "{{NAME}}_title");

    lv_obj_t * status = lv_label_create(screen);
    lv_label_set_text(status, "waiting");
    lv_obj_set_style_text_color(status, lv_color_hex(0x9AA3AD), 0);
    lv_obj_align(status, LV_ALIGN_CENTER, 0, 48);
    app_obj_set_name(status, "{{NAME}}_status");

    lv_obj_t * button = lv_button_create(screen);
    lv_obj_set_size(button, 160, 48);
    lv_obj_align(button, LV_ALIGN_CENTER, 0, 0);
    app_obj_set_name(button, "{{NAME}}_button");

    lv_obj_t * button_label = lv_label_create(button);
    lv_label_set_text(button_label, "CLICK");
    lv_obj_center(button_label);
    app_obj_set_name(button_label, "{{NAME}}_button_label");

    lv_obj_add_event_cb(button, {{NAME}}_click_cb, LV_EVENT_CLICKED, status);

    printf("[{{NAME}}] created\\n");
}

#endif
"""

SCENARIO_STEPS = [
    {"type": "wait", "ms": 100},
    {"type": "mark", "id": "start"},
    {"type": "snapshot", "label": "start"},
    {"type": "click_at", "x": 400, "y": 300},
    {"type": "wait", "ms": 100},
    {"type": "mark", "id": "clicked"},
    {"type": "snapshot", "label": "clicked"},
]


def scaffold_app(
    repo_root: str | Path,
    name: str,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = common.resolve_repo_root(repo_root)
    app_c = common._app_c(root)
    app_dir = common._app_dir(root, name)
    scenario_path = common._scenario_path(root, f"{name}.json")
    header_path = app_dir / f"{name}.h"
    source_path = app_dir / f"{name}.c"
    metadata_path = app_dir / discovery.METADATA_NAME

    if not app_c.is_file():
        raise AppError("app_c_missing", f"app.c not found: {app_c}")
    _validate_name(root, name, force=force)

    header = _render(HEADER_TEMPLATE, name)
    source = _render(SOURCE_TEMPLATE, name)
    scenario = (
        json.dumps(
            {
                "schema": "lvgl-verify-loop-scenario-v1",
                "name": name,
                "app": name,
                "steps": SCENARIO_STEPS,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    _validate_scenario(scenario, name)

    created: list[str] = []
    updated: list[str] = []
    writes: list[tuple[Path, bytes, bool]] = []
    for path, data in (
        (header_path, header.encode("utf-8")),
        (source_path, source.encode("utf-8")),
        (scenario_path, scenario.encode("utf-8")),
    ):
        if path.exists():
            if path.read_bytes() != data:
                updated.append(common._relative(path, root))
                writes.append((path, data, True))
        else:
            created.append(common._relative(path, root))
            writes.append((path, data, False))

    result: dict[str, Any] = {
        "ok": True,
        "action": "create",
        "at": common._now_iso(),
        "name": name,
        "repo_root": str(root),
        "dry_run": dry_run,
        "files": {
            "app_c": common._relative(app_c, root),
            "metadata": (
                common._relative(metadata_path, root)
                if metadata_path.is_file()
                else None
            ),
            "header": common._relative(header_path, root),
            "source": common._relative(source_path, root),
            "scenario": common._relative(scenario_path, root),
        },
        "created": created,
        "updated": updated,
        "build_required": True,
        "commands": [
            f"{common._tool_command(root, 'cli.py')} --lvgl 9.6 "
            f"--scenario user/scenarios/{name}.json",
            f"{common._tool_command(root, 'serve.py')} --app {name}",
        ],
    }
    if dry_run:
        return result

    _write_all(writes)
    return result


def _validate_name(root: Path, name: str, *, force: bool) -> None:
    common._require_plain_name(name, create=True)
    if policy.is_reserved_create_name(root, name):
        raise AppError("name_reserved", f'name "{name}" is reserved')
    user_app = common._user_app(root)
    app_dir = common._app_dir(root, name)
    scenario_path = common._scenario_path(root, f"{name}.json")
    if app_dir.exists() and not force:
        raise AppError(
            "app_exists",
            f"{app_dir} already exists; use --force to overwrite generated files",
        )
    if scenario_path.exists() and not force:
        raise AppError(
            "app_exists",
            f"{scenario_path} already exists; use --force to overwrite it",
        )
    if app_dir.exists() and not app_dir.is_dir():
        raise AppError(
            "app_exists", f"{app_dir} exists and is not a directory"
        )

    symbol = f"{name}_create"
    app_c = common._app_c(root)
    for path in _user_sources(user_app):
        if path == app_c:
            continue
        if (
            force
            and app_dir in path.parents
            and path.name in (f"{name}.c", f"{name}.h")
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"\b{re.escape(symbol)}\b", text):
            raise AppError(
                "app_conflict",
                f"symbol {symbol} already exists in {common._relative(path, root)}",
            )

    entries, _issues = discovery.scan_apps(user_app)
    for entry in entries:
        if entry.name == name and entry.entry != symbol:
            raise AppError(
                "app_conflict",
                f'app "{name}" already uses entry {entry.entry}',
            )
        if entry.entry == symbol and entry.name != name:
            raise AppError(
                "app_conflict",
                f'symbol {symbol} is already used by "{entry.name}"',
            )


def _user_sources(user_app: Path) -> list[Path]:
    if not user_app.is_dir():
        return []
    return sorted(
        path
        for path in user_app.rglob("*")
        if path.is_file() and path.suffix in (".c", ".h")
    )


def _render(template: str, name: str) -> str:
    return (
        template.replace("{{NAME}}", name)
        .replace("{{GUARD}}", f"{name.upper()}_H")
        .replace("{{TITLE}}", name.replace("_", " ").upper())
    )


def _validate_scenario(text: str, name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="new-app-scenario-") as tmp:
        path = Path(tmp) / f"{name}.json"
        path.write_text(text, encoding="utf-8")
        try:
            document = load_scenario(path)
        except ScenarioError as exc:
            raise AppError("app_invalid", str(exc)) from exc
    if document.get("app") != name:
        raise AppError(
            "app_invalid", "generated scenario has the wrong app field"
        )
    if len(document.get("steps", [])) != len(SCENARIO_STEPS):
        raise AppError(
            "app_invalid", "generated scenario has the wrong step count"
        )


def _write_all(writes: list[tuple[Path, bytes, bool]]) -> None:
    backups: dict[Path, bytes] = {}
    created: list[Path] = []
    created_dirs: list[Path] = []
    try:
        for path, _, existed in writes:
            if not existed and not path.parent.exists():
                missing: list[Path] = []
                parent = path.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir()
                    created_dirs.append(directory)
        for path, data, existed in writes:
            if existed:
                backups[path] = path.read_bytes()
            common._replace_bytes(path, data)
            if not existed:
                created.append(path)
    except BaseException:
        for path in created:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        for path, data in backups.items():
            try:
                common._replace_bytes(path, data)
            except OSError:
                pass
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
