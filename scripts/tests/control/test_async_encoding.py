from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control import Recording, Runtime
from scripts.tests.support import read_png_rgb

BUTTON_CENTER = (112, 324)


def read_timeline(session_dir: Path) -> list[dict]:
    text = (session_dir / "timeline.ndjson").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


class AsyncEncodingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self, **kwargs) -> Runtime:
        options = {
            "lvgl": "9.6",
            "build": True,
            "app": "test_ui",
            "record_changed_only": False,
            "sessions_root": self.sessions_root,
        }
        options.update(kwargs)
        return Runtime(**options)

    def test_stop_finalizes_every_reserved_frame(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        rt.pointer("down", *BUTTON_CENTER)
        rt.wait(ms=64)
        reserved = rt.frame_count
        self.assertGreaterEqual(reserved, 2)

        rows = read_timeline(rt.session_dir)
        frame_rows = [row for row in rows if row.get("type") == "frame"]
        self.assertEqual(len(frame_rows), reserved)

        rt.stop()
        recording = Recording.open(rt.session_dir)
        self.assertEqual(len(recording.frames), reserved)
        self.assertEqual(recording.manifest["frame_count"], reserved)
        final_rows = recording.timeline()
        end_rows = [row for row in final_rows if row.get("type") == "end"]
        self.assertEqual(end_rows[0]["frame_count"], reserved)
        for row in final_rows:
            if row.get("type") == "frame":
                self.assertTrue((rt.session_dir / row["file"]).is_file())
        self.assertFalse((rt.session_dir / ".encode").exists())
        for path in recording.frames:
            self.assertEqual(read_png_rgb(path)[:2], (800, 600))

    def test_first_frame_is_complete_at_ready(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        self.assertEqual(rt.ready["frames"], 1)
        self.assertTrue((rt.session_dir / "frames" / "000001.png").is_file())
        encode_dir = rt.session_dir / ".encode"
        self.assertEqual(
            list(encode_dir.glob("*")) if encode_dir.exists() else [], []
        )

    def test_encode_budget_allows_one_oversized_frame(self) -> None:
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_ENCODE_BUDGET_BYTES": "1"}
        ):
            rt = self._runtime()
            self.addCleanup(rt.stop)
            rt.start()
            rt.wait(frames=5)
            rt.stop()

        recording = Recording.open(rt.session_dir)
        self.assertEqual(len(recording.frames), 6)
        self.assertEqual(recording.manifest["frame_count"], 6)
        self.assertFalse((rt.session_dir / ".encode").exists())

    def test_snapshot_during_async_recording(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        rt.wait(frames=3)

        reply = rt.snapshot("async")
        snapshot = rt.session_dir / reply["file"]
        self.assertTrue(snapshot.is_file())

        rt.stop()
        recording = Recording.open(rt.session_dir)
        self.assertTrue(snapshot.is_file())
        for path in recording.frames:
            read_png_rgb(path)


if __name__ == "__main__":
    unittest.main()
