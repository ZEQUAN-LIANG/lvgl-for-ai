from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

from host import HostHandler, HostServer, HostState  # noqa: E402
from perf_control import PerfController, PerfError  # noqa: E402
from perf_protocol import demo_sample  # noqa: E402


class FakeBroker:
    def __init__(self, *, open_: bool = True) -> None:
        self.is_open = open_
        self.sent: list[tuple[str, str]] = []

    def send(
        self, data: bytes, *, source: str = "api", private: bool = False
    ) -> dict[str, int]:
        del private
        self.sent.append((source, data.decode("utf-8")))
        return {"bytes": len(data), "total_tx": sum(len(item[1]) for item in self.sent)}


def provider(
    mode: str, seq: int, tick: int, state: dict[str, object]
) -> object:
    del mode, state
    return demo_sample(seq, tick)


class PerfControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = FakeBroker()
        self.controller = PerfController(self.broker, provider=provider)

    def tearDown(self) -> None:
        self.controller.stop()

    def wait_for(self, predicate, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("condition did not become true before timeout")

    def test_start_demo_sends_layout_and_frames(self) -> None:
        self.controller.start("demo", 0.2, "landscape")
        self.assertEqual(self.broker.sent[0][1], "PERF LANDSCAPE\n")
        self.assertEqual(self.broker.sent[1][1], "PERF DEMO\n")
        self.wait_for(
            lambda: len(
                [line for _, line in self.broker.sent if line.startswith("PERF v=1")]
            )
            >= 2
        )
        status = self.controller.status()
        self.assertTrue(status["running"])
        self.assertEqual(status["layout"], "landscape")
        self.assertEqual(status["mode"], "demo")
        self.assertGreaterEqual(status["sent"], 2)
        self.assertIsNotNone(status["sample"])
        self.controller.stop()
        self.assertFalse(self.controller.status()["running"])

    def test_layout_switch(self) -> None:
        result = self.controller.set_layout("portrait")
        self.assertEqual(result["layout"], "portrait")
        self.assertEqual(self.broker.sent[-1][1], "PERF PORTRAIT\n")

    def test_bad_layout_rejected(self) -> None:
        with self.assertRaises(PerfError):
            self.controller.set_layout("diagonal")

    def test_default_interval_is_300ms(self) -> None:
        self.controller.start("demo")
        self.assertEqual(self.controller.status()["interval_s"], 0.3)
        self.controller.stop()

    def test_bad_interval_rejected(self) -> None:
        with self.assertRaises(PerfError):
            self.controller.start("demo", 0.01)

    def test_closed_serial_rejected(self) -> None:
        self.broker.is_open = False
        with self.assertRaises(PerfError) as context:
            self.controller.start("demo", 0.2)
        self.assertEqual(context.exception.code, "serial_not_open")
        self.assertFalse(self.controller.status()["running"])

    def test_live_is_windows_only(self) -> None:
        with mock.patch("perf_control.platform.system", return_value="Linux"):
            with self.assertRaises(PerfError) as context:
                self.controller.start("live", 1.0)
        self.assertEqual(context.exception.code, "unsupported")

    def test_stop_is_idempotent(self) -> None:
        self.controller.stop()
        self.controller.stop()
        self.assertFalse(self.controller.status()["running"])


def request_json(
    method: str, url: str, payload: dict[str, object] | None = None
) -> tuple[int, dict[str, object]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class PerfHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = HostState(
            fake=True,
            config={
                "log_dir": str(root / "logs"),
                "flash_cache_dir": str(root / "cache"),
            },
        )
        self.state.broker.open("COM99", 115200)
        self.server = HostServer(("127.0.0.1", 0), HostHandler, self.state)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.state.perf.stop()
        self.server.shutdown()
        self.server.server_close()
        self.state.broker.close()
        self.tmp.cleanup()

    def test_page_and_control_flow(self) -> None:
        with urllib.request.urlopen(f"{self.base}/perf/", timeout=10) as page:
            self.assertEqual(page.status, 200)
            html = page.read().decode("utf-8")
        self.assertIn("PERF TAPE", html)
        self.assertIn("/api/perf/status", html)

        status, payload = request_json(
            "GET", f"{self.base}/api/perf/status"
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["running"])

        status, payload = request_json(
            "POST",
            f"{self.base}/api/perf/layout",
            {"layout": "landscape"},
        )
        self.assertEqual((status, payload["layout"]), (200, "landscape"))

        status, payload = request_json(
            "POST",
            f"{self.base}/api/perf/start",
            {"mode": "demo", "interval": 0.2, "layout": "portrait"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["running"])

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, current = request_json("GET", f"{self.base}/api/perf/status")
            if current.get("sample") is not None and current["sent"] >= 1:
                break
            time.sleep(0.05)
        self.assertIsNotNone(current.get("sample"))
        self.assertEqual(current["layout"], "portrait")

        status, payload = request_json(
            "POST", f"{self.base}/api/perf/stop", {}
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["running"])


if __name__ == "__main__":
    unittest.main()
