
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import assets as assets_cli
from lvgl_ai import paths
from lvgl_ai.assets import (
    AssetError,
    FontOptions,
    ImageOptions,
    build_image_data,
    generate_font,
    generate_image,
    rasterize_font,
    resolve_lvgl_version,
)
from lvgl_ai.assets.corpus import build_charset, parse_ranges, scan_c_strings
from lvgl_ai.assets.emit import (
    MANIFEST_SCHEMA,
    merge_manifest_entry,
    sanitize_identifier,
    write_if_changed,
)
from lvgl_ai.assets.font import render_font_header
from lvgl_ai.assets.image import render_image_header
from lvgl_ai.assets.vendor import load_png, versions
from lvgl_ai.assets.version import parse_version, version_available

REPO_ROOT = paths.REPO_ROOT
ASSETS_PY = REPO_ROOT / "core" / "assets.py"
FONT = REPO_ROOT / "lvgl-src" / "9.6" / "scripts" / "generators" / "built_in_font" / "Montserrat-Medium.ttf"
CJK_FONT = REPO_ROOT / "lvgl-src" / "9.6" / "scripts" / "generators" / "built_in_font" / "SourceHanSansSC-Normal.otf"
SDK_96 = REPO_ROOT / "sdk" / "9.6"
SRC_84 = REPO_ROOT / "lvgl-src" / "8.4"


def _tempdir():
    try:
        import support

        return support.RetryingTemporaryDirectory()
    except Exception:
        return tempfile.TemporaryDirectory()


def _write_png(path: Path, rows: list[list[int]], *, alpha: bool) -> None:
    png = load_png()
    with path.open("wb") as handle:
        png.Writer(
            width=len(rows[0]) // (4 if alpha else 3),
            height=len(rows),
            greyscale=False,
            alpha=alpha,
        ).write(handle, rows)


def _rgba_rows() -> list[list[int]]:
    return [
        [255, 0, 0, 255, 0, 255, 0, 128],
        [0, 0, 255, 0, 255, 255, 255, 255],
    ]


def _rgb_rows() -> list[list[int]]:
    return [
        [255, 0, 0, 0, 255, 0],
        [0, 0, 255, 255, 255, 255],
    ]


class VendorTest(unittest.TestCase):
    def test_bundled_versions_load(self) -> None:
        info = versions()
        self.assertEqual(info["freetype"], "2.13.2")
        self.assertTrue(info["pypng"].startswith("0.20220715"))
        self.assertTrue(Path(info["vendor_dir"]).is_dir())


class VersionTest(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("9.6"), (9, 6))
        with self.assertRaises(ValueError):
            parse_version("9")
        with self.assertRaises(ValueError):
            parse_version("nine")

    def test_auto_prefers_highest_present_version(self) -> None:
        with _tempdir() as tmp:
            root = Path(tmp) / "repo"
            (root / "sdk" / "9.4").mkdir(parents=True)
            (root / "lvgl-src" / "8.4").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"LVGL_AI_LVGL_VERSION": ""}):
                self.assertEqual(resolve_lvgl_version(root, "auto"), "9.4")
            self.assertEqual(resolve_lvgl_version(root, "8.4"), "8.4")
            self.assertTrue(version_available(root, "9.4"))
            self.assertFalse(version_available(root, "9.6"))
            with self.assertRaises(ValueError):
                resolve_lvgl_version(root, "7.0")


class CorpusTest(unittest.TestCase):
    def test_parse_ranges(self) -> None:
        self.assertEqual(parse_ranges(["0x20-0x22,0x41"]), {0x20, 0x21, 0x22, 0x41})
        with self.assertRaises(AssetError):
            parse_ranges(["0x30-0x20"])

    def test_scan_c_strings_skips_comments_and_decodes_escapes(self) -> None:
        source = r'''
        // "ignored"
        const char * a = "你好";
        const char * b = "A\x42你";
        /* "block" */
        char c = '"';
        '''
        self.assertEqual(scan_c_strings(source), ["你好", "AB你"])

    def test_build_charset_merges_sources(self) -> None:
        with _tempdir() as tmp:
            corpus = Path(tmp) / "corpus.txt"
            corpus.write_text("中文", encoding="utf-8")
            codepoints, meta = build_charset(
                texts=("AB",), text_files=(corpus,), ranges=("0x30-0x31",)
            )
            self.assertIn(ord("A"), codepoints)
            self.assertIn(ord("中"), codepoints)
            self.assertIn(ord("0"), codepoints)
            self.assertEqual(meta["explicit_charset"], True)


