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
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = REPO_ROOT / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from lvgl_ai.apps import common, registry  # noqa: E402

ADAPTER_SCHEMA = "lvgl-ai-chip-adapter-v1"
ASSET_SCHEMA = "lvgl-ai-assets-v1"
EXPORT_SCHEMA = "lvgl-ai-export-v1"
SDK_INCLUDE = '#include "lvgl_ai_sdk.h"\n'
TEXT_SUFFIXES = {".c", ".h"}
ASSET_MODES = {"ezip", "raw"}
ASSET_PLACEMENTS = {"flash", "psram", "sram"}
ASSET_TRANSFORMS = {"none", "rotate", "scale", "rotate_scale"}
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


class ExportError(common.AppError):
    """Domain error for export-specific failures."""


def export_app(
    repo_root: str | Path,
    app: str,
    *,
    chip: str = "sifli",
    output_dir: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    adapter_dir = Path(__file__).resolve().parent
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
        else adapter_dir / app
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
    )
    asset_info = _asset_plan(adapter_dir, adapter, source_dir, app, plan)
    plan["src/app/app.c"] = _entry_source(
        app_symbol, app=app, has_assets=asset_info["has_assets"]
    ).encode("utf-8")
    _apply_cache_config(plan, asset_info["cache"])
    plan["export.json"] = _export_manifest(app, app_symbol, asset_info).encode("utf-8")
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
            f'LVGL_AI_USER_APP_DIR="{destination / "src" / "app"}" '
            f"python -I core/cli.py --lvgl 9.4 --scenario user/scenarios/{app}.json"
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
        "assets": asset_info["assets"],
        "cache": asset_info["cache"],
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
    missing = [key for key in ("board", "lvgl_version") if not payload.get(key)]
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
        raise ExportError("app_missing", f"cannot read {app_c}: {exc}") from exc
    for name, symbol in registry.parse_app_entries(text):
        if name == app:
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
) -> dict[str, bytes]:
    plan: dict[str, bytes] = {}

    for path in sorted(templates_dir.rglob("*")):
        if path.is_file():
            plan[path.relative_to(templates_dir).as_posix()] = path.read_bytes()

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

    asset_dir = root / "user" / "asset"
    if asset_dir.is_dir():
        for path in sorted(asset_dir.rglob("*")):
            if path.is_file():
                plan[f"src/asset/{path.relative_to(asset_dir).as_posix()}"] = (
                    path.read_bytes()
                )

    plan["README.md"] = _export_readme(app, app_symbol).encode("utf-8")
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
        '#include "lvgl_ai_sdk.h"\n'
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


def _export_readme(app: str, app_symbol: str) -> str:
    return (
        f"# {app} · 黄山派导出\n"
        "\n"
        f"入口 `{app_symbol}`，由 `src/app/app.c` 的 `app_create()` 调用；生成入口先调 `app_assets_init()`。\n"
        "应用源码按 LVGL 9.4 基线原样复制；应用入口是 `void <app>_create(void)`，内部用 `lv_screen_active()`。\n"
        "资源角色与缓存配置记录在 `export.json`，资源声明在 `src/app/<app>/assets.json`。\n"
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
        f'LVGL_AI_USER_APP_DIR="chip-adapt/sifli/{app}/src/app" '
        f"python -I core/cli.py --lvgl 9.4 --scenario user/scenarios/{app}.json\n"
        "```\n"
    )


