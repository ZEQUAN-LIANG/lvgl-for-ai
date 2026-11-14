from __future__ import annotations

import json
import queue
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from broker import SerialBroker  # noqa: E402
from serial_backend import SerialError  # noqa: E402


class FakeBackend:
    def __init__(self) -> None:
        self.is_open = False
        self.port = ""
        self.writes: list[bytes] = []
        self.resets: list[int] = []
        self.fail_next = False
        self._queue: queue.Queue[bytes] = queue.Queue()

    def open(self, port: str, baud: int, *, read_timeout_ms: int = 50) -> None:
        self.is_open = True
        self.port = port

    def close(self) -> None:
        self.is_open = False

    def read(self, max_bytes: int = 4096) -> bytes:
        if self.fail_next:
            self.fail_next = False
            raise SerialError("simulated unplug", code="read_failed")
        try:
            return self._queue.get(timeout=0.01)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        return len(data)

    def reset(self, pulse_ms: int = 100) -> None:
        self.resets.append(int(pulse_ms))

    def set_rts(self, value: bool) -> None:
        pass

    def set_dtr(self, value: bool) -> None:
        pass

    def feed(self, data: bytes) -> None:
        self._queue.put(bytes(data))


class BrokerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config = {
            "default_baud": 1_000_000,
            "ring_buffer_bytes": 1024,
            "max_read_bytes": 1024,
            "log_dir": str(Path(self.temp.name) / "logs"),
        }
        self.backend = FakeBackend()
        self.broker = SerialBroker(
            self.config,
            backend_factory=lambda: self.backend,
        )
        self.broker.open("COM12", 1_000_000)

    def tearDown(self) -> None:
        self.broker.close()
        self.temp.cleanup()

    def _wait_for_seq(self, value: int, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.broker.current_seq() >= value:
                return
            time.sleep(0.01)
        self.fail(f"sequence did not reach {value}")

    def test_two_readers_share_cursor(self) -> None:
        self.backend.feed(b"hello")
        self._wait_for_seq(5)
        first = self.broker.read_since(0)
        second = self.broker.read_since(0)
        self.assertEqual(first["text"], "hello")
        self.assertEqual(second["text"], "hello")
        tail = self.broker.read_since(2)
        self.assertEqual(tail["text"], "llo")
        empty = self.broker.read_since(99)
        self.assertEqual(empty["text"], "")
        self.assertEqual(empty["next"], 5)

    def test_send_and_reset(self) -> None:
        sent = self.broker.send(b"abc")
        self.assertEqual(sent["bytes"], 3)
        self.assertEqual(self.backend.writes, [b"abc"])
        self.assertEqual(self.broker.status()["total_tx"], 3)
        self.broker.reset(50)
        self.assertEqual(self.backend.resets, [50])

    def test_expect(self) -> None:
        self.backend.feed(b"boot\nSFBL\n")
        self._wait_for_seq(10)
        result = self.broker.expect("SFBL", since=0, timeout_ms=1000)
        self.assertTrue(result["ok"])
        self.assertEqual(result["matched"], "SFBL")

    def test_ring_buffer_truncates(self) -> None:
        self.broker.close()
        self.config["ring_buffer_bytes"] = 4
        self.broker = SerialBroker(
            self.config,
            backend_factory=lambda: self.backend,
        )
        self.broker.open("COM12", 1_000_000)
        self.backend.feed(b"abcdefgh")
        self._wait_for_seq(8)
        result = self.broker.read_since(0)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "efgh")

    def test_close(self) -> None:
        status = self.broker.close()
        self.assertEqual(status["state"], "closed")
        self.assertFalse(status["open"])
        self.assertFalse(self.backend.is_open)

    def test_log_files_are_written(self) -> None:
        self.backend.feed(b"hello")
        self._wait_for_seq(5)
        status = self.broker.status()
        log_path = Path(status["log_path"])
        raw_path = Path(status["events_path"])
        self.assertTrue(log_path.is_file())
        self.assertTrue(raw_path.is_file())
        self.assertIn("hello", log_path.read_text(encoding="utf-8"))

    def test_detach_reports_and_stops_reconnect(self) -> None:
        result = self.broker.detach_for_flash()
        self.assertTrue(result["was_open"])
        self.assertEqual(result["port"], "COM12")
        self.assertEqual(result["baud"], 1_000_000)

        status = self.broker.status()
        self.assertFalse(status["open"])
        self.assertFalse(status["wanted"])

        self.broker.set_auto_reconnect(True)
        time.sleep(0.05)
        self.assertFalse(self.broker.status()["reconnecting"])

    def test_handoff_releases_port_without_reconnect(self) -> None:
        result = self.broker.handoff_to_flasher()
        self.assertTrue(result["was_open"])
        status = self.broker.status()
        self.assertFalse(status["open"])
        self.assertFalse(status["wanted"])

    def test_log_paths_survive_close(self) -> None:
        log_path = Path(self.broker.status()["log_path"])
        self.assertTrue(log_path.is_file())
        self.broker.close()
        status = self.broker.status()
        self.assertEqual(Path(status["log_path"]), log_path)
        self.assertTrue(log_path.is_file())

    def test_event_seq_continues_across_reopen(self) -> None:
        self.backend.feed(b"x")
        self._wait_for_seq(1)
        first_events = Path(self.broker.status()["events_path"])

        self.broker.close()
        self.broker.open("COM12", 1_000_000)
        self.backend.feed(b"y")
        self._wait_for_seq(2)
        second_events = Path(self.broker.status()["events_path"])

        self.assertNotEqual(first_events, second_events)
        first = json.loads(
            first_events.read_text(encoding="utf-8").splitlines()[0]
        )
        second = json.loads(
            second_events.read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)

    def test_auto_reconnect_after_read_error(self) -> None:
        self.broker.close()
        self.config["auto_reconnect"] = True
        self.config["reconnect_interval_s"] = 0.02
        self.config["reconnect_max_delay_s"] = 0.05
        backends: list[FakeBackend] = []

        def factory() -> FakeBackend:
            backend = FakeBackend()
            backends.append(backend)
            return backend

        self.broker = SerialBroker(
            self.config,
            backend_factory=factory,
        )
        self.broker.open("COM12", 1_000_000)
        self.assertEqual(len(backends), 1)
        backends[0].fail_next = True
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if len(backends) >= 2 and self.broker.status()["open"]:
                break
            time.sleep(0.01)
        self.assertGreaterEqual(len(backends), 2)
        self.assertTrue(self.broker.status()["open"])
        self.assertTrue(backends[-1].is_open)


if __name__ == "__main__":
    unittest.main()