class ImageTest(unittest.TestCase):
    def test_argb8888_exact_bytes(self) -> None:
        with _tempdir() as tmp:
            png_path = Path(tmp) / "rgba.png"
            _write_png(png_path, _rgba_rows(), alpha=True)
            image = build_image_data(ImageOptions(png_path, "ARGB8888"))
            self.assertEqual(image.cf, "ARGB8888")
            self.assertEqual(image.stride, 8)
            self.assertEqual(
                image.data,
                bytes(
                    [
                        0,
                        0,
                        255,
                        255,
                        0,
                        255,
                        0,
                        128,
                        255,
                        0,
                        0,
                        0,
                        255,
                        255,
                        255,
                        255,
                    ]
                ),
            )

    def test_auto_and_rgb565_compositing(self) -> None:
        with _tempdir() as tmp:
            rgba = Path(tmp) / "rgba.png"
            rgb = Path(tmp) / "rgb.png"
            _write_png(rgba, _rgba_rows(), alpha=True)
            _write_png(rgb, _rgb_rows(), alpha=False)
            self.assertEqual(build_image_data(ImageOptions(rgba)).cf, "ARGB8888")
            opaque = build_image_data(ImageOptions(rgb))
            self.assertEqual(opaque.cf, "RGB565")
            self.assertFalse(opaque.had_alpha)

            composited = build_image_data(
                ImageOptions(rgba, "RGB565", background=(255, 255, 255))
            )
            self.assertEqual(
                composited.data, bytes([0x00, 0xF8, 0xEF, 0x7F, 0xFF, 0xFF, 0xFF, 0xFF])
            )

    def test_a8_requires_alpha(self) -> None:
        with _tempdir() as tmp:
            rgb = Path(tmp) / "rgb.png"
            rgba = Path(tmp) / "rgba.png"
            _write_png(rgb, _rgb_rows(), alpha=False)
            _write_png(rgba, _rgba_rows(), alpha=True)
            with self.assertRaises(AssetError):
                build_image_data(ImageOptions(rgb, "A8"))
            a8 = build_image_data(ImageOptions(rgba, "A8"))
            self.assertEqual(a8.data, bytes([255, 128, 0, 255]))

    def test_v8_header_preserves_transparent_alpha(self) -> None:
        with _tempdir() as tmp:
            png_path = Path(tmp) / "rgba.png"
            _write_png(png_path, _rgba_rows(), alpha=True)
            image = build_image_data(ImageOptions(png_path, "ARGB8888"))
            text = render_image_header(
                name="logo",
                image=image,
                target_version="8.4",
                source_path=png_path,
                source_sha256="0" * 64,
            )
            self.assertIn("LV_IMG_CF_TRUE_COLOR_ALPHA", text)
            self.assertIn("0xFFFF0000", text)
            self.assertIn("0x8000FF00", text)
            self.assertIn("0x000000FF", text)
            self.assertNotIn("VERSION_MAJOR >= 9", text)

    def test_v8_size_limit(self) -> None:
        with _tempdir() as tmp:
            png_path = Path(tmp) / "wide.png"
            _write_png(
                png_path,
                [[255, 0, 0, 0, 0, 0] for _ in range(1)],
                alpha=False,
            )
            from lvgl_ai.assets.image import ImageData

            fake = ImageData(
                width=2048,
                height=1,
                cf="RGB565",
                data=b"\x00\x00" * 2048,
                stride=4096,
                had_alpha=False,
            )
            with self.assertRaises(AssetError):
                render_image_header(
                    name="wide",
                    image=fake,
                    target_version="8.4",
                    source_path=png_path,
                    source_sha256="0" * 64,
                )

    def test_generate_image_and_manifest(self) -> None:
        with _tempdir() as tmp:
            root = Path(tmp) / "repo"
            app_dir = root / "user" / "app" / "demo"
            app_dir.mkdir(parents=True)
            png_path = app_dir / "logo.png"
            _write_png(png_path, _rgba_rows(), alpha=True)
            output = app_dir / "logo.h"
            manifest = app_dir / "assets.json"
            result = generate_image(
                options=ImageOptions(png_path, "ARGB8888"),
                name="logo",
                output_path=output,
                repo_root=root,
                target_version="9.6",
                force=False,
                dry_run=False,
                manifest_path=manifest,
            )
            self.assertEqual(result["status"], "created")
            self.assertTrue(output.is_file())
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], MANIFEST_SCHEMA)
            self.assertIn("logo", payload["assets"])
            self.assertNotIn(str(root), manifest.read_text(encoding="utf-8"))
            again = generate_image(
                options=ImageOptions(png_path, "ARGB8888"),
                name="logo",
                output_path=output,
                repo_root=root,
                target_version="9.6",
                force=False,
                dry_run=False,
                manifest_path=manifest,
            )
            self.assertEqual(again["status"], "unchanged")


