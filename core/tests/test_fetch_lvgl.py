"""Unit tests for fetch_lvgl.py patch discovery and application.

These tests do not download anything. They exercise the patch ordering rules,
the series file validation, `git apply` on a plain directory, and the source
stamp written next to the installed tree.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = TOOL_ROOT / "tools"
for path in (TOOL_ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import fetch_lvgl  # noqa: E402

PATCH = """\
diff --git a/src/foo.c b/src/foo.c
--- a/src/foo.c
+++ b/src/foo.c
@@ -1 +1 @@
-old
+new
"""


class DownloadValidationTest(unittest.TestCase):
    def test_gzip_magic_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "archive.tar.gz"
            path.write_bytes(b"\x1f\x8bnot-really")
            self.assertTrue(fetch_lvgl._is_gzip(path))
            path.write_bytes(b"<!DOCTYPE html>")
            self.assertFalse(fetch_lvgl._is_gzip(path))


class PatchDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.patch_dir = self.root / "patches" / "9.6"
        self.patch_dir.mkdir(parents=True)
        self.write("0002-second.patch", PATCH)
        self.write("0001-first.patch", PATCH)

    def write(self, name: str, text: str) -> None:
        (self.patch_dir / name).write_text(text, encoding="utf-8")

    def test_series_controls_order_and_skips_comments(self) -> None:
        self.write("series", "# comment\n\n0002-second.patch\n0001-first.patch\n")
        names = [path.name for path in fetch_lvgl.discover_patches(self.patch_dir)]
        self.assertEqual(names, ["0002-second.patch", "0001-first.patch"])

    def test_missing_series_uses_sorted_glob(self) -> None:
        names = [path.name for path in fetch_lvgl.discover_patches(self.patch_dir)]
        self.assertEqual(names, ["0001-first.patch", "0002-second.patch"])

    def test_missing_patch_directory_means_no_patches(self) -> None:
        self.assertEqual(fetch_lvgl.discover_patches(self.root / "missing"), [])

    def test_series_rejects_parent_traversal(self) -> None:
        self.write("series", "../escape.patch\n")
        with self.assertRaises(SystemExit):
            fetch_lvgl.discover_patches(self.patch_dir)

    def test_series_rejects_absolute_path(self) -> None:
        self.write("series", "/tmp/escape.patch\n")
        with self.assertRaises(SystemExit):
            fetch_lvgl.discover_patches(self.patch_dir)

    def test_series_rejects_missing_patch(self) -> None:
        self.write("series", "missing.patch\n")
        with self.assertRaises(SystemExit):
            fetch_lvgl.discover_patches(self.patch_dir)

    def test_series_rejects_non_patch_extension(self) -> None:
        self.write("series", "notes.txt\n")
        with self.assertRaises(SystemExit):
            fetch_lvgl.discover_patches(self.patch_dir)


@unittest.skipUnless(shutil.which("git"), "git is required to apply patches")
class ApplyPatchesTest(unittest.TestCase):
    def test_git_apply_works_in_a_plain_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = root / "tree"
            (tree / "src").mkdir(parents=True)
            (tree / "src" / "foo.c").write_text("old\n", encoding="utf-8")
            patch = root / "0001.patch"
            patch.write_text(PATCH, encoding="utf-8")

            fetch_lvgl.apply_patches(tree, [patch])

            self.assertEqual(
                (tree / "src" / "foo.c").read_text(encoding="utf-8"), "new\n"
            )

    def test_main_applies_patches_before_installing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = root / "extracted" / "lvgl-9.6.0"
            (tree / "include" / "lvgl").mkdir(parents=True)
            (tree / "include" / "lvgl" / "lvgl.h").write_text(
                "/* lvgl */\n", encoding="utf-8"
            )
            (tree / "lv_version.h").write_text(
                "#define LVGL_VERSION_MAJOR 9\n"
                "#define LVGL_VERSION_MINOR 6\n"
                "#define LVGL_VERSION_PATCH 0\n",
                encoding="utf-8",
            )
            (tree / "src").mkdir()
            (tree / "src" / "foo.c").write_text("old\n", encoding="utf-8")

            patch_dir = root / "patches" / "9.6"
            patch_dir.mkdir(parents=True)
            (patch_dir / "series").write_text("0001.patch\n", encoding="utf-8")
            (patch_dir / "0001.patch").write_text(PATCH, encoding="utf-8")

            argv = [
                "fetch_lvgl.py",
                "--version",
                "9.6",
                "--repo-root",
                str(root),
            ]
            with mock.patch.object(fetch_lvgl, "download"), mock.patch.object(
                fetch_lvgl, "extract", return_value=tree
            ), mock.patch.object(sys, "argv", argv):
                self.assertEqual(fetch_lvgl.main(), 0)

            dest = root / "lvgl-src" / "9.6"
            self.assertEqual(
                (dest / "src" / "foo.c").read_text(encoding="utf-8"), "new\n"
            )
            stamp = json.loads(
                (dest / ".lvgl-ai-source.json").read_text(encoding="utf-8")
            )
            self.assertEqual(stamp["patches"], ["0001.patch"])

    def test_main_requires_force_when_existing_tree_lacks_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "lvgl-src" / "9.6"
            (dest / "include" / "lvgl").mkdir(parents=True)
            (dest / "include" / "lvgl" / "lvgl.h").write_text(
                "/* lvgl */\n", encoding="utf-8"
            )
            (dest / "lv_version.h").write_text(
                "#define LVGL_VERSION_MAJOR 9\n"
                "#define LVGL_VERSION_MINOR 6\n"
                "#define LVGL_VERSION_PATCH 0\n",
                encoding="utf-8",
            )
            patch_dir = root / "patches" / "9.6"
            patch_dir.mkdir(parents=True)
            (patch_dir / "series").write_text("0001.patch\n", encoding="utf-8")
            (patch_dir / "0001.patch").write_text(PATCH, encoding="utf-8")

            argv = [
                "fetch_lvgl.py",
                "--version",
                "9.6",
                "--repo-root",
                str(root),
            ]
            with mock.patch.object(fetch_lvgl, "download") as download, mock.patch.object(
                fetch_lvgl, "extract"
            ) as extract, mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit):
                    fetch_lvgl.main()
                download.assert_not_called()
                extract.assert_not_called()

    def test_stamp_records_names_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "0001.patch"
            patch.write_text(PATCH, encoding="utf-8")

            fetch_lvgl.write_source_stamp(root, "9.6", [patch])

            payload = json.loads(
                (root / ".lvgl-ai-source.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["schema"], fetch_lvgl.SOURCE_SCHEMA)
            self.assertEqual(payload["version"], "9.6")
            self.assertEqual(payload["tag"], "v9.6.0")
            self.assertEqual(payload["patches"], ["0001.patch"])
            self.assertEqual(len(payload["patch_sha256"]["0001.patch"]), 64)

    def test_stamp_matches_only_while_patch_content_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "0001.patch"
            patch.write_text(PATCH, encoding="utf-8")
            fetch_lvgl.write_source_stamp(root, "9.6", [patch])

            self.assertTrue(
                fetch_lvgl.source_stamp_matches(root, "9.6", [patch])
            )

            patch.write_text(PATCH + "\n", encoding="utf-8")
            self.assertFalse(
                fetch_lvgl.source_stamp_matches(root, "9.6", [patch])
            )

    def test_source_stamp_matches_requires_a_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(fetch_lvgl.source_stamp_matches(root, "9.6", []))


if __name__ == "__main__":
    unittest.main()
