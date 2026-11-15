
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lvgl_ai import apps as app_domain
from lvgl_ai.apps import common as app_common

TOOL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_ROOT.parent
APP_C = REPO_ROOT / "user" / "app" / "app.c"


class AppDomainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "user" / "app").mkdir(parents=True)
        (self.root / "user" / "scenarios").mkdir(parents=True)
        shutil.copy2(APP_C, self.root / "user" / "app" / "app.c")

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
            "schema": "lvgl-ai-scenario-v1",
            "name": name,
            "steps": [{"type": "wait", "ms": 16}],
        }
        if app is not None:
            payload["app"] = app
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _names(self) -> list[str]:
        return [
            name for name, _ in app_domain.parse_app_entries(
                self.app_c.read_text(encoding="utf-8")
            )
        ]

    def test_register_unregister_roundtrip(self) -> None:
        original = self.app_c.read_text(encoding="utf-8")
        registered, changed = app_domain.register_app(original, "hello")
        self.assertTrue(changed)
        self.assertEqual(self._names_of(registered)[-1], "hello")
        restored, info = app_domain.unregister_app(registered, "hello")
        self.assertTrue(info["changed"])
        self.assertNotIn("hello", info["includes"])
        self.assertEqual(restored, original)

    def _names_of(self, text: str) -> list[str]:
        return [name for name, _ in app_domain.parse_app_entries(text)]

    def test_scaffold_creates_registration_and_scenario(self) -> None:
        result = self._create("hello")
        self.assertEqual(result["action"], "create")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertTrue((self.root / "user/scenarios/hello.json").is_file())
        self.assertEqual(self._names()[-1], "hello")
        self.assertEqual(self._names()[0], "coffee")
        document = json.loads(
            (self.root / "user/scenarios/hello.json").read_text(encoding="utf-8")
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
        self.assertFalse((self.root / "user/scenarios/hello_alt.json").exists())

        restored = app_domain.restore_app(self.root, result["trash_id"])
        self.assertEqual(restored["action"], "restore")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertTrue((self.root / "user/scenarios/hello.json").is_file())
        self.assertTrue((self.root / "user/scenarios/hello_alt.json").is_file())
        self.assertIn("hello", self._names())
        self.assertFalse(trash.exists())

        deleted = app_domain.delete_app(self.root, "hello")
        purged = app_domain.permanently_delete(
            self.root, deleted["trash_id"], confirm=True
        )
        self.assertEqual(purged["action"], "purge")
        self.assertFalse((self.root / purged["path"]).exists())

    def test_delete_protects_builtins_and_scenarios(self) -> None:
        for name in ("coffee", "xiaohongshu", "spectrum", "demo", "settings"):
            with self.subTest(name=name):
                with self.assertRaises(app_domain.AppError) as raised:
                    app_domain.delete_app(self.root, name)
                self.assertEqual(raised.exception.code, "protected_app")
        self._create("hello")
        self._write_scenario("coffee", "hello")
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.delete_app(self.root, "hello")
        self.assertEqual(raised.exception.code, "protected_scenario")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())

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
        self.assertFalse(self.trash_root.exists() and any(self.trash_root.iterdir()))

    def test_restore_conflict_keeps_trash(self) -> None:
        self._create("hello")
        result = app_domain.delete_app(self.root, "hello")
        (self.root / "user/app/hello").mkdir()
        with self.assertRaises(app_domain.AppError) as raised:
            app_domain.restore_app(self.root, result["trash_id"])
        self.assertEqual(raised.exception.code, "restore_conflict")
        self.assertTrue((self.root / result["trash_dir"]).is_dir())

    def test_restore_ignores_tampered_paths_and_rejects_bad_names(self) -> None:
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
        orphan = self.root / "user/app/orphan"
        orphan.mkdir()
        (orphan / "orphan.c").write_text("void orphan_create(void) {}\n", encoding="utf-8")
        self._write_scenario("ghost", "ghost")

        payload = app_domain.list_apps(self.root)
        self.assertTrue(payload["app_c_present"])
        by_name = {entry["name"]: entry for entry in payload["apps"]}
        self.assertTrue(by_name["coffee"]["protected"])
        self.assertFalse(by_name["coffee"]["deletable"])
        self.assertTrue(by_name["hello"]["deletable"])
        self.assertEqual(by_name["hello"]["scenario_files"], ["hello.json"])
        orphan_paths = {entry["path"] for entry in payload["orphans"]}
        self.assertIn("user/app/orphan", orphan_paths)
        self.assertIn("user/scenarios/ghost.json", orphan_paths)

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

    def test_crlf_and_bom_survive_delete_and_restore(self) -> None:
        text = self.app_c.read_text(encoding="utf-8")
        self.app_c.write_bytes(
            b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        )
        self._create("hello")
        result = app_domain.delete_app(self.root, "hello")
        data = self.app_c.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        app_domain.restore_app(self.root, result["trash_id"])
        data = self.app_c.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_apps_package_avoids_forbidden_definition_names(self) -> None:
        package = TOOL_ROOT / "lvgl_ai" / "apps"
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
