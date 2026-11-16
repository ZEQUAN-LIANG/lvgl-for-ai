from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths

ensure_import_paths()

from broker import SerialBroker  # noqa: E402
from command_session import CommandSession  # noqa: E402
from fake_serial import FakeSerialBackend  # noqa: E402
from page_control import PageController, PageError  # noqa: E402


class PageControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = {
            "default_baud": 115200,
            "ring_buffer_bytes": 64 * 1024,
            "max_read_bytes": 16 * 1024,
            "auto_reconnect": False,
            "log_dir": self.tmp.name,
        }
        self.broker = SerialBroker(
            self.config, backend_factory=lambda: FakeSerialBackend()
        )
        self.broker.open("COM99", 115200)
        self.session = CommandSession(self.broker, timeout_ms=1000)
        self.pages = PageController(self.session)

    def tearDown(self) -> None:
        self.broker.close()
        self.tmp.cleanup()

    def test_pages_and_state(self) -> None:
        data = self.pages.pages()
        self.assertEqual(data["pages"], ["home", "status", "about"])
        self.assertEqual(data["current"], "home")

    def test_show_next_prev(self) -> None:
        self.assertEqual(self.pages.show("status"), "status")
        self.assertEqual(self.pages.state(), "status")
        self.assertEqual(self.pages.next(), "about")
        self.assertEqual(self.pages.prev(), "status")

    def test_unknown_page(self) -> None:
        with self.assertRaises(PageError) as context:
            self.pages.show("missing")
        self.assertEqual(context.exception.code, "page_unknown")

    def test_empty_page(self) -> None:
        with self.assertRaises(PageError) as context:
            self.pages.show("")
        self.assertEqual(context.exception.code, "page_name_empty")

    def test_ping(self) -> None:
        self.assertTrue(self.pages.ping())


if __name__ == "__main__":
    unittest.main()
