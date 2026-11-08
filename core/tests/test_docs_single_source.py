"""The two docs pages stay link indexes, not copies of drifting facts.

``docs/app.html`` and ``docs/scenario-server.html`` must point at code,
README or SPEC instead of restating the app list, HTTP routes, server
constants or scenario step vocabulary.  These tests pin that static
invariant: every link resolves, every symbol pointer names something in the
linked file, and facts owned by code do not reappear in the pages.
"""

from __future__ import annotations

import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402
from lvgl_ai.apps import parse_app_entries  # noqa: E402
from lvgl_ai.scenario import SCENARIO_SCHEMA, STEP_TYPES  # noqa: E402
from lvgl_ai.web import live_session, webapp, wire  # noqa: E402

DOCS_DIR = paths.REPO_ROOT / "docs"
PAGE_NAMES = ("app.html", "scenario-server.html")

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


def _parse_page(name: str) -> _PageParser:
    parser = _PageParser()
    parser.feed((DOCS_DIR / name).read_text(encoding="utf-8"))
    parser.close()
    return parser


def _token_pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])" + re.escape(value) + r"(?![\w-])")


def _numeric_pattern(fact: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\d.])" + re.escape(fact) + r"(?![\d.])")


def _server_route_literals() -> tuple[str, ...]:
    source = Path(webapp.__file__).read_text(encoding="utf-8")
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


class DocsSingleSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = {name: _parse_page(name) for name in PAGE_NAMES}
        app_c = (paths.USER_APP_DIR / "app.c").read_text(encoding="utf-8-sig")
        cls.app_names = [name for name, _symbol in parse_app_entries(app_c)]

    def _visible_text(self) -> str:
        return " ".join(
            text for page in self.pages.values() for text in page.texts
        )

    def test_every_link_resolves(self) -> None:
        for name, page in self.pages.items():
            for href in page.hrefs:
                if href.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                target = href.split("#", 1)[0]
                if not target:
                    continue
                resolved = (DOCS_DIR / target).resolve()
                self.assertTrue(
                    resolved.exists(),
                    f"{name}: broken link {href!r} -> {resolved}",
                )

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
                "link to webapp._WebHandler._route instead",
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
