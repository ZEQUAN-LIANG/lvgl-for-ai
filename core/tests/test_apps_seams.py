"""Private seam tests for the apps package: registry, scaffold, trash, views.

Public behavior is covered by ``test_apps.py`` and ``test_web_apps.py``; this
module reaches into the internal seams to cover branches that the lifecycle
API only hits indirectly.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lvgl_ai import apps as app_domain
from lvgl_ai.apps import common, policy, registry, scaffold, trash, views

TOOL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_ROOT.parent
APP_C = REPO_ROOT / "user" / "app" / "app.c"


class _TempRepo(unittest.TestCase):
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

    def _app_c_text(self) -> str:
        return self.app_c.read_text(encoding="utf-8")

    def _write_scenario(self, name: str, app: str) -> Path:
        path = self.root / "user" / "scenarios" / f"{name}.json"
        path.write_text(
            json.dumps({
                "schema": "lvgl-ai-scenario-v1",
                "name": name,
                "app": app,
                "steps": [{"type": "wait", "ms": 16}],
            }),
            encoding="utf-8",
        )
        return path


class PublicSurfaceTest(unittest.TestCase):
    def test_lifecycle_exports_are_the_seam_functions(self) -> None:
        self.assertIs(app_domain.AppError, common.AppError)
        self.assertIs(app_domain.resolve_repo_root, common.resolve_repo_root)
        self.assertIs(app_domain.is_protected_name, policy.is_protected_name)
        self.assertIs(
            app_domain.parse_app_entries, registry.parse_app_entries
        )
        self.assertIs(app_domain.register_app, registry.register_app)
        self.assertIs(app_domain.unregister_app, registry.unregister_app)
        self.assertIs(app_domain.scaffold_app, scaffold.scaffold_app)
        self.assertIs(app_domain.list_apps, views.list_apps)
        self.assertIs(app_domain.app_tree, views.app_tree)
        self.assertIs(app_domain.recent_apps, views.recent_apps)
        self.assertIs(app_domain.list_trash, trash.list_trash)
        self.assertIs(app_domain.delete_app, trash.delete_app)
        self.assertIs(app_domain.restore_app, trash.restore_app)
        self.assertIs(
            app_domain.permanently_delete, trash.permanently_delete
        )

    def test_app_error_keeps_signature_but_not_http_status(self) -> None:
        error = common.AppError("name_reserved", "reserved", status=418)
        self.assertEqual(error.code, "name_reserved")
        self.assertEqual(error.message, "reserved")
        self.assertEqual(error.detail, {})
        self.assertFalse(hasattr(error, "status"))


class RegistrySeamTest(_TempRepo):
    def test_register_is_idempotent(self) -> None:
        original = self._app_c_text()
        first, changed = registry.register_app(original, "hello")
        self.assertTrue(changed)
        second, changed_again = registry.register_app(first, "hello")
        self.assertFalse(changed_again)
        self.assertEqual(second, first)

    def test_unregister_missing_is_ok_only_when_requested(self) -> None:
        with self.assertRaises(common.AppError) as raised:
            registry.unregister_app(self._app_c_text(), "hello")
        self.assertEqual(raised.exception.code, "unknown_app")

        text, info = registry.unregister_app(
            self._app_c_text(), "hello", missing_ok=True
        )
        self.assertFalse(info["changed"])
        self.assertEqual(text, self._app_c_text())
        self.assertEqual(info["warnings"], ['app "hello" was not registered'])

    def test_invalid_registry_reports_domain_error(self) -> None:
        with self.assertRaises(common.AppError) as raised:
            registry.register_app("void app_create(void) {}\n", "hello")
        self.assertEqual(raised.exception.code, "app_registry_invalid")

    def test_duplicate_entry_conflict(self) -> None:
        text = self._app_c_text().replace(
            '    {"spectrum", spectrum_create},\n',
            '    {"spectrum", spectrum_create},\n'
            '    {"spectrum", spectrum_create},\n',
        )
        with self.assertRaises(common.AppError) as raised:
            registry.unregister_app(text, "spectrum")
        self.assertEqual(raised.exception.code, "app_conflict")

    def test_empty_apps_table_allows_the_first_registration(self) -> None:
        text = self._app_c_text()
        for row in (
            '    {"coffee", coffee_create},\n',
            '    {"xiaohongshu", xhs_page_create},\n',
            '    {"spectrum", spectrum_create},\n',
        ):
            text = text.replace(row, "")
        registered, changed = registry.register_app(text, "hello")
        self.assertTrue(changed)
        self.assertEqual(
            registry.parse_app_entries(registered),
            [("hello", "hello_create")],
        )

    def test_first_entry_is_recorded_and_compared_not_hardcoded(self) -> None:
        original = self._app_c_text()
        self.assertEqual(registry.parse_app_entries(original)[0][0], "coffee")
        registered, _ = registry.register_app(original, "hello")
        self.assertEqual(registry.parse_app_entries(registered)[0][0], "coffee")
        restored, _ = registry.unregister_app(registered, "hello")
        self.assertEqual(restored, original)

        renamed = original.replace(
            '    {"coffee", coffee_create},\n'
            '    {"xiaohongshu", xhs_page_create},',
            '    {"espresso", coffee_create},\n'
            '    {"xiaohongshu", xhs_page_create},',
        )
        escalated, changed = registry.register_app(renamed, "hello")
        self.assertTrue(changed)
        self.assertEqual(
            registry.parse_app_entries(escalated)[0][0], "espresso"
        )
        with self.assertRaises(common.AppError) as raised:
            registry.unregister_app(escalated, "espresso")
        self.assertIn("espresso must stay the first", raised.exception.message)


class ScaffoldSeamTest(_TempRepo):
    def test_dry_run_reports_without_writing(self) -> None:
        original = self._app_c_text()
        result = scaffold.scaffold_app(self.root, "hello", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(
            result["created"],
            [
                "user/app/hello/hello.h",
                "user/app/hello/hello.c",
                "user/scenarios/hello.json",
            ],
        )
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertEqual(self._app_c_text(), original)

    def test_force_keeps_existing_extra_files(self) -> None:
        app_dir = self.root / "user/app/hello"
        app_dir.mkdir()
        (app_dir / "keep.txt").write_text("keep\n", encoding="utf-8")
        scaffold.scaffold_app(self.root, "hello", force=True)
        self.assertTrue((app_dir / "keep.txt").is_file())
        self.assertTrue((app_dir / "hello.c").is_file())


class PolicySeamTest(_TempRepo):
    def test_derived_reserved_names_cover_all_sources(self) -> None:
        (self.root / "user/app/gamma").mkdir()
        self._write_scenario("promo", "promo")
        self.app_c.write_text(
            self._app_c_text()
            + 'static const char * url = "http://example.test/x";\n'
            + 'static const char * alias = "latte";\n'
            + '/* "mocha" is only mentioned in a comment */\n',
            encoding="utf-8",
        )
        names, _targets = policy._reserved_state(self.root)
        for expected in (
            "coffee",
            "xiaohongshu",
            "spectrum",
            "xhs",
            "gamma",
            "promo",
            "latte",
        ):
            self.assertIn(expected, names)
        self.assertNotIn("mocha", names)

    def test_reserved_check_keeps_existing_create_paths(self) -> None:
        (self.root / "user/app/gamma").mkdir()
        self._write_scenario("promo", "promo")
        self.app_c.write_text(
            self._app_c_text()
            + 'static const char * alias = "latte";\n',
            encoding="utf-8",
        )
        # Deletion policy names are always reserved, even with no target.
        self.assertTrue(policy.is_reserved_create_name(self.root, "coffee"))
        self.assertTrue(policy.is_reserved_create_name(self.root, "xhs"))
        # Derived identities with an existing target keep app_exists/--force.
        self.assertFalse(policy.is_reserved_create_name(self.root, "gamma"))
        self.assertFalse(policy.is_reserved_create_name(self.root, "promo"))
        # A literal-only alias has no other target, so it is reserved.
        self.assertTrue(policy.is_reserved_create_name(self.root, "latte"))

    def test_scenario_declared_names_keep_the_existing_create_path(self) -> None:
        path = self.root / "user/scenarios/custom.json"
        path.write_text(
            json.dumps({
                "schema": "lvgl-ai-scenario-v1",
                "name": "promo",
                "app": "coffee",
                "steps": [{"type": "wait", "ms": 16}],
            }),
            encoding="utf-8",
        )
        self.assertIn("promo", policy._reserved_state(self.root)[0])
        self.assertFalse(policy.is_reserved_create_name(self.root, "promo"))


class ScaffoldPolicyTest(_TempRepo):
    def _error(self, name: str, **kwargs) -> common.AppError:
        with self.assertRaises(common.AppError) as raised:
            scaffold.scaffold_app(self.root, name, **kwargs)
        return raised.exception

    def test_reserved_names_keep_exact_code_and_message(self) -> None:
        for name in (
            "coffee",
            "xiaohongshu",
            "spectrum",
            "demo",
            "app",
            "settings",
            "xhs",
        ):
            with self.subTest(name=name):
                error = self._error(name)
                self.assertEqual(error.code, "name_reserved")
                self.assertEqual(
                    error.message, f'name "{name}" is reserved'
                )

    def test_duplicate_and_force_keep_existing_results(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        error = self._error("hello")
        self.assertEqual(error.code, "app_exists")
        scaffold.scaffold_app(self.root, "hello", force=True)

    def test_recreating_after_delete_is_allowed(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        trash.delete_app(self.root, "hello")
        result = scaffold.scaffold_app(self.root, "hello")
        self.assertEqual(result["action"], "create")
        self.assertIn(
            "hello",
            [name for name, _ in registry.parse_app_entries(self._app_c_text())],
        )

    def test_literal_alias_is_reserved_without_a_static_list(self) -> None:
        self.app_c.write_text(
            self._app_c_text()
            + 'static const char * alias = "latte";\n',
            encoding="utf-8",
        )
        error = self._error("latte")
        self.assertEqual(error.code, "name_reserved")


class GuardSeamTest(_TempRepo):
    def test_scaffold_aborts_when_app_c_changes_before_write(self) -> None:
        original = self.app_c.read_bytes()
        real_register = registry.register_app

        def tamper(text: str, name: str):
            result = real_register(text, name)
            self.app_c.write_bytes(self.app_c.read_bytes() + b"// external\n")
            return result

        with mock.patch.object(
            registry, "register_app", side_effect=tamper
        ):
            with self.assertRaises(common.AppError) as raised:
                scaffold.scaffold_app(self.root, "hello")
        self.assertEqual(raised.exception.code, "app_conflict")
        self.assertIsInstance(raised.exception, common.AppCChanged)
        self.assertIn("changed on disk", raised.exception.message)
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertFalse((self.root / "user/scenarios/hello.json").exists())
        self.assertEqual(self.app_c.read_bytes(), original + b"// external\n")

    def test_delete_aborts_and_rolls_back_when_app_c_changes(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        real_unregister = registry.unregister_app

        def tamper(text: str, name: str, **kwargs):
            result = real_unregister(text, name, **kwargs)
            self.app_c.write_bytes(self.app_c.read_bytes() + b"// external\n")
            return result

        with mock.patch.object(
            registry, "unregister_app", side_effect=tamper
        ):
            with self.assertRaises(common.AppError) as raised:
                trash.delete_app(self.root, "hello")
        self.assertEqual(raised.exception.code, "app_conflict")
        self.assertIsInstance(raised.exception, common.AppCChanged)
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertIn(b"// external", self.app_c.read_bytes())
        self.assertIn(
            "hello",
            [name for name, _ in registry.parse_app_entries(self._app_c_text())],
        )

    def test_restore_aborts_and_rolls_back_when_app_c_changes(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        deleted = trash.delete_app(self.root, "hello")
        real_move = common._move_path

        def tamper(source: Path, destination: Path) -> None:
            real_move(source, destination)
            self.app_c.write_bytes(self.app_c.read_bytes() + b"// external\n")

        with mock.patch.object(common, "_move_path", side_effect=tamper):
            with self.assertRaises(common.AppError) as raised:
                trash.restore_app(self.root, deleted["trash_id"])
        self.assertEqual(raised.exception.code, "app_conflict")
        self.assertIsInstance(raised.exception, common.AppCChanged)
        trash_dir = self.root / deleted["trash_dir"]
        self.assertTrue((trash_dir / "app/hello.c").is_file())
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertIn(b"// external", self.app_c.read_bytes())
        self.assertNotIn(
            "hello",
            [name for name, _ in registry.parse_app_entries(self._app_c_text())],
        )


class TrashSeamTest(_TempRepo):
    def test_meta_validation_rejects_bad_schema_and_scenarios(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        deleted = trash.delete_app(self.root, "hello")
        meta_path = self.root / deleted["trash_dir"] / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        meta["schema"] = "other"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaises(common.AppError) as raised:
            trash.restore_app(self.root, deleted["trash_id"])
        self.assertEqual(raised.exception.code, "invalid_trash")

        meta["schema"] = common.TRASH_SCHEMA
        meta["scenarios"] = ["../escape.json"]
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaises(common.AppError) as raised:
            trash.restore_app(self.root, deleted["trash_id"])
        self.assertEqual(raised.exception.code, "invalid_trash")

    def test_trash_id_guard_and_missing_entry(self) -> None:
        with self.assertRaises(common.AppError) as raised:
            trash.restore_app(self.root, "../../escape")
        self.assertEqual(raised.exception.code, "invalid_trash")
        self.assertIsInstance(raised.exception, trash.InvalidTrashId)
        with self.assertRaises(common.AppError) as raised:
            trash.restore_app(self.root, "20260101-000000-deadbeef")
        self.assertEqual(raised.exception.code, "unknown_trash")

    def test_purge_requires_confirmation_and_reports_missing(self) -> None:
        with self.assertRaises(common.AppError) as raised:
            trash.permanently_delete(
                self.root, "20260101-000000-deadbeef"
            )
        self.assertEqual(raised.exception.code, "confirmation_required")
        with self.assertRaises(common.AppError) as raised:
            trash.permanently_delete(
                self.root, "20260101-000000-deadbeef", confirm=True
            )
        self.assertEqual(raised.exception.code, "unknown_trash")

    def test_list_trash_marks_invalid_entries(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        deleted = trash.delete_app(self.root, "hello")
        meta_path = self.root / deleted["trash_dir"] / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["name"] = "../evil"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        entries = trash.list_trash(self.root)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["valid"])
        self.assertTrue(entries[0]["error"])


class ViewsSeamTest(_TempRepo):
    def test_scenario_index_records_invalid_files(self) -> None:
        self._write_scenario("good", "coffee")
        (self.root / "user/scenarios/bad.json").write_text(
            "{", encoding="utf-8"
        )
        index = views.scenario_index(self.root)
        by_name = {item["basename"]: item for item in index}
        self.assertTrue(by_name["good.json"]["valid"])
        self.assertEqual(by_name["good.json"]["app"], "coffee")
        self.assertFalse(by_name["bad.json"]["valid"])
        self.assertTrue(by_name["bad.json"]["error"])

    def test_scenarios_for_app_and_recent_kinds(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        self.assertEqual(
            [path.name for path in views.scenarios_for_app(self.root, "hello")],
            ["hello.json"],
        )
        recent = views.recent_apps(self.root, limit=50)
        kinds = {entry["path"]: entry["kind"] for entry in recent}
        self.assertEqual(kinds["user/app/app.c"], "registration")
        self.assertEqual(kinds["user/app/hello/hello.c"], "app")
        self.assertEqual(kinds["user/scenarios/hello.json"], "scenario")

        deleted = trash.delete_app(self.root, "hello")
        recent = views.recent_apps(self.root, limit=50)
        kinds = {entry["path"]: entry["kind"] for entry in recent}
        self.assertEqual(
            kinds[f"{deleted['trash_dir']}/meta.json"], "trash"
        )


class CommonSeamTest(_TempRepo):
    def test_source_roundtrip_preserves_bom_and_crlf(self) -> None:
        data = b"\xef\xbb\xbfone\r\ntwo\r\n"
        _, text, bom, eol = common._read_source(
            self._write_bytes(data, "source.c")
        )
        self.assertTrue(bom)
        self.assertEqual(eol, "\r\n")
        self.assertEqual(common._encode_source(text, bom, eol), data)

    def test_ensure_unchanged_flags_missing_file(self) -> None:
        with self.assertRaises(common.AppCChanged) as raised:
            common._ensure_unchanged(self.root / "missing.c", b"expected")
        self.assertEqual(raised.exception.code, "app_conflict")

    def test_relative_outside_root_returns_posix_path(self) -> None:
        outside = Path(tempfile.gettempdir()) / "outside.txt"
        self.assertEqual(
            common._relative(outside, self.root), outside.as_posix()
        )

    def _write_bytes(self, data: bytes, name: str) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path


if __name__ == "__main__":
    unittest.main()
