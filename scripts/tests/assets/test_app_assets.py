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

INTRO_DIR = paths.APPS_DIR / "intro"
ASSETS_DIR = INTRO_DIR / "assets"
INTRO_MANIFEST = paths.REPO_ROOT / "user" / ".cache" / "assets" / "intro.json"
HANDWRITTEN = (
    "intro.c",
    "intro.h",
    "intro_ui.c",
    "intro_ui.h",
    "intro_layout.c",
    "intro_layout.h",
)
LEGACY_IMAGE_NAME = re.compile(r"\b(?:idx_img_|IDX_IMG_)[A-Za-z0-9_]*")

SPECTRUM_DIR = paths.APPS_DIR / "spectrum"
SPECTRUM_README = SPECTRUM_DIR / "README.md"
SPECTRUM_COVERS = SPECTRUM_DIR / "covers_src"
SPECTRUM_HEADER = SPECTRUM_DIR / "spectrum_covers.h"
README_COVER = re.compile(r"covers_src[\\/]([^*`\s]+\.png)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IntroAssetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.generated = sorted(INTRO_DIR.glob("intro_img_*.h"))
        if INTRO_MANIFEST.is_file():
            payload = json.loads(INTRO_MANIFEST.read_text(encoding="utf-8"))
            self.assets = payload["assets"]
        else:
            self.assets = None

    def test_every_image_uses_the_intro_prefix(self) -> None:
        self.assertTrue(self.generated)
        for path in self.generated:
            with self.subTest(name=path.name):
                self.assertTrue(path.name.startswith("intro_img_"), path.name)

    def test_generated_outputs_exist_and_hashes_match_sources(self) -> None:
        if self.assets is None:
            self.skipTest("no replay log; regenerate assets to check hashes")
        for key, entry in self.assets.items():
            with self.subTest(key=key):
                self.assertEqual(entry["kind"], "image")
                self.assertTrue(key.startswith("intro_img_"), key)
                self.assertEqual(entry["name"], key)
                output = INTRO_DIR / entry["output"]
                source = ASSETS_DIR / entry["source"]
                self.assertTrue(output.is_file(), output)
                self.assertTrue(source.is_file(), source)
                self.assertEqual(entry["source_sha256"], _sha256(source))

    def test_no_legacy_index_image_names_remain(self) -> None:
        self.assertEqual(list(INTRO_DIR.glob("idx_img_*.h")), [])
        self.assertTrue(self.generated)
        if self.assets is not None:
            self.assertEqual(
                {path.name for path in self.generated},
                {entry["output"] for entry in self.assets.values()},
            )
        for path in [INTRO_DIR / name for name in HANDWRITTEN] + self.generated:
            with self.subTest(name=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(LEGACY_IMAGE_NAME.search(text))


class SpectrumCoversFrozenTest(unittest.TestCase):
    def test_frozen_header_and_sources_are_present(self) -> None:
        self.assertTrue(SPECTRUM_HEADER.is_file())
        self.assertTrue(sorted(SPECTRUM_COVERS.glob("*.png")))

    def test_readme_states_the_header_is_frozen(self) -> None:
        text = SPECTRUM_README.read_text(encoding="utf-8")
        self.assertIn("spectrum_covers.h", text)
        self.assertIn("冻结", text)

    def test_readme_examples_name_existing_sources(self) -> None:
        text = SPECTRUM_README.read_text(encoding="utf-8")
        names = README_COVER.findall(text)
        self.assertTrue(names, "README must show a real covers_src example")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue((SPECTRUM_COVERS / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
