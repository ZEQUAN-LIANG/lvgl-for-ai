from __future__ import annotations

import paths

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import appmgr as app_domain
from appmgr import common, discovery, policy, scaffold, trash, views
from scenario import scenario_index
from scripts.tests.support import symlinked_file

CONSOLE_ROOT = paths.CONSOLE_ROOT
REPO_ROOT = CONSOLE_ROOT.parent
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

    def _add_app(
        self, name: str, entry: str | None = None, *, default: bool = False
    ) -> Path:
        """Create an app directory.

        Without *entry* the directory follows the ``<name>_create``
        convention and carries no metadata, like a plain app in the repo.
        Passing *entry* writes a per-app ``app.json``, which is how an app
        deviates from the convention.
        """

        app_dir = self.root / "user" / "app" / name
        app_dir.mkdir(exist_ok=True)
        if entry is not None:
            (app_dir / discovery.METADATA_NAME).write_text(
                json.dumps({"entry": entry}), encoding="utf-8"
            )
        else:
            (app_dir / f"{name}.c").write_text(
                f"void {name}_create(void) {{}}\n", encoding="utf-8"
            )
        if default:
            self._set_default(name)
        return app_dir

    def _set_default(self, name: str) -> None:
        (self.root / "user" / "app" / discovery.METADATA_NAME).write_text(
            json.dumps({"default": name}), encoding="utf-8"
        )

    def _write_scenario(self, name: str, app: str) -> Path:
        path = self.root / "user" / "scenarios" / f"{name}.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-scenario-v1",
                    "name": name,
                    "app": app,
                    "steps": [{"type": "wait", "ms": 16}],
                }
            ),
            encoding="utf-8",
        )
        return path


class PublicSurfaceTest(unittest.TestCase):
    def test_lifecycle_exports_are_the_seam_functions(self) -> None:
        self.assertIs(app_domain.AppError, common.AppError)
        self.assertIs(app_domain.resolve_repo_root, common.resolve_repo_root)
        self.assertIs(app_domain.is_protected_name, policy.is_protected_name)
        self.assertIs(app_domain.scaffold_app, scaffold.scaffold_app)
        self.assertIs(app_domain.list_apps, views.list_apps)
        self.assertIs(app_domain.app_tree, views.app_tree)
        self.assertIs(app_domain.recent_apps, views.recent_apps)
        self.assertIs(app_domain.list_trash, trash.list_trash)
        self.assertIs(app_domain.delete_app, trash.delete_app)
        self.assertIs(app_domain.restore_app, trash.restore_app)
        self.assertIs(app_domain.permanently_delete, trash.permanently_delete)

    def test_app_error_keeps_signature_but_not_http_status(self) -> None:
        error = common.AppError("name_reserved", "reserved", status=418)
        self.assertEqual(error.code, "name_reserved")
        self.assertEqual(error.message, "reserved")
        self.assertEqual(error.detail, {})
        self.assertFalse(hasattr(error, "status"))


