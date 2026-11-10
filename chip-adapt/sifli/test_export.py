import importlib.util
import json
import shutil
import struct
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SDK_EZIP = REPO / "chip-adapt/sdk/sifli-sdk/tools/png2ezip/ezip.exe"

_spec = importlib.util.spec_from_file_location("sifli_export", HERE / "export.py")
sifli_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sifli_export)


def png_size(path):
    data = Path(path).read_bytes()
    return struct.unpack(">II", data[16:24])


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


class SifliExportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.user_app = self.root / "user" / "app"
        self.user_app.mkdir(parents=True)
        for name in ("app.c", "app.h", "lvgl_compat.h"):
            shutil.copy2(REPO / "user" / "app" / name, self.user_app / name)
        watch = self.user_app / "hspi_watch"
        watch.mkdir()
        shutil.copy2(
            REPO / "user" / "app" / "hspi_watch" / "hspi_watch.c",
            watch / "hspi_watch.c",
        )
        shutil.copy2(
            REPO / "user" / "app" / "hspi_watch" / "hspi_watch.h",
            watch / "hspi_watch.h",
        )
        shutil.copy2(
            REPO / "user" / "app" / "hspi_watch" / "assets.json",
            watch / "assets.json",
        )
        shutil.copytree(
            REPO / "user" / "app" / "hspi_watch" / "assets",
            watch / "assets",
        )
        self.output = self.root / "exported"

    def _export(self, *args, **kwargs):
        return sifli_export.export_app(self.root, *args, **kwargs)

    def test_sources_are_copied_without_version_rewrites(self):
        result = self._export("hspi_watch", output_dir=self.output)
        self.assertTrue(result["ok"])
        ported = (self.output / "src" / "app" / "hspi_watch" / "hspi_watch.c").read_text(
            encoding="utf-8"
        )
        self.assertTrue(ported.startswith('#include "lvgl_ai_sdk.h"'))
        self.assertNotIn("lvgl_ai_94_compat.h", ported)
        self.assertIn("LVGL_VERSION_MINOR >= 4", ported)
        self.assertNotIn("LVGL_VERSION_MINOR >= 6", ported)
        original = (
            REPO / "user" / "app" / "hspi_watch" / "hspi_watch.c"
        ).read_text(encoding="utf-8")
        self.assertEqual(ported.split("\n", 1)[1], original)

        header = (self.output / "src" / "app" / "lvgl_ai_sdk.h").read_text(
            encoding="utf-8"
        )
        self.assertIn("LVGL_AI_EZIP_ASSETS", header)
        self.assertFalse(
            (self.output / "src" / "app" / "lvgl_ai_94_compat.h").exists()
        )

    @unittest.skipUnless(
        (REPO / "chip-adapt/sdk/sifli-sdk/tools/png2ezip/ezip.exe").is_file(),
        "SiFli SDK is not downloaded",
    )
    def test_images_follow_asset_manifest(self):
        result = self._export("hspi_watch", output_dir=self.output)
        self.assertIn("src/ezip/watch_bg.c", result["files"])
        self.assertIn("src/raw/watch_ring.c", result["files"])
        self.assertIn("src/raw/watch_hour.c", result["files"])
        self.assertNotIn("src/ezip/watch_ring.c", result["files"])
        header = (
            self.output / "src" / "app" / "hspi_watch" / "assets.h"
        ).read_text(encoding="utf-8")
        self.assertIn("extern const lv_image_dsc_t watch_bg;", header)
        self.assertIn("extern const lv_image_dsc_t watch_hour_raw;", header)
        self.assertIn("#define watch_hour (*app_asset_watch_hour())", header)
        source = (
            self.output / "src" / "app" / "hspi_watch" / "assets.c"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "app_cache_copy_alloc(&watch_hour_raw, ROTATE_MEM)", source
        )
        proj = (self.output / "project" / "proj.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("CONFIG_IMAGE_CACHE_IN_PSRAM_SIZE=524288", proj)
        self.assertIn("CONFIG_ROTATE_MEM_IN_PSRAM=y", proj)
        self.assertIn("CONFIG_LV_CACHE_DEF_SIZE=0", proj)
        self.assertTrue((self.output / "export.json").is_file())

    @unittest.skipUnless(SDK_EZIP.is_file(), "SiFli SDK is not downloaded")
    def test_generated_assets_header_exposes_size_macros_and_symbols(self):
        self._export("hspi_watch", output_dir=self.output)
        header = (
            self.output / "src" / "app" / "hspi_watch" / "assets.h"
        ).read_text(encoding="utf-8")
        sdk_branch, local_branch = header.split("#else", 1)
        local_header = (
            REPO / "user" / "app" / "hspi_watch" / "watch_assets.h"
        ).read_text(encoding="utf-8")
        manifest = json.loads(
            (REPO / "user" / "app" / "hspi_watch" / "assets.json").read_text(
                encoding="utf-8"
            )
        )
        for name, spec in manifest["assets"].items():
            width, height = png_size(
                REPO / "user" / "app" / "hspi_watch" / "assets" / spec["file"]
            )
            macro = name.upper()
            self.assertRegex(sdk_branch, rf"(?m)^#define {macro}_W {width}$")
            self.assertRegex(sdk_branch, rf"(?m)^#define {macro}_H {height}$")
            self.assertIn(f"#define {macro}_W {width}", local_header)
            self.assertIn(f"#define {macro}_H {height}", local_header)
            if spec["mode"] == "raw" and spec["placement"] != "flash":
                self.assertIn(
                    f"extern const lv_image_dsc_t {name}_raw;", sdk_branch
                )
                self.assertIn(
                    f"#define {name} (*app_asset_{name}())", sdk_branch
                )
            else:
                self.assertIn(
                    f"extern const lv_image_dsc_t {name};", sdk_branch
                )
        self.assertIn("void app_assets_init(void);", sdk_branch)
        self.assertNotIn("watch_assets.h", sdk_branch)
        self.assertIn('#include "watch_assets.h"', local_branch)

    @unittest.skipUnless(SDK_EZIP.is_file(), "SiFli SDK is not downloaded")
    def test_size_macros_follow_png_dimensions(self):
        write_png(
            self.user_app / "hspi_watch" / "assets" / "watch_probe.png", 37, 19
        )
        manifest = self.user_app / "hspi_watch" / "assets.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["assets"]["watch_probe"] = {
            "file": "watch_probe.png",
            "mode": "raw",
            "placement": "flash",
            "transform": "none",
        }
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        self._export("hspi_watch", output_dir=self.output)
        header = (
            self.output / "src" / "app" / "hspi_watch" / "assets.h"
        ).read_text(encoding="utf-8")
        self.assertIn("#define WATCH_PROBE_W 37", header)
        self.assertIn("#define WATCH_PROBE_H 19", header)

    @unittest.skipUnless(SDK_EZIP.is_file(), "SiFli SDK is not downloaded")
    def test_sconscript_compiles_raw_sources_and_exposes_their_include_dir(
        self,
    ):
        self._export("hspi_watch", output_dir=self.output)
        src_dir = (self.output / "src").resolve()
        captured = self._run_sconscript(self.output / "src" / "SConscript")
        sources = {
            Path(path).resolve().relative_to(src_dir).as_posix()
            for path in captured["src"]
        }
        self.assertIn("raw/watch_ring.c", sources)
        self.assertIn("raw/watch_hour.c", sources)
        self.assertIn("ezip/watch_bg.c", sources)
        self.assertNotIn("app/sim_sifli.c", sources)
        include_dirs = {
            Path(path).resolve().relative_to(src_dir).as_posix()
            for path in captured["CPPPATH"]
        }
        self.assertIn("raw", include_dirs)

    @staticmethod
    def _run_sconscript(path):
        path = Path(path)
        captured = {}
        building = types.ModuleType("building")

        def define_group(name, src, **kwargs):
            captured.update({"name": name, "src": list(src), **kwargs})

        building.DefineGroup = define_group
        scope = {
            "__builtins__": __builtins__,
            "GetCurrentDir": lambda: str(path.parent),
            "Return": lambda value: captured.__setitem__("group", value),
        }
        with mock.patch.dict(sys.modules, {"building": building}):
            exec(
                compile(path.read_text(encoding="utf-8"), str(path), "exec"),
                scope,
            )
        return captured

    def test_ezip_transform_is_rejected(self):
        manifest = self.user_app / "hspi_watch" / "assets.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["assets"]["watch_bg"]["transform"] = "rotate"
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("hspi_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "asset_transform_conflict")
        self.assertFalse(self.output.exists())

    def test_unsupported_api_is_reported(self):
        bad = self.user_app / "coffee"
        bad.mkdir()
        (bad / "coffee_ui.c").write_text(
            "void bad(lv_obj_t * obj) { lv_obj_set_clickable(obj, false); }\n",
            encoding="utf-8",
        )
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("coffee", output_dir=self.output)
        self.assertEqual(raised.exception.code, "unsupported_api")
        self.assertFalse(self.output.exists())

    def test_dry_run_writes_nothing(self):
        result = self._export("hspi_watch", output_dir=self.output, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.output.exists())
        self.assertTrue(result["files"])

    def test_conflict_and_force(self):
        self._export("hspi_watch", output_dir=self.output)
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("hspi_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "app_conflict")
        result = self._export("hspi_watch", output_dir=self.output, force=True)
        self.assertTrue(result["updated"])


if __name__ == "__main__":
    unittest.main()
