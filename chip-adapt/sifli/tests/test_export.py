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

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]

_spec = importlib.util.spec_from_file_location(
    "sifli_export", HERE / "export.py"
)
sifli_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sifli_export)


def write_png(path, width, height):
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)
        )

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
        self.profiles = self.root / "chip-adapt" / "sifli" / "apps"
        self.profiles.mkdir(parents=True)
        for name in ("app.c", "app.h", "app_registry_lookup.h",
                     "lvgl_compat.h"):
            shutil.copy2(REPO / "user" / "app" / name, self.user_app / name)
        watch = self.user_app / "sift_watch"
        watch.mkdir()
        for name in ("sift_watch.c", "sift_watch.h"):
            shutil.copy2(
                REPO / "user" / "app" / "sift_watch" / name, watch / name
            )
        dimensions = {
            "watch_bg": (390, 450),
            "watch_ring": (280, 280),
            "watch_hour": (12, 96),
            "watch_minute": (8, 136),
            "watch_second": (8, 160),
        }
        assets = watch / "assets"
        assets.mkdir()
        for name, (width, height) in dimensions.items():
            write_png(assets / f"{name}.png", width, height)
        manifest = {
            "schema": "lvgl-verify-loop-sifli-app-v1",
            "local_header": "watch_assets.h",
            "assets": {
                name: {
                    "file": f"{name}.png",
                    "format": "rgb565",
                    "mode": "ezip" if name == "watch_bg" else "raw",
                    "placement": "flash" if name == "watch_bg" else "psram",
                    "transform": "none" if name == "watch_bg" else "rotate",
                }
                for name in dimensions
            },
            "cache": {
                "image_cache_psram_size": 524288,
                "image_cache_sram_size": 0,
                "rotate_mem": "psram",
                "lv_cache_def_size": 0,
                "lv_image_header_cache_cnt": 0,
            },
        }
        (self.profiles / "sift_watch.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        local_header = "\n".join(
            line
            for name, (width, height) in dimensions.items()
            for line in (
                f"#define {name.upper()}_W {width}",
                f"#define {name.upper()}_H {height}",
            )
        )
        (watch / "watch_assets.h").write_text(
            local_header + "\n", encoding="utf-8"
        )
        self.output = self.root / "exported"
        self.ezip = self._write_fake_ezip()

    def _write_fake_ezip(self):
        script = self.root / "fake_ezip.py"
        script.write_text(
            "import pathlib\n"
            "import sys\n"
            "\n"
            "png = pathlib.Path(sys.argv[sys.argv.index('-convert') + 1])\n"
            "output = pathlib.Path('output')\n"
            "output.mkdir(exist_ok=True)\n"
            "(output / f'{png.stem}.c').write_text(\n"
            "    f'const lv_image_dsc_t {png.stem} = {{ .data_size = 4096 }};\\n',\n"
            "    encoding='utf-8',\n"
            ")\n",
            encoding="utf-8",
        )
        return [sys.executable, str(script)]

    def _export(self, *args, **kwargs):
        kwargs.setdefault("ezip_tool", self.ezip)
        return sifli_export.export_app(self.root, *args, **kwargs)

    def _declare(self, name, **overrides):
        manifest = self.profiles / "sift_watch.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        spec = {
            "file": f"{name}.png",
            "mode": "raw",
            "placement": "flash",
            "transform": "none",
        }
        spec.update(overrides)
        payload["assets"][name] = spec
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_sources_are_copied_without_version_rewrites(self):
        result = self._export("sift_watch", output_dir=self.output)
        self.assertTrue(result["ok"])
        ported = (
            self.output / "src" / "app" / "sift_watch" / "sift_watch.c"
        ).read_text(encoding="utf-8")
        self.assertTrue(ported.startswith('#include "lvgl_verify_loop_sdk.h"'))
        self.assertNotIn("lvgl_verify_loop_94_compat.h", ported)
        self.assertIn("LVGL_VERSION_MINOR >= 4", ported)
        self.assertNotIn("LVGL_VERSION_MINOR >= 6", ported)
        original = (
            REPO / "user" / "app" / "sift_watch" / "sift_watch.c"
        ).read_text(encoding="utf-8")
        self.assertEqual(ported.split("\n", 1)[1], original)

        header = (self.output / "src" / "app" / "lvgl_verify_loop_sdk.h").read_text(
            encoding="utf-8"
        )
        self.assertIn("LVGL_VERIFY_LOOP_EZIP_ASSETS", header)
        self.assertFalse(
            (self.output / "src" / "app" / "lvgl_verify_loop_94_compat.h").exists()
        )

    def test_images_follow_asset_manifest(self):
        result = self._export("sift_watch", output_dir=self.output)
        self.assertIn("src/ezip/watch_bg.c", result["files"])
        self.assertIn("src/raw/watch_ring.c", result["files"])
        self.assertIn("src/raw/watch_hour.c", result["files"])
        self.assertNotIn("src/ezip/watch_ring.c", result["files"])
        header = (
            self.output / "src" / "app" / "sift_watch" / "assets.h"
        ).read_text(encoding="utf-8")
        self.assertIn("extern const lv_image_dsc_t watch_bg;", header)
        self.assertIn("extern const lv_image_dsc_t watch_hour_raw;", header)
        self.assertIn("#define watch_hour (*app_asset_watch_hour())", header)
        source = (
            self.output / "src" / "app" / "sift_watch" / "assets.c"
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

    def test_export_manifest_records_png_dimensions(self):
        self._export("sift_watch", output_dir=self.output)
        manifest = json.loads(
            (self.output / "export.json").read_text(encoding="utf-8")
        )
        dimensions = {
            record["name"]: (record["width"], record["height"])
            for record in manifest["assets"]
        }
        self.assertEqual(
            dimensions,
            {
                "watch_bg": (390, 450),
                "watch_ring": (280, 280),
                "watch_hour": (12, 96),
                "watch_minute": (8, 136),
                "watch_second": (8, 160),
            },
        )

    def test_export_documents_the_lvgl_94_baseline(self):
        result = self._export("sift_watch", output_dir=self.output)
        readme = (self.output / "README.md").read_text(encoding="utf-8")
        self.assertIn("--lvgl 9.4", readme)
        self.assertIn("chip-adapt/exports/sift_watch/src/app", readme)
        cli_commands = [
            command
            for command in result["commands"]
            if "console/entrypoints/cli.py" in command
        ]
        self.assertEqual(len(cli_commands), 1)
        self.assertIn("--lvgl 9.4", cli_commands[0])

    def test_runtime_verification_points_the_tool_at_the_exported_copy(self):
        # The variable name must match what the control layer reads
        # (paths.apps_dir_from_env); a near-miss verifies the wrong sources.
        result = self._export("sift_watch", output_dir=self.output)
        readme = (self.output / "README.md").read_text(encoding="utf-8")
        commands = [
            command
            for command in result["commands"]
            if "console/entrypoints/cli.py" in command
        ]
        for text in (readme, *commands):
            self.assertIn("LVGL_VERIFY_LOOP_APPS_DIR=", text)
            self.assertNotIn("USER_APP_DIR", text)

    def test_default_output_uses_exports_zone(self):
        exports = self.root / "chip-adapt" / "exports"
        with mock.patch.object(sifli_export.layout, "EXPORTS_DIR", exports):
            result = self._export("sift_watch")
        self.assertEqual(Path(result["output_dir"]), exports / "sift_watch")
        self.assertTrue((exports / "sift_watch" / "project").is_dir())

    def test_export_copy_is_self_contained(self):
        self._export("sift_watch", output_dir=self.output)
        app_dir = self.output / "src" / "app" / "sift_watch"
        self.assertTrue((app_dir / "watch_assets.h").is_file())
        roots = (str(self.root.resolve()), str(REPO.resolve()))
        for path in self.output.rglob("*"):
            self.assertFalse(path.is_symlink(), f"symlink in export: {path}")
            if path.is_file():
                data = path.read_bytes()
                for root in roots:
                    self.assertNotIn(root.encode("utf-8"), data, path)

    def test_generated_assets_header_exposes_size_macros_and_symbols(self):
        self._export("sift_watch", output_dir=self.output)
        app_dir = self.output / "src" / "app" / "sift_watch"
        header = (app_dir / "assets.h").read_text(encoding="utf-8")
        sdk_branch, local_branch = header.split("#else", 1)
        local_header = (app_dir / "watch_assets.h").read_text(encoding="utf-8")
        manifest = json.loads(
            (self.output / "export.json").read_text(encoding="utf-8")
        )
        dimensions = {
            "watch_bg": (390, 450),
            "watch_ring": (280, 280),
            "watch_hour": (12, 96),
            "watch_minute": (8, 136),
            "watch_second": (8, 160),
        }
        self.assertEqual(
            {record["name"] for record in manifest["assets"]}, set(dimensions)
        )
        by_name = {record["name"]: record for record in manifest["assets"]}
        for name, (width, height) in dimensions.items():
            spec = by_name[name]
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

    def test_size_macros_follow_png_dimensions(self):
        write_png(
            self.user_app / "sift_watch" / "assets" / "watch_probe.png", 37, 19
        )
        self._declare("watch_probe")
        self._export("sift_watch", output_dir=self.output)
        header = (
            self.output / "src" / "app" / "sift_watch" / "assets.h"
        ).read_text(encoding="utf-8")
        self.assertIn("#define WATCH_PROBE_W 37", header)
        self.assertIn("#define WATCH_PROBE_H 19", header)

    def test_broken_png_is_rejected(self):
        assets = self.user_app / "sift_watch" / "assets"
        (assets / "watch_broken.png").write_bytes(b"not a png")
        self._declare("watch_broken")
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("sift_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "asset_invalid")
        self.assertFalse(self.output.exists())

    def test_zero_size_png_is_rejected(self):
        write_png(
            self.user_app / "sift_watch" / "assets" / "watch_empty.png", 0, 0
        )
        self._declare("watch_empty")
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("sift_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "asset_invalid")
        self.assertFalse(self.output.exists())

    def test_asset_names_must_not_collide_after_uppercasing(self):
        self._declare("watch_probe")
        self._declare("WATCH_PROBE")
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("sift_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "asset_macro_conflict")
        self.assertEqual(raised.exception.detail["macro"], "WATCH_PROBE")
        self.assertEqual(
            raised.exception.detail["names"], ["watch_probe", "WATCH_PROBE"]
        )
        self.assertFalse(self.output.exists())

    def test_template_kconfig_does_not_redefine_sdk_cache_symbols(self):
        template = (
            REPO
            / "chip-adapt"
            / "sifli"
            / "templates"
            / "project"
            / "Kconfig.proj"
        ).read_text(encoding="utf-8")
        self.assertNotIn("ROTATE_MEM_", template)
        self.assertNotIn("IMAGE_CACHE_", template)
        self.assertIn("CUSTOM_MEM_MAP", template)

    def test_sconscript_compiles_raw_sources_and_exposes_their_include_dir(
        self,
    ):
        self._export("sift_watch", output_dir=self.output)
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
        manifest = self.profiles / "sift_watch.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["assets"]["watch_bg"]["transform"] = "rotate"
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("sift_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "asset_transform_conflict")
        self.assertFalse(self.output.exists())

    def test_unsupported_api_is_reported(self):
        name = "coffee"
        bad = self.user_app / name
        bad.mkdir()
        (bad / "app.json").write_text(
            json.dumps({"entry": "bad_create"}), encoding="utf-8"
        )
        (bad / "bad_ui.c").write_text(
            "void bad(lv_obj_t * obj) { lv_obj_set_clickable(obj, false); }\n",
            encoding="utf-8",
        )
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export(name, output_dir=self.output)
        self.assertEqual(raised.exception.code, "unsupported_api")
        self.assertFalse(self.output.exists())

    def test_dry_run_writes_nothing(self):
        result = self._export(
            "sift_watch", output_dir=self.output, dry_run=True
        )
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.output.exists())
        self.assertTrue(result["files"])

    def test_conflict_and_force(self):
        self._export("sift_watch", output_dir=self.output)
        with self.assertRaises(sifli_export.ExportError) as raised:
            self._export("sift_watch", output_dir=self.output)
        self.assertEqual(raised.exception.code, "app_conflict")
        result = self._export("sift_watch", output_dir=self.output, force=True)
        self.assertTrue(result["updated"])


if __name__ == "__main__":
    unittest.main()
