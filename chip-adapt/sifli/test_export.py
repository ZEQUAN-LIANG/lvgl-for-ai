import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

_spec = importlib.util.spec_from_file_location("sifli_export", HERE / "export.py")
sifli_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sifli_export)


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
