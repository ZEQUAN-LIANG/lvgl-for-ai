import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import asset_plan


def write_png(path, width, height):
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    row = b"\x00" + b"\x00\x00\x00" * width
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    )
    png += chunk(b"IDAT", zlib.compress(row * height, 9))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)


class AssetPlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "probe_app"
        self.assets = self.source / "assets"
        self.assets.mkdir(parents=True)

    def _write_fake_ezip(self, *, symbol=True):
        script = self.root / ("fake_ezip.py" if symbol else "fake_ezip_bad.py")
        c_source = (
            "const lv_image_dsc_t {name} = { .data_size = 4096 };"
            if symbol
            else "const lv_image_dsc_t other_symbol = { .data_size = 1 };"
        )
        script.write_text(
            "import pathlib\n"
            "import sys\n"
            "\n"
            "png = pathlib.Path(sys.argv[sys.argv.index('-convert') + 1])\n"
            "output = pathlib.Path('output')\n"
            "output.mkdir(exist_ok=True)\n"
            f"c_source = {c_source!r}\n"
            "text = c_source.replace('{name}', png.stem)\n"
            "(output / f'{png.stem}.c').write_text(text, encoding='utf-8')\n",
            encoding="utf-8",
        )
        return [sys.executable, str(script)]

    def _write_manifest(self, assets, *, cache=None, local_header=""):
        payload = {
            "schema": "lvgl-ai-assets-v1",
            "local_header": local_header,
            "assets": assets,
        }
        if cache is not None:
            payload["cache"] = cache
        (self.source / "assets.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def _plan(self, *, ezip_tool=None):
        return asset_plan.plan_assets(
            self.source,
            {"ezip_chip": "sf52x"},
            ezip_tool=ezip_tool or self._write_fake_ezip(),
        )

    @staticmethod
    def _spec(name, **overrides):
        spec = {
            "file": f"{name}.png",
            "mode": "raw",
            "placement": "psram",
            "transform": "rotate",
        }
        spec.update(overrides)
        return spec

    def test_missing_manifest_defaults_each_png_to_ezip_flash(self):
        write_png(self.assets / "probe.png", 12, 8)
        plan = self._plan()
        self.assertIsInstance(plan, asset_plan.AssetPlan)
        self.assertTrue(plan.has_assets)
        self.assertIsInstance(plan.records, list)
        self.assertIsInstance(plan.files, dict)
        self.assertIsInstance(plan.cache, dict)
        self.assertEqual(plan.local_header, "")
        self.assertEqual(len(plan.records), 1)
        record = plan.records[0]
        self.assertEqual(record["name"], "probe")
        self.assertEqual(record["file"], "probe.png")
        self.assertEqual(record["mode"], "ezip")
        self.assertEqual(record["placement"], "flash")
        self.assertEqual(record["transform"], "none")
        self.assertFalse(record["hot"])
        self.assertEqual((record["width"], record["height"]), (12, 8))
        self.assertEqual(record["size"], 4096)
        self.assertIn("src/ezip/probe.c", plan.files)
        self.assertIn("src/app/probe_app/assets.h", plan.files)
        self.assertIn("src/app/probe_app/assets.c", plan.files)
        self.assertEqual(
            plan.cache,
            {
                "image_cache_psram_size": 0,
                "image_cache_sram_size": 0,
                "rotate_mem": None,
                "lv_cache_def_size": 0,
                "lv_image_header_cache_cnt": 0,
            },
        )

    def test_no_assets_returns_empty_plan(self):
        plan = self._plan()
        self.assertFalse(plan.has_assets)
        self.assertEqual(plan.records, [])
        self.assertEqual(plan.files, {})
        self.assertEqual(plan.local_header, "")
        self.assertEqual(plan.cache["image_cache_psram_size"], 0)

    def test_raw_hot_asset_generates_size_macros_and_cache(self):
        write_png(self.assets / "probe.png", 37, 19)
        self._write_manifest(
            {"probe": self._spec("probe")}, local_header="probe_assets.h"
        )
        plan = self._plan()
        record = plan.records[0]
        self.assertTrue(record["hot"])
        self.assertEqual((record["width"], record["height"]), (37, 19))
        header = plan.files["src/app/probe_app/assets.h"].decode("utf-8")
        self.assertIn("#define PROBE_W 37", header)
        self.assertIn("#define PROBE_H 19", header)
        self.assertIn("extern const lv_image_dsc_t probe_raw;", header)
        self.assertIn("#define probe (*app_asset_probe())", header)
        self.assertIn('#include "probe_assets.h"', header)
        source = plan.files["src/app/probe_app/assets.c"].decode("utf-8")
        self.assertIn("app_cache_copy_alloc(&probe_raw, ROTATE_MEM)", source)
        self.assertEqual(plan.local_header, "probe_assets.h")
        self.assertEqual(
            plan.cache,
            {
                "image_cache_psram_size": 8192,
                "image_cache_sram_size": 0,
                "rotate_mem": "psram",
                "lv_cache_def_size": 0,
                "lv_image_header_cache_cnt": 0,
            },
        )

    def test_cache_overrides_replace_computed_sizes(self):
        write_png(self.assets / "probe.png", 37, 19)
        self._write_manifest(
            {"probe": self._spec("probe")},
            cache={
                "image_cache_psram_size": 524288,
                "image_cache_sram_size": 16384,
                "rotate_mem": "sram",
                "lv_cache_def_size": 1024,
                "lv_image_header_cache_cnt": 7,
            },
        )
        plan = self._plan()
        self.assertEqual(plan.cache["image_cache_psram_size"], 524288)
        self.assertEqual(plan.cache["image_cache_sram_size"], 16384)
        self.assertEqual(plan.cache["rotate_mem"], "sram")
        self.assertEqual(plan.cache["lv_cache_def_size"], 1024)
        self.assertEqual(plan.cache["lv_image_header_cache_cnt"], 7)

    def test_broken_png_is_rejected(self):
        (self.assets / "probe.png").write_bytes(b"not a png")
        with self.assertRaises(asset_plan.ExportError) as raised:
            self._plan()
        self.assertEqual(raised.exception.code, "asset_invalid")

    def test_zero_size_png_is_rejected(self):
        write_png(self.assets / "probe.png", 0, 0)
        with self.assertRaises(asset_plan.ExportError) as raised:
            self._plan()
        self.assertEqual(raised.exception.code, "asset_invalid")

    def test_uppercase_name_collision_is_rejected(self):
        write_png(self.assets / "probe.png", 1, 1)
        write_png(self.assets / "PROBE.png", 1, 1)
        self._write_manifest(
            {
                "probe": self._spec("probe"),
                "PROBE": self._spec("PROBE"),
            }
        )
        with self.assertRaises(asset_plan.ExportError) as raised:
            self._plan()
        self.assertEqual(raised.exception.code, "asset_macro_conflict")
        self.assertEqual(raised.exception.detail["macro"], "PROBE")
        self.assertEqual(raised.exception.detail["names"], ["probe", "PROBE"])

    def test_unsupported_transform_is_rejected(self):
        write_png(self.assets / "probe.png", 1, 1)
        self._write_manifest(
            {"probe": self._spec("probe", transform="flip")}
        )
        with self.assertRaises(asset_plan.ExportError) as raised:
            self._plan()
        self.assertEqual(raised.exception.code, "asset_invalid")
        self.assertEqual(raised.exception.detail["transform"], "flip")

    def test_ezip_output_without_symbol_is_rejected(self):
        write_png(self.assets / "probe.png", 1, 1)
        self._write_manifest(
            {
                "probe": {
                    "file": "probe.png",
                    "mode": "ezip",
                    "placement": "flash",
                    "transform": "none",
                }
            }
        )
        with self.assertRaises(asset_plan.ExportError) as raised:
            self._plan(ezip_tool=self._write_fake_ezip(symbol=False))
        self.assertEqual(raised.exception.code, "ezip_symbol_missing")


if __name__ == "__main__":
    unittest.main()
