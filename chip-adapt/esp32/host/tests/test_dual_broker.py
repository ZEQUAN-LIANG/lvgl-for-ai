from __future__ import annotations

import os
import queue
import sys
import tempfile
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

from broker import SerialBroker  # noqa: E402
from dual_broker import DualBroker  # noqa: E402
from serial_backend import SerialBackend, SerialError  # noqa: E402


class FakeDualBackend(SerialBackend):
    def __init__(self) -> None:
        self.is_open = False
        self.writes: list[bytes] = []
        self._queue: queue.Queue[bytes] = queue.Queue()

    def open(
        self, port: str, baud: int, *, read_timeout_ms: int = 50
    ) -> None:
        _ = port, baud, read_timeout_ms
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def read(self, max_bytes: int = 4096) -> bytes:
        _ = max_bytes
        try:
            return self._queue.get(timeout=0.01)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        if data.strip() == b"ping":
            self._queue.put(b"@PONG\n")
        return len(data)

    def reset(self, pulse_ms: int = 100) -> None:
        _ = pulse_ms

    def set_rts(self, value: bool) -> None:
        _ = value

    def set_dtr(self, value: bool) -> None:
        _ = value

    def link_status(self) -> dict:
        return {
            "active": "ble" if self.is_open else "none",
            "ble": {"ready": self.is_open, "name": "LVGL-C6-PERF"},
            "serial": {
                "open": self.is_open,
                "port": "COM13",
                "baud": 115200,
                "last_error": "",
            },
        }


class DualBrokerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {
            "log_dir": self.tmp.name,
            "ring_buffer_bytes": 4096,
            "default_baud": 115200,
            "auto_reconnect": False,
        }
        self.backend = FakeDualBackend()
        self.broker = DualBroker(
            self.config, backend_factory=lambda: self.backend
        )
        self.addCleanup(self.broker.close)

    def test_open_uses_dual_port_and_status(self) -> None:
        status = self.broker.open()
        self.assertEqual(status["port"], "dual")
        self.assertEqual(status["transport"], "dual")
        self.assertEqual(status["links"]["active"], "ble")
        self.assertEqual(status["links"]["serial"]["port"], "COM13")
        self.assertTrue(Path(status["log_dir"]).is_dir())

    def test_send_and_expect(self) -> None:
        self.broker.open()
        cursor = self.broker.current_seq()
        self.broker.send(b"ping\n")
        result = self.broker.expect("@PONG", since=cursor, timeout_ms=500)
        self.assertTrue(result["ok"])
        self.assertEqual(result["matched"], "@PONG")

    def test_detach_for_flash_keeps_serial_port(self) -> None:
        self.broker.open()
        released = self.broker.detach_for_flash()
        self.assertTrue(released["was_open"])
        self.assertEqual(released["serial_port"], "COM13")
        self.assertFalse(self.broker.is_open)

    def test_status_before_open(self) -> None:
        status = self.broker.status()
        self.assertEqual(status["transport"], "dual")
        self.assertEqual(status["links"]["active"], "none")


class SerialBrokerPortRegressionTest(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows COM validation only")
    def test_serial_broker_rejects_ble_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broker = SerialBroker(
                {
                    "log_dir": tmp,
                    "ring_buffer_bytes": 4096,
                    "auto_reconnect": False,
                },
                backend_factory=FakeDualBackend,
            )
            with self.assertRaises(SerialError) as context:
                broker.open("LVGL-C6-PERF")
            self.assertEqual(context.exception.code, "port_invalid")


if __name__ == "__main__":
    unittest.main()
