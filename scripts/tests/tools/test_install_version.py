from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import install_version
import paths

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
    (repo / "console").mkdir(parents=True)
    (repo / "user" / "app").mkdir(parents=True)
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

    def test_meta_layout_is_used_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            meta = repo / "scripts" / "meta"
            meta.mkdir(parents=True)
            (repo / "versions.json").replace(meta / "versions.json")
            (meta / "VERSION.json").write_text(
                json.dumps({"tool_version": "0.2.0"}), encoding="utf-8"
            )
            index = install_version._load_index(repo)
            self.assertEqual(index["default"], "9.6")
            self.assertEqual(install_version._tool_version(repo), "0.2.0")

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
            archive.writestr("dist/lvgl/9.4/manifest.json", "{}\n")
            archive.writestr(engine, "engine\n")
        return pack

    def test_pack_zip_installs_sdk_and_engine(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            pack = self._write_pack(root)
            code, out, err = run_main(
                [
                    "--lvgl",
                    "9.4",
                    "--mode",
                    "pack",
                    "--pack",
                    str(pack),
                    "--repo-root",
                    str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 0, err)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(
                (repo / "dist" / "lvgl" / "9.4" / "manifest.json").is_file()
            )
            self.assertTrue(
                (
                    repo / "build" / "lvgl_9_4" / paths.engine_filename()
                ).is_file()
            )

    def test_missing_pack_source_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            code, _, err = run_main(
                [
                    "--lvgl",
                    "9.4",
                    "--mode",
                    "pack",
                    "--repo-root",
                    str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("pack mode needs", err)

    def test_pack_manifest_must_match_the_tool(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            (repo / "VERSION.json").write_text(
                json.dumps({"tool_version": "0.2.0"}), encoding="utf-8"
            )
            pack = root / "pack.zip"
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("dist/lvgl/9.4/manifest.json", "{}\n")
                archive.writestr(
                    f"build/lvgl_9_4/{paths.engine_filename()}", "engine\n"
                )
                archive.writestr(
                    "pack.json",
                    json.dumps(
                        {
                            "schema": install_version.PACK_SCHEMA,
                            "lvgl": "9.4",
                            "core_version": "0.1.0",
                        }
                    ),
                )
            code, _, err = run_main(
                [
                    "--lvgl",
                    "9.4",
                    "--mode",
                    "pack",
                    "--pack",
                    str(pack),
                    "--repo-root",
                    str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("requires tool", err)

    def test_pack_copies_legacy_smoke_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            pack = root / "pack.zip"
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("dist/lvgl/9.4/manifest.json", "{}\n")
                archive.writestr(
                    f"build/lvgl_9_4/{paths.engine_filename()}", "engine\n"
                )
                archive.writestr("smoke/legacy_smoke.json", "{}\n")
            code, out, err = run_main(
                [
                    "--lvgl",
                    "9.4",
                    "--mode",
                    "pack",
                    "--pack",
                    str(pack),
                    "--repo-root",
                    str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 0, err)
            self.assertTrue(
                (repo / "smoke" / "9.4" / "legacy_smoke.json").is_file()
            )
            payload = json.loads(out)
            self.assertEqual(
                Path(payload["smoke"]),
                repo / "smoke" / "9.4" / "legacy_smoke.json",
            )

    def test_yes_downloads_a_file_url_and_remembers_the_version(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            pack = root / "pack.zip"
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("dist/lvgl/9.4/manifest.json", "{}\n")
                archive.writestr(
                    f"build/lvgl_9_4/{paths.engine_filename()}", "engine\n"
                )
                archive.writestr(
                    "pack.json",
                    json.dumps(
                        {
                            "schema": install_version.PACK_SCHEMA,
                            "lvgl": "9.4",
                            "core_version": "0.2.0",
                        }
                    ),
                )
            (repo / "VERSION.json").write_text(
                json.dumps({"tool_version": "0.2.0"}), encoding="utf-8"
            )
            digest = install_version._sha256(pack)
            index = json.loads(
                (repo / "versions.json").read_text(encoding="utf-8")
            )
            index["versions"]["9.4"]["pack"] = {
                "gitee": pack.as_uri(),
                "sha256": digest,
            }
            (repo / "versions.json").write_text(
                json.dumps(index), encoding="utf-8"
            )
            actions = install_version.ensure_pack_for_version(
                repo, "9.4", interactive=False, yes=True
            )
            self.assertEqual(actions, ["download_pack", "install_pack"])
            self.assertTrue(
                (repo / "dist" / "lvgl" / "9.4" / "manifest.json").is_file()
            )
            state = install_version._load_prompt_state(repo)
            self.assertIn("9.4", state["accepted"])

    def test_offline_missing_pack_is_an_install_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = make_repo(Path(raw))
            index = json.loads(
                (repo / "versions.json").read_text(encoding="utf-8")
            )
            index["versions"]["9.4"]["pack"] = {"gitee": "file:///unused.zip"}
            (repo / "versions.json").write_text(
                json.dumps(index), encoding="utf-8"
            )
            with self.assertRaises(install_version.InstallError):
                install_version.ensure_pack_for_version(
                    repo, "9.4", interactive=False, offline=True
                )

    def test_unsafe_zip_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = make_repo(root)
            pack = root / "bad.zip"
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("../escape.txt", "x")
            code, _, err = run_main(
                [
                    "--lvgl",
                    "9.4",
                    "--mode",
                    "pack",
                    "--pack",
                    str(pack),
                    "--repo-root",
                    str(repo),
                    "--json",
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("unsafe pack member", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
