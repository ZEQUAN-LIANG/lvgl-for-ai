from __future__ import annotations

import base64
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
from device_control import DeviceController, DeviceError  # noqa: E402
from fake_serial import FakeSerialBackend  # noqa: E402


class DeviceControllerTest(unittest.TestCase):
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
        self.session = CommandSession(self.broker, timeout_ms=2000)
        self.device = DeviceController(self.session)

    def tearDown(self) -> None:
        self.broker.close()
        self.tmp.cleanup()

    def test_sys_info(self) -> None:
        info = self.device.sys_info()
        self.assertEqual(info["chip"], "ESP32-C6")
        self.assertEqual(info["flash"], "4MB")
        self.assertEqual(info["app"], "c6_demo")
        self.assertEqual(info["page"], "home")

    def test_wifi_scan_and_connect(self) -> None:
        networks = self.device.wifi_scan()
        self.assertGreaterEqual(len(networks), 4)
        self.assertEqual(networks[0]["ssid"], "Waveshare-2.4G")
        self.assertEqual(networks[0]["security"], "WPA2")

        result = self.device.wifi_connect("Waveshare-2.4G", "secret")
        self.assertEqual(result["ssid"], "Waveshare-2.4G")
        self.assertEqual(result["ip"], "192.168.1.42")
        status = self.device.wifi_status()
        self.assertEqual(status["state"], "connected")
        self.assertEqual(status["ssid"], "Waveshare-2.4G")
        self.assertTrue(status["auto"])
        self.assertTrue(self.device.wifi_disconnect())
        self.assertEqual(self.device.wifi_status()["state"], "disconnected")

        unicode_result = self.device.wifi_connect("C6 实验室", "密码")
        self.assertEqual(unicode_result["ssid"], "C6 实验室")
        self.assertEqual(self.device.wifi_status()["ssid"], "C6 实验室")

    def test_wifi_secure_network_needs_password(self) -> None:
        with self.assertRaises(DeviceError) as context:
            self.device.wifi_connect("Waveshare-2.4G", "")
        self.assertEqual(context.exception.code, "wifi_connect_failed")

    def test_wifi_password_is_redacted_in_tx_events(self) -> None:
        self.device.wifi_connect("Waveshare-2.4G", "super-secret")
        status = self.broker.status()
        events = Path(status["events_path"]).read_text(encoding="utf-8")
        command = b"wifi connect Waveshare-2.4G super-secret\n"
        encoded = base64.b64encode(command).decode("ascii")
        self.assertNotIn(encoded, events)
        self.assertIn('"redacted": true', events)

    def test_bluetooth(self) -> None:
        status = self.device.bt_status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["discoverable"])
        self.assertTrue(self.device.bt_enable(True))
        self.assertEqual(self.device.bt_name("C6 Lab"), "C6 Lab")
        self.assertEqual(self.device.bt_name("C6 实验室"), "C6 实验室")
        self.assertTrue(self.device.bt_discoverable(True))
        status = self.device.bt_status()
        self.assertTrue(status["enabled"])
        self.assertTrue(status["discoverable"])
        self.assertEqual(status["name"], "C6 实验室")
        self.assertTrue(self.device.bt_enable(False))
        self.assertFalse(self.device.bt_status()["discoverable"])

    def test_brightness_and_reset(self) -> None:
        self.assertEqual(self.device.brightness(55), 55)
        self.assertTrue(self.device.reset())


if __name__ == "__main__":
    unittest.main()
