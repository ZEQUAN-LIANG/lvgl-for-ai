"""Changed-only recording against the real engine.

The default coffee screen is static for the first few ticks; the hidden demo
button at (112, 324) gives a deterministic pixel change. These tests verify
that identical frames are skipped without breaking frame numbers, timeline
rows, diff rows, snapshots or the raw live preview.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from lvgl_ai import Recording, Runtime

BUTTON_CENTER = (112, 324)


class ChangedFramesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self, **kwargs) -> Runtime:
        options = {
            "lvgl": "9.6",
            "build": True,
            "app": "coffee",
            "sessions_root": self.sessions_root,
        }
        options.update(kwargs)
        return Runtime(**options)

    def test_static_ticks_are_skipped_and_changes_stay_contiguous(self) -> None:
        rt = self._runtime(record_changed_only=True)
        self.addCleanup(rt.stop)
        rt.start()

        for _ in range(3):
            rt.tick(16)
        self.assertEqual(rt.frame_count, 1)
        self.assertEqual(rt.t_ms, 48)

        # A wait with no visual change keeps frame_start == frame_end.
        rt.wait(ms=64)
        self.assertEqual(rt.frame_count, 1)

        before_snapshot = rt.frame_count
        rt.snapshot("still")
        self.assertEqual(rt.frame_count, before_snapshot)

        rt.pointer("down", *BUTTON_CENTER)
        rt.wait(ms=64)
        self.assertGreater(rt.frame_count, 1)

        rt.pointer("up", *BUTTON_CENTER)
        rt.wait(ms=64)
        self.assertGreater(rt.frame_count, 1)
        # The engine's reserved-frame count; the manifest counts drained PNGs.
        reserved = rt.frame_count

        rt.stop()
        recording = Recording.open(rt.session_dir)
        frames = recording.frames
        self.assertGreaterEqual(len(frames), 2)
        frame_nos = [int(path.stem) for path in frames]
        self.assertEqual(frame_nos, list(range(1, len(frames) + 1)))

        timeline = recording.timeline()
        frame_rows = [row for row in timeline if row.get("type") == "frame"]
        self.assertEqual([row["frame_no"] for row in frame_rows], frame_nos)
        self.assertEqual(
            [row["file"] for row in frame_rows],
            [f"frames/{number:06d}.png" for number in frame_nos],
        )
        wait_rows = [row for row in timeline if row.get("type") == "wait"]
        self.assertTrue(
            any(
                row["frame_start"] == 1 and row["frame_end"] == 1
                for row in wait_rows
            )
        )

        diffs = recording.frame_diffs()
        self.assertEqual([row["frame_no"] for row in diffs], frame_nos[1:])
        self.assertEqual(
            [row["prev_frame_no"] for row in diffs], frame_nos[:-1]
        )
        for row in diffs:
            self.assertGreater(row["max_delta"], 0.0)

        manifest = recording.manifest
        self.assertEqual(manifest["frame_count"], len(frames))
        self.assertEqual(manifest["frame_count"], reserved)
        self.assertIs(manifest["record_changed_only"], True)
        self.assertIs(manifest["truncated"], False)
        self.assertTrue(list((rt.session_dir / "snapshots").glob("*.png")))

    def test_max_frames_counts_retained_frames_only(self) -> None:
        rt = self._runtime(record_changed_only=True, max_frames=1)
        self.addCleanup(rt.stop)
        rt.start()

        static = rt.tick(16)
        self.assertIs(static["truncated"], False)
        self.assertEqual(rt.frame_count, 1)

        rt.pointer("down", *BUTTON_CENTER)
        changed = rt.tick(16)
        self.assertIs(changed["truncated"], True)
        self.assertEqual(rt.frame_count, 1)
        reserved = rt.frame_count

        rt.stop()
        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.manifest["frame_count"], 1)
        self.assertEqual(recording.manifest["frame_count"], reserved)
        self.assertEqual(
            recording.manifest["frame_count"], len(recording.frames)
        )
        self.assertIs(recording.manifest["truncated"], True)
        self.assertEqual(len(recording.frames), 1)

    def test_live_frame_is_rewritten_only_when_pixels_change(self) -> None:
        rt = self._runtime(
            record=False, live_frame=True, record_changed_only=True
        )
        self.addCleanup(rt.stop)
        rt.start()

        live_path = rt.session_dir / "live.rgba"
        self.assertTrue(live_path.is_file())
        raw = live_path.read_bytes()
        self.assertEqual(len(raw), 800 * 600 * 4)
        self.assertEqual(set(raw[3::4]), {255})
        before = hashlib.sha256(raw).hexdigest()
        start_count = rt.frame_count

        rt.tick(16)
        rt.tick(16)
        self.assertEqual(rt.frame_count, start_count)
        self.assertEqual(
            hashlib.sha256(live_path.read_bytes()).hexdigest(), before
        )

        rt.pointer("down", *BUTTON_CENTER)
        rt.tick(16)
        self.assertGreater(rt.frame_count, start_count)
        self.assertNotEqual(
            hashlib.sha256(live_path.read_bytes()).hexdigest(), before
        )

        rt.stop()
        self.assertFalse(live_path.exists())
        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.frames, [])
        self.assertIs(recording.manifest["record_changed_only"], True)

    def test_live_frame_uses_the_configured_display_size(self) -> None:
        rt = self._runtime(
            record=False,
            live_frame=True,
            record_changed_only=True,
            width=640,
            height=480,
        )
        self.addCleanup(rt.stop)
        rt.start()

        live_path = rt.session_dir / "live.rgba"
        raw = live_path.read_bytes()
        self.assertEqual(len(raw), 640 * 480 * 4)
        self.assertEqual(set(raw[3::4]), {255})

        rt.stop()
        self.assertFalse(live_path.exists())

    def test_changed_only_keeps_reference_rows_aligned_with_retained_frames(
        self,
    ) -> None:
        baseline = self._runtime(build=True, record_changed_only=False)
        baseline.start()
        baseline.wait(16)
        baseline.stop()
        reference = baseline.session_dir / "frames" / "000002.png"

        rt = self._runtime(record_changed_only=True, reference=reference)
        self.addCleanup(rt.stop)
        rt.start()

        for _ in range(3):
            rt.tick(16)
        self.assertEqual(rt.frame_count, 1)

        rt.pointer("down", *BUTTON_CENTER)
        rt.wait(64)
        rt.mark("after_press")
        rt.snapshot("after_press")
        rt.pointer("up", *BUTTON_CENTER)
        rt.wait(64)
        rt.stop()

        recording = Recording.open(rt.session_dir)
        frame_nos = [int(path.stem) for path in recording.frames]
        self.assertGreater(len(frame_nos), 1)
        self.assertEqual(frame_nos, list(range(1, len(frame_nos) + 1)))

        timeline = recording.timeline()
        frame_rows = [row for row in timeline if row.get("type") == "frame"]
        self.assertEqual([row["frame_no"] for row in frame_rows], frame_nos)
        self.assertEqual(
            [row["file"] for row in frame_rows],
            [f"frames/{number:06d}.png" for number in frame_nos],
        )

        diffs = recording.frame_diffs()
        self.assertEqual([row["frame_no"] for row in diffs], frame_nos[1:])
        self.assertEqual([row["prev_frame_no"] for row in diffs], frame_nos[:-1])

        reference_rows = recording.reference_diffs()
        self.assertIsNotNone(reference_rows)
        self.assertEqual([row["frame_no"] for row in reference_rows], frame_nos)
        self.assertTrue(
            all(row["prev_frame_no"] is None for row in reference_rows)
        )
        self.assertEqual(reference_rows[0]["changed_px"], 0)
        self.assertEqual(recording.manifest["frame_count"], len(frame_nos))
        self.assertEqual(
            recording.manifest["artifacts"]["reference_diffs"],
            "reference_diffs.ndjson",
        )

    def test_recording_keeps_png_evidence_and_a_raw_preview(self) -> None:
        rt = self._runtime(
            record=True, live_frame=True, record_changed_only=True
        )
        self.addCleanup(rt.stop)
        rt.start()

        live_path = rt.session_dir / "live.rgba"
        frame_path = rt.session_dir / "frames" / "000001.png"
        self.assertTrue(live_path.is_file())
        self.assertTrue(frame_path.is_file())
        before = hashlib.sha256(live_path.read_bytes()).hexdigest()

        rt.pointer("down", *BUTTON_CENTER)
        rt.tick(16)
        self.assertNotEqual(
            hashlib.sha256(live_path.read_bytes()).hexdigest(), before
        )

        rt.stop()
        self.assertGreaterEqual(
            len(list((rt.session_dir / "frames").glob("*.png"))), 2
        )
        self.assertFalse(live_path.exists())
        self.assertTrue(frame_path.is_file())
        recording = Recording.open(rt.session_dir)
        self.assertGreaterEqual(recording.manifest["frame_count"], 2)

    def test_live_preview_continues_after_the_frame_cap(self) -> None:
        rt = self._runtime(
            record=True,
            live_frame=True,
            record_changed_only=True,
            max_frames=1,
        )
        self.addCleanup(rt.stop)
        rt.start()

        live_path = rt.session_dir / "live.rgba"
        before = hashlib.sha256(live_path.read_bytes()).hexdigest()
        self.assertEqual(rt.frame_count, 1)

        rt.pointer("down", *BUTTON_CENTER)
        changed = rt.tick(16)
        self.assertIs(changed["truncated"], True)
        self.assertEqual(rt.frame_count, 1)
        after_down = hashlib.sha256(live_path.read_bytes()).hexdigest()
        self.assertNotEqual(after_down, before)

        rt.pointer("up", *BUTTON_CENTER)
        rt.tick(16)
        self.assertNotEqual(
            hashlib.sha256(live_path.read_bytes()).hexdigest(), after_down
        )

        rt.stop()
        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.manifest["frame_count"], 1)
        self.assertIs(recording.manifest["truncated"], True)

    def test_tick_updates_virtual_time_and_skips_checks_on_request(self) -> None:
        rt = self._runtime(record_changed_only=True)
        self.addCleanup(rt.stop)
        rt.start()

        rt.tick(16)
        self.assertGreaterEqual(rt.t_ms, 16)
        stamp = rt.t_ms
        rt.tick(32, track_check=False)
        self.assertGreater(rt.t_ms, stamp)

        rt.stop()
        checks = Recording.open(rt.session_dir).manifest["checks"]
        commands = [check["cmd"] for check in checks]
        self.assertIn("tick 16", commands)
        self.assertNotIn("tick 32", commands)


if __name__ == "__main__":
    unittest.main()
