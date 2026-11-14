"""Tests for the maintainer-only release uploader."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import upload_release


class ReleaseAssetsTest(unittest.TestCase):
    def test_selects_zips_and_checksums_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "lvgl-verify-loop-0.2.0-full-win64.zip").write_bytes(b"full")
            (root / "lvgl-verify-loop-0.2.0-full-sifli-win64.zip").write_bytes(
                b"sifli"
            )
            (root / "lvgl-verify-loop-0.2.0-full-win64.zip.sha256").write_text(
                "hash\n", encoding="utf-8"
            )
            (root / "RELEASE_NOTES.md").write_text("notes\n", encoding="utf-8")
            (root / "lvgl-verify-loop-0.2.0-notes.txt").write_text(
                "junk\n", encoding="utf-8"
            )
            assets = upload_release.release_assets(root, "0.2.0")
            self.assertEqual(
                [path.name for path in assets],
                [
                    "lvgl-verify-loop-0.2.0-full-sifli-win64.zip",
                    "lvgl-verify-loop-0.2.0-full-win64.zip",
                    "lvgl-verify-loop-0.2.0-full-win64.zip.sha256",
                ],
            )

    def test_missing_zip_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(upload_release.UploadError):
                upload_release.release_assets(Path(raw), "0.2.0")

    def test_glob_metacharacters_in_version_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(upload_release.UploadError):
                upload_release.release_assets(Path(raw), "*")


class TokenTest(unittest.TestCase):
    def test_token_comes_from_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {"GITEE_TOKEN": "secret"}, clear=True):
            self.assertEqual(
                upload_release.resolve_token("GITEE_TOKEN", "Gitee"),
                "secret",
            )

    def test_missing_token_names_the_environment_variable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(upload_release.UploadError) as caught:
                upload_release.resolve_token("GITHUB_TOKEN", "GitHub")
        self.assertIn("GITHUB_TOKEN", str(caught.exception))


class NotesTest(unittest.TestCase):
    def test_default_notes_are_optional(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(upload_release.load_notes(Path(raw), None))

    def test_explicit_missing_notes_are_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(upload_release.UploadError):
                upload_release.load_notes(
                    Path(raw), Path(raw) / "missing.md"
                )

    def test_notes_file_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            notes = root / "notes.md"
            notes.write_text("release notes\n", encoding="utf-8")
            self.assertEqual(
                upload_release.load_notes(root, notes), "release notes\n"
            )


if __name__ == "__main__":
    unittest.main()
