from __future__ import annotations

import paths

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

CONSOLE_ROOT = paths.CONSOLE_ROOT
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))


SPECTRUM_DIR = paths.APPS_DIR / "spectrum"
MANIFEST = SPECTRUM_DIR / "assets.json"
README = SPECTRUM_DIR / "README.md"
COVERS = SPECTRUM_DIR / "covers_src"
README_COVER = re.compile(r"covers_src[\\/]([^*`\s]+\.png)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SpectrumCoversFrozenTest(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.entry = payload["assets"]["spectrum_covers"]

    def test_covers_entry_is_frozen(self) -> None:
        self.assertIs(self.entry.get("frozen"), True)
        self.assertEqual(self.entry["output"], "spectrum_covers.h")

    def test_frozen_hashes_cover_every_source_png(self) -> None:
        hashes = self.entry.get("source_hashes")
        self.assertIsInstance(hashes, dict)
        expected = {f"covers_src/{path.name}" for path in COVERS.glob("*.png")}
        self.assertEqual(set(hashes), expected)
        for relative, digest in hashes.items():
            with self.subTest(source=relative):
                self.assertTrue(relative.startswith("covers_src/"))
                self.assertEqual(digest, _sha256(SPECTRUM_DIR / relative))

    def test_readme_examples_name_existing_sources(self) -> None:
        text = README.read_text(encoding="utf-8")
        names = README_COVER.findall(text)
        self.assertTrue(names, "README must show a real covers_src example")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue((COVERS / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
