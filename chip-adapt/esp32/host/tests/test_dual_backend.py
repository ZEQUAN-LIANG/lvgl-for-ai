from __future__ import annotations

import queue
import sys
import time
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

from dual_backend import DualBackend  # noqa: E402
from serial_backend import SerialBackend, SerialError  # noqa: E402


class FakeSerial(SerialBackend):
    def __init__(self) -> None:
        self.is_open = False
        self.open_enabled = True
        self.port = ""
        self.writes: list[bytes] = []
        self._queue: queue.Queue[bytes] = queue.Queue()

    def open(  # type: ignore[override]
        self, port: str, baud: int, *, read_timeout_ms: int = 50
    ) -> None:
        _ = baud, read_timeout_ms
        if not self.open_enabled:
            raise SerialError("serial unavailable", code="open_failed")
        self.port = port
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def read(self, max_bytes: int = 4096) -> bytes:
        _ = max_bytes
        if not self.is_open:
            raise SerialError("serial closed", code="not_open")
        try:
            return self._queue.get(timeout=0.01)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise SerialError("serial closed", code="not_open")
        self.writes.append(bytes(data))
        return len(data)

    def reset(self, pulse_ms: int = 100) -> None:
        _ = pulse_ms

    def set_rts(self, value: bool) -> None:
        _ = value

    def set_dtr(self, value: bool) -> None:
        _ = value

    def emit(self, data: bytes) -> None:
        self._queue.put(data)


class FakeBle:
    def __init__(self) -> None:
        self.ready = False
        self.open_enabled = True
        self.writes: list[bytes] = []
        self.opens = 0
        self._queue: queue.Queue[bytes] = queue.Queue()

    def open(
        self,
        _name: str,
        _baud: int = 0,
        *,
        read_timeout_ms: int = 50,
    ) -> None:
        _ = read_timeout_ms
        self.opens += 1
        if not self.open_enabled:
            raise SerialError("ble unavailable", code="ble_not_found")
        self.ready = True

    def close(self) -> None:
        self.ready = False

    def read(self, max_bytes: int = 4096) -> bytes:
        _ = max_bytes
        if not self.ready:
            raise SerialError("ble closed", code="ble_disconnected")
        try:
            return self._queue.get(timeout=0.01)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        if not self.ready:
            raise SerialError("ble closed", code="ble_disconnected")
        self.writes.append(bytes(data))
        return len(data)

    def status(self) -> dict:
        return {
            "ready": self.ready,
            "name": "LVGL-C6-PERF",
            "address": "AA:BB:CC:DD:EE:FF",
            "mtu": 256,
            "chunk": 253,
            "subscribed": self.ready,
            "last_error": "",
        }

    def emit(self, data: bytes) -> None:
        self._queue.put(data)


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class DualBackendTest(unittest.TestCase):
    def make_backend(self, **config):
        self.serial = FakeSerial()
        self.ble = FakeBle()
        values = {
            "serial_port": "COM99",
            "serial_enabled": True,
            "ble_enabled": True,
            "link_wait_s": 0.1,
            "default_baud": 115200,
        }
        values.update(config)
        backend = DualBackend(
            values,
            serial_factory=lambda: self.serial,
            ble_factory=lambda: self.ble,
        )
        self.addCleanup(backend.close)
        backend.open(read_timeout_ms=20)
        return backend

    def test_serial_only_writes_serial(self) -> None:
        backend = self.make_backend(ble_enabled=False)
        self.assertTrue(wait_until(lambda: self.serial.is_open))
        self.assertEqual(backend.write(b"PERF PING\n"), 10)
        self.assertEqual(self.serial.writes, [b"PERF PING\n"])

    def test_ble_preferred_when_ready(self) -> None:
        backend = self.make_backend()
        self.assertTrue(wait_until(lambda: self.ble.ready))
        self.assertEqual(backend.status()["active"], "ble")
        backend.write(b"PERF PING\n")
        self.assertEqual(self.ble.writes, [b"PERF PING\n"])
        self.assertEqual(self.serial.writes, [])

    def test_ble_disconnect_falls_back_to_serial(self) -> None:
        backend = self.make_backend()
        self.assertTrue(wait_until(lambda: self.ble.ready))
        self.ble.open_enabled = False
        self.ble.ready = False
        self.assertTrue(
            wait_until(lambda: backend.status()["active"] == "serial")
        )
        backend.write(b"PERF PORTRAIT\n")
        self.assertEqual(self.serial.writes, [b"PERF PORTRAIT\n"])

    def test_ble_reconnect_switches_back(self) -> None:
        backend = self.make_backend()
        self.assertTrue(wait_until(lambda: self.ble.ready))
        self.ble.open_enabled = False
        self.ble.ready = False
        self.assertTrue(
            wait_until(lambda: backend.status()["active"] == "serial")
        )
        self.ble.open_enabled = True
        self.assertTrue(
            wait_until(lambda: backend.status()["active"] == "ble")
        )
        backend.write(b"PERF DEMO\n")
        self.assertTrue(self.ble.writes)

    def test_some_links_down_reports_no_link(self) -> None:
        backend = self.make_backend(serial_port="COM99")
        self.assertTrue(wait_until(lambda: self.serial.is_open))
        self.ble.open_enabled = False
        self.ble.ready = False
        self.serial.open_enabled = False
        self.serial.close()
        self.assertTrue(
            wait_until(lambda: backend.status()["active"] == "none")
        )
        with self.assertRaises(SerialError) as context:
            backend.write(b"PERF PING\n")
        self.assertEqual(context.exception.code, "no_link")

    def test_reads_merge_both_links(self) -> None:
        backend = self.make_backend()
        self.assertTrue(
            wait_until(lambda: self.serial.is_open and self.ble.ready)
        )
        self.serial.emit(b"usb")
        self.ble.emit(b"ble")
        received = b""
        deadline = time.monotonic() + 2.0
        while len(received) < 6 and time.monotonic() < deadline:
            received += backend.read()
        self.assertIn(b"usb", received)
        self.assertIn(b"ble", received)

    def test_status_exposes_both_links(self) -> None:
        backend = self.make_backend()
        self.assertTrue(
            wait_until(lambda: self.serial.is_open and self.ble.ready)
        )
        status = backend.status()
        self.assertEqual(status["active"], "ble")
        self.assertTrue(status["serial"]["open"])
        self.assertEqual(status["serial"]["port"], "COM99")
        self.assertTrue(status["ble"]["ready"])

    def test_serial_only_mode_ignores_ble(self) -> None:
        backend = self.make_backend(ble_enabled=False)
        self.assertTrue(wait_until(lambda: self.serial.is_open))
        self.assertEqual(backend.status()["active"], "serial")
        self.assertEqual(self.ble.opens, 0)


if __name__ == "__main__":
    unittest.main()
