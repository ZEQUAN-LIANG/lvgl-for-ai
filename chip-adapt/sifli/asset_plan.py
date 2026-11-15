"""SiFli export asset planning.

The module owns everything between an app's asset manifest and the generated
resource files: manifest validation, PNG dimensions, ezip conversion, symbol
renaming, cache math and the assets header/source text.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

ADAPTER_DIR = Path(__file__).resolve().parent
REPO_ROOT = ADAPTER_DIR.parents[1]
CORE_ROOT = REPO_ROOT / "core"
for _path in (CORE_ROOT, ADAPTER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import layout
from lvgl_ai.apps import common

ASSET_SCHEMA = "lvgl-ai-assets-v1"
ASSET_MODES = {"ezip", "raw"}
ASSET_PLACEMENTS = {"flash", "psram", "sram"}
ASSET_TRANSFORMS = {"none", "rotate", "scale", "rotate_scale"}


class ExportError(common.AppError):
    pass


@dataclass(frozen=True)
class AssetPlan:
    records: list[dict[str, Any]]
    files: dict[str, bytes]
    cache: dict[str, Any]
    local_header: str
    has_assets: bool


def plan_assets(
    source_dir: str | Path,
    adapter: dict[str, Any],
    *,
    ezip_tool: Sequence[str] | None = None,
) -> AssetPlan:
    source_dir = Path(source_dir)
    app = source_dir.name
    assets_dir = source_dir / "assets"
    pngs = (
        sorted(path for path in assets_dir.glob("*.png") if path.is_file())
        if assets_dir.is_dir()
        else []
    )
    manifest = _load_asset_manifest(source_dir, pngs)
    assets = manifest["assets"]
    overrides = manifest["cache"]
    if not assets:
        return AssetPlan(
            records=[],
            files={},
            cache=_compute_cache([], overrides),
            local_header=manifest["local_header"],
            has_assets=False,
        )

    if ezip_tool is None:
        tool = layout.SDK_DIR / "tools" / "png2ezip" / "ezip.exe"
        if not tool.is_file():
            raise ExportError("ezip_missing", f"ezip tool not found: {tool}")
        ezip_command = [str(tool)]
    else:
        ezip_command = [str(part) for part in ezip_tool]
    chip = str(adapter.get("ezip_chip", "sf52x"))

    records: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(dir=ADAPTER_DIR) as tmp:
        tmp_path = Path(tmp)
        for name, spec in assets.items():
            png = assets_dir / spec["file"]
            width, height = _png_size(png)
            shutil.copy2(png, tmp_path / png.name)
            cfile = "2" if spec["mode"] == "ezip" else "1"
            section = "ROM3_IMG" if spec["mode"] == "ezip" else "ROM2_IMG"
            command = [
                *ezip_command,
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
            target = (
                f"src/{'ezip' if spec['mode'] == 'ezip' else 'raw'}/{name}.c"
            )
            files[target] = text.encode("utf-8")
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
    files.update(_generate_assets(app, records, manifest["local_header"]))
    return AssetPlan(
        records=records,
        files=files,
        cache=cache,
        local_header=manifest["local_header"],
        has_assets=True,
    )


def _load_asset_manifest(source_dir: Path, pngs: list[Path]) -> dict[str, Any]:
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
    raw_cache = payload.get("cache", {})
    if not isinstance(raw_assets, dict):
        raise ExportError(
            "asset_manifest_invalid",
            f"{manifest_path} has no assets",
            detail={"file": str(manifest_path)},
        )
    if not raw_assets:
        if not isinstance(raw_cache, dict) or not raw_cache:
            raise ExportError(
                "asset_manifest_invalid",
                f"{manifest_path} has no assets",
                detail={"file": str(manifest_path)},
            )
        return {
            "assets": {},
            "cache": raw_cache,
            "local_header": str(payload.get("local_header", "")),
        }

    macros: dict[str, str] = {}
    for name in raw_assets:
        macro = str(name).upper()
        if macro in macros:
            raise ExportError(
                "asset_macro_conflict",
                f"assets {macros[macro]} and {name} both generate "
                f"{macro}_W/{macro}_H",
                detail={"macro": macro, "names": [macros[macro], str(name)]},
            )
        macros[macro] = str(name)

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
        cache["lv_image_header_cache_cnt"] = overrides[
            "lv_image_header_cache_cnt"
        ]

    rotate_size = sum(
        record["size"] for record in hot if "rotate" in record["transform"]
    )
    if (
        cache["rotate_mem"] == "psram"
        and cache["image_cache_psram_size"] < rotate_size + 4096
    ):
        cache["image_cache_psram_size"] = rotate_size + 4096
    if (
        cache["rotate_mem"] == "sram"
        and cache["image_cache_sram_size"] < rotate_size + 4096
    ):
        cache["image_cache_sram_size"] = rotate_size + 4096
    return cache


def _cache_expr(record: dict[str, Any]) -> str:
    if "rotate" in record["transform"]:
        return "ROTATE_MEM"
    if record["placement"] == "psram":
        return "IMAGE_CACHE_PSRAM"
    return "IMAGE_CACHE_SRAM"


def _generate_assets(
    app: str,
    records: list[dict[str, Any]],
    local_header: str,
) -> dict[str, bytes]:
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
        body.append(
            f"    return {name}_hot != NULL ? {name}_hot : &{name}_raw;"
        )
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
    return {
        f"src/app/{app}/assets.h": "\n".join(header).encode("utf-8"),
        f"src/app/{app}/assets.c": "\n".join(body).encode("utf-8"),
    }
