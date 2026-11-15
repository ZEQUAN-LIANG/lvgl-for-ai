
from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import lvgl_ai
import lvgl_ai.apps as apps
import lvgl_ai.control as control

EXPECTED_EXPORTS = [
    "BuildError",
    "EngineNotFound",
    "LatError",
    "LinkError",
    "ProtocolError",
    "Recording",
    "Runtime",
    "RuntimeCrash",
    "ScenarioError",
    "__version__",
    "play_scenario",
    "session_index",
]

EXPECTED_APPS_SIGNATURES = {
    "list_apps": "(repo_root: 'str | Path') -> 'dict[str, Any]'",
    "app_tree": (
        "(repo_root: 'str | Path', name: 'str', *, "
        "max_entries: 'int' = 400, max_depth: 'int' = 6) -> 'dict[str, Any]'"
    ),
    "recent_apps": (
        "(repo_root: 'str | Path', *, limit: 'int' = 8) -> 'list[dict[str, Any]]'"
    ),
    "list_trash": "(repo_root: 'str | Path') -> 'list[dict[str, Any]]'",
    "scaffold_app": (
        "(repo_root: 'str | Path', name: 'str', *, "
        "force: 'bool' = False, dry_run: 'bool' = False) -> 'dict[str, Any]'"
    ),
    "delete_app": "(repo_root: 'str | Path', name: 'str') -> 'dict[str, Any]'",
    "restore_app": "(repo_root: 'str | Path', trash_id: 'str') -> 'dict[str, Any]'",
    "permanently_delete": (
        "(repo_root: 'str | Path', trash_id: 'str', *, "
        "confirm: 'bool' = False) -> 'dict[str, Any]'"
    ),
}

LEGACY_MODULES = tuple(
    ".".join(parts)
    for parts in (
        ("lvgl_ai", "core"),
        ("lvgl_ai", "core", "build"),
        ("lvgl_ai", "core", "build_plan"),
        ("lvgl_ai", "core", "engine_link"),
        ("lvgl_ai", "core", "errors"),
        ("lvgl_ai", "core", "input"),
        ("lvgl_ai", "core", "keys"),
        ("lvgl_ai", "core", "recording"),
        ("lvgl_ai", "core", "retention"),
        ("lvgl_ai", "core", "runtime"),
        ("lvgl_ai", "core", "session"),
        ("lvgl_ai", "core", "session_schema"),
        ("lvgl_ai", "web", "server"),
        ("lvgl_ai", "web", "stream"),
        ("lvgl_ai", "web", "page"),
        ("lvgl_ai", "web", "region_images"),
        ("lvgl_ai", "region"),
    )
)


class PublicExportTest(unittest.TestCase):
    def test_top_level_exports_are_unchanged(self) -> None:
        self.assertEqual(lvgl_ai.__all__, EXPECTED_EXPORTS)
        for name in EXPECTED_EXPORTS:
            with self.subTest(name=name):
                self.assertTrue(hasattr(lvgl_ai, name))

    def test_lat_error_remains_the_tool_error_alias(self) -> None:
        self.assertIs(lvgl_ai.LatError, lvgl_ai.ToolError)
        self.assertIs(control.LatError, control.ToolError)
        self.assertNotIn("ToolError", lvgl_ai.__all__)
        self.assertIn("ToolError", control.__all__)


class AppsLifecycleContractTest(unittest.TestCase):
    def test_apps_lifecycle_signatures_are_unchanged(self) -> None:
        for name, signature in EXPECTED_APPS_SIGNATURES.items():
            with self.subTest(name=name):
                self.assertIn(name, apps.__all__)
                self.assertEqual(
                    str(inspect.signature(getattr(apps, name))), signature
                )


class LegacyImportPathsRemovedTest(unittest.TestCase):
    def test_legacy_modules_are_not_importable(self) -> None:
        for name in LEGACY_MODULES:
            with self.subTest(name=name):
                try:
                    spec = importlib.util.find_spec(name)
                except ModuleNotFoundError:
                    spec = None
                self.assertTrue(
                    spec is None or spec.loader is None,
                    f"legacy module still importable: {name}",
                )


if __name__ == "__main__":
    unittest.main()
