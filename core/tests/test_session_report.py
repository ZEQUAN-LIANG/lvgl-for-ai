"""Session evidence summary and report tool.

The fixtures build finished ``sessions/<id>/`` directories directly; no engine
and no web server is ever started.
"""

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
from support import read_png_rgb, write_png_rgb

SESSION_NAME = "20260102-030405-abcd"
FRAME_1 = "frames/000001.png"
FRAME_2 = "frames/000002.png"
SNAPSHOT = "snapshots/001_after_click.png"


def make_session(
    root: Path,
    *,
    name: str = SESSION_NAME,
    status: str = "ok",
    app: str = "coffee",
    display: dict | None = None,
    record_changed_only: bool = True,
    with_timeline: bool = True,
    with_frame_diffs: bool = True,
    with_frames: bool = True,
    with_snapshot: bool = True,
    frame_count: int = 2,
    engine_log: str | None = None,
    error: dict | None = None,
) -> Path:
    session = root / name
    (session / "frames").mkdir(parents=True)
    if with_frames:
        write_png_rgb(session / FRAME_1, 2, 2, [(255, 0, 0)] * 4)
        write_png_rgb(session / FRAME_2, 2, 2, [(0, 255, 0)] * 4)
    if with_snapshot:
        (session / "snapshots").mkdir()
        write_png_rgb(session / SNAPSHOT, 1, 1, [(0, 0, 255)])

    if with_timeline:
        rows = [
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "frame",
                "frame_no": 1,
                "t_ms": 0,
                "file": FRAME_1,
            },
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "input",
                "seq": 1,
                "source": "scenario",
                "frame_no": 1,
                "t_ms": 0,
                "device": "pointer",
                "action": "down",
                "x": 112,
                "y": 324,
                "hit": "btn",
                "hit_class": "lv_button",
            },
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "mark",
                "frame_no": 1,
                "t_ms": 16,
                "id": "start",
            },
        ]
        if with_snapshot:
            rows.append(
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "snapshot",
                    "frame_no": 1,
                    "t_ms": 16,
                    "label": "after_click",
                    "file": SNAPSHOT,
                }
            )
        rows.extend(
            [
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "frame",
                    "frame_no": 2,
                    "t_ms": 32,
                    "file": FRAME_2,
                },
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "input",
                    "seq": 2,
                    "source": "scenario",
                    "frame_no": 2,
                    "t_ms": 32,
                    "device": "key",
                    "action": "press",
                    "key": "ENTER",
                    "delivered": True,
                },
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "end",
                    "frame_count": frame_count,
                    "t_ms": 32,
                    "truncated": False,
                },
            ]
        )
        (session / "timeline.ndjson").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    if with_frame_diffs:
        diff = {
            "schema": "lvgl-ai-frame-diffs-v1",
            "frame_no": 2,
            "prev_frame_no": 1,
            "t_ms": 32,
            "width": 2,
            "height": 2,
            "threshold": 10,
            "bbox": {"x": 0, "y": 0, "w": 2, "h": 2},
            "changed_px": 9,
            "changed_ratio": 0.25,
            "max_delta": 0.2,
        }
        (session / "frame_diffs.ndjson").write_text(
            json.dumps(diff) + "\n", encoding="utf-8"
        )

    if engine_log is None:
        engine_log = (
            "[app] apps=coffee,settings\n"
            "[app] app_create\n"
            "[app] app=settings\n"
            "[app] app=coffee\n"
        )
    (session / "engine.log").write_text(engine_log, encoding="utf-8")

    artifacts = {"manifest": "manifest.json", "engine_log": "engine.log"}
    if with_timeline:
        artifacts["timeline"] = "timeline.ndjson"
    if with_frame_diffs:
        artifacts["frame_diffs"] = "frame_diffs.ndjson"
    if with_frames:
        artifacts["frames"] = [FRAME_1, FRAME_2]
    if with_snapshot:
        artifacts["snapshots"] = [SNAPSHOT]

    manifest = {
        "schema": "lvgl-ai-session-v1",
        "id": name,
        "status": status,
        "app": app,
        "record_changed_only": record_changed_only,
        "mode": "headless",
        "input": ["real", "virtual"],
        "build": {"status": "ok", "log": "build.log"},
        "lvgl": "9.6.0",
        "lvgl_src": "I:/lvgl-src/9.6",
        "adapter": "9x",
        "display": display,
        "tool_version": "0.1.0",
        "frame_count": frame_count,
        "truncated": False,
        "log_truncated": False,
        "checks": [],
        "error": error,
        "artifacts": artifacts,
    }
    (session / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return session


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
        self.assertGreater(width, 1)
        self.assertGreater(height, 1)
        self.assertEqual(
            (self.frame.read_bytes(), snapshot.read_bytes()), before
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
