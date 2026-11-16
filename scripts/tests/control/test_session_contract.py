from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control import Recording, session_index
from control import session_schema
from control.retention import prune_sessions
from scripts.tests.session_fixtures import (
    FRAME_1,
    FRAME_2,
    SESSION_NAME,
    SNAPSHOT,
    make_summary_session,
)
from scripts.tests.web_support import WebHarness

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

    def test_recording_summary_and_web_share_display_status_and_files(
        self,
    ) -> None:
        recording = Recording.open(self.session)
        manifest = recording.manifest
        index = session_index(self.session)

        status, _, listing = self.harness.json("GET", "/api/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(len(listing["sessions"]), 1)
        entry = listing["sessions"][0]

        status, _, detail = self.harness.json(
            "GET", f"/api/sessions/{SESSION_NAME}"
        )
        self.assertEqual(status, 200)

        self.assertEqual(manifest["schema"], "lvgl-verify-loop-session-v1")
        self.assertEqual(manifest["id"], SESSION_NAME)
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["display"], DISPLAY)
        self.assertEqual(manifest["frame_count"], 2)

        self.assertEqual(index["display"], DISPLAY)
        self.assertEqual(detail["manifest"]["display"], DISPLAY)
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(index["status"], "ok")
        self.assertEqual(detail["manifest"]["status"], "ok")

        expected_frames = [FRAME_1, FRAME_2]
        self.assertEqual(
            [path.name for path in recording.frames],
            ["000001.png", "000002.png"],
        )
        self.assertEqual(
            Path(index["frames"]["last"]).name,
            "000002.png",
        )
        self.assertEqual(index["frames"]["count"], 2)
        self.assertEqual(
            [frame["file"] for frame in detail["frames"]], expected_frames
        )
        self.assertEqual(detail["frames_available"], 2)
        self.assertEqual(detail["frame_count"], 2)
        self.assertEqual(
            Path(index["snapshots"]["items"][0]["path"]).name,
            Path(SNAPSHOT).name,
        )
        self.assertEqual(
            [snapshot["file"] for snapshot in detail["snapshots"]], [SNAPSHOT]
        )

    def test_web_reads_the_same_annotation_and_whiteboard_documents(
        self,
    ) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_NAME}/annotations"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["annotations"]["schema"], "lvgl-verify-loop-annotations-v1"
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
            {"schema": "lvgl-verify-loop-whiteboards-v1", "whiteboards": []},
        )

    def test_retention_sees_the_same_session_name_and_status(self) -> None:
        make_summary_session(
            self.root,
            name=OLD_SESSION,
            display=DISPLAY,
            with_annotations=False,
            with_snapshot=False,
        )

        removed = prune_sessions(self.root, limit=1)

        self.assertEqual(removed, [])
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            sorted([SESSION_NAME, OLD_SESSION]),
        )


class FileLayoutConstantsTest(unittest.TestCase):
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
        with (
            mock.patch.object(session_schema, "FRAMES_DIR", "frames-b3"),
            mock.patch.object(
                session_schema, "ANNOTATIONS_FILE", "notes-b3.json"
            ),
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

            index = session_index(self.session)
            self.assertEqual(
                Path(index["frames"]["last"]).parent.name, "frames-b3"
            )
            self.assertEqual(index["annotations"]["count"], 1)
            self.assertEqual(index["annotations"]["notes"][0]["id"], "n1")

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

        self.assertEqual(removed, [])
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            sorted([SESSION_NAME, OLD_SESSION]),
        )

    def test_web_reads_follow_the_shared_names(self) -> None:
        whiteboards = {
            "schema": "lvgl-verify-loop-whiteboards-v1",
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
        with (
            mock.patch.object(session_schema, "FRAMES_DIR", "frames-b3"),
            mock.patch.object(
                session_schema, "ANNOTATIONS_FILE", "notes-b3.json"
            ),
            mock.patch.object(
                session_schema, "WHITEBOARDS_FILE", "boards-b3.json"
            ),
            mock.patch.object(
                session_schema, "MANIFEST_FILE", "session-b3.json"
            ),
        ):
            (self.session / "frames").rename(self.session / "frames-b3")
            (self.session / "annotations.json").rename(
                self.session / "notes-b3.json"
            )
            (self.session / "manifest.json").rename(
                self.session / "session-b3.json"
            )
            (self.session / "boards-b3.json").write_text(
                json.dumps(whiteboards), encoding="utf-8"
            )

            harness = WebHarness(self.root)
            self.addCleanup(harness.close)

            status, _, listing = harness.json("GET", "/api/sessions")
            self.assertEqual(status, 200)
            self.assertEqual(
                [entry["id"] for entry in listing["sessions"]],
                [SESSION_NAME],
            )

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


class SessionIdContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_generator_matches_the_shared_validator(self) -> None:
        for _ in range(5):
            session_id = session_schema.new_session_id()
            self.assertRegex(session_id, r"^\d{8}-\d{6}-[0-9a-f]{4}$")
            self.assertTrue(session_schema.is_session_id(session_id))

    def test_validator_rejects_the_old_web_loose_format(self) -> None:
        for value in (
            "loose-session",
            "20260102-030405-ABCD",
            "20260102-030405-abcd-extra",
            "20260102-030405-abcd/..",
            "",
        ):
            with self.subTest(value=value):
                self.assertFalse(session_schema.is_session_id(value))

    def test_web_lists_and_serves_only_canonical_session_directories(
        self,
    ) -> None:
        loose = make_summary_session(
            self.root,
            name="loose-session",
            display=DISPLAY,
            with_annotations=False,
            with_snapshot=False,
        )
        self.assertTrue((loose / "manifest.json").is_file())
        make_summary_session(
            self.root,
            name=SESSION_NAME,
            display=DISPLAY,
            with_annotations=False,
            with_snapshot=False,
        )
        harness = WebHarness(self.root)
        self.addCleanup(harness.close)

        status, _, payload = harness.json("GET", "/api/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(
            [entry["id"] for entry in payload["sessions"]], [SESSION_NAME]
        )

        status, _, payload = harness.json("GET", "/api/sessions/loose-session")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "unknown_session")


class RecordedContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_summary_session(
            self.root,
            display=DISPLAY,
            with_annotations=False,
        )

    def _manifest(self) -> dict:
        return json.loads(
            (self.session / "manifest.json").read_text(encoding="utf-8")
        )

    def test_record_false_manifest_ignores_a_stray_timeline_file(self) -> None:
        manifest = self._manifest()
        self.assertEqual(manifest["frame_count"], 2)
        manifest["frame_count"] = 0
        manifest["artifacts"] = {
            "manifest": "manifest.json",
            "engine_log": "engine.log",
        }
        (self.session / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        self.assertTrue((self.session / "timeline.ndjson").is_file())
        self.assertTrue((self.session / "frame_diffs.ndjson").is_file())

        self.assertFalse(
            session_schema.session_is_recorded(manifest, self.session)
        )
        self.assertFalse(session_index(self.session)["recorded"])

    def test_recorded_needs_manifest_intent_and_both_evidence_files(
        self,
    ) -> None:
        manifest = self._manifest()
        self.assertTrue(
            session_schema.session_is_recorded(manifest, self.session)
        )

        (self.session / "frame_diffs.ndjson").unlink()
        self.assertFalse(
            session_schema.session_is_recorded(manifest, self.session)
        )

        (self.session / "timeline.ndjson").unlink()
        self.assertFalse(
            session_schema.session_is_recorded(manifest, self.session)
        )


class ManifestSourceFieldsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_summary_session(self.root, display=DISPLAY)
        self.path = self.session / "manifest.json"

    def _write(self, **changes) -> None:
        manifest = json.loads(self.path.read_text(encoding="utf-8"))
        manifest.update(changes)
        self.path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_missing_scenario_or_source_digest_is_rejected(self) -> None:
        for field in ("scenario", "source_digest"):
            with self.subTest(field=field):
                self.setUp()
                manifest = json.loads(self.path.read_text(encoding="utf-8"))
                del manifest[field]
                self.path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    Recording.open(self.session)
                self.assertIn(field, str(caught.exception))

    def test_null_and_object_values_are_accepted(self) -> None:
        self._write(
            scenario={"path": "user/scenarios/x.json", "sha256": "a" * 64},
            source_digest={"dir": "apps", "sha256": "b" * 64, "files": 2},
        )

        self.assertEqual(
            Recording.open(self.session).manifest["schema"],
            "lvgl-verify-loop-session-v1",
        )

    def test_incomplete_objects_are_rejected(self) -> None:
        cases = [
            {"scenario": {"path": "x.json"}},
            {"source_digest": {"dir": "apps", "files": 1}},
            {"scenario": "user/scenarios/x.json"},
            {"source_digest": []},
        ]
        for change in cases:
            with self.subTest(change=change):
                self.setUp()
                self._write(**change)
                with self.assertRaises(ValueError):
                    Recording.open(self.session)


class DisplayValidatorTest(unittest.TestCase):
    def test_accepts_positive_dimensions_and_ignores_extra_fields(
        self,
    ) -> None:
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
