from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from events import EventHub  # noqa: E402


class EventHubTest(unittest.TestCase):
    def test_publish_snapshot_and_cursor(self) -> None:
        hub = EventHub(maxlen=10)
        first = hub.publish("ai", "job.start", "start", {"job_id": "abc"})
        hub.publish("cli", "serial.send", "help", {"bytes": 4})
        snapshot = hub.snapshot(0)
        self.assertEqual(len(snapshot["events"]), 2)
        self.assertEqual(snapshot["events"][0]["actor"], "ai")
        self.assertEqual(snapshot["next"], first["seq"] + 1)
        tail = hub.snapshot(first["seq"])
        self.assertEqual(len(tail["events"]), 1)
        self.assertEqual(tail["events"][0]["actor"], "cli")

    def test_wait(self) -> None:
        hub = EventHub()
        self.assertFalse(hub.wait(0, 0.01))
        hub.publish("web", "serial.open", "opened")
        self.assertTrue(hub.wait(0, 0.1))


if __name__ == "__main__":
    unittest.main()
