from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from control import session_index
from control.evidence import INDEX_FIELDS
from scripts.tests.session_fixtures import make_session
from scripts.tests.control.test_session_report import make_query_session


class SessionIndexDegradeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_crash_tolerates_a_torn_timeline_line(self) -> None:
        session = make_query_session(self.root)
        path = session / "timeline.ndjson"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                '{"schema": "lvgl-verify-loop-timeline-v1", "type": "fra'
            )
        manifest_path = session / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "crash"
        manifest["error"] = {
            "code": "crash",
            "message": "engine died",
            "detail": {},
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        index = session_index(session)

        self.assertEqual(index["status"], "crash")
        self.assertEqual(index["counts"]["inputs"], 2)
        self.assertEqual(index["error"]["code"], "crash")

    def test_build_error_has_no_display_or_frames(self) -> None:
        session = make_session(
            self.root,
            status="build_error",
            display=None,
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
            error={
                "code": "build_error",
                "message": "compile failed",
                "detail": {},
            },
        )

        index = session_index(session)

        self.assertEqual(index["status"], "build_error")
        self.assertIsNone(index["display"])
        self.assertEqual(index["frame_count"], 0)
        self.assertFalse(index["recorded"])
        self.assertEqual(index["next_reads"], [])

    def test_link_error_is_readable(self) -> None:
        session = make_session(
            self.root,
            status="link_error",
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
            error={
                "code": "link_error",
                "message": "undefined symbol",
                "detail": {},
            },
        )

        index = session_index(session)

        self.assertEqual(index["status"], "link_error")
        self.assertEqual(index["error"]["code"], "link_error")
        self.assertEqual(index["raw_files"].get("timeline"), None)

    def test_record_false_has_no_raw_recording_files(self) -> None:
        session = make_session(
            self.root,
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        index = session_index(session)

        self.assertFalse(index["recorded"])
        self.assertNotIn("timeline", index["raw_files"])
        self.assertNotIn("frame_diffs", index["raw_files"])
        self.assertEqual(index["timeline"]["first_frame_no"], None)
        self.assertEqual(index["timeline"]["end"], None)

    def test_next_reads_do_not_point_at_missing_files(self) -> None:
        session = make_session(
            self.root,
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        index = session_index(session)

        self.assertEqual(index["next_reads"], [])

    def test_index_keys_are_stable(self) -> None:
        session = make_query_session(self.root)

        self.assertEqual(tuple(session_index(session)), INDEX_FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
