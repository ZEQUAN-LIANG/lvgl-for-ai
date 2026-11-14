"""Whiteboard writes: scope, confirmation, PNG storage and one upsert path."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lvgl_ai.web.whiteboards import (
    WhiteboardError,
    read_whiteboards,
    save_whiteboard,
)
from lvgl_ai import Recording
from web_support import SESSION_ID, WebHarness, make_web_session

GLOBAL = {"kind": "global"}
FRAME = {"kind": "frame", "frame_no": 2}
RANGE = {"kind": "range", "frame_start": 1, "frame_end": 3}


class WhiteboardApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)
        self.document_path = self.session / "whiteboards.json"
        frame = sorted((self.session / "frames").glob("*.png"))[0]
        self.png = frame.read_bytes()
        self.data_url = "data:image/png;base64," + base64.b64encode(
            self.png
        ).decode("ascii")

    def payload(self, **overrides):
        payload = {
            "scope": FRAME,
            "text": "进度条应该匀速",
            "labels": ["起点", "终点"],
            "objects": {"version": "5.3.0", "objects": []},
            "image": self.data_url,
            "confirmed": True,
        }
        payload.update(overrides)
        return payload

    def post(self, payload=None):
        return self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/whiteboards",
            payload=payload if payload is not None else self.payload(),
        )

    def test_post_writes_document_and_content_addressed_png(self) -> None:
        status, _, response = self.post()
        self.assertEqual(status, 201, response)
        item = response["whiteboard"]
        self.assertEqual(item["scope"], FRAME)
        self.assertTrue(item["confirmed"])
        self.assertRegex(
            item["image"],
            r"^whiteboards/[A-Za-z0-9][A-Za-z0-9._-]*\.png$",
        )
        self.assertTrue((self.session / item["image"]).is_file())
        saved = json.loads(self.document_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema"], "lvgl-ai-whiteboards-v1")
        self.assertEqual(saved["whiteboards"], [item])

        filename = item["image"].rsplit("/", 1)[-1]
        status, headers, body = self.harness.request(
            "GET", f"/whiteboards/{SESSION_ID}/{filename}"
        )
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"].lower())
        self.assertEqual(body, self.png)

    def test_get_returns_an_empty_document_when_missing(self) -> None:
        status, _, response = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/whiteboards"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            response["whiteboards"],
            {"schema": "lvgl-ai-whiteboards-v1", "whiteboards": []},
        )

    def test_range_and_global_scopes_are_kept(self) -> None:
        for scope in (RANGE, GLOBAL):
            with self.subTest(scope=scope):
                status, _, response = self.post(self.payload(scope=scope))
                self.assertEqual(status, 201, response)
                self.assertEqual(response["whiteboard"]["scope"], scope)

    def test_same_id_upserts_and_updates_confirmation(self) -> None:
        first = self.post(self.payload(id="wb-fixed"))[2]["whiteboard"]
        second = self.post(
            self.payload(id="wb-fixed", confirmed=False, text="改过的期望")
        )[2]["whiteboard"]
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(second["confirmed"])
        saved = json.loads(self.document_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["whiteboards"]), 1)
        self.assertEqual(saved["whiteboards"][0]["text"], "改过的期望")

    def test_text_or_labels_are_required(self) -> None:
        status, _, response = self.post(self.payload(text="", labels=[]))
        self.assertEqual(status, 400, response)
        self.assertEqual(response["error"]["code"], "invalid_whiteboard")
        self.assertFalse(self.document_path.exists())

    def test_invalid_payloads_are_rejected_without_files(self) -> None:
        cases = [
            self.payload(scope={"kind": "frame"}),
            self.payload(scope={"kind": "range", "frame_start": 4, "frame_end": 3}),
            self.payload(scope={"kind": "global", "frame_no": 1}),
            self.payload(scope={"kind": "session"}),
            self.payload(labels=["x", 1]),
            self.payload(objects=[]),
            self.payload(confirmed="yes"),
            self.payload(unknown_field=1),
            self.payload(image="data:image/png;base64,bm90IGEgcG5n"),
            self.payload(image="data:image/jpeg;base64," + base64.b64encode(
                self.png
            ).decode("ascii")),
        ]
        for payload in cases:
            with self.subTest(payload=str(payload)[:80]):
                status, _, response = self.post(payload)
                self.assertEqual(status, 400, response)
                self.assertEqual(response["error"]["code"], "invalid_whiteboard")
                self.assertFalse(self.document_path.exists())
                self.assertFalse((self.session / "whiteboards").exists())

    def test_unreadable_document_is_409_and_not_overwritten(self) -> None:
        self.document_path.write_bytes(b"{broken\n")
        before = self.document_path.read_bytes()
        status, _, response = self.post()
        self.assertEqual(status, 409, response)
        self.assertEqual(response["error"]["code"], "whiteboards_unreadable")
        self.assertEqual(self.document_path.read_bytes(), before)

    def test_delete_whiteboard_removes_it_and_its_png(self) -> None:
        first = self.post(self.payload(id="wb-one"))[2]["whiteboard"]
        second = self.post(self.payload(id="wb-two", scope=GLOBAL))[2]["whiteboard"]
        for item in (first, second):
            self.assertTrue((self.session / item["image"]).is_file())
        status, _, response = self.harness.json(
            "DELETE", f"/api/sessions/{SESSION_ID}/whiteboards/wb-one"
        )
        self.assertEqual(status, 200, response)
        self.assertEqual(response["deleted"], "wb-one")
        self.assertEqual(
            [item["id"] for item in response["whiteboards"]["whiteboards"]],
            ["wb-two"],
        )
        self.assertFalse((self.session / first["image"]).is_file())
        self.assertTrue((self.session / second["image"]).is_file())
        saved = json.loads(self.document_path.read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in saved["whiteboards"]], ["wb-two"])

    def test_delete_unknown_whiteboard_is_404(self) -> None:
        status, _, response = self.harness.json(
            "DELETE", f"/api/sessions/{SESSION_ID}/whiteboards/missing"
        )
        self.assertEqual(status, 404, response)
        self.assertEqual(response["error"]["code"], "unknown_whiteboard")
        self.assertFalse(self.document_path.exists())

    def test_unknown_session_is_404(self) -> None:
        status, _, response = self.harness.json(
            "POST",
            "/api/sessions/does-not-exist/whiteboards",
            payload=self.payload(),
        )
        self.assertEqual(status, 404, response)
        self.assertEqual(response["error"]["code"], "unknown_session")


class WhiteboardTransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.session = make_web_session(Path(self._tmp.name))
        self.recording = Recording.open(self.session)
        frame = sorted((self.session / "frames").glob("*.png"))[0]
        self.data_url = "data:image/png;base64," + base64.b64encode(
            frame.read_bytes()
        ).decode("ascii")

    def payload(self, **overrides):
        payload = {
            "scope": GLOBAL,
            "text": "整体风格保持深色",
            "labels": [],
            "objects": {},
            "image": self.data_url,
            "confirmed": True,
        }
        payload.update(overrides)
        return payload

    def test_document_and_image_are_written(self) -> None:
        document, item = save_whiteboard(self.recording, self.payload())
        self.assertEqual(document["whiteboards"], [item])
        self.assertTrue((self.session / item["image"]).is_file())
        self.assertEqual(read_whiteboards(self.recording), document)

    def test_document_write_failure_removes_the_new_image(self) -> None:
        from unittest import mock

        real_replace = Path.replace

        def failing_replace(path, target):
            if path.name == "whiteboards.json.tmp":
                raise OSError("disk full")
            return real_replace(path, target)

        with mock.patch.object(Path, "replace", failing_replace):
            with self.assertRaises(WhiteboardError) as caught:
                save_whiteboard(self.recording, self.payload())
        self.assertEqual(caught.exception.code, "whiteboards_write_error")
        self.assertFalse((self.session / "whiteboards.json").exists())
        self.assertEqual(list((self.session / "whiteboards").glob("*.png")), [])


class WhiteboardDocumentSeamTest(unittest.TestCase):
    """B6: whiteboards share the document transaction behind Recording."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.session = make_web_session(Path(self._tmp.name))
        self.recording = Recording.open(self.session)
        frames = sorted((self.session / "frames").glob("*.png"))
        self.first_png = frames[0].read_bytes()
        self.second_png = frames[1].read_bytes()

    def data_url(self, data: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(data).decode(
            "ascii"
        )

    def payload(self, **overrides):
        payload = {
            "scope": GLOBAL,
            "text": "整体风格保持深色",
            "labels": [],
            "objects": {},
            "image": self.data_url(self.first_png),
            "confirmed": True,
        }
        payload.update(overrides)
        return payload

    def test_save_and_read_use_only_the_recording_document_seam(self) -> None:
        class SeamRecording:
            """Expose the document seam and nothing else."""

            def __init__(self, recording: Recording) -> None:
                self._recording = recording

            @property
            def whiteboards_store(self):
                return self._recording.whiteboards_store

            @property
            def whiteboards(self):
                return self._recording.whiteboards

            @whiteboards.setter
            def whiteboards(self, value) -> None:
                self._recording.whiteboards = value

            def __getattr__(self, name: str):
                raise AssertionError(f"unexpected recording attribute: {name}")

        seam = SeamRecording(self.recording)
        document, item = save_whiteboard(seam, self.payload(id="seam"))

        self.assertEqual([entry["id"] for entry in document["whiteboards"]], ["seam"])
        self.assertEqual(read_whiteboards(seam), document)
        self.assertTrue((self.session / item["image"]).is_file())

    def test_upsert_prunes_the_previous_content_addressed_image(self) -> None:
        _document, first = save_whiteboard(
            self.recording, self.payload(id="wb-fixed")
        )
        _document, second = save_whiteboard(
            self.recording,
            self.payload(id="wb-fixed", image=self.data_url(self.second_png)),
        )

        self.assertNotEqual(first["image"], second["image"])
        self.assertFalse((self.session / first["image"]).exists())
        self.assertTrue((self.session / second["image"]).is_file())

    def test_concurrent_saves_keep_every_whiteboard(self) -> None:
        def save(index: int):
            return save_whiteboard(
                self.recording,
                self.payload(
                    id=f"wb{index}",
                    text=f"board {index}",
                    image=self.data_url(self.first_png),
                ),
            )[1]

        with ThreadPoolExecutor(max_workers=5) as pool:
            items = list(pool.map(save, range(5)))

        self.assertEqual(
            sorted(item["id"] for item in items), ["wb0", "wb1", "wb2", "wb3", "wb4"]
        )
        saved = json.loads(
            (self.session / "whiteboards.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(saved["whiteboards"]), 5)
        for item in items:
            self.assertTrue((self.session / item["image"]).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
