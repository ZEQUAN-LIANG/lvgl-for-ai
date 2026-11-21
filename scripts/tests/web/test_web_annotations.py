from __future__ import annotations

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from control import Recording
from web.annotations import (
    AnnotationConflict,
    AnnotationError,
    delete_note,
    write_note,
)
from scripts.tests.web_support import SESSION_ID, WebHarness, make_web_session

NOTE_FIELDS = {
    "id",
    "frame_no",
    "t_ms",
    "regions",
    "tags",
    "text",
    "author",
    "source",
    "feedback_anchor",
}


def valid_note(**overrides):
    note = {
        "frame_no": 2,
        "t_ms": 16,
        "regions": [{"x": 0, "y": 0, "w": 2, "h": 2}],
        "tags": ["layout"],
        "text": "button is too low",
    }
    note.update(overrides)
    return note


class AnnotationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)
        self.annotations_path = self.session / "annotations.json"

    def test_post_note_writes_the_documented_fields(self) -> None:
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(),
        )
        self.assertEqual(status, 201, payload)
        note = payload["note"]
        self.assertEqual(set(note), NOTE_FIELDS)
        self.assertIsInstance(note["id"], str)
        self.assertTrue(note["id"])

        saved = json.loads(self.annotations_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema"], "lvgl-verify-loop-annotations-v1")
        self.assertEqual(saved["notes"], [note])
        self.assertEqual(
            Recording.open(self.session).annotations["notes"], [note]
        )

        region = note["regions"][0]
        self.assertRegex(
            region["image"], r"^regions/[A-Za-z0-9][A-Za-z0-9._-]*\.png$"
        )
        self.assertTrue((self.session / region["image"]).is_file())
        filename = region["image"].rsplit("/", 1)[-1]
        status, headers, body = self.harness.request(
            "GET", f"/regions/{SESSION_ID}/{filename}"
        )
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"].lower())
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_post_note_honours_an_explicit_id_and_appends(self) -> None:
        first = valid_note(id="n1")
        second = valid_note(id="n2", text="second", tags=["color"])
        for note in (first, second):
            status, _, payload = self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=note,
            )
            self.assertEqual(status, 201, payload)
            saved_note = payload["note"]
            self.assertEqual(saved_note["id"], note["id"])
            self.assertEqual(saved_note["frame_no"], note["frame_no"])
            self.assertEqual(saved_note["regions"][0]["x"], 0)
            self.assertEqual(
                saved_note["regions"][0]["image"],
                f"regions/{note['id']}-0.png",
            )

        saved = json.loads(self.annotations_path.read_text(encoding="utf-8"))
        self.assertEqual([note["id"] for note in saved["notes"]], ["n1", "n2"])

    def test_get_annotations_returns_an_empty_document_when_missing(
        self,
    ) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/annotations"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["annotations"],
            {"schema": "lvgl-verify-loop-annotations-v1", "notes": []},
        )

    def test_delete_note_removes_it_and_its_legacy_crop(self) -> None:
        regions = self.session / "regions"
        regions.mkdir()
        (regions / "old-0.png").write_bytes(b"\x89PNG\r\n\x1a\nold")
        self.annotations_path.write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-annotations-v1",
                    "notes": [
                        {
                            "id": "old",
                            "frame_no": 1,
                            "t_ms": 0,
                            "regions": [
                                {
                                    "x": 0,
                                    "y": 0,
                                    "w": 1,
                                    "h": 1,
                                    "image": "regions/old-0.png",
                                }
                            ],
                            "tags": [],
                            "text": "old",
                            "author": "human",
                            "source": "web",
                            "feedback_anchor": {"kind": "t_ms", "t_ms": 0},
                        },
                        {
                            **valid_note(id="keep"),
                            "author": "human",
                            "source": "web",
                            "feedback_anchor": {"kind": "t_ms", "t_ms": 16},
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        status, _, payload = self.harness.json(
            "DELETE", f"/api/sessions/{SESSION_ID}/annotations/old"
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["deleted"], "old")
        self.assertEqual(
            [note["id"] for note in payload["annotations"]["notes"]], ["keep"]
        )
        self.assertFalse((regions / "old-0.png").exists())
        saved = json.loads(self.annotations_path.read_text(encoding="utf-8"))
        self.assertEqual([note["id"] for note in saved["notes"]], ["keep"])

    def test_delete_unknown_note_is_404(self) -> None:
        status, _, payload = self.harness.json(
            "DELETE", f"/api/sessions/{SESSION_ID}/annotations/missing"
        )
        self.assertEqual(status, 404, payload)
        self.assertEqual(payload["error"]["code"], "unknown_annotation")
        self.assertFalse(self.annotations_path.exists())

    def test_document_shaped_payload_is_not_an_append_path(self) -> None:
        notes = [valid_note(id="a"), valid_note(id="b", frame_no=3, text="b")]
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload={
                "schema": "lvgl-verify-loop-annotations-v1",
                "notes": notes,
            },
        )
        self.assertGreaterEqual(status, 400, payload)
        self.assertLess(status, 500, payload)
        self.assertFalse(self.annotations_path.exists())

    def test_concurrent_posts_keep_every_note_and_a_valid_file(self) -> None:
        def post(index: int):
            return self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=valid_note(id=f"n{index}", text=f"note {index}"),
            )[0]

        with ThreadPoolExecutor(max_workers=5) as pool:
            statuses = list(pool.map(post, range(5)))
        self.assertEqual(statuses, [201] * 5)

        saved = json.loads(self.annotations_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(note["id"] for note in saved["notes"]),
            ["n0", "n1", "n2", "n3", "n4"],
        )
        self.assertEqual(
            Recording.open(self.session).annotations["notes"], saved["notes"]
        )

    def test_invalid_payloads_are_4xx_and_do_not_create_the_file(self) -> None:
        bad_notes = [
            {},
            valid_note(frame_no=0),
            valid_note(frame_no=-1),
            valid_note(frame_no="2"),
            valid_note(frame_no=True),
            valid_note(t_ms=-1),
            valid_note(t_ms=1.5),
            valid_note(t_ms="16"),
            valid_note(regions="box"),
            valid_note(regions=[{"x": 0, "y": 0, "w": 0, "h": 2}]),
            valid_note(regions=[{"x": -1, "y": 0, "w": 1, "h": 1}]),
            valid_note(regions=[{"x": 0, "y": 0, "w": 1}]),
            valid_note(regions=[{"x": 0, "y": 0, "w": 1, "h": 1, "extra": 1}]),
            valid_note(
                regions=[
                    {
                        "x": 0,
                        "y": 0,
                        "w": 1,
                        "h": 1,
                        "image": "regions/user-supplied.png",
                    }
                ]
            ),
            valid_note(tags="layout"),
            valid_note(tags=[1]),
            valid_note(text=3),
            valid_note(id=""),
            valid_note(id=7),
            valid_note(unknown_field="x"),
            {**valid_note(), "schema": "lvgl-verify-loop-annotations-v0"},
        ]
        for note in bad_notes:
            with self.subTest(note=note):
                status, _, payload = self.harness.json(
                    "POST",
                    f"/api/sessions/{SESSION_ID}/annotations",
                    payload=note,
                )
                self.assertGreaterEqual(status, 400, payload)
                self.assertLess(status, 500, payload)
                self.assertFalse(self.annotations_path.exists())
        self.assertEqual(list(self.session.glob("annotations.json*")), [])

    def test_malformed_json_is_4xx_and_leaves_the_file_alone(self) -> None:
        for raw in (b"{not json", b"[]", b"null", b"\xff\xfe"):
            with self.subTest(raw=raw):
                status, _, payload = self.harness.json(
                    "POST",
                    f"/api/sessions/{SESSION_ID}/annotations",
                    raw=raw,
                    headers={"Content-Type": "application/json"},
                )
                self.assertGreaterEqual(status, 400, payload)
                self.assertLess(status, 500, payload)
        self.assertFalse(self.annotations_path.exists())

    def test_rejected_payload_does_not_modify_an_existing_file(self) -> None:
        status, _, _ = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(id="keep"),
        )
        self.assertEqual(status, 201)
        before = self.annotations_path.read_bytes()
        status, _, _ = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(frame_no="broken"),
        )
        self.assertGreaterEqual(status, 400)
        self.assertEqual(self.annotations_path.read_bytes(), before)
        self.assertEqual(list(self.session.glob("annotations.json.*.tmp")), [])

    def test_duplicate_id_is_rejected_without_touching_the_file(self) -> None:
        self.assertEqual(
            self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=valid_note(id="dup"),
            )[0],
            201,
        )
        before = self.annotations_path.read_bytes()
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(id="dup", text="again"),
        )
        self.assertEqual(status, 409, payload)
        self.assertEqual(self.annotations_path.read_bytes(), before)

    def test_corrupt_existing_annotations_are_not_overwritten(self) -> None:
        broken = b"{broken\n"
        self.annotations_path.write_bytes(broken)
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(),
        )
        self.assertGreaterEqual(status, 400, payload)
        self.assertLess(status, 500, payload)
        self.assertEqual(self.annotations_path.read_bytes(), broken)

    def test_oversized_payload_is_rejected_before_writing(self) -> None:
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            raw=b"x" * (12 * 1024 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 413, payload)
        self.assertFalse(self.annotations_path.exists())

    def test_unknown_session_returns_404(self) -> None:
        status, _, payload = self.harness.json(
            "POST",
            "/api/sessions/does-not-exist/annotations",
            payload=valid_note(),
        )
        self.assertEqual(status, 404, payload)
        self.assertEqual(payload["error"]["code"], "unknown_session")

    def test_error_codes_match_the_http_contract(self) -> None:
        cases = [
            (valid_note(frame_no=0), 400, "invalid_annotation"),
        ]
        for note, expected_status, expected_code in cases:
            with self.subTest(code=expected_code):
                status, _, payload = self.harness.json(
                    "POST",
                    f"/api/sessions/{SESSION_ID}/annotations",
                    payload=note,
                )
                self.assertEqual(status, expected_status, payload)
                self.assertEqual(payload["error"]["code"], expected_code)
                self.assertEqual(
                    set(payload["error"]), {"code", "message", "detail"}
                )
                self.assertEqual(payload["error"]["detail"], {})
                self.assertFalse(self.annotations_path.exists())

        self.assertEqual(
            self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=valid_note(id="dup"),
            )[0],
            201,
        )
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(id="dup"),
        )
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "duplicate_annotation_id")

    def test_corrupt_document_maps_to_annotations_unreadable(self) -> None:
        self.annotations_path.write_bytes(b"{broken\n")
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=valid_note(),
        )
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "annotations_unreadable")

    def test_write_failure_maps_to_500_and_leaves_no_file(self) -> None:
        with mock.patch.object(
            Path, "replace", side_effect=OSError("disk full")
        ):
            status, _, payload = self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=valid_note(id="n1"),
            )
        self.assertEqual(status, 500, payload)
        self.assertEqual(payload["error"]["code"], "annotations_write_error")
        self.assertFalse(self.annotations_path.exists())


class WriteNoteTransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)
        self.recording = Recording.open(self.session)
        self.annotations_path = self.session / "annotations.json"

    def test_success_returns_document_and_note(self) -> None:
        document, saved = write_note(self.recording, valid_note(id="n1"))

        self.assertEqual(document["schema"], "lvgl-verify-loop-annotations-v1")
        self.assertEqual(document["notes"], [saved])
        self.assertEqual(set(saved), NOTE_FIELDS)
        self.assertEqual(saved["regions"][0]["image"], "regions/n1-0.png")
        self.assertTrue((self.session / "regions/n1-0.png").is_file())
        self.assertEqual(
            json.loads(self.annotations_path.read_text(encoding="utf-8")),
            document,
        )

    def test_note_without_regions_writes_no_crops(self) -> None:
        document, saved = write_note(
            self.recording, valid_note(id="plain", regions=[])
        )
        self.assertEqual(saved["regions"], [])
        self.assertEqual(document["notes"], [saved])
        self.assertFalse((self.session / "regions").exists())
        self.assertTrue(self.annotations_path.is_file())

    def test_conflict_keeps_the_document(self) -> None:
        write_note(self.recording, valid_note(id="dup"))
        before = self.annotations_path.read_bytes()

        with self.assertRaises(AnnotationConflict) as caught:
            write_note(self.recording, valid_note(id="dup", text="again"))

        self.assertEqual(caught.exception.code, "duplicate_annotation_id")
        self.assertEqual(str(caught.exception), "duplicate note id: dup")
        self.assertEqual(self.annotations_path.read_bytes(), before)

    def test_invalid_payloads_raise_invalid_annotation_and_write_nothing(
        self,
    ) -> None:
        payloads = [
            {},
            valid_note(frame_no=0),
            valid_note(frame_no="2"),
            valid_note(regions="box"),
            valid_note(
                regions=[{"x": 0, "y": 0, "w": 1, "h": 1, "image": "x"}]
            ),
            valid_note(tags=[1]),
            valid_note(unknown_field="x"),
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(AnnotationError) as caught:
                    write_note(self.recording, payload)
                self.assertEqual(caught.exception.code, "invalid_annotation")
                self.assertFalse(self.annotations_path.exists())
                self.assertFalse((self.session / "regions").exists())

    def test_document_write_failure_keeps_the_previous_document(self) -> None:
        write_note(self.recording, valid_note(id="keep"))
        before = self.annotations_path.read_bytes()
        real_replace = Path.replace

        def failing_replace(path, target):
            if path.name.startswith(
                "annotations.json."
            ) and path.name.endswith(".tmp"):
                raise OSError("disk full")
            return real_replace(path, target)

        with mock.patch.object(Path, "replace", failing_replace):
            with self.assertRaises(AnnotationError) as caught:
                write_note(self.recording, valid_note(id="new"))

        self.assertEqual(caught.exception.code, "annotations_write_error")
        self.assertEqual(self.annotations_path.read_bytes(), before)
        self.assertEqual(
            [path.name for path in (self.session / "regions").glob("*.png")],
            ["keep-0.png"],
        )

    def test_concurrent_writes_keep_every_note(self) -> None:
        def post(index: int) -> str:
            _document, saved = write_note(
                self.recording,
                valid_note(id=f"n{index}", text=f"note {index}"),
            )
            return saved["id"]

        with ThreadPoolExecutor(max_workers=5) as pool:
            ids = list(pool.map(post, range(5)))

        self.assertEqual(sorted(ids), ["n0", "n1", "n2", "n3", "n4"])
        saved = Recording.open(self.session).annotations
        self.assertEqual(
            sorted(note["id"] for note in saved["notes"]),
            ["n0", "n1", "n2", "n3", "n4"],
        )
        self.assertEqual(
            json.loads(self.annotations_path.read_text(encoding="utf-8")),
            saved,
        )


class AnnotationDocumentSeamTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)
        self.recording = Recording.open(self.session)

    def test_write_note_reads_and_writes_only_the_recording_seam(self) -> None:
        class SeamRecording:
            def __init__(self, recording: Recording) -> None:
                self._recording = recording

            @property
            def annotations(self):
                return self._recording.annotations

            @annotations.setter
            def annotations(self, value) -> None:
                self._recording.annotations = value

            @property
            def annotations_store(self):
                return self._recording.annotations_store

            @property
            def frames(self):
                return self._recording.frames

            def __getattr__(self, name: str):
                raise AssertionError(f"unexpected recording attribute: {name}")

        document, saved = write_note(
            SeamRecording(self.recording), valid_note(id="seam")
        )

        self.assertEqual([note["id"] for note in document["notes"]], ["seam"])
        self.assertEqual(saved["regions"][0]["image"], "regions/seam-0.png")
        self.assertTrue((self.session / "regions/seam-0.png").is_file())

    def test_write_note_prunes_unreferenced_region_images(self) -> None:
        regions = self.session / "regions"
        regions.mkdir()
        stale = regions / "stale-0.png"
        stale.write_bytes(b"stale")

        write_note(self.recording, valid_note(id="n1"))

        self.assertFalse(stale.exists())
        self.assertTrue((regions / "n1-0.png").is_file())

    def test_delete_note_removes_only_the_deleted_notes_images(self) -> None:
        write_note(self.recording, valid_note(id="n1"))
        write_note(self.recording, valid_note(id="n2"))

        delete_note(self.recording, "n1")

        self.assertFalse((self.session / "regions/n1-0.png").exists())
        self.assertTrue((self.session / "regions/n2-0.png").is_file())


