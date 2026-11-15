from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import session_report
from support import write_png_rgb
from test_session_report import make_query_session

OLD = "20260102-030405-abcd"
NEW = "20260103-000000-bbbb"


def run_report(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = session_report.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def write_note(
    session: Path,
    note_id: str,
    *,
    anchor: dict | None = None,
    regions: list[dict] | None = None,
    text: str = "button is too low",
) -> None:
    path = session / "annotations.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["notes"].append(
        {
            "id": note_id,
            "frame_no": 2,
            "t_ms": 16,
            "regions": regions
            if regions is not None
            else [{"x": 0, "y": 0, "w": 1, "h": 1}],
            "tags": [],
            "text": text,
            "author": "human",
            "source": "chat",
            "feedback_anchor": anchor
            if anchor is not None
            else {"kind": "click", "seq_down": 1, "seq_up": 2},
        }
    )
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")


def set_context(
    session: Path, scenario: str | None, source: str | None
) -> None:
    path = session / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["scenario"] = (
        None
        if scenario is None
        else {"path": "user/scenarios/x.json", "sha256": scenario}
    )
    manifest["source_digest"] = (
        None
        if source is None
        else {"dir": "user/app", "sha256": source, "files": 3}
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class FeedbackRemapTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.old = make_query_session(self.root, name=OLD)
        self.new = make_query_session(self.root, name=NEW)
        set_context(self.old, "a" * 64, "b" * 64)
        set_context(self.new, "a" * 64, "b" * 64)
        (self.old / "annotations.json").write_text(
            '{"schema": "lvgl-ai-annotations-v1", "notes": []}\n',
            encoding="utf-8",
        )

    def feedback(self, *extra: str) -> tuple[int, str, str]:
        return run_report(
            [
                "feedback",
                str(self.old),
                "--previous",
                str(self.new),
                "--json",
                *extra,
            ]
        )

    def test_same_scene_reports_zero_pixel_change(self) -> None:
        write_note(self.old, "note-1")
        before = (self.old / "annotations.json").read_bytes()

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["located"], 1)
        self.assertEqual(payload["unmapped"], 0)
        self.assertEqual(payload["notes_with_pixel_change"], 0)
        item = payload["items"][0]
        self.assertTrue(item["located"])
        self.assertEqual(item["new_frame"], 4)
        self.assertIn("changed_px", item["pixel_diff"])
        self.assertIn("max_delta", item["pixel_diff"])
        self.assertEqual(item["pixel_diff"]["threshold"], 10)
        self.assertEqual(item["anchor_unreliable_reasons"], [])
        self.assertEqual((self.old / "annotations.json").read_bytes(), before)
        lowered = out.lower()
        for word in ("fixed", "unfixed", "pass", "fail", "approved"):
            with self.subTest(word=word):
                self.assertNotIn(word, lowered)

    def test_changed_pixels_are_numeric_not_a_verdict(self) -> None:
        write_note(self.old, "note-1")
        write_png_rgb(
            self.new / "frames/000004.png", 2, 2, [(250, 250, 250)] * 4
        )

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["notes_with_pixel_change"], 1)
        diff = payload["items"][0]["pixel_diff"]
        self.assertGreater(diff["changed_px"], 0)
        self.assertGreater(diff["changed_ratio"], 0)
        self.assertGreater(diff["max_delta"], 0)
        self.assertIsInstance(diff["changed_px"], int)
        self.assertIsInstance(diff["changed_ratio"], float)
        self.assertIsInstance(diff["max_delta"], float)

    def test_changed_scene_source_and_display_are_context(self) -> None:
        write_note(self.old, "note-1")
        set_context(self.new, "c" * 64, "d" * 64)

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["context"]["scenario_changed"])
        self.assertTrue(payload["context"]["source_changed"])
        self.assertFalse(payload["context"]["source_unknown"])

    def test_missing_digest_is_unknown(self) -> None:
        write_note(self.old, "note-1")
        set_context(self.new, None, None)

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["context"]["scenario_changed"], "unknown")
        self.assertEqual(payload["context"]["source_changed"], "unknown")
        self.assertTrue(payload["context"]["source_unknown"])
        self.assertIn(
            "source_unknown",
            payload["items"][0]["anchor_unreliable_reasons"],
        )

    def test_missing_old_region_image_is_reported(self) -> None:
        write_note(
            self.old,
            "note-1",
            regions=[
                {
                    "x": 0,
                    "y": 0,
                    "w": 1,
                    "h": 1,
                    "image": "regions/missing.png",
                }
            ],
        )
        (self.old / "frames/000004.png").unlink()

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        item = json.loads(out)["items"][0]
        self.assertIn("old_image_missing", item["anchor_unreliable_reasons"])
        self.assertIsNone(item["pixel_diff"])

    def test_size_change_skips_the_pixel_comparison(self) -> None:
        write_note(
            self.old,
            "note-1",
            regions=[
                {
                    "x": 0,
                    "y": 0,
                    "w": 2,
                    "h": 2,
                    "image": "regions/small.png",
                }
            ],
        )
        (self.old / "regions").mkdir()
        write_png_rgb(self.old / "regions/small.png", 1, 1, [(10, 10, 10)])

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        item = json.loads(out)["items"][0]
        self.assertIn("size_changed", item["anchor_unreliable_reasons"])
        self.assertIsNone(item["pixel_diff"])

    def test_out_of_bounds_region_is_reported(self) -> None:
        write_note(
            self.old,
            "note-1",
            regions=[
                {
                    "x": 50,
                    "y": 50,
                    "w": 2,
                    "h": 2,
                    "image": "regions/oob.png",
                }
            ],
        )
        (self.old / "regions").mkdir()
        write_png_rgb(self.old / "regions/oob.png", 2, 2, [(10, 10, 10)] * 4)

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        item = json.loads(out)["items"][0]
        self.assertIn("out_of_bounds", item["anchor_unreliable_reasons"])
        self.assertIsNone(item["pixel_diff"])

    def test_fallback_anchor_is_flagged(self) -> None:
        write_note(
            self.old,
            "note-1",
            anchor={"kind": "mark", "id": "missing"},
        )

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        item = json.loads(out)["items"][0]
        self.assertFalse(item["located"])
        self.assertEqual(json.loads(out)["unmapped"], 1)

    def test_only_eight_human_notes_are_compared(self) -> None:
        for index in range(10):
            write_note(self.old, f"note-{index}")

        code, out, err = self.feedback()

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["total"], 8)
        self.assertEqual(
            [item["note_id"] for item in payload["items"]],
            [f"note-{index}" for index in range(2, 10)],
        )

    def test_latest_session_with_notes_is_discovered(self) -> None:
        write_note(self.old, "note-1")

        code, out, err = run_report(
            ["feedback", "--previous", str(self.new), "--json"]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["located"], 1)

    def test_no_notes_session_is_an_error(self) -> None:
        for child in self.root.iterdir():
            annotations = child / "annotations.json"
            annotations.write_text(
                '{"schema": "lvgl-ai-annotations-v1", "notes": []}\n',
                encoding="utf-8",
            )

        code, out, err = run_report(
            ["feedback", "--previous", str(self.new), "--json"]
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("no other session", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
