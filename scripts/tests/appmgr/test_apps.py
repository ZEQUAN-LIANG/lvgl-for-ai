from __future__ import annotations

import paths

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import appmgr as app_domain
from appmgr import common as app_common
from appmgr import discovery

CONSOLE_ROOT = paths.CONSOLE_ROOT
REPO_ROOT = CONSOLE_ROOT.parent
APP_C = REPO_ROOT / "user" / "app" / "app.c"


class AppDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "user" / "app").mkdir(parents=True)
        (self.root / "user" / "scenarios").mkdir(parents=True)
        shutil.copy2(APP_C, self.root / "user" / "app" / "app.c")
        for name in ("coffee", "spectrum"):
            app_dir = self.root / "user" / "app" / name
            app_dir.mkdir()
            (app_dir / f"{name}.c").write_text(
                f"void {name}_create(void) {{}}\n", encoding="utf-8"
            )
        (self.root / "user" / "app" / "app.json").write_text(
            json.dumps({"default": "coffee"}), encoding="utf-8"
        )

    @property
    def app_c(self) -> Path:
        return self.root / "user" / "app" / "app.c"

    @property
    def trash_root(self) -> Path:
        return self.root / "user" / ".trash" / "apps"

    def _create(self, name: str) -> dict:
        return app_domain.scaffold_app(self.root, name)

    def _write_scenario(self, name: str, app: str | None) -> Path:
        path = self.root / "user" / "scenarios" / f"{name}.json"
        payload = {
            "schema": "lvgl-verify-loop-scenario-v1",
            "name": name,
            "steps": [{"type": "wait", "ms": 16}],
        }
        if app is not None:
            payload["app"] = app
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _names(self) -> list[str]:
        return [
            entry.name
            for entry in discovery.scan_apps(self.root / "user" / "app")[0]
        ]

    def test_scaffold_creates_scenario_without_metadata(self) -> None:
        original = self.app_c.read_bytes()
        result = self._create("hello")
        self.assertEqual(result["action"], "create")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertFalse((self.root / "user/app/hello/app.json").exists())
        self.assertTrue((self.root / "user/scenarios/hello.json").is_file())
        self.assertIn("hello", self._names())
        self.assertEqual(self._names()[0], "coffee")
        self.assertEqual(self.app_c.read_bytes(), original)
        document = json.loads(
            (self.root / "user/scenarios/hello.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document["app"], "hello")

    def test_delete_moves_app_and_all_scenarios_then_restore(self) -> None:
        self._create("hello")
        self._write_scenario("hello_alt", "hello")
        result = app_domain.delete_app(self.root, "hello")
        trash = self.root / result["trash_dir"]
        self.assertTrue((trash / "meta.json").is_file())
        self.assertTrue((trash / "app/hello.c").is_file())
        self.assertTrue((trash / "scenarios/hello.json").is_file())
        self.assertTrue((trash / "scenarios/hello_alt.json").is_file())
        self.assertNotIn("hello", self._names())
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertFalse((self.root / "user/scenarios/hello.json").exists())
        self.assertFalse(
            (self.root / "user/scenarios/hello_alt.json").exists()
        )

        restored = app_domain.restore_app(self.root, result["trash_id"])
        self.assertEqual(restored["action"], "restore")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertTrue((self.root / "user/scenarios/hello.json").is_file())
        self.assertTrue(
            (self.root / "user/scenarios/hello_alt.json").is_file()
        )
        self.assertIn("hello", self._names())
        self.assertFalse(trash.exists())

        deleted = app_domain.delete_app(self.root, "hello")
        purged = app_domain.permanently_delete(
            self.root, deleted["trash_id"], confirm=True
        )
        self.assertEqual(purged["action"], "purge")
        self.assertFalse((self.root / purged["path"]).exists())

    def test_delete_protects_only_the_default_app(self) -> None:
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.delete_app(self.root, "coffee")
        self.assertEqual(raised.exception.code, "protected_app")

        spectrum = self.root / "user/app/spectrum"
        (spectrum / "spectrum.c").write_text(
            "void spectrum_create(void) {}\n", encoding="utf-8"
        )
        self._write_scenario("spectrum", "spectrum")
        deleted = app_domain.delete_app(self.root, "spectrum")
        self.assertFalse(spectrum.exists())
        self.assertFalse(
            (self.root / "user/scenarios/spectrum.json").exists()
        )
        app_domain.restore_app(self.root, deleted["trash_id"])
        self.assertTrue(spectrum.is_dir())
        self.assertTrue(
            (self.root / "user/scenarios/spectrum.json").is_file()
        )

        self._create("hello")
        self._write_scenario("coffee", "hello")
        deleted = app_domain.delete_app(self.root, "hello")
        trash = self.root / deleted["trash_dir"]
        self.assertTrue((trash / "scenarios/coffee.json").is_file())
        self.assertFalse((self.root / "user/app/hello").exists())

    def test_delete_rollback_on_move_failure(self) -> None:
        self._create("hello")
        scenario = self._write_scenario("hello", "hello")
        real_move = app_common._move_path
        calls = {"count": 0}

        def flaky(source: Path, destination: Path) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated move failure")
            real_move(source, destination)

        with mock.patch.object(app_common, "_move_path", side_effect=flaky):
            with self.assertRaises(app_domain.AppError) as raised:
                app_domain.delete_app(self.root, "hello")
        self.assertEqual(raised.exception.code, "app_io_error")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertTrue(scenario.is_file())
        self.assertIn("hello", self._names())
        self.assertFalse(
            self.trash_root.exists() and any(self.trash_root.iterdir())
        )

    def test_restore_conflict_keeps_trash(self) -> None:
        self._create("hello")
        result = app_domain.delete_app(self.root, "hello")
        (self.root / "user/app/hello").mkdir()
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.restore_app(self.root, result["trash_id"])
        self.assertEqual(raised.exception.code, "restore_conflict")
        self.assertTrue((self.root / result["trash_dir"]).is_dir())

    def test_restore_ignores_tampered_paths_and_rejects_bad_names(
        self,
    ) -> None:
        self._create("hello")
        result = app_domain.delete_app(self.root, "hello")
        meta_path = self.root / result["trash_dir"] / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["app_dir"] = "../../evil"
        meta["name"] = "../evil"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.restore_app(self.root, result["trash_id"])
        self.assertEqual(raised.exception.code, "invalid_name")
        entries = app_domain.list_trash(self.root)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["valid"])

    def test_purge_requires_confirmation(self) -> None:
        self._create("hello")
        result = app_domain.delete_app(self.root, "hello")
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.permanently_delete(self.root, result["trash_id"])
        self.assertEqual(raised.exception.code, "confirmation_required")
        app_domain.permanently_delete(
            self.root, result["trash_id"], confirm=True
        )

    def test_list_apps_tree_and_recent(self) -> None:
        self._create("hello")
        # A directory declaring ``<name>_create`` is an app, not an orphan.
        convention = self.root / "user/app/plain"
        convention.mkdir()
        (convention / "plain.c").write_text(
            "void plain_create(void) {}\n", encoding="utf-8"
        )
        # Only an app directory whose metadata cannot be read stays orphaned.
        broken = self.root / "user/app/broken"
        broken.mkdir()
        (broken / "app.json").write_text("{", encoding="utf-8")
        harness = self.root / "user/app/demo"
        harness.mkdir()
        (harness / "panel.c").write_text(
            "void demo_harness_create(void) {}\n", encoding="utf-8"
        )
        self._write_scenario("ghost", "ghost")

        payload = app_domain.list_apps(self.root)
        self.assertTrue(payload["app_c_present"])
        by_name = {entry["name"]: entry for entry in payload["apps"]}
        self.assertTrue(by_name["coffee"]["protected"])
        self.assertFalse(by_name["coffee"]["deletable"])
        self.assertFalse(by_name["spectrum"]["protected"])
        self.assertTrue(by_name["spectrum"]["deletable"])
        self.assertTrue(by_name["hello"]["deletable"])
        self.assertTrue(by_name["plain"]["deletable"])
        self.assertEqual(by_name["hello"]["scenario_files"], ["hello.json"])
        orphan_paths = {entry["path"] for entry in payload["orphans"]}
        self.assertIn("user/app/broken", orphan_paths)
        self.assertIn("user/scenarios/ghost.json", orphan_paths)
        self.assertNotIn("user/app/demo", orphan_paths)
        self.assertNotIn("user/app/plain", orphan_paths)

        view = app_domain.app_tree(self.root, "hello")
        self.assertTrue(view["registered"])
        self.assertEqual(view["tree"]["type"], "dir")
        child_names = {child["name"] for child in view["tree"]["children"]}
        self.assertIn("hello.c", child_names)
        self.assertIn("hello.h", child_names)
        self.assertEqual(view["scenarios"][0]["name"], "hello.json")

        recent = app_domain.recent_apps(self.root, limit=50)
        paths = {entry["path"] for entry in recent}
        self.assertIn("user/app/app.c", paths)
        self.assertIn("user/app/hello/hello.c", paths)
        self.assertIn("user/scenarios/hello.json", paths)

    def test_name_and_trash_id_safety(self) -> None:
        with self.assertRaises(app_domain.AppError):
            app_domain.delete_app(self.root, "../escape")
        with self.assertRaises(app_domain.AppError):
            app_domain.restore_app(self.root, "../../escape")
        with self.assertRaises(app_domain.AppError):
            app_domain.permanently_delete(
                self.root, "not-a-trash-id", confirm=True
            )
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.delete_app(self.root, "missing")
        self.assertEqual(raised.exception.code, "unknown_app")

    def test_app_c_is_never_rewritten_by_scaffold_or_trash(self) -> None:
        text = self.app_c.read_text(encoding="utf-8")
        self.app_c.write_bytes(
            b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        )
        original = self.app_c.read_bytes()
        self._create("hello")
        result = app_domain.delete_app(self.root, "hello")
        self.assertEqual(self.app_c.read_bytes(), original)
        app_domain.restore_app(self.root, result["trash_id"])
        self.assertEqual(self.app_c.read_bytes(), original)

    def test_apps_package_avoids_forbidden_definition_names(self) -> None:
        package = CONSOLE_ROOT / "appmgr"
        texts = [
            path.read_text(encoding="utf-8")
            for path in sorted(package.glob("*.py"))
        ]
        self.assertTrue(texts)
        for text in texts:
            for forbidden in (
                "def tree(",
                "def inspect(",
                "def baseline(",
                "def accept(",
            ):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
