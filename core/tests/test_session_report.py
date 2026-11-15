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
from lvgl_ai import session_index
from lvgl_ai.control.evidence import INDEX_FIELDS
from session_fixtures import (
    FRAME_1,
    FRAME_2,
    SESSION_NAME,
    SNAPSHOT,
    make_session,
    make_summary_session,
)
from support import distinct_rgb, read_png_rgb, write_png_rgb


def make_query_session(root: Path, name: str = SESSION_NAME) -> Path:
    session = make_session(
        root,
        name=name,
        display={"width": 40, "height": 30},
        with_snapshot=False,
        frames=4,
    )
    frames = session / "frames"
    for number in (1, 2, 3, 4):
        write_png_rgb(
            frames / f"{number:06d}.png", 2, 2, [(number * 20, 0, 0)] * 4
        )
    snapshots = session / "snapshots"
    snapshots.mkdir()
    write_png_rgb(snapshots / "001_after.png", 2, 2, [(0, 0, 255)] * 4)
    timeline = [
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 1,
            "t_ms": 0,
            "file": "frames/000001.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 2,
            "t_ms": 16,
            "file": "frames/000002.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "input",
            "seq": 1,
            "frame_no": 2,
            "t_ms": 16,
            "device": "pointer",
            "action": "down",
            "x": 10,
            "y": 20,
            "hit": "btn",
            "hit_class": "lv_button",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "wait",
            "t_ms_start": 16,
            "t_ms_end": 32,
            "frame_start": 2,
            "frame_end": 3,
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "mark",
            "frame_no": 2,
            "t_ms": 16,
            "id": "after_click",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "snapshot",
            "frame_no": 2,
            "t_ms": 16,
            "label": "after",
            "file": "snapshots/001_after.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 3,
            "t_ms": 32,
            "file": "frames/000003.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "input",
            "seq": 2,
            "frame_no": 3,
            "t_ms": 32,
            "device": "pointer",
            "action": "up",
            "x": 10,
            "y": 20,
            "hit": "btn",
            "hit_class": "lv_button",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 4,
            "t_ms": 48,
            "file": "frames/000004.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "end",
            "frame_count": 4,
            "t_ms": 48,
            "truncated": False,
        },
    ]
    (session / "timeline.ndjson").write_text(
        "".join(json.dumps(row) + "\n" for row in timeline),
        encoding="utf-8",
    )
    (session / "frame_diffs.ndjson").write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "schema": "lvgl-ai-frame-diffs-v1",
                    "frame_no": 2,
                    "prev_frame_no": 1,
                    "t_ms": 16,
                    "width": 2,
                    "height": 2,
                    "threshold": 10,
                    "bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
                    "changed_px": 1,
                    "changed_ratio": 0.25,
                    "max_delta": 0.2,
                },
                {
                    "schema": "lvgl-ai-frame-diffs-v1",
                    "frame_no": 4,
                    "prev_frame_no": 3,
                    "t_ms": 48,
                    "width": 2,
                    "height": 2,
                    "threshold": 10,
                    "bbox": {"x": 1, "y": 1, "w": 1, "h": 1},
                    "changed_px": 3,
                    "changed_ratio": 0.75,
                    "max_delta": 0.4,
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (session / "annotations.json").write_text(
        json.dumps(
            {
                "schema": "lvgl-ai-annotations-v1",
                "notes": [
                    {
                        "id": "note-1",
                        "frame_no": 2,
                        "t_ms": 16,
                        "regions": [{"x": 0, "y": 0, "w": 1, "h": 1}],
                        "tags": [],
                        "text": "button is too low",
                        "author": "human",
                        "source": "chat",
                        "feedback_anchor": {
                            "kind": "click",
                            "seq_down": 1,
                            "seq_up": 2,
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = json.loads(
        (session / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["frame_count"] = 4
    manifest["artifacts"]["frames"] = [
        f"frames/{number:06d}.png" for number in (1, 2, 3, 4)
    ]
    manifest["artifacts"]["snapshots"] = ["snapshots/001_after.png"]
    (session / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return session


class SessionIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_index_reports_the_documented_fields(self) -> None:
        session = make_summary_session(
            self.root, display={"width": 390, "height": 450}
        )

        index = session_index(session)

        self.assertEqual(tuple(index), INDEX_FIELDS)
        self.assertEqual(index["schema"], "lvgl-ai-session-index-v1")
        self.assertEqual(index["session_id"], SESSION_NAME)
        self.assertEqual(index["session_dir"], str(session.resolve()))
        self.assertEqual(index["status"], "ok")
        self.assertEqual(index["display"], {"width": 390, "height": 450})
        self.assertEqual(index["frame_count"], 2)
        self.assertTrue(index["record_changed_only"])
        self.assertEqual(index["requested_app"], "coffee")
        self.assertEqual(index["effective_app"], "coffee")
        self.assertTrue(index["recorded"])
        self.assertIsNone(index["error"])

        snapshots = index["snapshots"]
        self.assertEqual(snapshots["count"], 1)
        self.assertEqual(snapshots["dir"], "snapshots")
        self.assertEqual(snapshots["items"][0]["label"], "after_click")
        self.assertEqual(snapshots["items"][0]["path"], SNAPSHOT)
        self.assertEqual(index["frames"]["last"], FRAME_2)
        self.assertEqual(index["diffs"]["rows"], 1)
        self.assertEqual(index["diffs"]["changed_rows"], 1)
        self.assertEqual(index["marks"][0]["id"], "start")
        self.assertEqual(index["inputs"]["hit_named"], 1)
        self.assertEqual(index["inputs"]["hit_empty"], 1)
        self.assertIn("[app] app=coffee", index["log_tail"])

        from_manifest = session_index(session / "manifest.json")
        self.assertEqual(from_manifest, index)

    def test_index_bounds_raw_files_and_next_reads(self) -> None:
        session = make_query_session(self.root)

        index = session_index(session)
        payload = json.dumps(
            index, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        self.assertLessEqual(len(payload), 6 * 1024)
        self.assertEqual(index["raw_files"]["timeline"]["rows"], 10)
        self.assertEqual(index["raw_files"]["frame_diffs"]["rows"], 2)
        self.assertIn("timeline", index["next_reads"][-1]["command"])

    def test_compact_index_is_bounded(self) -> None:
        session = make_query_session(self.root)

        compact = session_index(session, compact=True)
        payload = json.dumps(
            compact, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        self.assertLessEqual(len(payload), 2 * 1024)
        self.assertNotIn("items", compact["snapshots"])
        self.assertEqual(compact["clicks"], [])
        self.assertEqual(compact["marks"], [])
        self.assertNotIn("top", compact["diffs"])

    def test_recorded_session_missing_evidence_files_raises(self) -> None:
        for missing, name in (
            ("timeline.ndjson", "20260120-000000-aaaa"),
            ("frame_diffs.ndjson", "20260121-000000-bbbb"),
        ):
            with self.subTest(missing=missing):
                session = make_summary_session(self.root, name=name)
                (session / missing).unlink()
                with self.assertRaises(FileNotFoundError) as caught:
                    session_index(session)
                self.assertIn(missing, str(caught.exception))

    def test_record_false_session_has_empty_evidence(self) -> None:
        session = make_summary_session(
            self.root,
            with_timeline=False,
            with_frame_diffs=False,
            with_frames=False,
            with_snapshot=False,
            frame_count=0,
        )

        index = session_index(session)

        self.assertEqual(index["status"], "ok")
        self.assertFalse(index["recorded"])
        self.assertEqual(index["marks"], [])
        self.assertEqual(index["inputs"], {"hit_named": 0, "hit_empty": 0})
        self.assertEqual(index["diffs"]["rows"], 0)
        self.assertEqual(index["snapshots"]["count"], 0)
        self.assertEqual(index["frames"]["count"], 0)

    def test_crash_session_without_recording_files_keeps_its_error(self) -> None:
        error = {
            "code": "crash",
            "message": "engine exited with 3",
            "detail": {"exit_code": 3, "log_tail": ["boom"]},
        }
        session = make_summary_session(
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

        index = session_index(session)

        self.assertEqual(index["status"], "crash")
        self.assertFalse(index["recorded"])
        self.assertEqual(index["diffs"]["rows"], 0)
        self.assertEqual(index["error"], error)
        self.assertIsNone(index["effective_app"])

    def test_missing_manifest_or_engine_log_is_an_error(self) -> None:
        session = make_summary_session(self.root)
        missing_manifest = make_summary_session(
            self.root, name="20260103-000000-beef"
        )
        (missing_manifest / "manifest.json").unlink()
        missing_log = make_summary_session(
            self.root, name="20260104-000000-cafe"
        )
        (missing_log / "engine.log").unlink()

        for path in (session / "does-not-exist", missing_manifest, missing_log):
            with self.subTest(path=path.name):
                with self.assertRaises(FileNotFoundError):
                    session_index(path)

    def test_log_tail_is_capped_and_zero_returns_empty(self) -> None:
        log = "".join(f"line {index}\n" for index in range(10))
        session = make_summary_session(self.root, engine_log=log)

        index = session_index(session, log_tail_lines=3)

        self.assertEqual(index["log_tail"], ["line 7", "line 8", "line 9"])
        self.assertEqual(
            session_index(session, log_tail_lines=0)["log_tail"], []
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

    def test_json_prints_the_same_index_on_one_line(self) -> None:
        session = make_summary_session(
            self.root, display={"width": 390, "height": 450}
        )

        with mock.patch(
            "subprocess.Popen", side_effect=AssertionError("must not spawn")
        ):
            code, out, err = run_report([str(session), "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        payload = one_json(out)
        self.assertEqual(payload, json.loads(json.dumps(session_index(session))))
        self.assertEqual(payload["session_id"], SESSION_NAME)
        self.assertEqual(payload["schema"], "lvgl-ai-session-index-v1")

    def test_human_output_is_bounded_and_lists_evidence(self) -> None:
        session = make_query_session(self.root)

        code, out, err = run_report([str(session)])

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertLessEqual(len(out.splitlines()), 80)
        self.assertIn("status: ok", out)
        self.assertIn("display: 40x30", out)
        self.assertIn("frames: 4", out)
        self.assertIn("requested app: coffee", out)
        self.assertIn("effective app: coffee", out)
        self.assertIn("changed=2", out)
        self.assertIn("1:2", out)
        self.assertIn("after_click", out)
        self.assertIn("[app] app=coffee", out)
        lowered = out.lower()
        for word in ("pass", "fail", "baseline", "approval", "acceptance"):
            with self.subTest(word=word):
                self.assertNotIn(word, lowered)

    def test_default_and_latest_use_the_sessions_root_env(self) -> None:
        make_summary_session(self.root, name="20260101-000000-aaaa")
        make_summary_session(
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
        corrupt_manifest = make_summary_session(
            self.root, name="20260105-000000-d00d"
        )
        (corrupt_manifest / "manifest.json").write_text("{", encoding="utf-8")
        corrupt_timeline = make_summary_session(
            self.root, name="20260106-000000-feed"
        )
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
        session = make_summary_session(self.root)

        code, out, err = run_report([str(session), "--log-tail", "2"])

        self.assertEqual(code, 0, err)
        self.assertIn("[app] app=settings", out)
        self.assertIn("[app] app=coffee", out)
        self.assertNotIn("[app] apps=coffee,settings", out)

    def test_missing_effective_app_is_reported_as_unknown(self) -> None:
        session = make_summary_session(
            self.root, engine_log="[app] app_create\nhello\n"
        )

        json_code, json_out, _ = run_report([str(session), "--json"])
        human_code, human_out, _ = run_report([str(session)])

        self.assertEqual(json_code, 0)
        self.assertIsNone(one_json(json_out)["effective_app"])
        self.assertEqual(human_code, 0)
        self.assertIn("effective app: 未知", human_out)

    def test_full_is_not_an_entry_point(self) -> None:
        session = make_summary_session(self.root)

        code, out, err = run_report([str(session), "--json", "--full"])

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("unrecognized", err)


class QueryCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_query_session(self.root)

    def test_timeline_excludes_frame_rows_by_default(self) -> None:
        code, out, err = run_report(
            ["timeline", str(self.session), "--limit", "3", "--json"]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(payload["returned"], 3)
        self.assertGreater(payload["total"], 3)
        self.assertTrue(payload["truncated"])
        self.assertNotIn("frame", {row["type"] for row in payload["rows"]})

    def test_timeline_filters_by_type_and_time(self) -> None:
        code, out, err = run_report(
            [
                "timeline",
                str(self.session),
                "--type",
                "input",
                "--after-t",
                "20",
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual([row["seq"] for row in payload["rows"]], [2])

    def test_diffs_window_and_frame_filters(self) -> None:
        code, out, err = run_report(
            [
                "diffs",
                str(self.session),
                "--after-t",
                "40",
                "--before-t",
                "50",
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["rows"][0]["frame_no"], 4)
        self.assertTrue(Path(payload["rows"][0]["image"]).is_file())

    def test_frames_last_and_direction(self) -> None:
        code, out, err = run_report(
            ["frames", str(self.session), "--last", "2", "--json"]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(
            [row["frame_no"] for row in one_json(out)["rows"]], [3, 4]
        )

        code, out, err = run_report(
            [
                "frames",
                str(self.session),
                "--around-frame",
                "3",
                "--direction",
                "before",
                "--last",
                "2",
                "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(
            [row["frame_no"] for row in one_json(out)["rows"]], [1, 2]
        )

    def test_resolve_click_event_and_result(self) -> None:
        code, out, err = run_report(
            [
                "resolve",
                str(self.session),
                "--click",
                "1:2",
                "--at",
                "event",
                "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        event = one_json(out)
        self.assertEqual(event["frame_no"], 2)
        self.assertEqual(event["image_kind"], "frame")

        code, out, err = run_report(
            [
                "resolve",
                str(self.session),
                "--click",
                "1:2",
                "--at",
                "result",
                "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        result = one_json(out)
        self.assertEqual(result["frame_no"], 4)
        self.assertEqual(result["basis"], "click_2_after")
        self.assertEqual(result["candidates"], {"before": 2, "after": 4})

    def test_resolve_mark_prefers_a_snapshot_at_the_same_t_ms(self) -> None:
        code, out, err = run_report(
            ["resolve", str(self.session), "--mark", "after_click", "--json"]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(payload["image_kind"], "snapshot")
        self.assertEqual(payload["snapshot"], "after")
        self.assertEqual(payload["frame_no"], 2)

    def test_notes_and_resolve_note(self) -> None:
        code, out, err = run_report(
            [
                "notes",
                str(self.session),
                "--resolve",
                "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        note = one_json(out)["notes"][0]
        self.assertEqual(note["id"], "note-1")
        self.assertEqual(note["author"], "human")
        self.assertEqual(note["resolved"]["frame_no"], 4)

        code, out, err = run_report(
            [
                "resolve",
                str(self.session),
                "--note",
                "note-1",
                "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(one_json(out)["frame_no"], 4)

    def test_resolve_note_finds_it_in_a_sibling_session(self) -> None:
        new_session = make_query_session(
            self.root, name="20260103-000000-bbbb"
        )
        (new_session / "annotations.json").write_text(
            '{"schema": "lvgl-ai-annotations-v1", "notes": []}\n',
            encoding="utf-8",
        )

        code, out, err = run_report(
            [
                "resolve",
                str(new_session),
                "--note",
                "note-1",
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(one_json(out)["frame_no"], 4)

    def test_context_join_is_bounded(self) -> None:
        code, out, err = run_report(
            [
                "context",
                str(self.session),
                "--click",
                "1:2",
                "--window-ms",
                "200",
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertEqual(payload["schema"], "lvgl-ai-context-v1")
        self.assertLessEqual(len(out.encode("utf-8")), 5 * 1024)
        self.assertEqual(
            [row["seq"] for row in payload["inputs"]], [1, 2]
        )
        self.assertTrue(payload["diffs"])

    def test_query_help_lists_the_bound_commands(self) -> None:
        code, out, err = run_report(["--help"])

        self.assertEqual(code, 0, err)
        for command in (
            "timeline", "diffs", "frames", "notes", "resolve", "context",
            "feedback", "crop", "compare",
        ):
            with self.subTest(command=command):
                self.assertIn(command, out)


class VisualEvidenceCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_summary_session(self.root)
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

    def test_crop_accepts_a_session_relative_input(self) -> None:
        output = self.root / "crop.png"

        code, out, err = run_report(
            [
                "crop",
                FRAME_2,
                "--session",
                str(self.session),
                "--region",
                "0,0,1,1",
                "--out",
                str(output),
            ]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(read_png_rgb(output), (1, 1, [(0, 255, 0)]))

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

    def test_compare_two_sessions_uses_their_latest_snapshots(self) -> None:
        left_session = make_summary_session(
            self.root, name="20260107-000000-aaaa"
        )
        right_session = make_summary_session(
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

    def test_compare_sessions_fall_back_to_the_last_frame(self) -> None:
        left_session = make_summary_session(
            self.root, name="20260109-000000-cccc", with_snapshot=False
        )
        right_session = make_summary_session(
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
        session = make_summary_session(
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
        session = make_summary_session(
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
