from __future__ import annotations

import paths

import re
import sys
import unittest

CONSOLE_ROOT = paths.CONSOLE_ROOT
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

SPECTRUM_DIR = paths.APPS_DIR / "spectrum"
README = SPECTRUM_DIR / "README.md"
COVERS = SPECTRUM_DIR / "covers_src"
COVERS_HEADER = SPECTRUM_DIR / "spectrum_covers.h"
README_COVER = re.compile(r"covers_src[\\/]([^*`\s]+\.png)")


class SpectrumCoversFrozenTest(unittest.TestCase):
    def test_frozen_header_and_sources_are_present(self) -> None:
        self.assertTrue(COVERS_HEADER.is_file())
        self.assertTrue(sorted(COVERS.glob("*.png")))

    def test_readme_states_the_header_is_frozen(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("spectrum_covers.h", text)
        self.assertIn("冻结", text)

    def test_readme_examples_name_existing_sources(self) -> None:
        text = README.read_text(encoding="utf-8")
        names = README_COVER.findall(text)
        self.assertTrue(names, "README must show a real covers_src example")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue((COVERS / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