class FontTest(unittest.TestCase):
    @unittest.skipUnless(FONT.is_file(), "LVGL test font is unavailable")
    def test_rasterize_and_render(self) -> None:
        data = rasterize_font(
            FontOptions(
                font_path=FONT,
                size=16,
                bpp=4,
                codepoints=tuple(range(0x20, 0x7F)),
            )
        )
        self.assertEqual(len(data.glyphs), 95)
        self.assertGreater(data.line_height, 0)
        self.assertGreaterEqual(data.base_line, 0)
        self.assertGreater(data.total_bitmap_bytes, 0)
        text = render_font_header(
            name="test_font_16",
            data=data,
            target_version="9.6",
            source_path=FONT,
            source_sha256="0" * 64,
            face_index=0,
            size=16,
        )
        self.assertIn("LVGL_VERSION_MAJOR == 8", text)
        self.assertIn("LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4", text)
        self.assertIn("LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6", text)
        self.assertIn("LV_FONT_KERNING_NONE", text)
        self.assertIn("LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY", text)
        self.assertNotIn(str(FONT), text)
        self.assertNotIn(str(Path.home()), text)

    @unittest.skipUnless(FONT.is_file(), "LVGL test font is unavailable")
    def test_bpp_changes_bitmap_size(self) -> None:
        codepoints = tuple(range(0x20, 0x5F))
        sizes = {}
        for bpp in (1, 4, 8):
            data = rasterize_font(
                FontOptions(font_path=FONT, size=16, bpp=bpp, codepoints=codepoints)
            )
            sizes[bpp] = data.total_bitmap_bytes
        self.assertLess(sizes[1], sizes[4])
        self.assertLess(sizes[4], sizes[8])

    @unittest.skipUnless(FONT.is_file(), "LVGL test font is unavailable")
    def test_bpp8_header_requires_lvgl_93(self) -> None:
        data = rasterize_font(
            FontOptions(
                font_path=FONT,
                size=16,
                bpp=8,
                codepoints=(ord("A"),),
            )
        )
        text = render_font_header(
            name="bpp8_font_16",
            data=data,
            target_version="9.6",
            source_path=FONT,
            source_sha256="0" * 64,
            face_index=0,
            size=16,
        )
        self.assertIn("LVGL_VERSION_MINOR < 3", text)
        self.assertIn("not supported before LVGL 9.3", text)

    @unittest.skipUnless(FONT.is_file(), "LVGL test font is unavailable")
    def test_bpp8_rejected_for_lvgl_91(self) -> None:
        with _tempdir() as tmp:
            with self.assertRaises(AssetError) as context:
                generate_font(
                    options=FontOptions(
                        font_path=FONT,
                        size=16,
                        bpp=8,
                        codepoints=(ord("A"),),
                    ),
                    name="bad_bpp8",
                    output_path=Path(tmp) / "bad_bpp8.h",
                    repo_root=Path(tmp),
                    target_version="9.1",
                    force=False,
                    dry_run=False,
                    manifest_path=None,
                )
        self.assertIn("8 bpp", str(context.exception))

    @unittest.skipUnless(FONT.is_file(), "LVGL test font is unavailable")
    def test_missing_glyph_is_reported(self) -> None:
        data = rasterize_font(
            FontOptions(
                font_path=FONT,
                size=16,
                bpp=4,
                codepoints=(ord("A"), 0x10FFFF),
            )
        )
        self.assertIn(0x10FFFF, data.missing)

    @unittest.skipUnless(CJK_FONT.is_file(), "CJK test font is unavailable")
    def test_cjk_glyphs(self) -> None:
        data = rasterize_font(
            FontOptions(
                font_path=CJK_FONT,
                size=16,
                bpp=4,
                codepoints=(ord("你"), ord("好")),
            )
        )
        self.assertEqual(len(data.glyphs), 2)
        self.assertEqual([glyph.code for glyph in data.glyphs], [ord("你"), ord("好")])

    @unittest.skipUnless(FONT.is_file(), "LVGL test font is unavailable")
    def test_generated_header_compiles(self) -> None:
        gcc = shutil.which("gcc")
        if not gcc or not SDK_96.is_dir() or not SRC_84.is_dir():
            self.skipTest("gcc or LVGL trees are unavailable")
        data = rasterize_font(
            FontOptions(
                font_path=FONT,
                size=16,
                bpp=4,
                codepoints=tuple(range(0x20, 0x7F)),
            )
        )
        text = render_font_header(
            name="compile_font_16",
            data=data,
            target_version="9.6",
            source_path=FONT,
            source_sha256="0" * 64,
            face_index=0,
            size=16,
        )
        with _tempdir() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "font.h").write_text(text, encoding="utf-8")
            (tmp_path / "use.c").write_text(
                '#include "font.h"\n'
                "const lv_font_t * use_font(void) { return &compile_font_16; }\n",
                encoding="utf-8",
            )
            common = [
                gcc,
                "-fsyntax-only",
                "-std=gnu11",
                "-Wall",
                "-Wextra",
                "-DLV_CONF_INCLUDE_SIMPLE",
                "-DLV_KCONFIG_IGNORE",
                "-DLV_LVGL_H_INCLUDE_SIMPLE",
                f"-I{tmp_path}",
            ]
            result = subprocess.run(
                common
                + [f"-I{SDK_96}", f"-I{SDK_96 / 'include'}", f"-I{SDK_96 / 'include' / 'lvgl'}"]
                + [str(tmp_path / "use.c")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(
                common
                + [
                    "-DLVGL_MAJOR_8=1",
                    f"-I{REPO_ROOT / 'core' / 'engine'}",
                    f"-I{SRC_84}",
                    f"-I{SRC_84 / 'src'}",
                    str(tmp_path / "use.c"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


class CliTest(unittest.TestCase):
    def _run(self, *args: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = assets_cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_doctor_json(self) -> None:
        code, out, err = self._run("doctor", "--json")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["freetype"], "2.13.2")

    def test_help_from_other_directory(self) -> None:
        with _tempdir() as tmp:
            result = subprocess.run(
                [sys.executable, "-I", str(ASSETS_PY), "font", "--help"],
                cwd=tmp,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--font", result.stdout)

    def test_image_dry_run_and_write(self) -> None:
        with _tempdir() as tmp:
            root = Path(tmp) / "repo"
            app_dir = root / "user" / "app" / "demo"
            app_dir.mkdir(parents=True)
            png_path = app_dir / "logo.png"
            _write_png(png_path, _rgba_rows(), alpha=True)
            out_path = app_dir / "logo.h"
            code, out, err = self._run(
                "image",
                "--repo-root",
                str(root),
                "--app",
                "demo",
                "--input",
                str(png_path),
                "--output",
                str(out_path),
                "--dry-run",
                "--json",
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["status"], "dry-run")
            self.assertFalse(out_path.exists())
            code, out, err = self._run(
                "image",
                "--repo-root",
                str(root),
                "--app",
                "demo",
                "--input",
                str(png_path),
                "--output",
                str(out_path),
                "--json",
            )
            self.assertEqual(code, 0, err)
            self.assertTrue(out_path.is_file())
            self.assertTrue((app_dir / "assets.json").is_file())

    def test_missing_app_is_an_error(self) -> None:
        with _tempdir() as tmp:
            root = Path(tmp) / "repo"
            (root / "user" / "app").mkdir(parents=True)
            code, _out, err = self._run(
                "font",
                "--repo-root",
                str(root),
                "--app",
                "missing",
                "--font",
                str(FONT),
                "--output",
                str(root / "x.h"),
            )
            self.assertEqual(code, 1)
            self.assertIn("app not found", err)


class ManifestTest(unittest.TestCase):
    def test_merge_and_conflict(self) -> None:
        with _tempdir() as tmp:
            manifest = Path(tmp) / "assets.json"
            merge_manifest_entry(
                manifest,
                {
                    "kind": "image",
                    "name": "logo",
                    "output": "logo.h",
                    "status": "generated",
                },
                target_lvgl="9.6",
            )
            merge_manifest_entry(
                manifest,
                {
                    "kind": "font",
                    "name": "text",
                    "output": "text.h",
                    "status": "generated",
                },
                target_lvgl="9.6",
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(set(payload["assets"]), {"logo", "text"})
            with self.assertRaises(AssetError):
                merge_manifest_entry(
                    manifest,
                    {"kind": "font", "name": "logo", "output": "logo.h"},
                    target_lvgl="9.6",
                )

    def test_write_if_changed(self) -> None:
        with _tempdir() as tmp:
            path = Path(tmp) / "x.h"
            self.assertEqual(write_if_changed(path, "one"), "created")
            self.assertEqual(write_if_changed(path, "one"), "unchanged")
            with self.assertRaises(AssetError):
                write_if_changed(path, "two")
            self.assertEqual(write_if_changed(path, "two", force=True), "updated")


class IdentifierTest(unittest.TestCase):
    def test_sanitize_identifier(self) -> None:
        self.assertEqual(sanitize_identifier("my-font"), "my_font")
        self.assertEqual(sanitize_identifier("16font"), "asset_16font")
        self.assertEqual(sanitize_identifier("static"), "asset_static")
        self.assertEqual(sanitize_identifier("---"), "asset")


if __name__ == "__main__":
    unittest.main(verbosity=2)