def _asset_plan(
    adapter_dir: Path,
    adapter: dict[str, Any],
    source_dir: Path,
    app: str,
    plan: dict[str, bytes],
) -> dict[str, Any]:
    assets_dir = source_dir / "assets"
    pngs = (
        sorted(path for path in assets_dir.glob("*.png") if path.is_file())
        if assets_dir.is_dir()
        else []
    )
    manifest = _load_asset_manifest(source_dir, app, pngs)
    assets = manifest["assets"]
    overrides = manifest["cache"]
    if not assets:
        return {
            "has_assets": False,
            "assets": [],
            "cache": _compute_cache([], overrides),
            "local_header": manifest["local_header"],
        }

    tool_setting = adapter.get("ezip")
    if not tool_setting:
        raise ExportError("ezip_missing", "adapter has no ezip tool")
    tool = (adapter_dir / str(tool_setting)).resolve()
    if not tool.is_file():
        raise ExportError("ezip_missing", f"ezip tool not found: {tool}")
    chip = str(adapter.get("ezip_chip", "sf52x"))

    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(dir=adapter_dir) as tmp:
        tmp_path = Path(tmp)
        for name, spec in assets.items():
            png = assets_dir / spec["file"]
            width, height = _png_size(png)
            shutil.copy2(png, tmp_path / png.name)
            cfile = "2" if spec["mode"] == "ezip" else "1"
            section = "ROM3_IMG" if spec["mode"] == "ezip" else "ROM2_IMG"
            command = [
                str(tool),
                "-convert",
                png.name,
                f"-{spec['format']}",
                "-cfile",
                cfile,
                "-section",
                section,
                "-lvgl_version",
                "9",
                "-chip",
                chip,
            ]
            try:
                result = subprocess.run(
                    command,
                    cwd=tmp_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExportError(
                    "ezip_failed",
                    f"ezip failed for {png.name}: {exc}",
                    detail={"file": str(png)},
                ) from exc
            output = tmp_path / "output" / f"{name}.c"
            if result.returncode != 0 or not output.is_file():
                raise ExportError(
                    "ezip_failed",
                    f"ezip failed for {png.name}",
                    detail={
                        "file": str(png),
                        "stdout": result.stdout[-2000:],
                        "stderr": result.stderr[-2000:],
                    },
                )
            text = output.read_text(encoding="utf-8")
            if f"lv_image_dsc_t {name}" not in text:
                raise ExportError(
                    "ezip_symbol_missing",
                    f"ezip output has no lv_image_dsc_t {name}",
                    detail={"file": str(png)},
                )
            hot = spec["mode"] == "raw" and spec["placement"] != "flash"
            if hot:
                text = _rename_dsc_symbol(text, name, f"{name}_raw")
            target = f"src/{'ezip' if spec['mode'] == 'ezip' else 'raw'}/{name}.c"
            plan[target] = text.encode("utf-8")
            records.append(
                {
                    "name": name,
                    "file": spec["file"],
                    "mode": spec["mode"],
                    "placement": spec["placement"],
                    "transform": spec["transform"],
                    "hot": hot,
                    "width": width,
                    "height": height,
                    "size": _parse_data_size(text),
                }
            )

    cache = _compute_cache(records, overrides)
    _generate_assets(plan, app, records, manifest["local_header"])
    return {
        "has_assets": True,
        "assets": records,
        "cache": cache,
        "local_header": manifest["local_header"],
    }


def _load_asset_manifest(
    source_dir: Path, app: str, pngs: list[Path]
) -> dict[str, Any]:
    manifest_path = source_dir / "assets.json"
    files = {path.name: path for path in pngs}
    if not manifest_path.is_file():
        return {
            "assets": {
                path.stem: {
                    "file": path.name,
                    "mode": "ezip",
                    "placement": "flash",
                    "transform": "none",
                    "format": "rgb565",
                }
                for path in pngs
            },
            "cache": {},
            "local_header": "",
        }

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExportError(
            "asset_manifest_invalid",
            f"cannot read {manifest_path}: {exc}",
            detail={"file": str(manifest_path)},
        ) from exc
    if payload.get("schema") != ASSET_SCHEMA:
        raise ExportError(
            "asset_manifest_invalid",
            f"unexpected asset schema in {manifest_path}",
            detail={"schema": payload.get("schema")},
        )
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, dict) or not raw_assets:
        raise ExportError(
            "asset_manifest_invalid",
            f"{manifest_path} has no assets",
            detail={"file": str(manifest_path)},
        )

    assets: dict[str, dict[str, str]] = {}
    declared: set[str] = set()
    for name, spec in raw_assets.items():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)) is None:
            raise ExportError(
                "asset_invalid",
                f"asset name is not a C identifier: {name}",
                detail={"asset": str(name)},
            )
        if not isinstance(spec, dict):
            raise ExportError(
                "asset_invalid",
                f"asset {name} is not an object",
                detail={"asset": str(name)},
            )
        file_name = str(spec.get("file", f"{name}.png"))
        if file_name not in files:
            raise ExportError(
                "asset_file_missing",
                f"asset {name} references missing PNG: {file_name}",
                detail={"asset": str(name), "file": file_name},
            )
        if Path(file_name).stem != name:
            raise ExportError(
                "asset_name_mismatch",
                f"asset {name} must match PNG stem {Path(file_name).stem}",
                detail={"asset": str(name), "file": file_name},
            )
        if file_name in declared:
            raise ExportError(
                "asset_duplicate",
                f"PNG {file_name} is declared more than once",
                detail={"file": file_name},
            )
        declared.add(file_name)
        mode = str(spec.get("mode", "ezip"))
        placement = str(spec.get("placement", "flash"))
        transform = str(spec.get("transform", "none"))
        image_format = str(spec.get("format", "rgb565"))
        if mode not in ASSET_MODES:
            raise ExportError(
                "asset_invalid",
                f"asset {name} has unsupported mode: {mode}",
                detail={"asset": str(name), "mode": mode},
            )
        if placement not in ASSET_PLACEMENTS:
            raise ExportError(
                "asset_invalid",
                f"asset {name} has unsupported placement: {placement}",
                detail={"asset": str(name), "placement": placement},
            )
        if transform not in ASSET_TRANSFORMS:
            raise ExportError(
                "asset_invalid",
                f"asset {name} has unsupported transform: {transform}",
                detail={"asset": str(name), "transform": transform},
            )
        if image_format not in {"rgb565", "rgb888"}:
            raise ExportError(
                "asset_invalid",
                f"asset {name} has unsupported format: {image_format}",
                detail={"asset": str(name), "format": image_format},
            )
        if mode == "ezip" and transform != "none":
            raise ExportError(
                "asset_transform_conflict",
                f"asset {name}: EZIP cannot be rotated or scaled; use mode raw",
                detail={"asset": str(name), "transform": transform},
            )
        if mode == "ezip" and placement != "flash":
            raise ExportError(
                "asset_placement_unsupported",
                f"asset {name}: EZIP assets stay in flash",
                detail={"asset": str(name), "placement": placement},
            )
        assets[str(name)] = {
            "file": file_name,
            "mode": mode,
            "placement": placement,
            "transform": transform,
            "format": image_format,
        }

    missing = set(files) - declared
    if missing:
        raise ExportError(
            "asset_unlisted",
            f"assets.json does not declare: {', '.join(sorted(missing))}",
            detail={"files": sorted(missing)},
        )
    cache = payload.get("cache", {})
    if not isinstance(cache, dict):
        raise ExportError(
            "asset_manifest_invalid",
            f"{manifest_path}: cache must be an object",
            detail={"file": str(manifest_path)},
        )
    local_header = payload.get("local_header", "")
    if not isinstance(local_header, str):
        raise ExportError(
            "asset_manifest_invalid",
            f"{manifest_path}: local_header must be a string",
            detail={"file": str(manifest_path)},
        )
    return {"assets": assets, "cache": cache, "local_header": local_header}