class DiscoverySeamTest(_TempRepo):
    def test_directories_without_metadata_are_not_apps(self) -> None:
        self._add_app("hello")
        helper = self.root / "user" / "app" / "demo"
        helper.mkdir()
        (helper / "panel.c").write_text(
            "void app_panel_create(void) {}\n", encoding="utf-8"
        )
        entries, issues = discovery.scan_apps(self.root / "user" / "app")
        self.assertEqual([entry.name for entry in entries], ["hello"])
        self.assertEqual(issues, [])

    def test_invalid_metadata_is_reported(self) -> None:
        app_dir = self.root / "user" / "app" / "broken"
        app_dir.mkdir()
        (app_dir / discovery.METADATA_NAME).write_text(
            '{"entry": "not valid"}', encoding="utf-8"
        )
        entries, issues = discovery.scan_apps(self.root / "user" / "app")
        self.assertEqual(entries, [])
        self.assertEqual(len(issues), 1)
        self.assertIn("C identifier", issues[0].message)
        with self.assertRaises(discovery.DiscoveryError):
            discovery.discover_apps(self.root / "user" / "app")

    def test_registry_is_generated_from_metadata(self) -> None:
        self._add_app("coffee", default=True)
        self._add_app("hello")
        apps_dir = self.root / "user" / "app"
        target = discovery.write_registry(apps_dir)
        first = target.read_bytes()
        self.assertIn(
            b'{"coffee", coffee_create}', first
        )
        self.assertIn(b'{"hello", hello_create}', first)
        self.assertLess(
            first.index(b'{"coffee"'), first.index(b'{"hello"')
        )
        before = target.stat().st_mtime_ns
        discovery.write_registry(apps_dir)
        self.assertEqual(target.stat().st_mtime_ns, before)
        self._add_app("later")
        discovery.write_registry(apps_dir)
        self.assertIn(b'{"later", later_create}', target.read_bytes())

    def test_root_default_selects_the_first_app(self) -> None:
        self._add_app("one")
        self._add_app("two", default=True)
        entries = discovery.discover_apps(self.root / "user" / "app")
        self.assertEqual([entry.name for entry in entries], ["two", "one"])
        self.assertTrue(entries[0].default)
        self.assertFalse(entries[1].default)

    def test_unknown_root_default_is_reported(self) -> None:
        self._add_app("one")
        self._set_default("missing")
        _entries, issues = discovery.scan_apps(self.root / "user" / "app")
        self.assertEqual(len(issues), 1)
        self.assertIn("is not a discovered app", issues[0].message)
        with self.assertRaises(discovery.DiscoveryError):
            discovery.discover_apps(self.root / "user" / "app")

    def test_convention_directory_needs_no_metadata(self) -> None:
        self._add_app("plain")
        entries, issues = discovery.scan_apps(self.root / "user" / "app")
        self.assertEqual(issues, [])
        self.assertEqual([entry.name for entry in entries], ["plain"])
        self.assertEqual(entries[0].entry, "plain_create")

    def test_helper_directory_without_the_entry_symbol_is_not_an_app(
        self,
    ) -> None:
        self._add_app("plain")
        helper = self.root / "user" / "app" / "demo"
        helper.mkdir()
        (helper / "demo_compat.c").write_text(
            "void demo_harness_create(bool visible) {}\n", encoding="utf-8"
        )
        entries, issues = discovery.scan_apps(self.root / "user" / "app")
        self.assertEqual(issues, [])
        self.assertEqual([entry.name for entry in entries], ["plain"])


class PolicySeamTest(_TempRepo):
    def test_default_app_follows_root_metadata(self) -> None:
        self._add_app("coffee", default=True)
        self._add_app("spectrum")
        self.assertTrue(policy.is_protected_name(self.root, "coffee"))
        self.assertFalse(policy.is_protected_name(self.root, "spectrum"))

        self._set_default("spectrum")
        self.assertTrue(policy.is_protected_name(self.root, "spectrum"))
        self.assertFalse(policy.is_protected_name(self.root, "coffee"))

    def test_reserved_names_cover_all_sources(self) -> None:
        self._add_app("coffee", default=True)
        self._add_app("alias_owner")
        (self.root / "user" / "app" / "gamma").mkdir()
        self._write_scenario("promo", "promo")
        names, _targets = policy._reserved_state(self.root)
        for expected in (
            "coffee",
            "alias_owner",
            "gamma",
            "promo",
            "app",
        ):
            self.assertIn(expected, names)

    def test_reserved_check_keeps_existing_create_paths(self) -> None:
        self._add_app("coffee", default=True)
        self._add_app("alias_owner")
        (self.root / "user" / "app" / "gamma").mkdir()
        self._write_scenario("promo", "promo")
        self.assertTrue(policy.is_reserved_create_name(self.root, "coffee"))
        self.assertFalse(policy.is_reserved_create_name(self.root, "gamma"))
        self.assertFalse(policy.is_reserved_create_name(self.root, "promo"))


class PolicyScopeDocumentationTest(unittest.TestCase):
    def test_module_docstring_marks_derived_policy(self) -> None:
        doc = policy.__doc__ or ""
        self.assertIn("no hand-maintained app registry", doc)
        self.assertIn("discovered default app", doc)
        self.assertNotIn("PROTECTED_APPS", doc)
        self.assertNotIn("PROTECTED_SCENARIOS", doc)


