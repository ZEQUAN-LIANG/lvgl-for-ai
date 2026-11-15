from __future__ import annotations

import importlib.util
import inspect
import unittest

import paths
from control import (
    BuildError,
    EngineNotFound,
    LatError,
    LinkError,
    ProtocolError,
    Recording,
    Runtime,
    RuntimeCrash,
    ScenarioError,
    ToolError,
    session_index,
)
import appmgr as apps_module
import control
import scenario

EXPECTED_CONTROL_EXPORTS = [
    "BuildError",
    "EngineNotFound",
    "LatError",
    "LinkError",
    "ProtocolError",
    "Recording",
    "Runtime",
    "RuntimeCrash",
    "ScenarioError",
    "ToolError",
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
        ("lvgl_ai",),
        ("lvgl_ai", "core"),
        ("lvgl_ai", "control"),
        ("lvgl_ai", "web"),
        ("lvgl_ai", "apps"),
        ("lvgl_ai", "region"),
        ("lvgl_ai", "web", "server"),
        ("lvgl_ai", "web", "stream"),
        ("lvgl_ai", "web", "page"),
        ("lvgl_ai", "web", "region_images"),
    )
)


class PublicExportTest(unittest.TestCase):
    def test_control_exports_are_the_public_surface(self) -> None:
        self.assertEqual(control.__all__, EXPECTED_CONTROL_EXPORTS)
        for name in EXPECTED_CONTROL_EXPORTS:
            with self.subTest(name=name):
                self.assertTrue(hasattr(control, name))

    def test_scenario_and_paths_carry_the_remaining_public_api(self) -> None:
        self.assertTrue(callable(scenario.play_scenario))
        self.assertIs(ToolError, LatError)
        self.assertIs(control.LatError, control.ToolError)
        self.assertEqual(paths.TOOL_VERSION, "0.2.2")

    def test_control_errors_are_the_same_objects(self) -> None:
        self.assertIs(Runtime, control.Runtime)
        self.assertIs(Recording, control.Recording)
        self.assertIs(BuildError, control.BuildError)
        self.assertIs(EngineNotFound, control.EngineNotFound)
        self.assertIs(LinkError, control.LinkError)
        self.assertIs(ProtocolError, control.ProtocolError)
        self.assertIs(RuntimeCrash, control.RuntimeCrash)
        self.assertIs(ScenarioError, control.ScenarioError)
        self.assertIs(session_index, control.session_index)


class AppsLifecycleContractTest(unittest.TestCase):
    def test_apps_lifecycle_signatures_are_unchanged(self) -> None:
        for name, signature in EXPECTED_APPS_SIGNATURES.items():
            with self.subTest(name=name):
                self.assertIn(name, apps_module.__all__)
                self.assertEqual(
                    str(inspect.signature(getattr(apps_module, name))),
                    signature,
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

    def test_tool_root_is_not_a_package(self) -> None:
        try:
            spec = importlib.util.find_spec("console")
        except ModuleNotFoundError:
            spec = None
        self.assertTrue(spec is None or spec.loader is None)


if __name__ == "__main__":
    unittest.main()
