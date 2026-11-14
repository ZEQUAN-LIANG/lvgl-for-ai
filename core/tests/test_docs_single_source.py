"""The docs index pages stay indexes, not copies of drifting facts.

``docs/app.html`` and ``docs/scenario-server.html`` must point at code or
README instead of restating the app list, HTTP routes, server constants or
scenario step vocabulary.  These tests pin that static invariant: every link
resolves, every symbol pointer names something in the linked file, and facts
owned by code do not reappear in the pages.
``docs/index.html`` is the entry page and ``chip-adapt/docs/sifli.html`` is a
capability page; both are link-checked only, so they may mention app names,
routes and constants as illustrative facts.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402
from lvgl_ai.apps import parse_app_entries  # noqa: E402
from lvgl_ai.scenario import SCENARIO_SCHEMA, STEP_TYPES  # noqa: E402
from lvgl_ai.web import live_session, routes, webapp, wire  # noqa: E402

DOCS_DIR = paths.REPO_ROOT / "docs"
SIFLI_PAGE = paths.REPO_ROOT / "chip-adapt" / "docs" / "sifli.html"
PAGE_NAMES = ("app.html", "scenario-server.html")
# index.html is the entry page and sifli.html is a capability page; neither is
# a fact index, so both are link-checked only.
LINK_PAGES = PAGE_NAMES + ("index.html", "sifli.html")


def _link_page(name: str) -> Path:
    if name == "sifli.html":
        return SIFLI_PAGE
    return DOCS_DIR / name


# Server constants whose values may not be copied into the docs.  Names may
# appear as symbol pointers; values may not.
CONSTANT_SOURCES = {
    webapp: (
        "DEFAULT_HOST",
        "DEFAULT_PORT",
        "MAX_BODY_BYTES",
        "PAGE_HEARTBEAT_TTL_S",
        "PAGE_CLOSE_GRACE_S",
        "MAX_DRAIN_BYTES",
        "CSP",
    ),
    live_session: (
        "LIVE_INPUT_STEP_MS",
        "LIVE_TEST_TICK_MS",
        "LIVE_TEST_INTERVAL_S",
        "LIVE_TICK_MS",
        "LIVE_TICK_INTERVAL_S",
    ),
    wire: ("PAGE_HEARTBEAT_INTERVAL_MS", "STREAM_MAGIC", "MAX_FRAME_BYTES"),
}
REGEX_CONSTANTS = ((webapp, "SESSION_ID_RE"), (webapp, "FILE_NAME_RE"))
ROUTE_PREFIXES = ("/api/", "/frames/", "/snapshots/", "/regions/")
LINE_POINTER = re.compile(
    r"\b[\w./-]+\.(?:c|h|py|md|json|html|txt|ndjson)\s*:\s*\d"
)
ANCHOR_POINTER = re.compile(r"#L\d+")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.texts: list[str] = []
        self.pointers: list[tuple[str | None, str]] = []
        self.last_href: str | None = None
        self.ptr_target: str | None = None
        self.ptr_parts: list[str] | None = None
        self.skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.last_href = str(values["href"])
            self.hrefs.append(self.last_href)
        classes = (values.get("class") or "").split()
        if tag == "span" and "ptr" in classes:
            self.ptr_target = self.last_href
            self.ptr_parts = []
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self.ptr_parts is not None:
            pointer = " ".join("".join(self.ptr_parts).split())
            if pointer:
                self.pointers.append((self.ptr_target, pointer))
            self.ptr_parts = None
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if self.ptr_parts is not None:
            self.ptr_parts.append(data)
        if self.skip:
            return
        text = " ".join(data.split())
        if text:
            self.texts.append(text)


def _parse_page(path: Path) -> _PageParser:
    parser = _PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


EXTERNAL_HREF_PREFIXES = ("#", "http://", "https://", "mailto:")
MISSING_DOWNLOAD_DIRS = (
    Path("chip-adapt") / "vendor" / "sifli-sdk",
)


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _optional_target(target: Path, repo_root: Path) -> bool:
    return any(
        _within(target, (repo_root / directory).resolve())
        for directory in MISSING_DOWNLOAD_DIRS
    )


def broken_links(
    page: Path, *, base_dir: Path, repo_root: Path
) -> list[str]:
    parser = _PageParser()
    parser.feed(page.read_text(encoding="utf-8"))
    parser.close()
    problems: list[str] = []
    for href in parser.hrefs:
        if href.startswith(EXTERNAL_HREF_PREFIXES):
            continue
        target = href.split("#", 1)[0]
        if not target:
            continue
        resolved = (base_dir / target).resolve()
        if _optional_target(resolved, repo_root):
            continue
        if not resolved.exists():
            problems.append(f"{page.name}: broken link {href!r} -> {resolved}")
    return problems


def _token_pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])" + re.escape(value) + r"(?![\w-])")


def _numeric_pattern(fact: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\d.])" + re.escape(fact) + r"(?![\d.])")


def _server_route_literals() -> tuple[str, ...]:
    source = Path(routes.__file__).read_text(encoding="utf-8")
    return tuple(
        sorted(
            set(
                re.findall(
                    r'"(/(?:api|frames|snapshots|regions)[^"]*)"', source
                )
            )
        )
    )


def _humanized_byte_facts(value: object) -> list[str]:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 1024 * 1024
        and value % (1024 * 1024) == 0
    ):
        return [f"{value // (1024 * 1024)} MiB"]
    return []


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
        self.page.write_text(
            f'<a href="{href}">link</a>', encoding="utf-8"
        )
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

    def test_sdk_download_link_may_be_absent(self) -> None:
        (self.repo_root / "chip-adapt" / "vendor" / "sifli-sdk").mkdir(
            parents=True
        )
        self.assertEqual(
            self._check("../chip-adapt/vendor/sifli-sdk/version.txt"), []
        )

class DocsEntryPageTest(unittest.TestCase):
    def test_index_page_is_link_checked(self) -> None:
        self.assertIn("index.html", LINK_PAGES)
        self.assertTrue((DOCS_DIR / "index.html").is_file())

    def test_index_page_links_to_the_index_pages(self) -> None:
        hrefs = set(_parse_page(DOCS_DIR / "index.html").hrefs)
        for name in PAGE_NAMES:
            self.assertIn(name, hrefs)
        self.assertIn("../core/SKILL.md", hrefs)


class DocsSingleSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = {
            name: _parse_page(DOCS_DIR / name) for name in PAGE_NAMES
        }
        app_c = (paths.USER_APP_DIR / "app.c").read_text(encoding="utf-8-sig")
        cls.app_names = [name for name, _symbol in parse_app_entries(app_c)]

    def _visible_text(self) -> str:
        return " ".join(
            text for page in self.pages.values() for text in page.texts
        )

    def test_every_link_resolves(self) -> None:
        for name in LINK_PAGES:
            page = _link_page(name)
            self.assertEqual(
                broken_links(
                    page,
                    base_dir=page.parent,
                    repo_root=paths.REPO_ROOT,
                ),
                [],
                name,
            )

    def test_every_link_page_exists(self) -> None:
        for name in LINK_PAGES:
            with self.subTest(name=name):
                self.assertTrue(_link_page(name).is_file(), name)
        # The sifli page is link-checked against real repository links only.
        self.assertTrue(_parse_page(SIFLI_PAGE).hrefs)

    def test_sifli_page_is_link_checked_but_not_an_index_page(self) -> None:
        self.assertIn("sifli.html", LINK_PAGES)
        self.assertNotIn("sifli.html", PAGE_NAMES)

    def test_one_off_audit_report_is_not_an_index_page(self) -> None:
        # The untracked audit report may exist in the main checkout; it never
        # joins the index or link-check lists.
        audit_pages = sorted(
            path.name for path in DOCS_DIR.glob("audit-*.html")
        )
        for name in audit_pages:
            with self.subTest(name=name):
                self.assertNotIn(name, PAGE_NAMES)
                self.assertNotIn(name, LINK_PAGES)

    def test_every_symbol_pointer_names_something_in_the_linked_file(self) -> None:
        for name, page in self.pages.items():
            self.assertTrue(page.pointers, f"{name}: no symbol pointers found")
            for href, pointer in page.pointers:
                self.assertIsNotNone(
                    href, f"{name}: symbol pointer {pointer!r} has no link"
                )
                target = href.split("#", 1)[0]
                resolved = (DOCS_DIR / target).resolve()
                self.assertTrue(
                    resolved.is_file(),
                    f"{name}: symbol pointer {pointer!r} links to a "
                    f"non-file {href!r}",
                )
                source = resolved.read_text(encoding="utf-8")
                for token in pointer.split(","):
                    symbol = token.strip().strip("`")
                    if not symbol:
                        continue
                    leaf = symbol.rsplit(".", 1)[-1].split("[", 1)[0]
                    self.assertIsNotNone(
                        _token_pattern(leaf).search(source),
                        f"{name}: pointer {symbol!r} not found in {href!r}",
                    )

    def test_pointers_use_symbols_not_line_numbers(self) -> None:
        for name, page in self.pages.items():
            pointers = " ".join(page.texts) + " " + " ".join(page.hrefs)
            self.assertIsNone(
                LINE_POINTER.search(pointers),
                f"{name}: line-number pointer found; use a symbol pointer",
            )
            self.assertIsNone(
                ANCHOR_POINTER.search(pointers),
                f"{name}: #L line anchor found; use a symbol pointer",
            )

    def test_no_app_list_copy(self) -> None:
        self.assertTrue(self.app_names, "app.c must declare at least one app")
        text = self._visible_text()
        for name in self.app_names:
            self.assertIsNone(
                _token_pattern(name).search(text),
                f"docs copy app name {name!r}; link to user/app/app.c instead",
            )

    def test_no_http_route_copy(self) -> None:
        text = self._visible_text()
        for route in ROUTE_PREFIXES + _server_route_literals():
            self.assertNotIn(
                route,
                text,
                f"docs copy HTTP route {route!r}; "
                "link to routes.route instead",
            )

    def test_no_scenario_vocabulary_copy(self) -> None:
        text = self._visible_text()
        self.assertNotIn(
            SCENARIO_SCHEMA,
            text,
            "docs copy the scenario schema literal; link to scenario.py",
        )
        for step_type in STEP_TYPES:
            self.assertIsNone(
                _token_pattern(step_type).search(text),
                f"docs copy scenario step type {step_type!r}; "
                "link to scenario.STEP_TYPES instead",
            )

    def test_no_server_constant_value_copy(self) -> None:
        text = self._visible_text()
        facts: list[str] = []
        for module, names in CONSTANT_SOURCES.items():
            for name in names:
                value = getattr(module, name)
                if isinstance(value, bytes):
                    value = value.decode("ascii")
                facts.append(str(value))
                facts.extend(_humanized_byte_facts(value))
                if isinstance(value, float) and value.is_integer():
                    facts.append(str(int(value)))
        for module, name in REGEX_CONSTANTS:
            facts.append(getattr(module, name).pattern)
        for fact in facts:
            if re.fullmatch(r"[\d.]+", fact):
                copied = _numeric_pattern(fact).search(text)
            else:
                copied = fact in text
            self.assertFalse(
                copied,
                f"docs copy server constant value {fact!r}; "
                "link to the owning module instead",
            )


if __name__ == "__main__":
    unittest.main()
