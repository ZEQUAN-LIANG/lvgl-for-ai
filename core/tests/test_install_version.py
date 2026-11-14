"""Unit tests for ``core/tools/install_version.py``.

The source path is intentionally not exercised here: it downloads LVGL and
builds an SDK. These tests cover the version index, ``--list``, pack installs
and error handling without network or toolchain access.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import install_version
from lvgl_ai import paths


INDEX = {
    "schema": install_version.INDEX_SCHEMA,
    "default": "9.6",
    "versions": {
        "9.6": {"tag": "v9.6.0", "intro": True},
        "9.4": {"tag": "v9.4.0", "intro": True},
        "8.3": {"tag": "v8.3.11", "intro": False},
    },
}


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    (repo / "core").mkdir(parents=True)
    (repo / "user").mkdir()
    (repo / "versions.json").write_text(
        json.dumps(INDEX, indent=2), encoding="utf-8"
    )
    return repo


def run_main(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install_version.main(argv)
    return code, out.getvalue(), err.getvalue()


class VersionIndexTest(unittest.TestCase):
    def test_index_is_loaded_and_default_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            index = install_version._load_index(repo)
            self.assertEqual(index["default"], "9.6")
            self.assertEqual(index["versions"]["9.4"]["tag"], "v9.4.0")

    def test_unknown_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            with self.assertRaises(install_version.InstallError):
                install_version._version_entry(
                    install_version._load_index(repo), "9.2"
                )


class ListTest(unittest.TestCase):
    def test_list_reports_install_state_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            code, out, err = run_main(
                ["--list", "--json", "--repo-root", str(repo)]
            )
            self.assertEqual(code, 0, err)
            payload = json.loads(out)
            versions = {row["version"]: row for row in payload["versions"]}
            self.assertTrue(versions["9.6"]["default"])
            self.assertFalse(versions["9.6"]["sdk"])
            self.assertFalse(versions["8.3"]["intro"])

    def test_list_human_table_is_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            code, out, err = run_main(["--list", "--repo-root", str(repo)])
            self.assertEqual(code, 0, err)
            self.assertIn("version", out)
            self.assertIn("9.4", out)
            self.assertIn("v9.4.0", out)


class PackInstallTest(unittest.TestCase):
    def _write_pack(self, root: Path) -> Path:
        pack = root / "pack.zip"
        engine = f"build/lvgl_9_4/{paths.engine_filename()}"
        with zipfile.ZipFile(pack, "w") as archive:
            archive.writestr("sdk/9.4/manifest.json", "{}\n")
            archive.writestr(engine, "engine\n")
        return pack

    def test_pack_zip_installs_sdk_and_engine(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            pack = self._write_pack(root)
            code, out, err = run_main(
                [
                    "--lvgl", "9.4",
                    "--mode", "pack",
                    "--pack", str(pack),
                    "--repo-root", str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 0, err)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue((repo / "sdk" / "9.4" / "manifest.json").is_file())
            self.assertTrue(
                (repo / "build" / "lvgl_9_4" / paths.engine_filename()).is_file()
            )

    def test_missing_pack_source_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            code, _, err = run_main(
                [
                    "--lvgl", "9.4",
                    "--mode", "pack",
                    "--repo-root", str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("pack mode needs", err)

    def test_unsafe_zip_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            pack = root / "bad.zip"
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("../escape.txt", "x")
            code, _, err = run_main(
                [
                    "--lvgl", "9.4",
                    "--mode", "pack",
                    "--pack", str(pack),
                    "--repo-root", str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("unsafe pack member", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
