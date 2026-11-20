#!/usr/bin/env python3
"""Generate LVGL font/image C arrays.

    python -I console/entrypoints/assets_tool.py font --app coffee --font C:\\Windows\\Fonts\\Deng.ttf --size 16
    python -I console/entrypoints/assets_tool.py image --app coffee --input logo.png --cf ARGB8888
    python -I console/entrypoints/assets_tool.py doctor --json

The converter is a file tool: it does not start the engine, a display or a
session.  The generated headers are plain LVGL C and do not need this tool at
build or run time.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CONSOLE_ROOT = Path(__file__).resolve().parent.parent
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

import paths
from assets import (
    AssetError,
    FontOptions,
    ImageOptions,
    SUPPORTED_VERSIONS,
    generate_font,
    generate_image,
    resolve_lvgl_version,
)
from assets.corpus import build_charset
from assets.emit import sanitize_identifier
from assets.version import version_available
from assets.vendor import versions as vendor_versions

_APP_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo-root",
        type=_path,
        default=None,
        help="workspace root (default: the skill's repository root)",
    )
    parser.add_argument("--app", help="app name under user/app/<name>/")
    parser.add_argument(
        "--output",
        help="output header path; relative paths resolve against the app dir "
        "when --app is given, otherwise against --repo-root",
    )
    parser.add_argument(
        "--name", help="C symbol name (default: source + size)"
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite a changed output"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="validate without writing"
    )
    parser.add_argument(
        "--json", action="store_true", help="print one JSON line"
    )
    parser.add_argument(
        "--lvgl",
        default="auto",
        metavar="auto|" + "|".join(SUPPORTED_VERSIONS),
        help="target LVGL version (default: auto)",
    )
    parser.add_argument(
        "--manifest",
        help="asset manifest path (default: user/.cache/assets/<app>.json when --app is given)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assets",
        description="Convert TTF fonts and PNG images to LVGL C arrays.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    font = subparsers.add_parser("font", help="convert a TTF/OTF to lv_font_t")
    _add_common(font)
    font.add_argument("--font", required=True, help="TTF/OTF/TTC path")
    font.add_argument(
        "--face-index", type=int, default=0, help="TTC face index"
    )
    font.add_argument(
        "--size", type=int, default=16, help="pixel size (default: 16)"
    )
    font.add_argument(
        "--bpp",
        type=int,
        default=4,
        choices=(1, 2, 4, 8),
        help="bits per pixel",
    )
    font.add_argument(
        "--text", action="append", default=[], help="extra UTF-8 text"
    )
    font.add_argument(
        "--text-file",
        action="append",
        default=[],
        type=_path,
        help="UTF-8 corpus file",
    )
    font.add_argument(
        "--range",
        action="append",
        default=[],
        help="codepoint range, e.g. 0x20-0x7E (repeatable)",
    )
    font.add_argument(
        "--scan-app",
        action="store_true",
        help="scan the app's .c/.h string literals for glyphs",
    )
    font.add_argument(
        "--no-scan",
        action="store_true",
        help="do not scan the app when --app is given",
    )
    font.add_argument(
        "--metrics",
        choices=("face", "glyphs"),
        default="face",
        help="line metrics source (default: face)",
    )
    font.add_argument("--line-height", type=int, default=None)
    font.add_argument("--base-line", type=int, default=None)

    image = subparsers.add_parser(
        "image", help="convert a PNG to lv_image_dsc_t"
    )
    _add_common(image)
    image.add_argument("--input", required=True, help="PNG input path")
    image.add_argument(
        "--cf",
        choices=("auto", "RGB565", "ARGB8888", "RGB888", "A8"),
        default="auto",
        help="colour format (default: auto by alpha)",
    )
    image.add_argument(
        "--background",
        default="0x000000",
        help="background colour for formats without alpha (default: black)",
    )
    image.add_argument(
        "--dither",
        action="store_true",
        help="Floyd-Steinberg dithering for RGB565",
    )

    doctor = subparsers.add_parser("doctor", help="check bundled dependencies")
    doctor.add_argument("--repo-root", type=_path, default=None)
    doctor.add_argument("--lvgl", default="auto")
    doctor.add_argument("--json", action="store_true")

    return parser


def _resolve_repo_root(value: Path | None) -> Path:
    root = (value or paths.REPO_ROOT).expanduser().resolve()
    if not root.is_dir():
        raise AssetError(f"repo root not found: {root}")
    return root


def _resolve_app(repo_root: Path, app: str | None) -> Path | None:
    if not app:
        return None
    if not _APP_RE.fullmatch(app):
        raise AssetError(
            f"invalid app name {app!r}; expected ^[a-z][a-z0-9_]{{0,31}}$"
        )
    app_dir = repo_root / "user" / "app" / app
    if not app_dir.is_dir():
        raise AssetError(
            f"app not found: {app_dir}. Create it with "
            f"'python -I scripts/new_app.py {app}' or pass --output."
        )
    return app_dir


def _resolve_output(
    args: argparse.Namespace, repo_root: Path, app_dir: Path | None, name: str
) -> Path:
    if args.output:
        output = Path(args.output).expanduser()
        if not output.is_absolute():
            base = app_dir if app_dir is not None else repo_root
            output = base / output
        if output.suffix == "":
            output = output.with_suffix(".h")
        return output.resolve()
    if app_dir is None:
        raise AssetError(
            "pass --app or --output to choose where the header goes"
        )
    return (app_dir / f"{name}.h").resolve()


def manifest_path(repo_root: Path, app: str) -> Path:
    """Default replay log for *app*.

    The log records what each generated header was built from.  It is derived
    data, so it lives under ``user/.cache/`` instead of next to the sources;
    the generated ``*.h`` files carry the same facts in their header comment.
    """

    return repo_root / "user" / ".cache" / "assets" / f"{app}.json"


def _resolve_manifest(
    args: argparse.Namespace,
    repo_root: Path,
    app_dir: Path | None,
    dry_run: bool,
) -> Path | None:
    if args.manifest:
        manifest = Path(args.manifest).expanduser()
        if not manifest.is_absolute():
            manifest = repo_root / manifest
        return manifest.resolve()
    if app_dir is not None and not dry_run:
        return manifest_path(repo_root, app_dir.name)
    return None


def _parse_background(value: str) -> tuple[int, int, int]:
    text = value.strip()
    if text.startswith("#"):
        text = "0x" + text[1:]
    try:
        color = int(text, 0)
    except ValueError as exc:
        raise AssetError(f"invalid --background {value!r}") from exc
    if not 0 <= color <= 0xFFFFFF:
        raise AssetError(f"--background out of range: {value!r}")
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


def _summary_print(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    kind = payload.get("kind")
    status = payload.get("status")
    wrote = payload.get("wrote")
    bits = [f"[assets] {kind} {status}: {wrote}"]
    if payload.get("glyphs") is not None:
        bits.append(f"{payload['glyphs']} glyphs")
    if payload.get("width") is not None:
        bits.append(f"{payload['width']}x{payload['height']}")
    if payload.get("cf") is not None:
        bits.append(str(payload["cf"]))
    if payload.get("bytes") is not None:
        bits.append(f"{payload['bytes']} bytes")
    print(" | ".join(bits))
    for warning in payload.get("warnings", []):
        print(f"[assets] warning: {warning}", file=sys.stderr)


def _run_font(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _resolve_repo_root(args.repo_root)
    app_dir = _resolve_app(repo_root, args.app)
    font_path = Path(args.font).expanduser()
    if not font_path.is_absolute():
        font_path = (repo_root / font_path).resolve()
    default_name = sanitize_identifier(f"{font_path.stem}_{args.size}", "font")
    name = sanitize_identifier(args.name or default_name, "font")
    output = _resolve_output(args, repo_root, app_dir, name)
    manifest = _resolve_manifest(args, repo_root, app_dir, args.dry_run)

    scan_app = args.scan_app or (
        args.app is not None
        and not args.no_scan
        and not (args.text or args.text_file or args.range)
    )
    if args.scan_app and args.no_scan:
        raise AssetError("--scan-app and --no-scan are mutually exclusive")
    if scan_app and app_dir is None:
        raise AssetError("--scan-app requires --app")

    codepoints, corpus_meta = build_charset(
        texts=args.text,
        text_files=[path for path in args.text_file if path is not None],
        ranges=args.range,
        scan_app_dir=app_dir if scan_app else None,
    )
    target = resolve_lvgl_version(repo_root, args.lvgl)
    warnings: list[str] = []
    if not version_available(repo_root, target):
        warnings.append(
            f"target LVGL {target} is not present under dist/lvgl/ or engine/lvgl/; "
            "the header can still be generated but cannot be built locally"
        )
    if args.name and sanitize_identifier(args.name, "font") != args.name:
        warnings.append(
            f"asset name {args.name!r} was sanitized to {name!r} for C identifiers"
        )
    result = generate_font(
        options=FontOptions(
            font_path=font_path,
            face_index=args.face_index,
            size=args.size,
            bpp=args.bpp,
            codepoints=tuple(codepoints),
            metrics=args.metrics,
            line_height=args.line_height,
            base_line=args.base_line,
        ),
        name=name,
        output_path=output,
        repo_root=repo_root,
        target_version=target,
        force=args.force,
        dry_run=args.dry_run,
        manifest_path=manifest,
    )
    result["warnings"] = list(result.get("warnings", [])) + warnings
    result["charset"] = {
        "codepoints": len(codepoints),
        **{
            key: value
            for key, value in corpus_meta.items()
            if key != "codepoint_count"
        },
    }
    return result


def _run_image(args: argparse.Namespace) -> dict[str, object]:
    repo_root = _resolve_repo_root(args.repo_root)
    app_dir = _resolve_app(repo_root, args.app)
    input_path = Path(args.input).expanduser()
    if not input_path.is_absolute():
        input_path = (repo_root / input_path).resolve()
    default_name = sanitize_identifier(input_path.stem, "image")
    name = sanitize_identifier(args.name or default_name, "image")
    output = _resolve_output(args, repo_root, app_dir, name)
    manifest = _resolve_manifest(args, repo_root, app_dir, args.dry_run)
    target = resolve_lvgl_version(repo_root, args.lvgl)
    warnings: list[str] = []
    if not version_available(repo_root, target):
        warnings.append(
            f"target LVGL {target} is not present under dist/lvgl/ or engine/lvgl/; "
            "the header can still be generated but cannot be built locally"
        )
    if args.name and sanitize_identifier(args.name, "image") != args.name:
        warnings.append(
            f"asset name {args.name!r} was sanitized to {name!r} for C identifiers"
        )
    result = generate_image(
        options=ImageOptions(
            input_path=input_path,
            requested_cf=args.cf,
            background=_parse_background(args.background),
            dither=args.dither,
        ),
        name=name,
        output_path=output,
        repo_root=repo_root,
        target_version=target,
        force=args.force,
        dry_run=args.dry_run,
        manifest_path=manifest,
    )
    result["warnings"] = list(result.get("warnings", [])) + warnings
    return result


def _run_doctor(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args.repo_root)
    try:
        target = resolve_lvgl_version(repo_root, args.lvgl)
        info = vendor_versions()
        payload: dict[str, object] = {
            "ok": True,
            "python": sys.version.split()[0],
            "target_lvgl": target,
            "target_available": version_available(repo_root, target),
            **info,
        }
    except (AssetError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        if payload.get("ok"):
            print(
                f"[assets] ok: python {payload['python']}, "
                f"FreeType {payload['freetype']}, pypng {payload['pypng']}, "
                f"target LVGL {payload['target_lvgl']}"
            )
        else:
            print(f"[assets] error: {payload.get('error')}", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return _run_doctor(args)
        if args.command == "font":
            payload = _run_font(args)
        else:
            payload = _run_image(args)
        _summary_print(payload, args.json)
        return 0
    except (AssetError, OSError, ValueError) as exc:
        print(f"[assets] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
