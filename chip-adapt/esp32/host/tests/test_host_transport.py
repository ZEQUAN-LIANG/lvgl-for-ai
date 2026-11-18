from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

from host import HostState  # noqa: E402


class HostTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def make_state(self, **config) -> HostState:
        values = {"log_dir": self.tmp.name}
        values.update(config)
        state = HostState(config=values)
        self.addCleanup(state.broker.close)
        return state

    def test_fake_transport_keeps_serial_port(self) -> None:
        state = HostState(fake=True)
        self.addCleanup(state.broker.close)
        self.assertEqual(state.transport, "fake")
        ports = state.port_list()
        self.assertEqual(ports[0]["kind"], "serial")
        self.assertEqual(ports[0]["port"], "COM99")

    def test_dual_transport_lists_ble_entry(self) -> None:
        state = self.make_state(
            transport="dual",
            serial_enabled=False,
            ble_enabled=False,
        )
        self.assertEqual(state.transport, "dual")
        self.assertEqual(state.ble_name, "LVGL-C6-PERF")
        ports = state.port_list()
        self.assertEqual(ports[0]["kind"], "ble")
        self.assertEqual(ports[0]["port"], "ble")
        status = state.broker.status()
        self.assertEqual(status["transport"], "dual")
        self.assertEqual(status["links"]["active"], "none")

    def test_ble_transport_disables_serial(self) -> None:
        state = self.make_state(transport="ble")
        self.assertEqual(state.transport, "ble")
        self.assertFalse(state.config["serial_enabled"])

    def test_serial_transport_uses_serial_broker(self) -> None:
        state = self.make_state(transport="serial")
        self.assertEqual(state.transport, "serial")
        self.assertFalse(hasattr(state.broker, "link_status"))


if __name__ == "__main__":
    unittest.main()
