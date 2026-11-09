"""Virtual pointer, virtual time, full frames and timeline evidence.

All tests here use the real engine with a temporary session root. The button
below is created by ``user/app/app.c``; its screen rectangle is
x=32..192, y=300..348, so the center is (112, 324).
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from lvgl_ai import Runtime
from support import read_ndjson, read_png_rgb

BUTTON_CENTER = (112, 324)


def frame_hashes(session_dir: Path) -> list[tuple[str, str]]:
    hashes = []
    for path in sorted((session_dir / "frames").glob("*.png")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes.append((path.name, digest))
    return hashes


class PointerTimelineIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self) -> Runtime:
        return Runtime(lvgl="9.6", build=True, sessions_root=self.sessions_root)

    def test_pointer_hits_named_button_and_timeline_input_rows(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        down = rt.pointer("down", *BUTTON_CENTER)
        self.assertEqual(down["hit"], "demo_button")
        self.assertEqual(down["hit_class"], "lv_button")
        rt.tick(16)
        up = rt.pointer("up", *BUTTON_CENTER)
        self.assertEqual(up["hit"], "demo_button")
        self.assertEqual(up["hit_class"], "lv_button")

        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        inputs = [row for row in rows if row["type"] == "input"]
        self.assertEqual(
            [(row["device"], row["action"], row["x"], row["y"]) for row in inputs],
            [("pointer", "down", 112, 324), ("pointer", "up", 112, 324)],
        )
        for row in inputs:
            self.assertEqual(row["schema"], "lvgl-ai-timeline-v1")
            self.assertEqual(row["hit"], "demo_button")
            self.assertEqual(row["hit_class"], "lv_button")

        # The callback only runs when LVGL itself delivers the click.
        log_text = (rt.session_dir / "engine.log").read_text(encoding="utf-8")
        self.assertIn("[app] demo_button clicked", log_text)

    def test_tick_and_wait_produce_one_png_per_step_and_wait_row(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        self.assertEqual(rt.ready["frames"], 1)

        rt.tick(16)
        self.assertEqual(rt.ready["frames"], 1)  # ready is a snapshot of startup
        rt.wait(48)

        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        frame_rows = [row for row in rows if row["type"] == "frame"]
        self.assertEqual([row["frame_no"] for row in frame_rows], [1, 2, 3, 4, 5])
        self.assertEqual([row["t_ms"] for row in frame_rows], [0, 16, 32, 48, 64])
        self.assertEqual([row["file"] for row in frame_rows], [
            "frames/000001.png",
            "frames/000002.png",
            "frames/000003.png",
            "frames/000004.png",
            "frames/000005.png",
        ])

        wait_rows = [row for row in rows if row["type"] == "wait"]
        self.assertEqual(len(wait_rows), 1)
        wait_row = wait_rows[0]
        self.assertEqual(wait_row["schema"], "lvgl-ai-timeline-v1")
        self.assertEqual((wait_row["t_ms_start"], wait_row["t_ms_end"]), (16, 64))
        self.assertEqual((wait_row["frame_start"], wait_row["frame_end"]), (2, 5))

        rt.stop()
        frames = sorted((rt.session_dir / "frames").glob("*.png"))
        self.assertEqual(
            [path.name for path in frames],
            [f"{index:06d}.png" for index in range(1, 6)],
        )
        for path in frames:
            width, height, _ = read_png_rgb(path)
            self.assertEqual((width, height), (800, 600))

        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        end_rows = [row for row in rows if row["type"] == "end"]
        self.assertEqual(len(end_rows), 1)
        self.assertEqual(end_rows[0]["frame_count"], 5)
        self.assertEqual(end_rows[0]["t_ms"], 64)
        self.assertIs(end_rows[0]["truncated"], False)

    def test_wait_frames_advances_exactly_n_frames(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        rt.tick(16)
        rt.wait(frames=3)
        rt.stop()

        frames = sorted((rt.session_dir / "frames").glob("*.png"))
        self.assertEqual(len(frames), 5)
        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        frame_rows = [row for row in rows if row["type"] == "frame"]
        self.assertEqual([row["t_ms"] for row in frame_rows], [0, 16, 32, 48, 64])
        wait_row = [row for row in rows if row["type"] == "wait"][0]
        self.assertEqual((wait_row["t_ms_start"], wait_row["t_ms_end"]), (16, 64))
        self.assertEqual((wait_row["frame_start"], wait_row["frame_end"]), (2, 5))

    def test_snapshot_and_mark_leave_named_files_and_rows(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        rt.pointer("down", *BUTTON_CENTER)

        reply = rt.snapshot("after_click")
        self.assertEqual(reply["file"], "snapshots/001_after_click.png")
        snapshot_path = rt.session_dir / "snapshots" / "001_after_click.png"
        self.assertTrue(snapshot_path.is_file())
        width, height, _ = read_png_rgb(snapshot_path)
        self.assertEqual((width, height), (800, 600))

        rt.mark("checkpoint")

        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        snapshots = [row for row in rows if row["type"] == "snapshot"]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["label"], "after_click")
        self.assertEqual(snapshots[0]["file"], "snapshots/001_after_click.png")
        marks = [row for row in rows if row["type"] == "mark"]
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["id"], "checkpoint")

    def test_input_events_are_validated_sorted_and_delivered(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        replies = rt.input(
            [
                {"at_ms": 32, "device": "pointer", "action": "up", "x": 112, "y": 324},
                {"at_ms": 0, "device": "pointer", "action": "down", "x": 112, "y": 324},
                {"at_ms": 16, "device": "pointer", "action": "move", "x": 112, "y": 324},
            ]
        )
        self.assertEqual(len(replies), 3)
        self.assertEqual(
            [reply["hit"] for reply in replies],
            ["demo_button", "demo_button", "demo_button"],
        )

        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        inputs = [row for row in rows if row["type"] == "input"]
        self.assertEqual(
            [(row["action"], row["t_ms"]) for row in inputs],
            [("down", 0), ("move", 16), ("up", 32)],
        )
        for row in inputs:
            self.assertEqual(row["hit"], "demo_button")
            self.assertEqual(row["hit_class"], "lv_button")
        log_text = (rt.session_dir / "engine.log").read_text(encoding="utf-8")
        self.assertIn("[app] demo_button clicked", log_text)

    def test_key_and_encoder_events_are_delivered(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        replies = rt.input(
            [
                {"at_ms": 0, "device": "key", "action": "press", "key": "ENTER"},
                {"at_ms": 16, "device": "encoder", "action": "turn", "diff": -1},
            ]
        )
        self.assertEqual([reply["delivered"] for reply in replies], [True, True])

        rows = read_ndjson(rt.session_dir / "timeline.ndjson")
        inputs = [row for row in rows if row["type"] == "input"]
        self.assertEqual(len(inputs), 2)
        self.assertEqual(
            (inputs[0]["device"], inputs[0]["action"], inputs[0]["key"]),
            ("key", "press", "ENTER"),
        )
        self.assertIs(inputs[0]["delivered"], True)
        self.assertEqual(
            (inputs[1]["device"], inputs[1]["action"], inputs[1]["diff"]),
            ("encoder", "turn", -1),
        )
        self.assertIs(inputs[1]["delivered"], True)

        # Release the key so the next input starts from a defined state.
        rt.key("release", "ENTER")

    def test_same_input_sequence_has_identical_frames(self) -> None:
        def run_once(root: Path) -> list[tuple[str, str]]:
            rt = Runtime(lvgl="9.6", build=True, sessions_root=root)
            try:
                rt.start()
                rt.pointer("down", *BUTTON_CENTER)
                rt.wait(32)
                rt.pointer("move", 120, 330)
                rt.pointer("up", 120, 330)
                rt.tick(16)
            finally:
                rt.stop()
            return frame_hashes(rt.session_dir)

        first = run_once(Path(self._tmp.name) / "first")
        second = run_once(Path(self._tmp.name) / "second")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
