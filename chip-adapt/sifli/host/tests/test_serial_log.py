from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from serial_log import SerialLog, list_sessions  # noqa: E402


def _events(log: SerialLog) -> list[dict]:
    return [
        json.loads(line)
        for line in log.events_path.read_text(encoding="utf-8").splitlines()
    ]


class SerialLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "logs"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create(self, port: str = "COM12", event_seq: int = 0) -> SerialLog:
        return SerialLog.create(
            self.root,
            port=port,
            baud=1_000_000,
            opened_at="2026-01-01T00:00:00.000+08:00",
            event_seq=event_seq,
        )

    def test_writes_text_raw_and_events(self) -> None:
        log = self._create()
        log.write_rx(b"hello")
        log.write_event("tx", b"ok", source="api", extra={"pulse_ms": 50})
        log.close()

        self.assertIn("hello", log.log_path.read_text(encoding="utf-8"))
        self.assertEqual(log.raw_path.read_bytes(), b"hello")
        events = _events(log)
        self.assertEqual([event["dir"] for event in events], ["rx", "tx"])
        self.assertEqual(events[0]["source"], "device")
        self.assertEqual(events[1]["source"], "api")
        self.assertEqual(events[1]["pulse_ms"], 50)
        self.assertEqual([event["seq"] for event in events], [1, 2])

        meta = json.loads((log.dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["schema"], "sifli-host-serial-v1")
        self.assertEqual(meta["port"], "COM12")
        self.assertEqual(meta["baud"], 1_000_000)

    def test_event_seq_continues_after_reopen(self) -> None:
        first = self._create(event_seq=7)
        first.write_event("rx", b"a")
        first.close()

        second = self._create(event_seq=first.event_seq)
        second.write_event("rx", b"b")
        second.close()

        self.assertEqual(_events(second)[0]["seq"], 9)

    def test_directory_uses_suffix_on_collision(self) -> None:
        (self.root / "20260101-120000-COM12").mkdir()
        fake = mock.Mock()
        fake.now.return_value.strftime.return_value = "20260101-120000"
        with mock.patch("serial_log.datetime", fake):
            log = self._create()
        self.assertEqual(log.dir.name, "20260101-120000-COM12-2")
        log.close()

    def test_close_is_idempotent_and_writes_stop(self) -> None:
        log = self._create()
        log.write_rx(b"a")
        log.close()
        log.close()
        log.write_rx(b"b")
        self.assertEqual(log.raw_path.read_bytes(), b"a")

    def test_list_sessions(self) -> None:
        first = self._create("COM1")
        first.write_rx(b"x")
        first.close()
        second = self._create("COM2")
        second.close()

        sessions = list_sessions(self.root)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(
            {item["meta"]["port"] for item in sessions},
            {"COM1", "COM2"},
        )
        for item in sessions:
            self.assertIn("serial.log", item["files"])
        self.assertEqual(list_sessions(self.root / "missing"), [])


if __name__ == "__main__":
    unittest.main()
