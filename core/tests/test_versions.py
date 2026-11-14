"""The LVGL version matrix comes only from ``meta/versions.json``.

Every consumer keeps its own rendering (tuples, tags, CLI choices), but the
membership and flags must follow the version index.  The synthetic index below
uses versions that do not exist in the real repository, so a consumer that
still carries a hard-coded list fails here.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

import assets as assets_cli
from lvgl_ai import versions
from lvgl_ai.assets import version as asset_version
from tools import check_api_nav, fetch_lvgl, release_all

INDEX_SCHEMA = "lvgl-verify-loop-versions-v1"

SYNTHETIC_INDEX = {
    "schema": INDEX_SCHEMA,
    "default": "9.7",
    "versions": {
        "9.7": {
            "tag": "v9.7.0",
            "intro": True,
            "description": "synthetic preview",
            "sdk": True,
            "bundled": True,
            "legacy": False,
        },
        "7.0": {
            "tag": "v7.0.0",
            "intro": False,
            "description": "synthetic legacy",
            "sdk": True,
            "bundled": False,
            "legacy": True,
        },
    },
}


def write_index(root: Path) -> Path:
    meta = root / "meta"
    meta.mkdir(parents=True)
    path = meta / "versions.json"
    path.write_text(
        json.dumps(SYNTHETIC_INDEX, indent=2) + "\n", encoding="utf-8"
    )
    return path


class VersionIndexTest(unittest.TestCase):
    def test_membership_and_flags_follow_the_index(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_index(root)
            self.assertEqual(versions.supported(root), ("9.7", "7.0"))
            self.assertEqual(versions.default(root), "9.7")
            self.assertEqual(versions.intro(root), ("9.7",))
            self.assertEqual(versions.legacy(root), ("7.0",))
            self.assertEqual(versions.bundled(root), ("9.7",))
            self.assertEqual(
                versions.tags(root),
                {"9.7": "v9.7.0", "7.0": "v7.0.0"},
            )

    def test_invalid_default_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = write_index(root)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["default"] = "9.9"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(versions.VersionsError):
                versions.load(root)


class AssetVersionTest(unittest.TestCase):
    def test_supported_versions_come_from_the_index(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_index(root)
            (root / "sdk" / "9.7").mkdir(parents=True)
            (root / "sdk" / "9.6").mkdir()
            self.assertEqual(asset_version.available_versions(root), ["9.7"])
            self.assertEqual(
                asset_version.resolve_lvgl_version(root, "9.7"), "9.7"
            )
            with self.assertRaises(ValueError) as caught:
                asset_version.resolve_lvgl_version(root, "9.6")
            self.assertIn(
                "choose one of 7.0, 9.7", str(caught.exception)
            )

    def test_supported_constant_keeps_numeric_order(self) -> None:
        self.assertEqual(
            asset_version.SUPPORTED_VERSIONS,
            ("8.3", "8.4", "9.1", "9.4", "9.5", "9.6"),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_index(root)
            self.assertEqual(
                asset_version.supported_versions(root), ("7.0", "9.7")
            )

    def test_assets_cli_metavar_keeps_numeric_order(self) -> None:
        parser = assets_cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        font_help = subparsers.choices["font"].format_help()
        self.assertIn(
            "--lvgl auto|8.3|8.4|9.1|9.4|9.5|9.6", font_help
        )


class ToolListTest(unittest.TestCase):
    def test_release_all_lists_come_from_the_index(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_index(root)
            plan = release_all.version_plan(root)
            self.assertEqual(plan["supported"], ("9.7", "7.0"))
            self.assertEqual(plan["default"], "9.7")
            self.assertEqual(plan["intro"], ("9.7",))
            self.assertEqual(plan["legacy"], ("7.0",))
            self.assertEqual(plan["bundled"], ("9.7",))

    def test_api_nav_and_fetch_tags_use_the_package_index(self) -> None:
        self.assertEqual(
            check_api_nav.VERSIONS,
            ("9.6", "9.5", "9.4", "9.1", "8.4", "8.3"),
        )
        self.assertEqual(
            fetch_lvgl.TAGS,
            {
                "9.6": "v9.6.0",
                "9.5": "v9.5.0",
                "9.4": "v9.4.0",
                "9.1": "v9.1.0",
                "8.4": "v8.4.0",
                "8.3": "v8.3.11",
            },
        )


class PackageCopyTest(unittest.TestCase):
    def test_release_updates_only_the_package_copy(self) -> None:
        from tools import release

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source" / "versions.json"
            source.parent.mkdir()
            source.write_text(
                json.dumps(SYNTHETIC_INDEX, indent=2) + "\n", encoding="utf-8"
            )
            original = source.read_bytes()
            package = root / "package"
            (package / "meta").mkdir(parents=True)
            (package / "meta" / "versions.json").write_bytes(original)

            release.write_package_versions(package, tool_version="0.9.9")

            self.assertEqual(source.read_bytes(), original)
            payload = json.loads(
                (package / "meta" / "versions.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                payload["core"], {"version": "0.9.9", "platform": "win64"}
            )
            self.assertEqual(
                payload["versions"], SYNTHETIC_INDEX["versions"]
            )
            self.assertEqual(payload["default"], "9.7")


if __name__ == "__main__":
    unittest.main()
