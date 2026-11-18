from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

from ble_link import BleLink  # noqa: E402
from fake_ble import FakeAdv, FakeClient, FakeDevice, FakeScanner  # noqa: E402
from serial_backend import SerialError  # noqa: E402


class BleLinkTest(unittest.TestCase):
    def make_link(self, *, mtu: int = 256):
        device = FakeDevice("LVGL-C6-PERF")
        adv = FakeAdv("LVGL-C6-PERF", ["6e400001-b5a3-f393-e0a9-e50e24dcca9e"])
        scanner = FakeScanner([(device, adv)])
        clients: list[FakeClient] = []

        def client_factory(_device, *, disconnected_callback=None):
            client = FakeClient(
                _device,
                disconnected_callback=disconnected_callback,
                mtu_size=mtu,
            )
            clients.append(client)
            return client

        link = BleLink(
            {"ble_scan_timeout_s": 0.2, "ble_connect_timeout_s": 1.0},
            scanner_factory=lambda: scanner,
            client_factory=client_factory,
        )
        return link, clients

    def test_open_subscribes_and_reads_notifications(self) -> None:
        link, clients = self.make_link()
        self.addCleanup(link.close)
        link.open()
        self.assertTrue(link.ready)
        self.assertEqual(link.status()["mtu"], 256)
        self.assertEqual(link.status()["chunk"], 253)
        clients[0].emit(b"@PERF PONG\n")
        self.assertEqual(link.read(), b"@PERF PONG\n")

    def test_write_chunks_by_mtu(self) -> None:
        link, clients = self.make_link(mtu=23)
        self.addCleanup(link.close)
        link.open()
        self.assertEqual(link.status()["chunk"], 20)
        payload = bytes(range(45))
        self.assertEqual(link.write(payload), 45)
        self.assertEqual(clients[0].writes, [payload[:20], payload[20:40], payload[40:]])

    def test_disconnect_raises_on_empty_read(self) -> None:
        link, clients = self.make_link()
        self.addCleanup(link.close)
        link.open()
        clients[0].simulate_disconnect()
        with self.assertRaises(SerialError) as context:
            link.read()
        self.assertEqual(context.exception.code, "ble_disconnected")

    def test_no_device(self) -> None:
        link = BleLink(
            {"ble_scan_timeout_s": 0.1, "ble_connect_timeout_s": 0.2},
            scanner_factory=lambda: FakeScanner([]),
            client_factory=lambda device, **kwargs: FakeClient(device, **kwargs),
        )
        with self.assertRaises(SerialError) as context:
            link.open()
        self.assertEqual(context.exception.code, "ble_not_found")
        link.close()

    def test_close_is_idempotent(self) -> None:
        link, _clients = self.make_link()
        link.open()
        link.close()
        link.close()
        self.assertFalse(link.ready)


if __name__ == "__main__":
    unittest.main()
