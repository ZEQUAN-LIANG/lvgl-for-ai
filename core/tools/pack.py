#!/usr/bin/env python3
"""Build one downloadable LVGL version pack.

A pack contains a prebuilt host SDK and engine, plus a small manifest that
binds it to one core release.  The installer copies the two payload
directories into the workspace; legacy packs also carry a smoke scenario and
README so the prebuilt demo harness can be exercised without a compiler.

Usage::

    python -I core/tools/pack.py --lvgl 9.4 --out release/packs
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import sys

_BOOTSTRAP_TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402
from lvgl_ai.control.errors import BuildError  # noqa: E402
from lvgl_ai.digest import sha256_file  # noqa: E402

PACK_SCHEMA = "lvgl-verify-loop-pack-v1"
PACK_PLATFORM = "win64"
LEGACY_SMOKE_NAME = "legacy_smoke.json"


def pack_dir_name(version: str, tool_version: str) -> str:
    return f"lvgl-verify-loop-pack-{version}-win64"


def pack_zip_name(version: str, tool_version: str) -> str:
    return f"lvgl-verify-loop-{tool_version}-sdk-{version}-win64.zip"


def _legacy_zip_name(version: str, tool_version: str) -> str:
    return f"lvgl-verify-loop-{tool_version}-legacy-{version}-win64.zip"


def _write_smoke_readme(path: Path, version: str) -> None:
    path.write_text(
        "\n".join(
            (
                "# Legacy smoke fixture",
                "",
                f"This pack's engine is built with the LVGL {version} demo harness,",
                "not the intro app. Run it with:",
                "",
                "```bat",
                f"bin\\lvgl.cmd run --lvgl {version} --no-build \\",
                f"  --scenario smoke\\{LEGACY_SMOKE_NAME} --json",
                "```",
                "",
                "The scenario clicks the stable demo button at (112, 324) and",
                "captures two snapshots. The scenario is a test fixture; it is not",
                "a user template.",
                "",
            )
        ),
        encoding="utf-8",
    )


def _deterministic_zip(root: Path, zip_path: Path) -> str:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(
                f"{root.name}/{relative}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())
    return sha256_file(zip_path)


def build_pack(
    *,
    repo_root: Path,
    version: str,
    tool_version: str,
    engine: Path,
    sdk_dir: Path,
    out_dir: Path,
    legacy: bool = False,
    smoke_scenario: Path | None = None,
) -> dict[str, Any]:
    """Assemble and zip one version pack; return its manifest."""
    repo = repo_root.resolve()
    engine = engine.resolve()
    sdk_dir = sdk_dir.resolve()
    out = out_dir.resolve()
    if not engine.is_file():
        raise BuildError(f"pack: engine not found: {engine}")
    if not (sdk_dir / "manifest.json").is_file():
        raise BuildError(f"pack: SDK manifest not found: {sdk_dir}")

    name = pack_dir_name(version, tool_version)
    root = out / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    sdk_target = root / "sdk" / version
    shutil.copytree(sdk_dir, sdk_target)
    engine_target = root / "build" / f"lvgl_{paths.version_token(version)}" / (
        paths.engine_filename()
    )
    engine_target.parent.mkdir(parents=True)
    shutil.copy2(engine, engine_target)

    smoke_relative: str | None = None
    if legacy:
        if smoke_scenario is None or not smoke_scenario.is_file():
            raise BuildError(
                f"pack: legacy pack {version} needs a smoke scenario"
            )
        smoke_dir = root / "smoke"
        smoke_dir.mkdir()
        shutil.copy2(smoke_scenario, smoke_dir / LEGACY_SMOKE_NAME)
        _write_smoke_readme(smoke_dir / "README.md", version)
        smoke_relative = f"smoke/{LEGACY_SMOKE_NAME}"

    licenses = repo / "licenses"
    if licenses.is_dir():
        shutil.copytree(licenses, root / "licenses")

    sdk_manifest = json.loads(
        (sdk_target / "manifest.json").read_text(encoding="utf-8")
    )
    runtime_dlls = sdk_manifest.get("runtime_dlls", [])
    if isinstance(runtime_dlls, list):
        for name in runtime_dlls:
            if not isinstance(name, str):
                continue
            source = sdk_target / "lib" / name
            if not source.is_file():
                raise BuildError(f"pack: runtime DLL not found: {source}")
            shutil.copy2(source, engine_target.parent / name)
    manifest = {
        "schema": PACK_SCHEMA,
        "lvgl": version,
        "tag": sdk_manifest.get("lvgl_tag", "unknown"),
        "platform": PACK_PLATFORM,
        "tool_version": tool_version,
        "core_version": tool_version,
        "engine": engine_target.relative_to(root).as_posix(),
        "sdk": sdk_target.relative_to(root).as_posix(),
        "runtime_dlls": [
            name for name in runtime_dlls if isinstance(name, str)
        ],
        "smoke": smoke_relative,
        "legacy": bool(legacy),
        "sdk_manifest_sha256": sha256_file(sdk_target / "manifest.json"),
        "engine_sha256": sha256_file(engine_target),
    }
    (root / "pack.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    zip_name = (
        _legacy_zip_name(version, tool_version)
        if legacy
        else pack_zip_name(version, tool_version)
    )
    zip_path = out / zip_name
    digest = _deterministic_zip(root, zip_path)
    sha_path = zip_path.with_name(zip_path.name + ".sha256")
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    manifest["zip"] = str(zip_path)
    manifest["sha256"] = digest
    manifest["sha256_file"] = str(sha_path)
    manifest["bytes"] = zip_path.stat().st_size
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pack.py",
        description="Build one downloadable LVGL version pack.",
    )
    parser.add_argument("--lvgl", required=True, help="LVGL version, e.g. 9.4")
    parser.add_argument(
        "--version",
        default=paths.TOOL_VERSION,
        help=f"core tool version (default: {paths.TOOL_VERSION})",
    )
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--smoke-scenario", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = build_pack(
            repo_root=paths.REPO_ROOT,
            version=args.lvgl,
            tool_version=args.version,
            engine=args.engine,
            sdk_dir=args.sdk,
            out_dir=args.out,
            legacy=args.legacy,
            smoke_scenario=args.smoke_scenario,
        )
    except BuildError as exc:
        print(f"[pack] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"[pack] {summary['lvgl']}: {summary['zip']}")
        print(f"[pack] sha256: {summary['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
