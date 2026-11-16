from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from control.anchors import derive_anchor, resolve_anchor
from control.recording import Recording
from scripts.tests.session_fixtures import make_session
from scripts.tests.control.test_session_report import make_query_session


class ResolveAnchorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_query_session(self.root)
        self.recording = Recording.open(self.session)

    def test_click_event_is_the_frame_before_down(self) -> None:
        result = resolve_anchor(
            self.recording,
            {"kind": "click", "seq_down": 1, "seq_up": 2},
            at="event",
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["frame_no"], 2)
        self.assertEqual(result["image_kind"], "frame")
        self.assertEqual(result["basis"], "click_1_event")
        self.assertEqual(result["candidates"], {"before": 2, "after": 4})

    def test_click_result_is_the_first_evidence_after_up(self) -> None:
        result = resolve_anchor(
            self.recording,
            {"kind": "click", "seq_down": 1, "seq_up": 2},
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["frame_no"], 4)
        self.assertEqual(result["basis"], "click_2_after")
        self.assertEqual(result["relation"], "after")
        self.assertEqual(result["delta_ms"], 16)

    def test_click_offset_lands_on_the_requested_time(self) -> None:
        result = resolve_anchor(
            self.recording,
            {
                "kind": "click",
                "seq_down": 1,
                "seq_up": 2,
                "offset_ms": 16,
            },
        )

        self.assertTrue(result["resolved"])
        self.assertEqual(result["requested_t_ms"], 48)
        self.assertEqual(result["resolved_t_ms"], 48)
        self.assertEqual(result["resolved_t_ms"], 48)
        self.assertEqual(result["relation"], "exact")

    def test_input_event_and_result(self) -> None:
        event = resolve_anchor(
            self.recording, {"kind": "input", "seq": 1}, at="event"
        )
        result = resolve_anchor(self.recording, {"kind": "input", "seq": 1})

        self.assertEqual(event["frame_no"], 2)
        self.assertEqual(result["frame_no"], 2)
        self.assertEqual(result["image_kind"], "snapshot")
        self.assertEqual(result["basis"], "input_1_after")

    def test_mark_prefers_a_snapshot_at_the_same_t_ms(self) -> None:
        result = resolve_anchor(
            self.recording, {"kind": "mark", "id": "after_click"}
        )

        self.assertEqual(result["image_kind"], "snapshot")
        self.assertEqual(result["snapshot"], "after")
        self.assertEqual(result["frame_no"], 2)

    def test_repeated_mark_is_ambiguous(self) -> None:
        path = self.session / "timeline.ndjson"
        row = {
            "schema": "lvgl-verify-loop-timeline-v1",
            "type": "mark",
            "frame_no": 3,
            "t_ms": 32,
            "id": "after_click",
        }
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row) + "\n")

        result = resolve_anchor(
            Recording.open(self.session), {"kind": "mark", "id": "after_click"}
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertTrue(result["approximate"])

    def test_missing_mark_is_missing(self) -> None:
        result = resolve_anchor(self.recording, {"kind": "mark", "id": "nope"})

        self.assertFalse(result["resolved"])
        self.assertEqual(result["status"], "missing")

    def test_t_ms_falls_back_to_the_nearest_evidence(self) -> None:
        result = resolve_anchor(self.recording, {"kind": "t_ms", "t_ms": 24})

        self.assertTrue(result["resolved"])
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["relation"], "after")
        self.assertEqual(result["frame_no"], 3)

    def test_frame_lookup_uses_the_frame_number(self) -> None:
        result = resolve_anchor(
            self.recording, {"kind": "frame", "frame_no": 1}
        )

        self.assertEqual(result["frame_no"], 1)
        self.assertEqual(result["relation"], "exact")

    def test_record_false_session_has_no_timeline(self) -> None:
        session = make_session(
            self.root,
            name="20260201-000000-aaaa",
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        result = resolve_anchor(
            Recording.open(session),
            {"kind": "t_ms", "t_ms": 0},
        )

        self.assertEqual(result["status"], "no_timeline")
        self.assertFalse(result["resolved"])

    def test_snapshot_only_evidence_has_a_null_frame_no(self) -> None:
        path = self.session / "timeline.ndjson"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        rows.insert(
            0,
            {
                "schema": "lvgl-verify-loop-timeline-v1",
                "type": "snapshot",
                "frame_no": None,
                "t_ms": 0,
                "label": "early",
                "file": "snapshots/001_after.png",
            },
        )
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

        result = resolve_anchor(
            Recording.open(self.session), {"kind": "t_ms", "t_ms": 0}
        )

        self.assertEqual(result["frame_no"], None)
        self.assertEqual(result["image_kind"], "snapshot")
        self.assertEqual(result["snapshot"], "early")


class DeriveAnchorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_query_session(self.root)
        self.recording = Recording.open(self.session)

    def test_frame_after_a_click_derives_the_click(self) -> None:
        path = self.session / "timeline.ndjson"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("type") != "mark"
        ]
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

        anchor = derive_anchor(
            Recording.open(self.session), frame_no=4, t_ms=48
        )

        self.assertEqual(anchor["kind"], "click")
        self.assertEqual(anchor["seq_down"], 1)
        self.assertEqual(anchor["seq_up"], 2)
        self.assertEqual(anchor["offset_ms"], 16)

    def test_mark_wins_when_it_is_the_nearest_row(self) -> None:
        anchor = derive_anchor(self.recording, frame_no=3, t_ms=33)

        self.assertEqual(anchor["kind"], "mark")
        self.assertEqual(anchor["id"], "after_click")

    def test_plain_frame_falls_back_to_t_ms(self) -> None:
        anchor = derive_anchor(self.recording, frame_no=1, t_ms=0)

        self.assertEqual(anchor, {"kind": "t_ms", "t_ms": 0})

    def test_missing_timeline_falls_back_to_t_ms(self) -> None:
        session = make_session(
            self.root,
            name="20260201-000000-bbbb",
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        anchor = derive_anchor(Recording.open(session), frame_no=0, t_ms=12)

        self.assertEqual(anchor, {"kind": "t_ms", "t_ms": 12})


if __name__ == "__main__":
    unittest.main(verbosity=2)
