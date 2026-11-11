"""The replay model is the one evidence-to-view conversion for HTML and JSON.

``replay_model.load(recording)`` reads every evidence file once and exposes the
frame rows, snapshot labels, timeline rows, diff tables, log tails and note
view fields the page and the ``/api/sessions`` series both render.  Missing or
corrupt files degrade to the same empty values the page has always shown while
keeping the read error available to the JSON endpoints that used to raise.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lvgl_ai import Recording
from lvgl_ai.web import replay_model
from web_support import SESSION_ID, make_web_session


class _CountingRecording(Recording):
    """Recording that counts evidence reads, to prove at-most-once loading."""

    def __init__(self, path) -> None:
        super().__init__(path)
        self.reads = {
            "timeline": 0,
            "frame_diffs": 0,
            "annotations": 0,
            "log": 0,
            "build_log": 0,
        }

    @property
    def timeline_reads(self) -> int:
        return self.reads["timeline"]

    def timeline(self):
        self.reads["timeline"] += 1
        return super().timeline()

    def frame_diffs(self):
        self.reads["frame_diffs"] += 1
        return super().frame_diffs()

    @property
    def annotations(self):
        self.reads["annotations"] += 1
        return super().annotations

    def log(self):
        self.reads["log"] += 1
        return super().log()

    def build_log(self):
        self.reads["build_log"] += 1
        return super().build_log()


class ReplayModelLoadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root, frame_count=3)

    def _write_annotations(self, document) -> None:
        (self.session / "annotations.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )

    def test_one_timeline_read_feeds_frames_snapshots_and_timeline(self) -> None:
        recording = _CountingRecording(self.session)
        model = replay_model.load(recording)
        self.assertEqual(recording.timeline_reads, 0)

        self.assertEqual(model.session_id, SESSION_ID)
        self.assertEqual(model.manifest["frame_count"], 3)
        self.assertEqual([row["type"] for row in model.timeline][0], "frame")
        self.assertEqual(
            [frame["frame_no"] for frame in model.frames], [1, 2, 3]
        )
        self.assertEqual([frame["t_ms"] for frame in model.frames], [0, 16, 32])
        self.assertEqual(model.frames[0]["file"], "frames/000001.png")
        self.assertEqual(
            model.frames[0]["url"], f"/frames/{SESSION_ID}/000001.png"
        )
        self.assertEqual(len(model.snapshots), 1)
        self.assertEqual(model.snapshots[0]["label"], "after_click")
        self.assertEqual(model.snapshots[0]["frame_no"], 2)
        self.assertEqual(model.snapshots[0]["t_ms"], 16)
        self.assertEqual(
            model.snapshots[0]["url"],
            f"/snapshots/{SESSION_ID}/001_after_click.png",
        )
        self.assertEqual(recording.reads["timeline"], 1)

    def test_frames_before_timeline_still_read_the_timeline_once(self) -> None:
        recording = _CountingRecording(self.session)
        model = replay_model.load(recording)

        self.assertEqual(
            [frame["frame_no"] for frame in model.frames], [1, 2, 3]
        )
        self.assertEqual([frame["t_ms"] for frame in model.frames], [0, 16, 32])
        self.assertEqual(model.snapshots[0]["label"], "after_click")
        self.assertTrue(model.timeline)
        self.assertEqual(recording.reads["timeline"], 1)

    def test_missing_timeline_falls_back_to_file_numbers(self) -> None:
        (self.session / "timeline.ndjson").unlink()
        model = replay_model.load(Recording(self.session))

        self.assertEqual(model.timeline, [])
        self.assertIsInstance(model.timeline_error, FileNotFoundError)
        self.assertEqual(
            [frame["frame_no"] for frame in model.frames], [1, 2, 3]
        )
        self.assertEqual([frame["t_ms"] for frame in model.frames], [0, 0, 0])

    def test_corrupt_timeline_degrades_to_empty_rows(self) -> None:
        (self.session / "timeline.ndjson").write_text(
            "{broken\n", encoding="utf-8"
        )
        model = replay_model.load(Recording(self.session))

        self.assertEqual(model.timeline, [])
        self.assertIsInstance(model.timeline_error, ValueError)
        self.assertEqual(
            [frame["frame_no"] for frame in model.frames], [1, 2, 3]
        )
        self.assertEqual(model.snapshots[0]["label"], "001_after_click")

    def test_corrupt_diffs_and_annotations_degrade_with_their_errors(self) -> None:
        (self.session / "frame_diffs.ndjson").write_text(
            "{broken\n", encoding="utf-8"
        )
        (self.session / "annotations.json").write_text(
            "{broken\n", encoding="utf-8"
        )
        model = replay_model.load(Recording(self.session))

        self.assertEqual(model.frame_diffs, [])
        self.assertIsInstance(model.frame_diffs_error, ValueError)
        self.assertEqual(
            model.annotations,
            {"schema": "lvgl-ai-annotations-v1", "notes": []},
        )
        self.assertIn("invalid JSON", str(model.annotations_error))

    def test_reference_diffs_stay_none_when_missing(self) -> None:
        model = replay_model.load(Recording(self.session))
        self.assertIsNone(model.reference_diffs)
        self.assertIsNone(model.reference_diffs_error)

    def test_corrupt_reference_diffs_are_flagged_for_the_json_endpoint(self) -> None:
        (self.session / "reference_diffs.ndjson").write_text(
            "{broken\n", encoding="utf-8"
        )
        model = replay_model.load(Recording(self.session))

        self.assertEqual(model.reference_diffs, [])
        self.assertIsInstance(model.reference_diffs_error, ValueError)

    def test_note_views_carry_labels_tags_regions_and_crop_urls(self) -> None:
        self._write_annotations(
            {
                "schema": "lvgl-ai-annotations-v1",
                "notes": [
                    {
                        "id": "note-1",
                        "frame_no": 2,
                        "t_ms": 16,
                        "regions": [
                            {
                                "x": 1,
                                "y": 2,
                                "w": 3,
                                "h": 4,
                                "image": "regions/note-1-0.png",
                            },
                            {"x": 5, "y": 6, "w": 7, "h": 8},
                        ],
                        "tags": ["layout", "color"],
                        "text": "button is too low",
                    }
                ],
            }
        )
        model = replay_model.load(Recording(self.session))
        views = model.note_views()

        self.assertEqual(len(views), 1)
        view = views[0]
        self.assertEqual(view["id"], "note-1")
        self.assertTrue(view["has_frame"])
        self.assertEqual(view["meta"], "帧 2 · t=16 ms")
        self.assertEqual(view["tags"], "#layout #color")
        self.assertEqual(view["region_text"], "(1, 2) 3×4；(5, 6) 7×8")
        self.assertEqual(view["text"], "button is too low")
        self.assertEqual(
            view["crops"],
            [{"url": f"/regions/{SESSION_ID}/note-1-0.png", "alt": "标注区域图"}],
        )

    def test_note_without_frame_number_has_no_jump_attribute(self) -> None:
        self._write_annotations(
            {
                "schema": "lvgl-ai-annotations-v1",
                "notes": [
                    {
                        "id": "note-2",
                        "frame_no": "n/a",
                        "t_ms": 0,
                        "regions": [],
                        "tags": [],
                        "text": "",
                    }
                ],
            }
        )
        model = replay_model.load(Recording(self.session))
        view = model.note_views()[0]

        self.assertFalse(view["has_frame"])
        self.assertEqual(view["meta"], "帧 n/a · t=0 ms")
        self.assertEqual(view["tags"], "")
        self.assertEqual(view["region_text"], "")
        self.assertEqual(view["crops"], [])

    def test_log_tails_default_to_eighty_and_forty_lines(self) -> None:
        (self.session / "engine.log").write_text(
            "".join(f"line {number}\n" for number in range(1, 101)),
            encoding="utf-8",
        )
        (self.session / "build.log").write_text(
            "".join(f"build {number}\n" for number in range(1, 51)),
            encoding="utf-8",
        )
        model = replay_model.load(Recording(self.session))

        self.assertEqual(len(model.log_tail), 80)
        self.assertEqual(model.log_tail[0], "line 21")
        self.assertEqual(model.log_tail[-1], "line 100")
        self.assertEqual(len(model.build_log_tail), 40)
        self.assertEqual(model.build_log_tail[0], "build 11")

    def test_missing_build_log_is_empty_not_an_error(self) -> None:
        (self.session / "build.log").unlink()
        model = replay_model.load(Recording(self.session))
        self.assertEqual(model.build_log_tail, [])

    def test_sections_are_read_only_when_asked_for(self) -> None:
        recording = _CountingRecording(self.session)
        model = replay_model.load(recording)

        self.assertTrue(model.timeline)
        self.assertEqual(recording.reads["timeline"], 1)
        self.assertEqual(recording.reads["frame_diffs"], 0)
        self.assertEqual(recording.reads["annotations"], 0)
        self.assertEqual(recording.reads["log"], 0)
        self.assertEqual(recording.reads["build_log"], 0)

    def test_prime_reads_every_page_section_once(self) -> None:
        recording = _CountingRecording(self.session)
        replay_model.load(recording).prime()

        self.assertEqual(
            recording.reads,
            {
                "timeline": 1,
                "frame_diffs": 1,
                "annotations": 1,
                "log": 1,
                "build_log": 1,
            },
        )

    def test_note_missing_optional_values_renders_empty_text(self) -> None:
        self._write_annotations(
            {
                "schema": "lvgl-ai-annotations-v1",
                "notes": [
                    {
                        "id": "partial",
                        "regions": [],
                        "tags": [],
                        "text": "",
                    }
                ],
            }
        )
        view = replay_model.load(Recording(self.session)).note_views()[0]

        self.assertEqual(view["meta"], "帧  · t= ms")
        self.assertFalse(view["has_frame"])

    def test_empty_model_has_the_shapes_the_page_expects(self) -> None:
        model = replay_model.ReplayModel.empty()
        self.assertIsNone(model.session_id)
        self.assertEqual(model.manifest, {})
        self.assertEqual(
            (model.frames, model.snapshots, model.timeline), ([], [], [])
        )
        self.assertEqual(
            model.annotations,
            {"schema": "lvgl-ai-annotations-v1", "notes": []},
        )
        self.assertEqual(model.note_views(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
