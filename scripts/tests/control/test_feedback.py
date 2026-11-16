from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from entrypoints import feedback
from control.notes import add_note
from control.recording import Recording
from scripts.tests.session_fixtures import make_session
from scripts.tests.control.test_session_report import make_query_session


def run_feedback(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = feedback.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


class FeedbackAddTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_query_session(self.root)

    def _argv(self, *extra: str) -> list[str]:
        return [
            "add",
            "--session",
            str(self.session),
            "--click",
            "1:2",
            "--text",
            "button is too low",
            *extra,
        ]

    def test_add_writes_anchor_and_region_crop(self) -> None:
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            code, out, err = run_feedback(
                self._argv("--region", "0,0,1,1", "--json")
            )

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["feedback_anchor"]["kind"], "click")
        self.assertEqual(payload["resolved"]["frame_no"], 4)
        self.assertEqual(len(payload["region_images"]), 1)
        image = self.session / payload["region_images"][0]
        self.assertTrue(image.is_file())

        notes = Recording.open(self.session).annotations["notes"]
        note = next(item for item in notes if item["id"] == payload["note_id"])
        self.assertEqual(note["author"], "human")
        self.assertEqual(note["source"], "chat")
        self.assertEqual(note["feedback_anchor"]["seq_down"], 1)
        self.assertEqual(note["frame_no"], 4)

    def test_transcribed_by_ai_is_recorded(self) -> None:
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            code, _, err = run_feedback(self._argv("--transcribed-by", "ai"))

        self.assertEqual(code, 0, err)
        note = Recording.open(self.session).annotations["notes"][-1]
        self.assertEqual(note["transcribed_by"], "ai")

    def test_selector_is_required_and_mutually_exclusive(self) -> None:
        code, out, err = run_feedback(
            ["add", "--session", str(self.session), "--text", "x"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

        code, out, err = run_feedback(
            [
                "add",
                "--session",
                str(self.session),
                "--text",
                "x",
                "--click",
                "1:2",
                "--mark",
                "m",
            ]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_author_and_source_are_restricted(self) -> None:
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            bad_author = run_feedback(self._argv("--author", "ai"))
            bad_source = run_feedback(self._argv("--source", "import"))

        self.assertEqual(bad_author[0], 2)
        self.assertEqual(bad_source[0], 2)
        self.assertEqual(
            len(Recording.open(self.session).annotations["notes"]), 1
        )

    def test_session_must_stay_inside_the_sessions_root(self) -> None:
        outside = self.root.parent / "outside-session"
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir())
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            code, _, err = run_feedback(
                [
                    "add",
                    "--session",
                    str(outside),
                    "--text",
                    "x",
                    "--t-ms",
                    "0",
                ]
            )

        self.assertEqual(code, 2)
        self.assertIn("sessions root", err)

    def test_snapshot_supplies_the_region_crop_when_the_frame_is_gone(
        self,
    ) -> None:
        (self.session / "frames/000002.png").unlink()
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            code, out, err = run_feedback(
                [
                    "add",
                    "--session",
                    str(self.session),
                    "--t-ms",
                    "16",
                    "--region",
                    "0,0,1,1",
                    "--text",
                    "use the snapshot",
                    "--json",
                ]
            )

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["resolved"]["image_kind"], "snapshot")
        self.assertTrue((self.session / payload["region_images"][0]).is_file())

    def test_text_note_without_a_timeline_is_allowed(self) -> None:
        session = make_session(
            self.root,
            name="20260202-000000-aaaa",
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            code, out, err = run_feedback(
                [
                    "add",
                    "--session",
                    str(session),
                    "--t-ms",
                    "0",
                    "--text",
                    "plain text only",
                    "--json",
                ]
            )

        self.assertEqual(code, 0, err)
        note = Recording.open(session).annotations["notes"][0]
        self.assertEqual(note["frame_no"], 0)
        self.assertEqual(note["feedback_anchor"], {"kind": "t_ms", "t_ms": 0})

    def test_concurrent_adds_keep_every_note(self) -> None:
        recording = Recording.open(self.session)

        def add(index: int) -> str:
            _document, saved = add_note(
                recording,
                {
                    "frame_no": 2,
                    "t_ms": 16,
                    "regions": [],
                    "tags": [],
                    "text": f"note {index}",
                    "feedback_anchor": {
                        "kind": "click",
                        "seq_down": 1,
                        "seq_up": 2,
                    },
                },
                source="chat",
            )
            return saved["id"]

        with ThreadPoolExecutor(max_workers=5) as pool:
            ids = list(pool.map(add, range(5)))

        notes = Recording.open(self.session).annotations["notes"]
        saved_ids = {note["id"] for note in notes}
        self.assertTrue(set(ids) <= saved_ids)
        self.assertEqual(len(notes), 6)

    def test_region_outside_the_display_is_cropped_or_rejected(self) -> None:
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(self.root)}
        ):
            code, out, err = run_feedback(
                self._argv("--region", "500,500,10,10", "--json")
            )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("cannot be cropped", err)
        self.assertEqual(
            len(Recording.open(self.session).annotations["notes"]), 1
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
