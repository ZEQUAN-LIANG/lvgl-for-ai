
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import session_report
from lvgl_ai import summarize_session
from lvgl_ai.control.evidence import CLI_EVIDENCE_FIELDS, SUMMARY_FIELDS
from session_fixtures import (
    FRAME_1,
    FRAME_2,
    SESSION_NAME,
    SNAPSHOT,
    make_summary_session as make_session,
)
from support import distinct_rgb, read_png_rgb, write_png_rgb


class SummarizeSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_complete_session_reports_stable_fields_and_absolute_paths(self) -> None:
        session = make_session(
            self.root,
            display={"width": 390, "height": 450},
        )

        summary = summarize_session(session)

        self.assertEqual(summary["session_id"], SESSION_NAME)
        self.assertEqual(summary["session_dir"], str(session.resolve()))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["mode"], "headless")
        self.assertEqual(summary["display"], {"width": 390, "height": 450})
        self.assertEqual(summary["frame_count"], 2)
        self.assertTrue(summary["record_changed_only"])
        self.assertEqual(summary["requested_app"], "coffee")
        self.assertEqual(summary["effective_app"], "coffee")
        self.assertTrue(summary["recorded"])
        self.assertIsNone(summary["error"])

        self.assertEqual(len(summary["snapshots"]), 1)
        self.assertEqual(summary["snapshots"][0]["label"], "after_click")
        snapshot_path = Path(summary["snapshots"][0]["path"])
        self.assertTrue(snapshot_path.is_absolute())
        self.assertEqual(snapshot_path, (session / SNAPSHOT).resolve())

        self.assertEqual([frame["id"] for frame in summary["marks"]], ["start"])
        self.assertEqual(
            [row["device"] for row in summary["inputs"]], ["pointer", "key"]
        )
        self.assertEqual(summary["inputs"][0]["hit"], "btn")
        self.assertEqual(summary["frame_diffs"][0]["changed_px"], 9)

        frame_paths = [Path(path) for path in summary["frames"]]
        self.assertEqual(
            frame_paths, [(session / FRAME_1).resolve(), (session / FRAME_2).resolve()]
        )
        self.assertTrue(all(path.is_absolute() for path in frame_paths))
        self.assertIn("[app] app=coffee", summary["log_tail"])

        from_manifest = summarize_session(session / "manifest.json")
        self.assertEqual(from_manifest, summary)

    def test_summary_and_cli_field_lists_are_one_contract(self) -> None:
        session = make_session(self.root)

        summary = summarize_session(session)

        self.assertEqual(tuple(summary), SUMMARY_FIELDS)
        self.assertTrue(set(CLI_EVIDENCE_FIELDS) <= set(SUMMARY_FIELDS))
        self.assertIn("frames", SUMMARY_FIELDS)
        self.assertNotIn("frames", CLI_EVIDENCE_FIELDS)

    def test_recorded_session_missing_evidence_files_raises(self) -> None:
        for missing, name in (
            ("timeline.ndjson", "20260120-000000-aaaa"),
            ("frame_diffs.ndjson", "20260121-000000-bbbb"),
        ):
            with self.subTest(missing=missing):
                session = make_session(self.root, name=name)
                (session / missing).unlink()
                with self.assertRaises(FileNotFoundError) as caught:
                    summarize_session(session)
                self.assertIn(missing, str(caught.exception))

    def test_record_false_session_has_empty_evidence_and_recorded_false(self) -> None:
        session = make_session(
            self.root,
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        summary = summarize_session(session)

        self.assertEqual(summary["status"], "ok")
        self.assertFalse(summary["recorded"])
        self.assertEqual(summary["marks"], [])
        self.assertEqual(summary["inputs"], [])
        self.assertEqual(summary["frame_diffs"], [])
        self.assertEqual(summary["snapshots"], [])
        self.assertEqual(summary["frames"], [])

    def test_crash_session_without_recording_files_keeps_its_error(self) -> None:
        error = {
            "code": "crash",
            "message": "engine exited with 3",
            "detail": {"exit_code": 3, "log_tail": ["boom"]},
        }
        session = make_session(
            self.root,
            status="crash",
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
            engine_log="[app] app_create\nboom\n",
            error=error,
        )

        summary = summarize_session(session)

        self.assertEqual(summary["status"], "crash")
        self.assertFalse(summary["recorded"])
        self.assertEqual(summary["frame_diffs"], [])
        self.assertEqual(summary["error"], error)
        self.assertIsNone(summary["effective_app"])

    def test_missing_manifest_or_engine_log_is_an_error(self) -> None:
        session = make_session(self.root)
        missing_manifest = make_session(self.root, name="20260103-000000-beef")
        (missing_manifest / "manifest.json").unlink()
        missing_log = make_session(self.root, name="20260104-000000-cafe")
        (missing_log / "engine.log").unlink()

        for path in (session / "does-not-exist", missing_manifest, missing_log):
            with self.subTest(path=path.name):
                with self.assertRaises(FileNotFoundError):
                    summarize_session(path)

    def test_log_tail_is_capped_and_zero_returns_empty(self) -> None:
        log = "".join(f"line {index}\n" for index in range(10))
        session = make_session(self.root, engine_log=log)

        summary = summarize_session(session, log_tail_lines=3)

        self.assertEqual(summary["log_tail"], ["line 7", "line 8", "line 9"])
        self.assertEqual(
            summarize_session(session, log_tail_lines=0)["log_tail"], []
        )


def run_report(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = session_report.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def one_json(text: str) -> dict:
    lines = text.splitlines()
    if len(lines) != 1:
        raise AssertionError(f"expected exactly one stdout line, got {lines!r}")
    return json.loads(lines[0])


class SessionReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_json_prints_the_summary_on_one_line(self) -> None:
        session = make_session(self.root, display={"width": 390, "height": 450})

        with mock.patch(
            "subprocess.Popen", side_effect=AssertionError("must not spawn")
        ):
            code, out, err = run_report([str(session), "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        payload = one_json(out)
        self.assertEqual(payload["session_id"], SESSION_NAME)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["display"], {"width": 390, "height": 450})
        self.assertEqual(payload["snapshots"][0]["label"], "after_click")
        self.assertTrue(Path(payload["snapshots"][0]["path"]).is_absolute())
        self.assertTrue(Path(payload["frames"][0]).is_absolute())

    def test_human_output_lists_evidence_and_absolute_paths(self) -> None:
        session = make_session(self.root, display={"width": 390, "height": 450})

        code, out, err = run_report([str(session)])

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("status: ok", out)
        self.assertIn("display: 390x450", out)
        self.assertIn("frames: 2", out)
        self.assertIn("requested app: coffee", out)
        self.assertIn("effective app: coffee", out)
        self.assertIn(str((session / SNAPSHOT).resolve()), out)
        self.assertIn(str((session / FRAME_1).resolve()), out)
        self.assertIn("start", out)
        self.assertIn("pointer", out)
        self.assertIn("changed_px=9", out)
        self.assertIn("[app] app=coffee", out)
        lowered = out.lower()
        for word in ("pass", "fail", "baseline", "approval", "acceptance"):
            with self.subTest(word=word):
                self.assertNotIn(word, lowered)

    def test_default_and_latest_use_the_sessions_root_env(self) -> None:
        make_session(self.root, name="20260101-000000-aaaa")
        make_session(
            self.root,
            name="20260103-000000-bbbb",
            display={"width": 390, "height": 450},
        )

        with mock.patch.dict(
            os.environ, {"LVGL_AI_SESSIONS_ROOT": str(self.root)}
        ):
            default_code, default_out, default_err = run_report(["--json"])
            latest_code, latest_out, latest_err = run_report(
                ["--latest", "--json"]
            )

        self.assertEqual(default_code, 0, default_err)
        self.assertEqual(latest_code, 0, latest_err)
        self.assertEqual(
            one_json(default_out)["session_id"], "20260103-000000-bbbb"
        )
        self.assertEqual(
            one_json(latest_out)["session_id"], "20260103-000000-bbbb"
        )

    def test_empty_sessions_root_is_an_error(self) -> None:
        with mock.patch.dict(
            os.environ, {"LVGL_AI_SESSIONS_ROOT": str(self.root)}
        ):
            code, out, err = run_report(["--latest", "--json"])

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(str(self.root), err)

    def test_unknown_session_and_corrupt_files_exit_2(self) -> None:
        missing = self.root / "does-not-exist"
        corrupt_manifest = make_session(self.root, name="20260105-000000-d00d")
        (corrupt_manifest / "manifest.json").write_text("{", encoding="utf-8")
        corrupt_timeline = make_session(self.root, name="20260106-000000-feed")
        (corrupt_timeline / "timeline.ndjson").write_text(
            "{not json}\n", encoding="utf-8"
        )

        for path in (missing, corrupt_manifest, corrupt_timeline):
            with self.subTest(path=path.name):
                code, out, err = run_report([str(path), "--json"])
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn(str(path.name), err)

    def test_log_tail_flag_limits_the_human_log_section(self) -> None:
        session = make_session(self.root)

        code, out, err = run_report([str(session), "--log-tail", "2"])

        self.assertEqual(code, 0, err)
        self.assertIn("[app] app=settings", out)
        self.assertIn("[app] app=coffee", out)
        self.assertNotIn("[app] apps=coffee,settings", out)

    def test_missing_effective_app_is_reported_as_unknown(self) -> None:
        session = make_session(
            self.root, engine_log="[app] app_create\nhello\n"
        )

        json_code, json_out, _ = run_report([str(session), "--json"])
        human_code, human_out, _ = run_report([str(session)])

        self.assertEqual(json_code, 0)
        self.assertIsNone(one_json(json_out)["effective_app"])
        self.assertEqual(human_code, 0)
        self.assertIn("effective app: 未知", human_out)


class VisualEvidenceCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_session(self.root)
        self.frame = (self.session / FRAME_2).resolve()

    def test_pixel_prints_the_rgb_value(self) -> None:
        code, out, err = run_report(["pixel", str(self.frame), "--at", "1,1"])

        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertIn("0,255,0", out)
        self.assertIn("1,1", out)

    def test_pixel_rejects_coordinates_outside_the_image(self) -> None:
        code, out, err = run_report(["pixel", str(self.frame), "--at", "5,0"])

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("5,0", err)
        self.assertIn("2x2", err)

    def test_crop_writes_the_explicit_output_and_leaves_the_input_untouched(
        self,
    ) -> None:
        before = self.frame.read_bytes()
        output = self.root / "crop.png"

        code, out, err = run_report(
            [
                "crop",
                str(self.frame),
                "--region",
                "0,0,1,1",
                "--out",
                str(output),
            ]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertIn(str(output.resolve()), out)
        self.assertEqual(read_png_rgb(output), (1, 1, [(0, 255, 0)]))
        self.assertEqual(self.frame.read_bytes(), before)

    def test_crop_rejects_an_empty_region_and_writing_over_the_input(
        self,
    ) -> None:
        before = self.frame.read_bytes()
        output = self.root / "crop.png"

        empty_code, empty_out, empty_err = run_report(
            [
                "crop",
                str(self.frame),
                "--region",
                "5,5,1,1",
                "--out",
                str(output),
            ]
        )
        overwrite_code, overwrite_out, overwrite_err = run_report(
            [
                "crop",
                str(self.frame),
                "--region",
                "0,0,1,1",
                "--out",
                str(self.frame),
            ]
        )

        self.assertEqual(empty_code, 2)
        self.assertEqual(empty_out, "")
        self.assertIn("2x2", empty_err)
        self.assertFalse(output.exists())
        self.assertEqual(overwrite_code, 2)
        self.assertEqual(overwrite_out, "")
        self.assertIn("input", overwrite_err)
        self.assertEqual(self.frame.read_bytes(), before)

    def test_contact_sheet_writes_explicit_output_and_reports_labels(
        self,
    ) -> None:
        snapshot = (self.session / SNAPSHOT).resolve()
        before = (self.frame.read_bytes(), snapshot.read_bytes())
        output = self.root / "sheet.png"

        code, out, err = run_report(
            [
                "contact-sheet",
                "--out",
                str(output),
                "--input",
                f"first={self.frame}",
                "--input",
                f"second={snapshot}",
                "--columns",
                "2",
                "--tile",
                "64x48",
            ]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertIn(str(output.resolve()), out)
        self.assertIn("tiles: 2", out)
        self.assertIn("first", out)
        self.assertIn("second", out)
        width, height, _pixels = read_png_rgb(output)
        self.assertEqual((width, height), (152, 64))
        colors = distinct_rgb(output)
        self.assertIn((0, 255, 0), colors)
        self.assertIn((0, 0, 255), colors)
        self.assertEqual(
            (self.frame.read_bytes(), snapshot.read_bytes()), before
        )

    def test_visual_outputs_refuse_to_write_inside_session_evidence(self) -> None:
        snapshot = (self.session / SNAPSHOT).resolve()
        crop_out = self.session / "frames" / "crop.png"
        sheet_out = self.session / "sheet.png"

        crop_code, crop_out_text, crop_err = run_report(
            [
                "crop",
                str(self.frame),
                "--region",
                "0,0,1,1",
                "--out",
                str(crop_out),
            ]
        )
        sheet_code, sheet_out_text, sheet_err = run_report(
            [
                "contact-sheet",
                "--out",
                str(sheet_out),
                "--input",
                str(self.frame),
                "--input",
                str(snapshot),
            ]
        )

        self.assertEqual(crop_code, 2)
        self.assertEqual(crop_out_text, "")
        self.assertIn("session evidence", crop_err)
        self.assertFalse(crop_out.exists())
        self.assertEqual(sheet_code, 2)
        self.assertEqual(sheet_out_text, "")
        self.assertIn("session evidence", sheet_err)
        self.assertFalse(sheet_out.exists())


class CompareCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.left = self.root / "left.png"
        self.right = self.root / "right.png"
        self.heatmap = self.root / "heatmap.png"
        self.left_pixels = [(10, 20, 30)] * 4
        self.right_pixels = [(10, 20, 30)] * 3 + [(10, 20, 40)]
        write_png_rgb(self.left, 2, 2, self.left_pixels)
        write_png_rgb(self.right, 2, 2, self.right_pixels)

    def test_compare_two_pngs_writes_explicit_heatmap_and_metrics(self) -> None:
        left_before = self.left.read_bytes()
        right_before = self.right.read_bytes()

        code, out, err = run_report(
            [
                "compare",
                str(self.left),
                str(self.right),
                "--out",
                str(self.heatmap),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        payload = one_json(out)
        self.assertEqual(payload["left"], str(self.left.resolve()))
        self.assertEqual(payload["right"], str(self.right.resolve()))
        self.assertEqual((payload["width"], payload["height"]), (2, 2))
        self.assertEqual(
            payload["bbox"], {"x": 1, "y": 1, "w": 1, "h": 1}
        )
        self.assertEqual(payload["changed_px"], 1)
        self.assertEqual(payload["changed_ratio"], 0.25)
        self.assertAlmostEqual(payload["max_delta"], 10 / 255)
        self.assertEqual(payload["heatmap"], str(self.heatmap.resolve()))
        self.assertEqual(
            read_png_rgb(self.heatmap),
            (
                2,
                2,
                [
                    (24, 24, 24),
                    (24, 24, 24),
                    (24, 24, 24),
                    (255, 245, 0),
                ],
            ),
        )
        self.assertEqual(self.left.read_bytes(), left_before)
        self.assertEqual(self.right.read_bytes(), right_before)
        lowered = out.lower()
        for word in ("pass", "fail", "baseline", "approval", "acceptance"):
            with self.subTest(word=word):
                self.assertNotIn(word, lowered)

    def test_compare_without_out_reports_no_heatmap(self) -> None:
        code, out, err = run_report(
            ["compare", str(self.left), str(self.right), "--json"]
        )

        self.assertEqual(code, 0, err)
        self.assertIsNone(one_json(out)["heatmap"])
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            ["left.png", "right.png"],
        )

    def test_compare_human_output_lists_evidence(self) -> None:
        code, out, err = run_report(
            ["compare", str(self.left), str(self.right)]
        )

        self.assertEqual(code, 0, err)
        self.assertIn("compare: 2x2", out)
        self.assertIn("bbox: 1,1,1,1", out)
        self.assertIn("changed_px: 1", out)
        self.assertIn("changed_ratio: 0.250000000", out)
        self.assertIn("max_delta: 0.039215686", out)
        self.assertIn("heatmap: none", out)
        lowered = out.lower()
        for word in ("pass", "fail", "baseline", "approval", "acceptance"):
            with self.subTest(word=word):
                self.assertNotIn(word, lowered)

    def test_compare_two_sessions_uses_their_latest_snapshots(self) -> None:
        left_session = make_session(
            self.root, name="20260107-000000-aaaa"
        )
        right_session = make_session(
            self.root, name="20260108-000000-bbbb"
        )
        write_png_rgb(
            left_session / SNAPSHOT, 2, 2, [(10, 20, 30)] * 4
        )
        write_png_rgb(
            right_session / SNAPSHOT,
            2,
            2,
            [(10, 20, 30)] * 3 + [(10, 20, 40)],
        )

        code, out, err = run_report(
            [
                "compare",
                str(left_session),
                str(right_session),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(
            payload["left"], str((left_session / SNAPSHOT).resolve())
        )
        self.assertEqual(
            payload["right"], str((right_session / SNAPSHOT).resolve())
        )
        self.assertEqual(payload["changed_px"], 1)

    def test_compare_sessions_use_the_last_snapshot_in_summary_order(self) -> None:
        left_session = make_session(
            self.root, name="20260114-000000-aaaa"
        )
        right_session = make_session(
            self.root, name="20260115-000000-bbbb"
        )
        left_last = left_session / "snapshots" / "002_second.png"
        right_last = right_session / "snapshots" / "002_second.png"
        write_png_rgb(left_last, 2, 2, [(10, 20, 30)] * 4)
        write_png_rgb(
            right_last, 2, 2, [(10, 20, 30)] * 3 + [(10, 20, 40)]
        )

        code, out, err = run_report(
            [
                "compare",
                str(left_session),
                str(right_session),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(payload["left"], str(left_last.resolve()))
        self.assertEqual(payload["right"], str(right_last.resolve()))
        self.assertEqual(payload["changed_px"], 1)

    def test_compare_sessions_fall_back_to_the_last_frame(self) -> None:
        left_session = make_session(
            self.root, name="20260109-000000-cccc", with_snapshot=False
        )
        right_session = make_session(
            self.root, name="20260110-000000-dddd", with_snapshot=False
        )
        write_png_rgb(
            right_session / FRAME_2, 2, 2, [(0, 0, 255)] * 4
        )

        code, out, err = run_report(
            [
                "compare",
                str(left_session),
                str(right_session),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(
            payload["left"], str((left_session / FRAME_2).resolve())
        )
        self.assertEqual(
            payload["right"], str((right_session / FRAME_2).resolve())
        )
        self.assertEqual(payload["changed_px"], 4)
        self.assertEqual(payload["max_delta"], 1.0)

    def test_compare_rejects_a_session_without_images(self) -> None:
        session = make_session(
            self.root,
            name="20260111-000000-eeee",
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        code, out, err = run_report(
            ["compare", str(session), str(session), "--json"]
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("no snapshots or frames", err)

    def test_compare_size_mismatch_exits_2_without_writing(self) -> None:
        write_png_rgb(self.right, 1, 1, [(0, 0, 0)])

        code, out, err = run_report(
            [
                "compare",
                str(self.left),
                str(self.right),
                "--out",
                str(self.heatmap),
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("2x2", err)
        self.assertIn("1x1", err)
        self.assertFalse(self.heatmap.exists())

    def test_compare_refuses_to_overwrite_an_input(self) -> None:
        before = self.left.read_bytes()

        code, out, err = run_report(
            [
                "compare",
                str(self.left),
                str(self.right),
                "--out",
                str(self.left),
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("input", err)
        self.assertEqual(self.left.read_bytes(), before)

    def test_compare_refuses_a_heatmap_inside_session_evidence(self) -> None:
        session = make_session(
            self.root, name="20260112-000000-ffff"
        )
        output = session / "compare.png"

        code, out, err = run_report(
            [
                "compare",
                str(session),
                str(session),
                "--out",
                str(output),
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("session evidence", err)
        self.assertFalse(output.exists())

    def test_compare_refuses_a_heatmap_beside_png_evidence(self) -> None:
        session = make_session(
            self.root, name="20260113-000000-9999"
        )
        output = session / "compare.png"

        code, out, err = run_report(
            [
                "compare",
                str(session / FRAME_1),
                str(session / FRAME_2),
                "--out",
                str(output),
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("session evidence", err)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
