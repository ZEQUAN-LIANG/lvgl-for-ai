"""Annotation writes: one transaction appends a note; invalid payloads are 4xx.

``annotations.write_note`` holds the lock, validates the document and payload,
crops every region, writes ``annotations.json`` through the Recording setter
(temp file + replace) and rolls back the crops it touched on failure, so a
rejected request cannot corrupt the previous file or leave a new crop behind.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from lvgl_ai import Recording
from lvgl_ai.web.annotations import (
    AnnotationConflict,
    AnnotationError,
    write_note,
)
from web_support import SESSION_ID, WebHarness, make_web_session

NOTE_FIELDS = {"id", "frame_no", "t_ms", "regions", "tags", "text"}


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

    # ---- valid writes ---------------------------------------------------

    def test_post_note_writes_schema_and_all_six_fields(self) -> None:
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
        self.assertEqual(saved["schema"], "lvgl-ai-annotations-v1")
        self.assertEqual(saved["notes"], [note])
        self.assertEqual(
            Recording.open(self.session).annotations["notes"], [note]
        )

        region = note["regions"][0]
        image = region["image"]
        self.assertRegex(image, r"^regions/[A-Za-z0-9][A-Za-z0-9._-]*\.png$")
        self.assertTrue((self.session / image).is_file())
        filename = image.rsplit("/", 1)[-1]
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

    def test_get_annotations_returns_an_empty_document_when_missing(self) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/annotations"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["annotations"],
            {"schema": "lvgl-ai-annotations-v1", "notes": []},
        )

    def test_document_shaped_payload_is_not_an_append_path(self) -> None:
        # The web API only appends one dragged-box note; a whole document is
        # not a write path and is rejected as an invalid note payload.
        notes = [valid_note(id="a"), valid_note(id="b", frame_no=3, text="b")]
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload={"schema": "lvgl-ai-annotations-v1", "notes": notes},
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
        self.assertEqual(Recording.open(self.session).annotations["notes"], saved["notes"])

    # ---- rejected payloads ---------------------------------------------

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
            valid_note(regions=[{
                "x": 0, "y": 0, "w": 1, "h": 1,
                "image": "regions/user-supplied.png",
            }]),
            valid_note(regions=[{"x": 10, "y": 20, "w": 30, "h": 40}]),
            valid_note(tags="layout"),
            valid_note(tags=[1]),
            valid_note(text=3),
            valid_note(id=""),
            valid_note(id=7),
            valid_note(unknown_field="x"),
            {**valid_note(), "schema": "lvgl-ai-annotations-v0"},
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
        self.assertFalse((self.session / "annotations.json.tmp").exists())

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
            raw=b"x" * (1024 * 1024 + 1),
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

    # ---- error mapping --------------------------------------------------

    def test_error_codes_match_the_http_contract(self) -> None:
        cases = [
            (valid_note(frame_no=0), 400, "invalid_annotation"),
            (
                valid_note(regions=[{"x": 10, "y": 20, "w": 30, "h": 40}]),
                400,
                "region_image_error",
            ),
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

    def test_write_failure_maps_to_500_and_removes_new_crops(self) -> None:
        with mock.patch.object(Path, "replace", side_effect=OSError("disk full")):
            status, _, payload = self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=valid_note(id="n1"),
            )
        self.assertEqual(status, 500, payload)
        self.assertEqual(payload["error"]["code"], "annotations_write_error")
        self.assertFalse(self.annotations_path.exists())
        self.assertEqual(list((self.session / "regions").glob("*.png")), [])

    def test_crop_write_failure_maps_to_internal_error(self) -> None:
        real_write_bytes = Path.write_bytes

        def flaky_write_bytes(path, data):
            if path.parent.name == "regions" and path.suffix == ".png":
                raise OSError("disk full")
            return real_write_bytes(path, data)

        with mock.patch.object(Path, "write_bytes", flaky_write_bytes):
            status, _, payload = self.harness.json(
                "POST",
                f"/api/sessions/{SESSION_ID}/annotations",
                payload=valid_note(id="n1"),
            )
        self.assertEqual(status, 500, payload)
        self.assertEqual(payload["error"]["code"], "internal_error")
        self.assertEqual(payload["error"]["message"], "disk full")
        self.assertFalse(self.annotations_path.exists())
        self.assertEqual(list((self.session / "regions").glob("*.png")), [])


class WriteNoteTransactionTest(unittest.TestCase):
    """``annotations.write_note`` is the whole annotation transaction."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)
        self.recording = Recording.open(self.session)
        self.annotations_path = self.session / "annotations.json"

    def _crop_names(self) -> list[str]:
        regions = self.session / "regions"
        if not regions.is_dir():
            return []
        return sorted(path.name for path in regions.iterdir())

    def _seed_existing_note(self) -> None:
        regions = self.session / "regions"
        regions.mkdir(exist_ok=True)
        (regions / "keep-0.png").write_bytes(b"\x89PNG\r\n\x1a\nseed")
        self.annotations_path.write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-annotations-v1",
                    "notes": [
                        {
                            "id": "keep",
                            "frame_no": 1,
                            "t_ms": 0,
                            "regions": [
                                {
                                    "x": 0,
                                    "y": 0,
                                    "w": 1,
                                    "h": 1,
                                    "image": "regions/keep-0.png",
                                }
                            ],
                            "tags": [],
                            "text": "keep",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    # ---- success --------------------------------------------------------

    def test_success_returns_document_and_note_and_writes_crops(self) -> None:
        document, saved = write_note(self.recording, valid_note(id="n1"))

        self.assertEqual(document["schema"], "lvgl-ai-annotations-v1")
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

    # ---- rejected writes ------------------------------------------------

    def test_conflict_keeps_the_document_and_writes_no_crops(self) -> None:
        write_note(self.recording, valid_note(id="dup"))
        before = self.annotations_path.read_bytes()
        crops_before = self._crop_names()

        with self.assertRaises(AnnotationConflict) as caught:
            write_note(self.recording, valid_note(id="dup", text="again"))

        self.assertEqual(caught.exception.code, "duplicate_annotation_id")
        self.assertEqual(str(caught.exception), "duplicate note id: dup")
        self.assertEqual(self.annotations_path.read_bytes(), before)
        self.assertEqual(self._crop_names(), crops_before)

    def test_invalid_payloads_raise_invalid_annotation_and_write_nothing(
        self,
    ) -> None:
        payloads = [
            {},
            valid_note(frame_no=0),
            valid_note(frame_no="2"),
            valid_note(regions="box"),
            valid_note(regions=[{"x": 0, "y": 0, "w": 1, "h": 1, "image": "x"}]),
            valid_note(tags=[1]),
            valid_note(unknown_field="x"),
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(AnnotationError) as caught:
                    write_note(self.recording, payload)
                self.assertEqual(caught.exception.code, "invalid_annotation")
                self.assertFalse(self.annotations_path.exists())
                self.assertEqual(self._crop_names(), [])

    def test_bad_region_raises_region_image_error_before_any_crop(self) -> None:
        with self.assertRaises(AnnotationError) as caught:
            write_note(
                self.recording,
                valid_note(
                    id="far",
                    regions=[{"x": 10, "y": 20, "w": 30, "h": 40}],
                ),
            )
        self.assertEqual(caught.exception.code, "region_image_error")
        self.assertFalse(self.annotations_path.exists())
        self.assertFalse((self.session / "regions").exists())

    def test_crop_write_failure_removes_partial_crops(self) -> None:
        payload = valid_note(
            id="two",
            regions=[
                {"x": 0, "y": 0, "w": 1, "h": 1},
                {"x": 1, "y": 1, "w": 1, "h": 1},
            ],
        )
        real_write_bytes = Path.write_bytes
        crop_writes = {"count": 0}

        def flaky_write_bytes(path, data):
            if path.parent.name == "regions" and path.suffix == ".png":
                crop_writes["count"] += 1
                if crop_writes["count"] == 2:
                    real_write_bytes(path, b"partial")
                    raise OSError("disk full")
            return real_write_bytes(path, data)

        with mock.patch.object(Path, "write_bytes", flaky_write_bytes):
            with self.assertRaises(AnnotationError) as caught:
                write_note(self.recording, payload)

        self.assertEqual(caught.exception.code, "internal_error")
        self.assertEqual(str(caught.exception), "disk full")
        self.assertEqual(crop_writes["count"], 2)
        self.assertFalse(self.annotations_path.exists())
        self.assertEqual(self._crop_names(), [])

    def test_document_write_failure_restores_an_overwritten_crop(self) -> None:
        regions = self.session / "regions"
        regions.mkdir()
        stale = regions / "new-0.png"
        stale.write_bytes(b"stale crop")
        real_replace = Path.replace

        def failing_replace(path, target):
            if path.name == "annotations.json.tmp":
                raise OSError("disk full")
            return real_replace(path, target)

        with mock.patch.object(Path, "replace", failing_replace):
            with self.assertRaises(AnnotationError):
                write_note(self.recording, valid_note(id="new"))

        self.assertEqual(stale.read_bytes(), b"stale crop")
        self.assertFalse(self.annotations_path.exists())

    def test_document_write_failure_removes_only_new_crops(self) -> None:
        self._seed_existing_note()
        before = self.annotations_path.read_bytes()
        real_replace = Path.replace

        def failing_replace(path, target):
            if path.name == "annotations.json.tmp":
                raise OSError("disk full")
            return real_replace(path, target)

        with mock.patch.object(Path, "replace", failing_replace):
            with self.assertRaises(AnnotationError) as caught:
                write_note(self.recording, valid_note(id="new"))

        self.assertEqual(caught.exception.code, "annotations_write_error")
        self.assertEqual(self.annotations_path.read_bytes(), before)
        self.assertEqual(self._crop_names(), ["keep-0.png"])

    # ---- serialization --------------------------------------------------

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
