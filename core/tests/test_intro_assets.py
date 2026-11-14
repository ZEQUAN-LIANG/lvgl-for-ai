"""intro image headers, manifest entries and source hashes stay consistent."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402

INTRO_DIR = paths.USER_APP_DIR / "intro"
ASSETS_DIR = INTRO_DIR / "assets"
MANIFEST = INTRO_DIR / "assets.json"
HANDWRITTEN = (
    "intro.c",
    "intro.h",
    "intro_ui.c",
    "intro_ui.h",
    "intro_layout.c",
    "intro_layout.h",
)
LEGACY_IMAGE_NAME = re.compile(r"\b(?:idx_img_|IDX_IMG_)[A-Za-z0-9_]*")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IntroAssetsManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assets = payload["assets"]

    def test_every_image_uses_the_intro_prefix(self) -> None:
        self.assertTrue(self.assets)
        for key, entry in self.assets.items():
            with self.subTest(key=key):
                self.assertEqual(entry["kind"], "image")
                self.assertTrue(key.startswith("intro_img_"), key)
                self.assertEqual(entry["name"], key)
                self.assertEqual(entry["output"], f"{key}.h")

    def test_generated_outputs_exist_and_hashes_match_sources(self) -> None:
        for key, entry in self.assets.items():
            with self.subTest(key=key):
                output = INTRO_DIR / entry["output"]
                source = ASSETS_DIR / entry["source"]
                self.assertTrue(output.is_file(), output)
                self.assertTrue(source.is_file(), source)
                self.assertEqual(entry["source_sha256"], _sha256(source))

    def test_no_legacy_index_image_names_remain(self) -> None:
        self.assertEqual(list(INTRO_DIR.glob("idx_img_*.h")), [])
        generated = sorted(INTRO_DIR.glob("intro_img_*.h"))
        self.assertEqual(
            {path.name for path in generated},
            {entry["output"] for entry in self.assets.values()},
        )
        for path in [INTRO_DIR / name for name in HANDWRITTEN] + generated:
            with self.subTest(name=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(LEGACY_IMAGE_NAME.search(text))


if __name__ == "__main__":
    unittest.main()
