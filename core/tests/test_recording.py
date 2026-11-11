"""Recording: read one session's evidence without starting the engine.

The fixtures below build the minimal session described in SPEC
``### Testing Decisions / Seams``: manifest + timeline + one PNG +
frame_diffs + annotations + engine.log (plus build.log).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lvgl_ai import Recording
from session_fixtures import FRAME_1 as FRAME
from session_fixtures import make_recording_session as make_session
from support import write_png_rgb


class RecordingReadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_open_reads_every_session_artifact(self) -> None:
        session = make_session(self.root)
        recording = Recording.open(session)

        self.assertEqual(recording.path, session)
        self.assertEqual(recording.manifest["schema"], "lvgl-ai-session-v1")
        self.assertEqual(recording.manifest["status"], "ok")

        timeline = recording.timeline()
        self.assertEqual([row["type"] for row in timeline], ["frame", "end"])
        self.assertEqual(timeline[0]["file"], FRAME)

        self.assertEqual(recording.frames, [session / FRAME])
        self.assertEqual(recording.snapshots, [])

        diffs = recording.frame_diffs()
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["changed_px"], 1)
        self.assertIsNone(recording.reference_diffs())

        annotations = recording.annotations
        self.assertEqual(annotations["schema"], "lvgl-ai-annotations-v1")
        self.assertEqual(len(annotations["notes"]), 1)

        log_text = recording.log()
        self.assertIn("[app] app_create", log_text)
        self.assertEqual(recording.log_tail(1), ["[app] hello"])
        self.assertEqual(recording.log_tail(0), [])
        self.assertIn("# phase: build", recording.build_log())

    def test_open_never_starts_an_engine_process(self) -> None:
        session = make_session(self.root)
        with mock.patch(
            "subprocess.Popen", side_effect=AssertionError("Recording must not spawn")
        ):
            recording = Recording.open(session)
            recording.log_tail(5)
            recording.frame_diffs()

    def test_snapshot_files_are_listed(self) -> None:
        session = make_session(self.root)
        (session / "snapshots").mkdir()
        write_png_rgb(
            session / "snapshots" / "001_after_click.png", 1, 1, [(0, 0, 0)]
        )
        recording = Recording.open(session)
        self.assertEqual(
            recording.snapshots, [session / "snapshots" / "001_after_click.png"]
        )

    def test_open_accepts_manifest_path(self) -> None:
        session = make_session(self.root)
        recording = Recording.open(session / "manifest.json")
        self.assertEqual(recording.path, session)
        self.assertEqual(recording.manifest["id"], session.name)

    def test_missing_session_directory_raises_with_path(self) -> None:
        missing = self.root / "does-not-exist"
        with self.assertRaises(FileNotFoundError) as caught:
            Recording.open(missing)
        self.assertIn(str(missing), str(caught.exception))

    def test_missing_manifest_raises_with_path(self) -> None:
        session = make_session(self.root)
        (session / "manifest.json").unlink()
        with self.assertRaises(FileNotFoundError) as caught:
            Recording.open(session)
        self.assertIn("manifest.json", str(caught.exception))

    def test_missing_engine_log_raises_with_path(self) -> None:
        session = make_session(self.root, with_engine_log=False)
        with self.assertRaises(FileNotFoundError) as caught:
            Recording.open(session)
        self.assertIn("engine.log", str(caught.exception))

    def test_missing_timeline_raises_with_path(self) -> None:
        session = make_session(self.root, with_timeline=False)
        with self.assertRaises(FileNotFoundError) as caught:
            Recording.open(session)
        self.assertIn("timeline.ndjson", str(caught.exception))

    def test_missing_frame_diffs_raises_with_path(self) -> None:
        session = make_session(self.root, with_frame_diffs=False)
        with self.assertRaises(FileNotFoundError) as caught:
            Recording.open(session)
        self.assertIn("frame_diffs.ndjson", str(caught.exception))

    def test_record_false_session_without_recording_files_opens(self) -> None:
        session = make_session(
            self.root,
            artifacts={
                "manifest": "manifest.json",
                "build_log": "build.log",
                "engine_log": "engine.log",
            },
            with_timeline=False,
            with_frame_diffs=False,
            with_annotations=False,
            with_frames=False,
        )
        recording = Recording.open(session)
        self.assertEqual(recording.frames, [])
        self.assertEqual(recording.snapshots, [])
        with self.assertRaises(FileNotFoundError):
            recording.timeline()
        with self.assertRaises(FileNotFoundError):
            recording.frame_diffs()

    def test_missing_annotations_is_not_an_error(self) -> None:
        session = make_session(self.root, with_annotations=False)
        recording = Recording.open(session)
        self.assertEqual(
            recording.annotations,
            {"schema": "lvgl-ai-annotations-v1", "notes": []},
        )

    def test_bad_manifest_schema_raises_value_error_with_path(self) -> None:
        session = make_session(self.root, manifest_schema="lvgl-ai-session-v0")
        with self.assertRaises(ValueError) as caught:
            Recording.open(session)
        self.assertIn("manifest.json", str(caught.exception))
        self.assertIn("lvgl-ai-session-v1", str(caught.exception))

    def test_unknown_manifest_status_raises_value_error(self) -> None:
        session = make_session(self.root, status="failed")
        with self.assertRaises(ValueError) as caught:
            Recording.open(session)
        self.assertIn("status", str(caught.exception))

    def test_bad_timeline_schema_raises_value_error_with_line(self) -> None:
        session = make_session(self.root)
        path = session / "timeline.ndjson"
        rows = [
            {"schema": "lvgl-ai-timeline-v1", "type": "end"},
            {"schema": "lvgl-ai-timeline-v0", "type": "end"},
        ]
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        recording = Recording.open(session)
        with self.assertRaises(ValueError) as caught:
            recording.timeline()
        self.assertIn("timeline.ndjson:2", str(caught.exception))

    def test_unknown_timeline_row_type_raises_value_error(self) -> None:
        session = make_session(self.root)
        path = session / "timeline.ndjson"
        path.write_text(
            json.dumps({"schema": "lvgl-ai-timeline-v1", "type": "tree"}) + "\n",
            encoding="utf-8",
        )
        recording = Recording.open(session)
        with self.assertRaises(ValueError) as caught:
            recording.timeline()
        self.assertIn("type", str(caught.exception))

    def test_bad_frame_diff_schema_raises_value_error(self) -> None:
        session = make_session(self.root)
        path = session / "frame_diffs.ndjson"
        path.write_text(
            json.dumps({"schema": "lvgl-ai-frame-diffs-v0"}) + "\n", encoding="utf-8"
        )
        recording = Recording.open(session)
        with self.assertRaises(ValueError) as caught:
            recording.frame_diffs()
        self.assertIn("frame_diffs.ndjson:1", str(caught.exception))


class RecordingAnnotationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_annotations_are_writable_and_reloadable(self) -> None:
        session = make_session(self.root, with_annotations=False)
        recording = Recording.open(session)
        note = {
            "id": "n1",
            "frame_no": 2,
            "t_ms": 16,
            "regions": [{"x": 1, "y": 2, "w": 3, "h": 4}],
            "tags": ["color"],
            "text": "wrong background",
        }
        recording.annotations = {
            "schema": "lvgl-ai-annotations-v1",
            "notes": [note],
        }

        saved = json.loads(
            (session / "annotations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["schema"], "lvgl-ai-annotations-v1")
        self.assertEqual(saved["notes"], [note])
        self.assertEqual(Recording.open(session).annotations["notes"], [note])

    def test_annotations_setter_adds_schema_when_missing(self) -> None:
        session = make_session(self.root, with_annotations=False)
        recording = Recording.open(session)
        recording.annotations = {"notes": []}
        saved = json.loads(
            (session / "annotations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved, {"schema": "lvgl-ai-annotations-v1", "notes": []})

    def test_invalid_annotations_raise_value_error(self) -> None:
        session = make_session(self.root, with_annotations=False)
        recording = Recording.open(session)
        for value in (
            [],
            {"schema": "lvgl-ai-annotations-v0", "notes": []},
            {"schema": "lvgl-ai-annotations-v1", "notes": "nope"},
            {"schema": "lvgl-ai-annotations-v1", "notes": [1]},
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    recording.annotations = value
        self.assertFalse((session / "annotations.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