def range_note(**overrides):
    note = {
        "frame_no": 2,
        "t_ms": 16,
        "frame_start": 1,
        "frame_end": 3,
        "anchors": [
            {
                "frame_no": 2,
                "t_ms": 16,
                "regions": [{"x": 0, "y": 0, "w": 2, "h": 2}],
            },
            {
                "frame_no": 3,
                "t_ms": 32,
                "regions": [{"x": 1, "y": 1, "w": 2, "h": 2}],
            },
        ],
        "tags": ["motion"],
        "text": "动画应该匀速，不要跳",
    }
    note.update(overrides)
    return note


class RangeAnnotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)
        self.annotations_path = self.session / "annotations.json"

    def test_range_note_keeps_anchors_and_derives_legacy_regions(self) -> None:
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=range_note(),
        )
        self.assertEqual(status, 201, payload)
        note = payload["note"]
        self.assertEqual(note["frame_start"], 1)
        self.assertEqual(note["frame_end"], 3)
        self.assertEqual(len(note["anchors"]), 2)
        self.assertEqual(note["regions"], note["anchors"][0]["regions"])
        for anchor in note["anchors"]:
            for region in anchor["regions"]:
                self.assertRegex(
                    region["image"],
                    r"^regions/[A-Za-z0-9][A-Za-z0-9._-]*\.png$",
                )
                self.assertTrue((self.session / region["image"]).is_file())
        self.assertEqual(
            Recording.open(self.session).annotations["notes"], [note]
        )

    def test_anchor_annotated_frame_is_saved_and_served(self) -> None:
        frame = sorted((self.session / "frames").glob("*.png"))[0]
        data_url = "data:image/png;base64," + base64.b64encode(
            frame.read_bytes()
        ).decode("ascii")
        note = range_note(
            anchors=[
                {
                    "frame_no": 2,
                    "t_ms": 16,
                    "regions": [{"x": 0, "y": 0, "w": 2, "h": 2}],
                    "annotated": data_url,
                }
            ]
        )
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=note,
        )
        self.assertEqual(status, 201, payload)
        saved = payload["note"]["anchors"][0]
        self.assertRegex(
            saved["annotated"],
            r"^regions/[A-Za-z0-9][A-Za-z0-9._-]*-annotated\.png$",
        )
        self.assertTrue((self.session / saved["annotated"]).is_file())
        status, headers, _ = self.harness.request(
            "GET",
            f"/regions/{SESSION_ID}/" + saved["annotated"].rsplit("/", 1)[-1],
        )
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"].lower())

    def test_invalid_annotated_frame_is_rejected(self) -> None:
        note = range_note(
            anchors=[
                {
                    "frame_no": 2,
                    "t_ms": 16,
                    "regions": [],
                    "annotated": "data:image/png;base64,bm90IGEgcG5n",
                }
            ]
        )
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=note,
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_annotation")
        self.assertFalse(self.annotations_path.exists())

    def test_range_is_derived_from_anchors_when_missing(self) -> None:
        note = range_note()
        del note["frame_start"]
        del note["frame_end"]
        note["anchors"][0]["frame_no"] = 2
        note["frame_no"] = 2
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=note,
        )
        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["note"]["frame_start"], 2)
        self.assertEqual(payload["note"]["frame_end"], 3)

    def test_range_without_anchors_is_a_valid_text_note(self) -> None:
        note = range_note(anchors=[], frame_no=1, t_ms=0)
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload=note,
        )
        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["note"]["anchors"], [])
        self.assertEqual(payload["note"]["regions"], [])

    def test_bad_ranges_and_anchors_are_rejected(self) -> None:
        missing_end = range_note(frame_start=2)
        del missing_end["frame_end"]
        cases = [
            range_note(frame_start=4, frame_end=3),
            missing_end,
            range_note(anchors=[{"frame_no": 9, "t_ms": 0, "regions": []}]),
            range_note(frame_no=3),
            range_note(
                anchors=[
                    {
                        "frame_no": 2,
                        "t_ms": 16,
                        "regions": [],
                        "extra": 1,
                    }
                ]
            ),
            range_note(
                anchors=[
                    {
                        "frame_no": 2,
                        "t_ms": 16,
                        "regions": [
                            {
                                "x": 0,
                                "y": 0,
                                "w": 1,
                                "h": 1,
                                "image": "regions/x.png",
                            }
                        ],
                    }
                ]
            ),
        ]
        for note in cases:
            with self.subTest(note=str(note)[:100]):
                status, _, payload = self.harness.json(
                    "POST",
                    f"/api/sessions/{SESSION_ID}/annotations",
                    payload=note,
                )
                self.assertEqual(status, 400, payload)
                self.assertEqual(
                    payload["error"]["code"], "invalid_annotation"
                )
                self.assertFalse(self.annotations_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
