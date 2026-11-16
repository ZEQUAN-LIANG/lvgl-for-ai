from __future__ import annotations

import paths

import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

DOCS_DIR = paths.REPO_ROOT / "docs"
SIFLI_PAGE = paths.REPO_ROOT / "chip-adapt" / "docs" / "sifli.html"
SKILL_PAGE = DOCS_DIR / "skill" / "SKILL.md"


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.hrefs.append(str(values["href"]))


def _parse_page(path: Path) -> _PageParser:
    parser = _PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def broken_links(page: Path, base_dir: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    for href in _parse_page(page).hrefs:
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
    text = path.read_text(encoding="utf-8")
    return re.findall(r"\]\(([^)\s]+)\)", text)


class DocsLinkParserTest(unittest.TestCase):
    def test_anchor_hrefs_are_collected(self) -> None:
        parser = _PageParser()
        parser.feed('<a href="one.md">one</a><a href="two.md#part">two</a>')
        parser.close()
        self.assertEqual(parser.hrefs, ["one.md", "two.md#part"])


class DocsLinkPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo_root = Path(self._tmp.name)
        self.docs_dir = self.repo_root / "docs"
        self.docs_dir.mkdir()
        self.page = self.docs_dir / "page.html"

    def _check(self, href: str) -> list[str]:
        self.page.write_text(f'<a href="{href}">link</a>', encoding="utf-8")
        return broken_links(
            self.page, base_dir=self.docs_dir, repo_root=self.repo_root
        )

    def test_existing_repo_link_passes(self) -> None:
        (self.docs_dir / "target.md").write_text("target", encoding="utf-8")
        self.assertEqual(self._check("target.md"), [])

    def test_missing_repo_link_is_reported(self) -> None:
        errors = self._check("missing.md")
        self.assertEqual(len(errors), 1)
        self.assertIn("missing.md", errors[0])


class DocsEntryPageTest(unittest.TestCase):
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
