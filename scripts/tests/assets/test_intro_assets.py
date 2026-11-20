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
MANIFEST = paths.REPO_ROOT / "user" / ".cache" / "assets" / "intro.json"
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
    """Checks the generated headers, and the replay log when it is present.

    The replay log is derived data under ``user/.cache/`` (git ignored), so a
    clean checkout has no log: the file-level checks always run, the hash
    cross-checks only when the log is there.
    """

    def setUp(self) -> None:
        self.generated = sorted(INTRO_DIR.glob("intro_img_*.h"))
        if MANIFEST.is_file():
            payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
