"""Characterization: every reader agrees on one session's contract.

A complete session from ``session_fixtures`` is read through ``Recording``,
``summarize_session``, retention and the web JSON API. The assertions are
literal values from the fixture, so later refactors cannot silently change
the display, file names or status one entry point sees.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lvgl_ai import Recording, summarize_session
from lvgl_ai.control import session_schema
from lvgl_ai.control.retention import prune_sessions
from session_fixtures import (
    FRAME_1,
    FRAME_2,
    SESSION_NAME,
    SNAPSHOT,
    make_summary_session,
)
from web_support import WebHarness

DISPLAY = {"width": 390, "height": 450}
OLD_SESSION = "20260101-000000-aaaa"


class SessionContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_summary_session(
            self.root,
            display=DISPLAY,
            with_annotations=True,
        )
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)

    def test_recording_summary_and_web_share_display_status_and_files(self) -> None:
        recording = Recording.open(self.session)
        manifest = recording.manifest
        summary = summarize_session(self.session)

        status, _, listing = self.harness.json("GET", "/api/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(len(listing["sessions"]), 1)
        entry = listing["sessions"][0]

        status, _, detail = self.harness.json(
            "GET", f"/api/sessions/{SESSION_NAME}"
        )
        self.assertEqual(status, 200)

        # Manifest literal fields.
        self.assertEqual(manifest["schema"], "lvgl-ai-session-v1")
        self.assertEqual(manifest["id"], SESSION_NAME)
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["display"], DISPLAY)
        self.assertEqual(manifest["frame_count"], 2)

        # Every reader sees the same display and status.
        self.assertEqual(summary["display"], DISPLAY)
        self.assertEqual(detail["manifest"]["display"], DISPLAY)
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(detail["manifest"]["status"], "ok")

        # Every reader sees the same frame and snapshot names.
        expected_frames = [FRAME_1, FRAME_2]
        self.assertEqual(
            [path.name for path in recording.frames],
            ["000001.png", "000002.png"],
        )
        self.assertEqual(
            [Path(path).name for path in summary["frames"]],
            ["000001.png", "000002.png"],
        )
        self.assertEqual(
            [frame["file"] for frame in detail["frames"]], expected_frames
        )
        self.assertEqual(detail["frames_available"], 2)
        self.assertEqual(detail["frame_count"], 2)
        self.assertEqual(
            [Path(snapshot["path"]).name for snapshot in summary["snapshots"]],
            [Path(SNAPSHOT).name],
        )
        self.assertEqual(
            [snapshot["file"] for snapshot in detail["snapshots"]], [SNAPSHOT]
        )

    def test_web_reads_the_same_annotation_and_whiteboard_documents(self) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_NAME}/annotations"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["annotations"]["schema"], "lvgl-ai-annotations-v1"
        )
        self.assertEqual(
            [note["id"] for note in payload["annotations"]["notes"]], ["n1"]
        )
        self.assertEqual(
            payload["annotations"]["notes"][0]["text"], "button is too low"
        )

        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_NAME}/whiteboards"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["whiteboards"],
            {"schema": "lvgl-ai-whiteboards-v1", "whiteboards": []},
        )

    def test_retention_sees_the_same_session_name_and_status(self) -> None:
        old = make_summary_session(
            self.root,
            name=OLD_SESSION,
            display=DISPLAY,
            with_annotations=False,
            with_snapshot=False,
        )

        removed = prune_sessions(self.root, limit=1)

        self.assertEqual(removed, [old])
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            [SESSION_NAME],
        )


class FileLayoutConstantsTest(unittest.TestCase):
    """B3: one module owns the session file layout."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_summary_session(
            self.root,
            display=DISPLAY,
            with_annotations=True,
        )

    def test_recording_and_summary_follow_the_shared_names(self) -> None:
        frames = self.session / "frames"
        annotations = self.session / "annotations.json"
        with mock.patch.object(
            session_schema, "FRAMES_DIR", "frames-b3"
        ), mock.patch.object(
            session_schema, "ANNOTATIONS_FILE", "notes-b3.json"
        ):
            frames.rename(self.session / "frames-b3")
            annotations.rename(self.session / "notes-b3.json")

            recording = Recording.open(self.session)
            self.assertEqual(
                [path.parent.name for path in recording.frames],
                ["frames-b3", "frames-b3"],
            )
            self.assertEqual(
                [path.name for path in recording.frames],
                ["000001.png", "000002.png"],
            )
            self.assertEqual(
                [note["id"] for note in recording.annotations["notes"]],
                ["n1"],
            )

            summary = summarize_session(self.session)
            self.assertEqual(
                [Path(path).parent.name for path in summary["frames"]],
                ["frames-b3", "frames-b3"],
            )
            self.assertEqual(summary["annotations"]["count"], 1)
            self.assertEqual(
                summary["annotations"]["notes"][0]["id"], "n1"
            )

    def test_retention_follows_the_shared_manifest_name(self) -> None:
        old = make_summary_session(
            self.root,
            name=OLD_SESSION,
            display=DISPLAY,
            with_annotations=False,
            with_snapshot=False,
        )
        with mock.patch.object(
            session_schema, "MANIFEST_FILE", "session-b3.json"
        ):
            for path in (old, self.session):
                (path / "manifest.json").rename(path / "session-b3.json")

            removed = prune_sessions(self.root, limit=1)

        self.assertEqual(removed, [old])
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            [SESSION_NAME],
        )

    def test_web_reads_follow_the_shared_names(self) -> None:
        whiteboards = {
            "schema": "lvgl-ai-whiteboards-v1",
            "whiteboards": [
                {
                    "id": "wb1",
                    "scope": {"kind": "global"},
                    "text": "keep the dark theme",
                    "labels": [],
                    "objects": {},
                    "confirmed": True,
                }
            ],
        }
        with mock.patch.object(
            session_schema, "FRAMES_DIR", "frames-b3"
        ), mock.patch.object(
            session_schema, "ANNOTATIONS_FILE", "notes-b3.json"
        ), mock.patch.object(
            session_schema, "WHITEBOARDS_FILE", "boards-b3.json"
        ):
            (self.session / "frames").rename(self.session / "frames-b3")
            (self.session / "annotations.json").rename(
                self.session / "notes-b3.json"
            )
            (self.session / "boards-b3.json").write_text(
                json.dumps(whiteboards), encoding="utf-8"
            )

            harness = WebHarness(self.root)
            self.addCleanup(harness.close)

            status, _, detail = harness.json(
                "GET", f"/api/sessions/{SESSION_NAME}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(detail["frames_available"], 2)

            status, _, payload = harness.json(
                "GET", f"/api/sessions/{SESSION_NAME}/annotations"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                [note["id"] for note in payload["annotations"]["notes"]],
                ["n1"],
            )

            status, _, payload = harness.json(
                "GET", f"/api/sessions/{SESSION_NAME}/whiteboards"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                [item["id"] for item in payload["whiteboards"]["whiteboards"]],
                ["wb1"],
            )


class DisplayValidatorTest(unittest.TestCase):
    """B2: ``session_schema.validate_display`` is the one display rule."""

    def test_accepts_positive_dimensions_and_ignores_extra_fields(self) -> None:
        self.assertEqual(
            session_schema.validate_display(
                {"width": 390, "height": 450, "format": "XRGB8888"}
            ),
            {"width": 390, "height": 450},
        )

    def test_rejects_non_positive_or_non_integer_sizes(self) -> None:
        cases = [
            {"width": 0, "height": 450},
            {"width": -1, "height": 450},
            {"width": 390, "height": 0},
            {"width": 390, "height": -1},
            {"width": True, "height": 450},
            {"width": 390, "height": 1.5},
            {"width": 390},
            {"height": 450},
            "390x450",
        ]
        for display in cases:
            with self.subTest(display=display):
                with self.assertRaises(ValueError):
                    session_schema.validate_display(display)

    def test_none_is_only_valid_when_the_caller_allows_it(self) -> None:
        self.assertIsNone(
            session_schema.validate_display(None, allow_none=True)
        )
        with self.assertRaises(ValueError):
            session_schema.validate_display(None)

    def test_problem_text_names_the_first_bad_dimension(self) -> None:
        self.assertEqual(
            session_schema.display_problem({"width": 0, "height": 450}),
            "display.width must be >= 1; got 0",
        )
        self.assertEqual(
            session_schema.display_problem({"width": 640, "height": -1}),
            "display.height must be >= 1; got -1",
        )
        self.assertIsNone(
            session_schema.display_problem({"width": 390, "height": 450})
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
