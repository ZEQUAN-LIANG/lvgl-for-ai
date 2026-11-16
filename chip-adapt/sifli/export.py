#!/usr/bin/env python3
"""SiFli-SDK adapter: export a user app as a Huangshan Pi project.

The adapter owns the export pipeline, including ezip conversion. Sources are
copied as-is; an app must already use APIs available in LVGL 9.4. Apps that use
9.5/9.6-only APIs are rejected with a diagnostic instead of being rewritten.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ADAPTER_DIR = Path(__file__).resolve().parent
REPO_ROOT = ADAPTER_DIR.parents[1]
CONSOLE_ROOT = REPO_ROOT / "console"
for _path in (CONSOLE_ROOT, ADAPTER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import layout
from appmgr import common, registry
from asset_plan import AssetPlan, ExportError, plan_assets

ADAPTER_SCHEMA = "lvgl-verify-loop-chip-adapter-v1"
EXPORT_SCHEMA = "lvgl-verify-loop-export-v1"
SDK_INCLUDE = '#include "lvgl_verify_loop_sdk.h"\n'
TEXT_SUFFIXES = {".c", ".h"}
EXCLUDED_SOURCE_DIRS = {"design", "covers_src"}
INCOMPATIBLE_APIS = {
    "lv_obj_set_clickable": (
        "LVGL 9.6 API; use lv_obj_add_flag/lv_obj_remove_flag "
        "with LV_OBJ_FLAG_CLICKABLE"
    ),
    "lv_obj_set_scrollable": (
        "LVGL 9.6 API; use lv_obj_add_flag/lv_obj_remove_flag "
        "with LV_OBJ_FLAG_SCROLLABLE"
    ),
    "lv_obj_set_hidden": (
        "LVGL 9.6 API; use lv_obj_add_flag/lv_obj_remove_flag "
        "with LV_OBJ_FLAG_HIDDEN"
    ),
    "lv_obj_is_hidden": (
        "LVGL 9.6 API; use lv_obj_has_flag(LV_OBJ_FLAG_HIDDEN)"
    ),
}
MULTI_POINT_HEADER = "lv_draw_line_dsc_t"
MULTI_POINT_FIELDS = (".points", ".point_cnt")


def export_app(
    repo_root: str | Path,
    app: str,
    *,
    chip: str = "sifli",
    output_dir: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    ezip_tool: Sequence[str] | None = None,
) -> dict[str, Any]:
    adapter_dir = ADAPTER_DIR
    root = common.resolve_repo_root(repo_root)
    adapter = _load_adapter(adapter_dir)
    templates_dir = adapter_dir / str(adapter.get("templates", "templates"))
    if not templates_dir.is_dir():
        raise ExportError(
            "adapter_missing",
            f"adapter templates not found: {templates_dir}",
        )

    common._require_plain_name(app)
    app_symbol = _registered_symbol(root, app)
    source_dir = root / "user" / "app" / app
    if not source_dir.is_dir():
        raise ExportError(
            "app_missing",
            f"app directory not found: {source_dir}",
            detail={"app": app},
        )

    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else layout.EXPORTS_DIR / app
    )
    if destination.exists() and any(destination.iterdir()) and not force:
        raise ExportError(
            "app_conflict",
            f"output directory is not empty: {destination}",
            detail={"output_dir": str(destination)},
        )

    plan = _build_plan(
        root=root,
        app=app,
        app_symbol=app_symbol,
        source_dir=source_dir,
        templates_dir=templates_dir,
        lvgl_version=str(adapter["lvgl_version"]),
    )
    asset_plan = plan_assets(source_dir, adapter, ezip_tool=ezip_tool)
    plan.update(asset_plan.files)
    plan["src/app/app.c"] = _entry_source(
        app_symbol, app=app, has_assets=asset_plan.has_assets
    ).encode("utf-8")
    _apply_cache_config(plan, asset_plan.cache)
    plan["export.json"] = _export_manifest(app, app_symbol, asset_plan).encode(
        "utf-8"
    )
    warnings = _adapter_warnings(adapter_dir, adapter)

    created: list[str] = []
    updated: list[str] = []
    if not dry_run:
        for relative, data in plan.items():
            target = destination / relative
            existed = target.exists()
            target.parent.mkdir(parents=True, exist_ok=True)
            common._replace_bytes(target, data)
            (updated if existed else created).append(relative)

    commands = [
        f"cd {destination / 'project'} && scons --board={adapter['board']} -j8",
        (
            f'LVGL_VERIFY_LOOP_USER_APP_DIR="{destination / "src" / "app"}" '
            f"python -I console/entrypoints/cli.py --lvgl {adapter['lvgl_version']} "
            f"--scenario user/scenarios/{app}.json"
        ),
    ]
    return {
        "ok": True,
        "action": "export",
        "at": common._now_iso(),
        "app": app,
        "symbol": app_symbol,
        "chip": chip,
        "output_dir": str(destination),
        "files": sorted(plan),
        "created": sorted(created),
        "updated": sorted(updated),
        "dry_run": dry_run,
        "warnings": warnings,
        "assets": asset_plan.records,
        "cache": asset_plan.cache,
        "commands": commands,
    }


def _load_adapter(adapter_dir: Path) -> dict[str, Any]:
    path = adapter_dir / "adapter.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExportError(
            "adapter_missing", f"adapter not found: {path}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise ExportError(
            "adapter_invalid", f"cannot read adapter {path}: {exc}"
        ) from exc
    if payload.get("schema") != ADAPTER_SCHEMA:
        raise ExportError(
            "adapter_invalid",
            f"unexpected adapter schema in {path}",
            detail={"schema": payload.get("schema")},
        )
    missing = [
        key for key in ("board", "lvgl_version") if not payload.get(key)
    ]
    if missing:
        raise ExportError(
            "adapter_invalid",
            f"adapter is missing: {', '.join(missing)}",
            detail={"adapter": str(path)},
        )
    return payload


def _registered_symbol(root: Path, app: str) -> str:
    app_c = root / "user" / "app" / "app.c"
    try:
        text = app_c.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ExportError(
            "app_missing", f"cannot read {app_c}: {exc}"
        ) from exc
    for name, symbol in registry.parse_app_entries(text):
        if name == app:
            return symbol
    header = root / "user" / "app" / app / f"{app}.h"
    try:
        header_text = header.read_text(encoding="utf-8-sig")
    except OSError:
        header_text = ""
    symbol = f"{app}_create"
    if re.search(rf"\bvoid\s+{re.escape(symbol)}\s*\(", header_text):
        return symbol
    raise ExportError(
        "app_not_registered",
        f'app "{app}" is not registered in {app_c}',
        detail={"app": app},
    )


def _build_plan(
    *,
    root: Path,
    app: str,
    app_symbol: str,
    source_dir: Path,
    templates_dir: Path,
    lvgl_version: str,
) -> dict[str, bytes]:
    plan: dict[str, bytes] = {}

    for path in sorted(templates_dir.rglob("*")):
        if path.is_file():
            plan[path.relative_to(templates_dir).as_posix()] = (
                path.read_bytes()
            )

    shared_dir = root / "user" / "app"
    for name in ("app.h", "lvgl_compat.h"):
        source = shared_dir / name
        if source.is_file():
            plan[f"src/app/{name}"] = source.read_bytes()

    incompatible: dict[str, list[str]] = {}
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name.startswith("ccheck_tmp_") or path.suffix == ".dump":
            continue
        if EXCLUDED_SOURCE_DIRS & set(path.relative_to(source_dir).parts):
            continue
        relative = path.relative_to(source_dir).as_posix()
        label = f"user/app/{app}/{relative}"
        if path.suffix in TEXT_SUFFIXES:
            found = _incompatible_symbols(_read_text(path))
            if found:
                incompatible[label] = found
        data = (
            _copy_source(path)
            if path.suffix in TEXT_SUFFIXES
            else path.read_bytes()
        )
        plan[f"src/app/{app}/{relative}"] = data

    if incompatible:
        raise ExportError(
            "unsupported_api",
            "app uses APIs unavailable in LVGL 9.4",
            detail={"files": incompatible},
        )

    plan["README.md"] = _export_readme(app, app_symbol, lvgl_version).encode(
        "utf-8"
    )
    return plan


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace")


def _incompatible_symbols(text: str) -> list[str]:
    found = [name for name in INCOMPATIBLE_APIS if name in text]
    if MULTI_POINT_HEADER in text and any(
        field in text for field in MULTI_POINT_FIELDS
    ):
        found.append(MULTI_POINT_HEADER)
    return found


def _copy_source(path: Path) -> bytes:
    _, text, bom, eol = common._read_source(path)
    if path.suffix == ".c":
        text = SDK_INCLUDE + text
    return common._encode_source(text, bom, eol)


def _entry_source(app_symbol: str, *, app: str, has_assets: bool) -> str:
    include = f'#include "{app}/assets.h"\n' if has_assets else ""
    init = "    app_assets_init();\n" if has_assets else ""
    return (
        '#include "lvgl_verify_loop_sdk.h"\n'
        '#include "lvgl.h"\n'
        f"{include}"
        "\n"
        f"extern void {app_symbol}(void);\n"
        "\n"
        "void app_create(void)\n"
        "{\n"
        f"{init}"
        f"    {app_symbol}();\n"
        "}\n"
    )


def _export_readme(app: str, app_symbol: str, lvgl_version: str) -> str:
    return (
        f"# {app} · 黄山派导出\n"
        "\n"
        f"入口 `{app_symbol}`，由 `src/app/app.c` 的 `app_create()` 调用；生成入口先调 `app_assets_init()`。\n"
        f"应用源码按 LVGL {lvgl_version} 基线原样复制；应用入口是 `void <app>_create(void)`，内部用 `lv_screen_active()`。\n"
        "资源角色、PNG 宽高与缓存配置记录在 `export.json`，资源声明在 `src/app/<app>/assets.json`。\n"
        "\n"
        "## 构建\n"
        "\n"
        "```bash\n"
        "cd project\n"
        "scons --board=sf32lb52-lchspi-ulp -j8\n"
        "```\n"
        "\n"
        "## 运行时验证\n"
        "\n"
        "```bash\n"
        f'LVGL_VERIFY_LOOP_USER_APP_DIR="chip-adapt/exports/{app}/src/app" '
        f"python -I console/entrypoints/cli.py --lvgl {lvgl_version} "
        f"--scenario user/scenarios/{app}.json\n"
        "```\n"
    )


def _apply_cache_config(plan: dict[str, bytes], cache: dict[str, Any]) -> None:
    path = "project/proj.conf"
    text = plan[path].decode("utf-8")
    skip = (
        "CONFIG_IMAGE_CACHE_IN_PSRAM_SIZE=",
        "CONFIG_IMAGE_CACHE_IN_SRAM_SIZE=",
        "CONFIG_ROTATE_MEM_IN_PSRAM=",
        "CONFIG_ROTATE_MEM_IN_SRAM=",
        "CONFIG_LV_CACHE_DEF_SIZE=",
        "CONFIG_LV_IMAGE_HEADER_CACHE_DEF_CNT=",
    )
    lines = [line for line in text.splitlines() if not line.startswith(skip)]
    if cache["image_cache_psram_size"] > 0:
        lines.append(
            f"CONFIG_IMAGE_CACHE_IN_PSRAM_SIZE={cache['image_cache_psram_size']}"
        )
    if cache["image_cache_sram_size"] > 0:
        lines.append(
            f"CONFIG_IMAGE_CACHE_IN_SRAM_SIZE={cache['image_cache_sram_size']}"
        )
    if cache["rotate_mem"] == "psram":
        lines.append("CONFIG_ROTATE_MEM_IN_PSRAM=y")
    elif cache["rotate_mem"] == "sram":
        lines.append("CONFIG_ROTATE_MEM_IN_SRAM=y")
    lines.append(f"CONFIG_LV_CACHE_DEF_SIZE={cache['lv_cache_def_size']}")
    lines.append(
        f"CONFIG_LV_IMAGE_HEADER_CACHE_DEF_CNT={cache['lv_image_header_cache_cnt']}"
    )
    plan[path] = ("\n".join(lines) + "\n").encode("utf-8")


def _export_manifest(app: str, app_symbol: str, asset_plan: AssetPlan) -> str:
    return (
        json.dumps(
            {
                "schema": EXPORT_SCHEMA,
                "app": app,
                "symbol": app_symbol,
                "assets": asset_plan.records,
                "cache": asset_plan.cache,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def _adapter_warnings(adapter_dir: Path, adapter: dict[str, Any]) -> list[str]:
    if not layout.SDK_DIR.is_dir():
        return [f"SDK not found: {layout.SDK_DIR}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chip-adapt/sifli/export.py",
        description="Export a registered app as a Huangshan Pi SiFli project.",
    )
    parser.add_argument("app")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = export_app(
            args.repo_root,
            args.app,
            output_dir=args.output,
            dry_run=args.dry_run,
            force=args.force,
        )
    except Exception as exc:  # noqa: BLE001 - adapter CLI boundary
        print(f"[export] error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["output_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
