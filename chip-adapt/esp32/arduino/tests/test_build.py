from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parents[1]
if str(ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTER_DIR))

import build  # noqa: E402


class AdapterFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()
        (self.app_dir / "perf_monitor.c").write_text(
            "int app(void) { return 0; }\n", encoding="utf-8"
        )
        (self.app_dir / "perf_monitor.h").write_text(
            '#include "lvgl.h"\n', encoding="utf-8"
        )
        (self.app_dir / "perf_protocol.c").write_text(
            "int protocol(void) { return 0; }\n", encoding="utf-8"
        )
        (self.app_dir / "perf_protocol.h").write_text(
            "#pragma once\n", encoding="utf-8"
        )
        (self.app_dir / "perf_font_num_8.h").write_text(
            '#include "lvgl/lvgl.h"\n', encoding="utf-8"
        )
        (self.app_dir / "README.md").write_text("ignored\n", encoding="utf-8")

        self.lvgl_dir = self.root / "lvgl"
        self.lvgl_dir.mkdir()
        (self.lvgl_dir / "lvgl.h").write_text("/* lvgl */\n", encoding="utf-8")
        (self.lvgl_dir / "lvgl_private.h").write_text(
            "/* private */\n", encoding="utf-8"
        )
        (self.lvgl_dir / "lv_version.h").write_text(
            "#define LVGL_VERSION_MAJOR 9\n", encoding="utf-8"
        )
        (self.lvgl_dir / "library.properties").write_text(
            "name=lvgl\n", encoding="utf-8"
        )
        (self.lvgl_dir / "LICENCE.txt").write_text(
            "license\n", encoding="utf-8"
        )
        (self.lvgl_dir / "src").mkdir()
        (self.lvgl_dir / "src" / "lvgl.h").write_text(
            "/* src */\n", encoding="utf-8"
        )
        (self.lvgl_dir / "include").mkdir()
        (self.lvgl_dir / "include" / "lvgl").mkdir()
        (self.lvgl_dir / "include" / "lvgl" / "lvgl.h").write_text(
            "/* include */\n", encoding="utf-8"
        )

        self.vendor_zip = self.root / "vendor.zip"
        with zipfile.ZipFile(self.vendor_zip, "w") as archive:
            archive.writestr(
                "Arduino/examples/LVGL_Arduino/Display_ST7789.cpp",
                "void lcd_init(void) {}\n",
            )
            archive.writestr(
                "Arduino/examples/LVGL_Arduino/Display_ST7789.h",
                "void lcd_init(void);\n",
            )

        self.out_dir = self.root / "out"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def export(self, **kwargs):
        return build.prepare_workspace(
            out_dir=kwargs.pop("out_dir", self.out_dir),
            app_dir=self.app_dir,
            lvgl_dir=self.lvgl_dir,
            vendor_zip=self.vendor_zip,
            **kwargs,
        )


class ExportTest(AdapterFixture):
    def test_export_layout_and_include_patch(self) -> None:
        result = self.export(force=True)
        sketch = Path(result["sketch_dir"])
        self.assertTrue((sketch / "perf_c6.ino").is_file())
        self.assertTrue((sketch / "ble_uart.h").is_file())
        self.assertTrue((sketch / "ble_uart.cpp").is_file())
        self.assertTrue((sketch / "perf_monitor.c").is_file())
        self.assertTrue((sketch / "Display_ST7789.cpp").is_file())
        self.assertTrue((sketch / "perf_font_num_8.h").is_file())
        self.assertTrue(
            (Path(result["libraries_dir"]) / "lvgl" / "lvgl.h").is_file()
        )
        ino = (sketch / "perf_c6.ino").read_text(encoding="utf-8")
        self.assertIn("ble_uart_begin", ino)
        self.assertIn("ble_uart_pop_line", ino)
        self.assertIn("handle_line", ino)
        ble = (sketch / "ble_uart.cpp").read_text(encoding="utf-8")
        self.assertIn("6E400001-B5A3-F393-E0A9-E50E24DCCA9E", ble)
        self.assertIn("6E400002-B5A3-F393-E0A9-E50E24DCCA9E", ble)
        self.assertIn("6E400003-B5A3-F393-E0A9-E50E24DCCA9E", ble)
        header = (sketch / "ble_uart.h").read_text(encoding="utf-8")
        self.assertIn("LVGL-C6-PERF", header)
        font_header = (sketch / "perf_font_num_8.h").read_text(
            encoding="utf-8"
        )
        self.assertIn('#include "lvgl.h"', font_header)
        self.assertNotIn("lvgl/lvgl.h", font_header)
        self.assertFalse((sketch / "README.md").exists())

    def test_force_removes_stale_generated_files(self) -> None:
        self.export(force=True)
        stale = self.out_dir / build.SKETCH_NAME / "stale.h"
        stale.write_text("stale\n", encoding="utf-8")
        self.export(force=True)
        self.assertFalse(stale.exists())

    def test_existing_output_updates_in_place(self) -> None:
        self.export(force=True)
        app_file = self.out_dir / build.SKETCH_NAME / "perf_monitor.c"
        app_file.write_text("stale\n", encoding="utf-8")
        result = self.export(force=False)
        self.assertIn("int app(void)", app_file.read_text(encoding="utf-8"))
        self.assertTrue(result["files"])

    def test_incremental_export_keeps_unchanged_files(self) -> None:
        self.export(force=True)
        app_file = self.out_dir / build.SKETCH_NAME / "perf_monitor.c"
        before = app_file.stat().st_mtime_ns
        build_dir = self.out_dir / "build"
        build_dir.mkdir()
        marker = build_dir / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        result = self.export(force=False)
        self.assertEqual(app_file.stat().st_mtime_ns, before)
        self.assertTrue(marker.is_file())
        self.assertEqual(result["files"], [])

    def test_dry_run_does_not_create_output(self) -> None:
        result = self.export(force=True, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.out_dir.exists())

    def test_patch_lvgl_include(self) -> None:
        self.assertEqual(
            build.patch_lvgl_include('#include "lvgl/lvgl.h"'),
            '#include "lvgl.h"',
        )
        self.assertEqual(
            build.patch_lvgl_include("#include <lvgl/lvgl.h>"),
            "#include <lvgl.h>",
        )


class CommandTest(AdapterFixture):
    def test_build_command_uses_sketch_directory(self) -> None:
        command = build.build_command(
            arduino_cli="arduino-cli",
            out_dir=self.out_dir,
            fqbn="esp32:esp32:esp32c6",
        )
        self.assertIn(str(self.out_dir / build.SKETCH_NAME), command)
        self.assertIn("--libraries", command)
        self.assertIn(
            "compiler.c.extra_flags=" + build.BUILD_FLAGS, command
        )

    def test_build_dry_run_needs_no_arduino_cli(self) -> None:
        self.export(force=True)
        result = build.build_workspace(
            out_dir=self.out_dir,
            arduino_cli=None,
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["command"][0], "arduino-cli")

    def test_flash_dry_run_needs_no_image(self) -> None:
        result = build.flash_workspace(
            out_dir=self.out_dir,
            port="COM99",
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])
        self.assertIn("host.py", " ".join(result["command"]))
        self.assertIn("COM99", result["command"])

    def test_flash_job_result_shapes(self) -> None:
        self.assertTrue(
            build._flash_ok({"status": "ok", "result": {"ok": True}})
        )
        self.assertTrue(build._flash_ok({"ok": True}))
        self.assertFalse(build._flash_ok({"status": "error"}))
        self.assertFalse(build._flash_ok({"status": "ok", "result": {"ok": False}}))


if __name__ == "__main__":
    unittest.main()
