from __future__ import annotations

import paths

import inspect
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

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

DOCS_DIR = paths.REPO_ROOT / "docs"
SIFLI_PAGE = paths.REPO_ROOT / "chip-adapt" / "docs" / "sifli.html"
SKILL_PAGE = DOCS_DIR / "skill" / "SKILL.md"

EXPECTED_CONTROL_EXPORTS = {
    "BuildError": BuildError,
    "EngineNotFound": EngineNotFound,
    "LatError": LatError,
    "LinkError": LinkError,
    "ProtocolError": ProtocolError,
    "Recording": Recording,
    "Runtime": Runtime,
    "RuntimeCrash": RuntimeCrash,
    "ScenarioError": ScenarioError,
    "ToolError": ToolError,
    "session_index": session_index,
}

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


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.hrefs.append(str(values["href"]))


def broken_links(page: Path, base_dir: Path, repo_root: Path) -> list[str]:
    parser = _PageParser()
    parser.feed(page.read_text(encoding="utf-8"))
    parser.close()
    errors: list[str] = []
    for href in parser.hrefs:
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = href.split("#", 1)[0]
        if not target:
            continue
        resolved = (base_dir / target).resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            errors.append(f"{page.name}: link leaves the repo: {href}")
            continue
        if not resolved.exists():
            errors.append(f"{page.name}: missing link target: {href}")
    return errors


def _markdown_links(path: Path) -> list[str]:
    return re.findall(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8"))


class PublicSurfaceTest(unittest.TestCase):
    def test_control_exports_are_the_public_surface(self) -> None:
        self.assertEqual(
            control.__all__, list(EXPECTED_CONTROL_EXPORTS)
        )
        for name, expected in EXPECTED_CONTROL_EXPORTS.items():
            with self.subTest(name=name):
                self.assertIs(getattr(control, name), expected)

    def test_scenario_and_lat_error_alias(self) -> None:
        self.assertTrue(callable(scenario.play_scenario))
        self.assertIs(ToolError, LatError)
        self.assertEqual(paths.TOOL_VERSION, "0.2.3")

    def test_apps_lifecycle_signatures_are_unchanged(self) -> None:
        for name, signature in EXPECTED_APPS_SIGNATURES.items():
            with self.subTest(name=name):
                self.assertIn(name, apps_module.__all__)
                self.assertEqual(
                    str(inspect.signature(getattr(apps_module, name))),
                    signature,
                )


class EntryPageLinksTest(unittest.TestCase):
    def test_sifli_page_links_resolve(self) -> None:
        self.assertTrue(SIFLI_PAGE.is_file())
        self.assertEqual(
            broken_links(
                SIFLI_PAGE,
                base_dir=SIFLI_PAGE.parent,
                repo_root=paths.REPO_ROOT,
            ),
            [],
        )

    def test_skill_markdown_links_resolve(self) -> None:
        self.assertTrue(SKILL_PAGE.is_file())
        for href in _markdown_links(SKILL_PAGE):
            if href.startswith(("http://", "https://", "#")):
                continue
            target = (SKILL_PAGE.parent / href.split("#", 1)[0]).resolve()
            self.assertTrue(target.exists(), f"missing SKILL link: {href}")


if __name__ == "__main__":
    unittest.main()