class ScaffoldPolicyTest(_TempRepo):
    def _error(self, name: str, **kwargs) -> common.AppError:
        with self.assertRaises(common.AppError) as raised:
            scaffold.scaffold_app(self.root, name, **kwargs)
        return raised.exception

    def test_reserved_names_keep_exact_code_and_message(self) -> None:
        self._add_app("coffee", default=True)
        (self.root / "user" / "scenarios" / "settings.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-scenario-v1",
                    "name": "settings",
                    "steps": [{"type": "wait", "ms": 16}],
                }
            ),
            encoding="utf-8",
        )
        for name in ("coffee", "app", "settings"):
            with self.subTest(name=name):
                error = self._error(name)
                self.assertEqual(error.code, "name_reserved")
                self.assertEqual(error.message, f'name "{name}" is reserved')

    def test_scaffold_writes_no_metadata_and_keeps_an_existing_one(
        self,
    ) -> None:
        result = scaffold.scaffold_app(self.root, "hello")
        self.assertNotIn(
            "app.json", " ".join(result["created"])
        )
        self.assertFalse(
            (self.root / "user" / "app" / "hello" / "app.json").exists()
        )

        metadata = self.root / "user" / "app" / "hello" / "app.json"
        metadata.write_text(
            json.dumps({"entry": "hello_create"}), encoding="utf-8"
        )
        scaffold.scaffold_app(self.root, "hello", force=True)
        self.assertEqual(
            json.loads(metadata.read_text(encoding="utf-8"))["entry"],
            "hello_create",
        )

    def test_force_refuses_metadata_pointing_elsewhere(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        metadata = self.root / "user" / "app" / "hello" / "app.json"
        metadata.write_text(
            json.dumps({"entry": "renamed_create"}), encoding="utf-8"
        )
        error = self._error("hello", force=True)
        self.assertEqual(error.code, "app_conflict")

    def test_duplicate_and_force_keep_existing_results(self) -> None:
        original = self.app_c.read_bytes()
        scaffold.scaffold_app(self.root, "hello")
        self.assertEqual(self.app_c.read_bytes(), original)
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
            [
                entry.name
                for entry in discovery.scan_apps(
                    self.root / "user" / "app"
                )[0]
            ],
        )


class GuardSeamTest(_TempRepo):
    def test_delete_rolls_back_when_a_move_fails(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        scenario = self.root / "user/scenarios/hello.json"
        real_move = common._move_path
        calls = {"count": 0}

        def flaky(source: Path, destination: Path) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated move failure")
            real_move(source, destination)

        with mock.patch.object(common, "_move_path", side_effect=flaky):
            with self.assertRaises(common.AppError) as raised:
                trash.delete_app(self.root, "hello")
        self.assertEqual(raised.exception.code, "app_io_error")
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertTrue(scenario.is_file())


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
            trash.permanently_delete(self.root, "20260101-000000-deadbeef")
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
        index = scenario_index(self.root)
        by_name = {item["basename"]: item for item in index}
        self.assertTrue(by_name["good.json"]["valid"])
        self.assertEqual(by_name["good.json"]["app"], "coffee")
        self.assertFalse(by_name["bad.json"]["valid"])
        self.assertTrue(by_name["bad.json"]["error"])

    def test_scenario_index_skips_symlinked_scenarios(self) -> None:
        self._write_scenario("good", "coffee")
        target = Path(self._tmp.name) / "linked-target.json"
        target.write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-scenario-v1",
                    "name": "linked",
                    "app": "coffee",
                    "steps": [{"type": "wait", "ms": 16}],
                }
            ),
            encoding="utf-8",
        )
        symlinked_file(
            self, self.root / "user" / "scenarios" / "linked.json", target
        )

        index = scenario_index(self.root)
        self.assertEqual([item["basename"] for item in index], ["good.json"])
        self.assertEqual(
            [
                path.name
                for path in views.scenarios_for_app(self.root, "coffee")
            ],
            ["good.json"],
        )

    def test_scenarios_for_app_and_recent_kinds(self) -> None:
        scaffold.scaffold_app(self.root, "hello")
        self.assertEqual(
            [
                path.name
                for path in views.scenarios_for_app(self.root, "hello")
            ],
            ["hello.json"],
        )
        recent = views.recent_apps(self.root, limit=50)
        kinds = {entry["path"]: entry["kind"] for entry in recent}
        self.assertEqual(kinds["user/app/app.c"], "entrypoint")
        self.assertEqual(kinds["user/app/hello/hello.c"], "app")
        self.assertEqual(kinds["user/scenarios/hello.json"], "scenario")

        deleted = trash.delete_app(self.root, "hello")
        recent = views.recent_apps(self.root, limit=50)
        kinds = {entry["path"]: entry["kind"] for entry in recent}
        self.assertEqual(kinds[f"{deleted['trash_dir']}/meta.json"], "trash")


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
