from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import export_sdk


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class HeaderLayoutTest(unittest.TestCase):
    def test_96_copies_the_public_include_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            _write(source / "include" / "lvgl" / "lvgl.h")
            _write(source / "include" / "lvgl" / "lv_version.h")
            out = root / "sdk"
            include_dirs = export_sdk._copy_headers(source, out, "9.6")
            self.assertEqual(
                include_dirs,
                [".", "include", "include/lvgl", "include/freetype2"],
            )
            self.assertTrue((out / "include" / "lvgl" / "lvgl.h").is_file())
            self.assertTrue(
                (out / "include" / "freetype2" / "ft2build.h").is_file()
            )

    def test_legacy_copies_root_header_and_src_tree(self) -> None:
        for version in ("9.5", "9.4", "9.1", "8.4", "8.3"):
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    source = root / "source"
                    _write(source / "lvgl.h", '#include "src/lv_init.h"\n')
                    _write(source / "lv_version.h")
                    _write(source / "src" / "lv_init.h")
                    _write(source / "src" / "lvgl.h", '#include "../lvgl.h"\n')
                    _write(source / "src" / "misc" / "lv_log.h")
                    out = root / "sdk"
                    include_dirs = export_sdk._copy_headers(
                        source, out, version
                    )
                    self.assertEqual(
                        include_dirs, [".", "include", "include/freetype2"]
                    )
                    self.assertTrue((out / "include" / "lvgl.h").is_file())
                    self.assertTrue(
                        (
                            out / "include" / "freetype2" / "ft2build.h"
                        ).is_file()
                    )
                    self.assertTrue(
                        (out / "include" / "lv_version.h").is_file()
                    )
                    self.assertTrue(
                        (out / "include" / "src" / "lv_init.h").is_file()
                    )
                    self.assertTrue(
                        (
                            out / "include" / "src" / "misc" / "lv_log.h"
                        ).is_file()
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