def _rename_dsc_symbol(text: str, old: str, new: str) -> str:
    pattern = re.compile(rf"(lv_image_dsc_t\s+){re.escape(old)}\b")
    if pattern.search(text) is None:
        raise ExportError(
            "ezip_symbol_missing",
            f"ezip output has no lv_image_dsc_t {old}",
            detail={"asset": old},
        )
    return pattern.sub(rf"\g<1>{new}", text, count=1)


def _parse_data_size(text: str) -> int:
    match = re.search(r"\.data_size\s*=\s*(\d+)", text)
    return int(match.group(1)) if match else 0


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if (
        len(header) < 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        raise ExportError(
            "asset_invalid",
            f"{path.name} is not a PNG with an IHDR chunk",
            detail={"file": str(path)},
        )
    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0:
        raise ExportError(
            "asset_invalid",
            f"{path.name} has an empty PNG size",
            detail={"file": str(path)},
        )
    return width, height


def _compute_cache(
    records: list[dict[str, Any]], overrides: dict[str, Any]
) -> dict[str, Any]:
    hot = [record for record in records if record["hot"]]
    psram_size = sum(
        record["size"] for record in hot if record["placement"] == "psram"
    )
    sram_size = sum(
        record["size"] for record in hot if record["placement"] == "sram"
    )
    rotate_locations = {
        record["placement"]
        for record in hot
        if "rotate" in record["transform"]
    }
    rotate_mem = None
    if "psram" in rotate_locations:
        rotate_mem = "psram"
    elif "sram" in rotate_locations:
        rotate_mem = "sram"

    cache: dict[str, Any] = {
        "image_cache_psram_size": psram_size + 4096 if psram_size else 0,
        "image_cache_sram_size": sram_size + 4096 if sram_size else 0,
        "rotate_mem": rotate_mem,
        "lv_cache_def_size": 0,
        "lv_image_header_cache_cnt": 0,
    }
    if isinstance(overrides.get("image_cache_psram_size"), int):
        cache["image_cache_psram_size"] = overrides["image_cache_psram_size"]
    if isinstance(overrides.get("image_cache_sram_size"), int):
        cache["image_cache_sram_size"] = overrides["image_cache_sram_size"]
    if overrides.get("rotate_mem") in {"psram", "sram"}:
        cache["rotate_mem"] = overrides["rotate_mem"]
    if isinstance(overrides.get("lv_cache_def_size"), int):
        cache["lv_cache_def_size"] = overrides["lv_cache_def_size"]
    if isinstance(overrides.get("lv_image_header_cache_cnt"), int):
        cache["lv_image_header_cache_cnt"] = overrides["lv_image_header_cache_cnt"]

    rotate_size = sum(
        record["size"] for record in hot if "rotate" in record["transform"]
    )
    if cache["rotate_mem"] == "psram" and cache["image_cache_psram_size"] < rotate_size + 4096:
        cache["image_cache_psram_size"] = rotate_size + 4096
    if cache["rotate_mem"] == "sram" and cache["image_cache_sram_size"] < rotate_size + 4096:
        cache["image_cache_sram_size"] = rotate_size + 4096
    return cache


def _cache_expr(record: dict[str, Any]) -> str:
    if "rotate" in record["transform"]:
        return "ROTATE_MEM"
    if record["placement"] == "psram":
        return "IMAGE_CACHE_PSRAM"
    return "IMAGE_CACHE_SRAM"


def _generate_assets(
    plan: dict[str, bytes],
    app: str,
    records: list[dict[str, Any]],
    local_header: str,
) -> None:
    guard = re.sub(r"[^A-Za-z0-9]+", "_", app).upper() + "_SDK_ASSETS_H"
    header = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        '#include "lvgl_ai_sdk.h"',
        '#include "lvgl.h"',
        "",
        "#if defined(LVGL_AI_EZIP_ASSETS)",
        "",
    ]
    body = [
        '#include "lvgl_ai_sdk.h"',
        "",
        "#if defined(LVGL_AI_EZIP_ASSETS)",
        "",
        '#include "lvgl.h"',
        '#include "app_mem.h"',
        '#include "assets.h"',
        "",
    ]
    for record in records:
        macro = record["name"].upper()
        header.append(f"#define {macro}_W {record['width']}")
        header.append(f"#define {macro}_H {record['height']}")
    if records:
        header.append("")
    hot = [record for record in records if record["hot"]]
    for record in records:
        name = record["name"]
        if record["hot"]:
            header.append(f"extern const lv_image_dsc_t {name}_raw;")
            header.append(f"const lv_image_dsc_t * app_asset_{name}(void);")
            header.append(f"#define {name} (*app_asset_{name}())")
        else:
            header.append(f"extern const lv_image_dsc_t {name};")
    header.extend(["", "void app_assets_init(void);", "", "#else", ""])
    if local_header:
        header.append(f'#include "{local_header}"')
        header.append("")
    header.extend(
        [
            "static inline void app_assets_init(void)",
            "{",
            "}",
            "",
            "#endif",
            "",
            f"#endif /* {guard} */",
            "",
        ]
    )

    for record in hot:
        name = record["name"]
        body.append(f"static lv_image_dsc_t * {name}_hot;")
        body.append("")
        body.append(f"const lv_image_dsc_t * app_asset_{name}(void)")
        body.append("{")
        body.append(f"    return {name}_hot != NULL ? {name}_hot : &{name}_raw;")
        body.append("}")
        body.append("")
    body.append("void app_assets_init(void)")
    body.append("{")
    for record in hot:
        name = record["name"]
        body.append(
            f"    {name}_hot = app_cache_copy_alloc(&{name}_raw, {_cache_expr(record)});"
        )
    body.append("}")
    body.extend(["", "#endif", ""])
    plan[f"src/app/{app}/assets.h"] = "\n".join(header).encode("utf-8")
    plan[f"src/app/{app}/assets.c"] = "\n".join(body).encode("utf-8")


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


def _export_manifest(
    app: str, app_symbol: str, asset_info: dict[str, Any]
) -> str:
    return (
        json.dumps(
            {
                "schema": EXPORT_SCHEMA,
                "app": app,
                "symbol": app_symbol,
                "assets": asset_info["assets"],
                "cache": asset_info["cache"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def _adapter_warnings(adapter_dir: Path, adapter: dict[str, Any]) -> list[str]:
    sdk_path = adapter.get("sdk_path")
    if not sdk_path:
        return []
    sdk_dir = (adapter_dir / str(sdk_path)).resolve()
    if not sdk_dir.is_dir():
        return [f"SDK not found: {sdk_dir}"]
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
