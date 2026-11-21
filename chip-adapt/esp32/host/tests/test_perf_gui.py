from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
PERF_DIR = HOST_DIR / "perf"
for path in (HOST_DIR, PERF_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import perf_gui  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class HostClientTest(unittest.TestCase):
    def test_normalize_url(self) -> None:
        self.assertEqual(
            perf_gui.normalize_url("127.0.0.1:8767/"),
            "http://127.0.0.1:8767",
        )
        self.assertEqual(
            perf_gui.normalize_url("http://localhost:8767"),
            "http://localhost:8767",
        )

    def test_start_posts_json(self) -> None:
        response = FakeResponse({"ok": True, "mode": "live"})
        with mock.patch(
            "perf_gui.urllib.request.urlopen", return_value=response
        ) as urlopen:
            client = perf_gui.HostClient("127.0.0.1:8767")
            result = client.start("live", 2.5, "landscape")
        self.assertEqual(result["mode"], "live")
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8767/api/perf/start",
        )
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"mode": "live", "interval": 2.5, "layout": "landscape"},
        )
        self.assertEqual(request.get_method(), "POST")

    def test_status_uses_get(self) -> None:
        response = FakeResponse({"ok": True, "running": False})
        with mock.patch(
            "perf_gui.urllib.request.urlopen", return_value=response
        ) as urlopen:
            client = perf_gui.HostClient("http://127.0.0.1:8767")
            result = client.status()
        self.assertFalse(result["running"])
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)

    def test_close_link_posts_with_short_timeout(self) -> None:
        response = FakeResponse({"ok": True})
        with mock.patch(
            "perf_gui.urllib.request.urlopen", return_value=response
        ) as urlopen:
            client = perf_gui.HostClient("http://127.0.0.1:8767")
            result = client.close_link()
        self.assertTrue(result["ok"])
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8767/api/close")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(urlopen.call_args[1]["timeout"], 2.0)

    def test_error_payload_raises(self) -> None:
        response = FakeResponse(
            {"ok": False, "error": "serial_not_open", "message": "no port"}
        )
        with mock.patch(
            "perf_gui.urllib.request.urlopen", return_value=response
        ):
            client = perf_gui.HostClient("http://127.0.0.1:8767")
            with self.assertRaises(perf_gui.HostError) as context:
                client.stop()
        self.assertEqual(str(context.exception), "no port")

    def test_http_error_message(self) -> None:
        exc = urllib.error.HTTPError(
            "http://127.0.0.1:8767/api/perf/stop",
            409,
            "Conflict",
            {},
            io.BytesIO(b'{"ok": false, "message": "port busy"}'),
        )
        self.assertEqual(perf_gui.http_error_message(exc), "port busy")

    def test_unreachable_host(self) -> None:
        error = urllib.error.URLError("connection refused")
        with mock.patch("perf_gui.urllib.request.urlopen", side_effect=error):
            client = perf_gui.HostClient("http://127.0.0.1:8767")
            with self.assertRaises(perf_gui.HostError) as context:
                client.status()
        self.assertIn("unreachable", str(context.exception))


class FormatterTest(unittest.TestCase):
    def test_clock_text(self) -> None:
        self.assertEqual(perf_gui.clock_text({"hhmm": 2259}), "22:59")
        self.assertEqual(perf_gui.clock_text({}), "--:--")

    def test_memory(self) -> None:
        sample = {"mem_mb": 16384, "mem_total_mb": 32768}
        self.assertEqual(perf_gui.memory_percent(sample), 50)
        self.assertEqual(perf_gui.memory_sub(sample), "16.0/32G")

    def test_ping_text(self) -> None:
        self.assertEqual(perf_gui.ping_text({"ping_ms": 15}), "PING 15 MS")
        self.assertEqual(perf_gui.ping_text({"ping_ms": 1500}), "PING 1500")
        self.assertEqual(
            perf_gui.ping_text({"ping_ms": 15}, short=True), "PING 15"
        )

    def test_thread_helpers(self) -> None:
        sample = {"thread_count": 4, "bars": [10, 80, 30, 5, 99]}
        self.assertEqual(perf_gui.thread_count(sample), 4)
        self.assertEqual(perf_gui.thread_peak(sample), 80)

    def test_short_text(self) -> None:
        self.assertEqual(perf_gui.short_text("DESKTOP-A9IL", 8), "DESKTOP-")
        self.assertEqual(perf_gui.short_text(None, 8), "")


if __name__ == "__main__":
    unittest.main()
