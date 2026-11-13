from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import serial_backend  # noqa: E402


class NormalizePortTest(unittest.TestCase):
    def test_numeric_port(self) -> None:
        if os.name == "nt":
            self.assertEqual(serial_backend.normalize_port("12"), "COM12")
            self.assertEqual(serial_backend.normalize_port("com3"), "COM3")
        else:
            self.assertEqual(
                serial_backend.normalize_port("/dev/ttyUSB0"),
                "/dev/ttyUSB0",
            )

    def test_empty_port(self) -> None:
        with self.assertRaises(serial_backend.SerialError):
            serial_backend.normalize_port("")

    def test_invalid_windows_port(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows-specific validation")
        with self.assertRaises(serial_backend.SerialError):
            serial_backend.normalize_port("../COM1")
        with self.assertRaises(serial_backend.SerialError):
            serial_backend.normalize_port("LPT1")

    def test_list_ports_shape(self) -> None:
        ports = serial_backend.list_ports()
        self.assertIsInstance(ports, list)
        for item in ports:
            self.assertIn("port", item)
            self.assertIn("description", item)


if __name__ == "__main__":
    unittest.main()
