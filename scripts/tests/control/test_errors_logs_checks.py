from __future__ import annotations

from scripts.tests import support

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from entrypoints import cli
from scripts.tests.fake_runtime import FakeRuntime
from control import (
    BuildError,
    EngineNotFound,
    LinkError,
    ProtocolError,
    Recording,
    Runtime,
    RuntimeCrash,
    ScenarioError,
)
from scenario import play_scenario
from control.build import build_failure, format_build_log, run_capture
from control.errors import (
    SESSION_STATUSES,
    dump_error,
    status_for_error,
)
from control.runtime import (
    DEFAULT_MAX_FRAMES,
    DEFAULT_MAX_LOG_BYTES,
)

FAKE_ENGINE = support.FAKE_ENGINE
BUTTON_CENTER = (112, 324)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_ndjson(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TypedErrorShapesTest(unittest.TestCase):
    def test_status_vocabulary_is_exactly_five_values(self) -> None:
        self.assertEqual(
            SESSION_STATUSES,
            {"ok", "build_error", "link_error", "crash", "harness_error"},
        )

    def test_status_for_error_maps_each_layer(self) -> None:
        cases = [
            (BuildError("compile failed"), "build_error"),
            (LinkError("undefined symbol"), "link_error"),
            (RuntimeCrash("died"), "crash"),
            (ProtocolError("bad line"), "harness_error"),
            (ScenarioError("bad step"), "harness_error"),
            (
                EngineNotFound(
                    "missing",
                    configure_command=["cmake", "-S", "engine"],
                    build_command=["cmake", "--build", "build"],
                ),
                "harness_error",
            ),
            (ValueError("other"), "harness_error"),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(status_for_error(error), expected)

    def test_dump_error_carries_each_layer_detail(self) -> None:
        build = BuildError(
            "build failed: app.c:7:3: expected ';'",
            diagnostics=[
                {
                    "file": "app.c",
                    "line": 7,
                    "column": 3,
                    "severity": "error",
                    "message": "expected ';'",
                }
            ],
        )
        dump = dump_error(build)
        self.assertEqual(dump["code"], "build_error")
        self.assertEqual(dump["detail"]["diagnostics"][0]["file"], "app.c")
        self.assertEqual(dump["detail"]["diagnostics"][0]["line"], 7)

        link = LinkError("link failed", unresolved_symbols=["missing_symbol"])
        dump = dump_error(link)
        self.assertEqual(dump["code"], "link_error")
        self.assertEqual(
            dump["detail"]["unresolved_symbols"], ["missing_symbol"]
        )

        crash = RuntimeCrash("died", exit_code=3, log_tail=["last line"])
        dump = dump_error(crash)
        self.assertEqual(dump["code"], "crash")
        self.assertEqual(dump["detail"]["log_tail"], ["last line"])

        protocol = ProtocolError("bad seq", raw='{"seq": 9}', seq=9)
        dump = dump_error(protocol)
        self.assertEqual(dump["code"], "protocol_error")
        self.assertEqual(dump["detail"]["raw"], '{"seq": 9}')
        self.assertEqual(dump["detail"]["seq"], 9)

        scenario = ScenarioError("step 2: bad", step=2)
        dump = dump_error(scenario)
        self.assertEqual(dump["code"], "scenario_error")
        self.assertEqual(dump["detail"]["step"], 2)

        missing = EngineNotFound(
            "missing/lvgl_engine",
            configure_command=["cmake", "-S", "engine"],
            build_command=["cmake", "--build", "build"],
        )
        dump = dump_error(missing)
        self.assertEqual(dump["code"], "engine_not_found")
        self.assertEqual(
            dump["detail"]["configure_command"], ["cmake", "-S", "engine"]
        )
        self.assertEqual(
            dump["detail"]["build_command"], ["cmake", "--build", "build"]
        )
        self.assertIn("missing/lvgl_engine", missing.engine_path)

    def test_engine_not_found_message_contains_both_commands(self) -> None:
        error = EngineNotFound(
            "missing/lvgl_engine",
            configure_command=["cmake", "-S", "engine", "-B", "build"],
            build_command=[
                "cmake",
                "--build",
                "build",
                "--target",
                "lvgl_engine",
            ],
        )
        self.assertEqual(
            error.configure_command, ["cmake", "-S", "engine", "-B", "build"]
        )
        self.assertEqual(
            error.build_command,
            ["cmake", "--build", "build", "--target", "lvgl_engine"],
        )
        self.assertIn("configure: cmake -S engine -B build", str(error))
        self.assertIn(
            "build: cmake --build build --target lvgl_engine", str(error)
        )


class GccDiagnosticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gcc = shutil.which("gcc")
        if self.gcc is None:
            self.skipTest("gcc is not available")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _build(self, source: Path) -> BuildError | LinkError:
        result = run_capture(
            [self.gcc, str(source), "-o", str(self.root / "app.exe")],
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.output)
        return build_failure(result, format_build_log(result, "build"))

    def test_build_error_contains_file_and_line(self) -> None:
        source = self.root / "broken.c"
        source.write_text(
            "void app_create(void) {\n    int x = ;\n}\n", encoding="utf-8"
        )
        error = self._build(source)
        self.assertIsInstance(error, BuildError)
        self.assertTrue(error.diagnostics, error.log_text)
        first = error.first_error
        self.assertTrue(first["file"].endswith("broken.c"), first)
        self.assertEqual(first["line"], 2)
        self.assertIn(first["severity"], ("fatal error", "error"))
        self.assertIn("broken.c:2", str(error))

    def test_link_error_contains_undefined_symbol(self) -> None:
        source = self.root / "missing_symbol.c"
        source.write_text(
            "extern int missing_symbol(void);\n"
            "int main(void) { return missing_symbol(); }\n",
            encoding="utf-8",
        )
        error = self._build(source)
        self.assertIsInstance(error, LinkError)
        self.assertIn("missing_symbol", error.unresolved_symbols)
        self.assertTrue(error.log_text)


class BuildFailureSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gcc = shutil.which("gcc")
        if self.gcc is None:
            self.skipTest("gcc is not available")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sessions_root = self.root / "user" / "sessions"
        self.source = self.root / "app.c"

    def _runtime(self) -> Runtime:
        return Runtime(
            lvgl="9.6",
            app="test_ui",
            build=True,
            record_changed_only=False,
            sessions_root=self.sessions_root,
            _build_command=[
                self.gcc,
                str(self.source),
                "-o",
                str(self.root / "app.exe"),
            ],
        )

    def _start_and_capture(self, error_type) -> tuple[Runtime, BaseException]:
        runtime = self._runtime()
        with mock.patch(
            "control.build_plan.cache_needs_configure",
            return_value=False,
        ):
            with self.assertRaises(error_type) as caught:
                runtime.start()
        self.addCleanup(runtime.stop)
        return runtime, caught.exception

    def _manifest(self, runtime: Runtime) -> dict:
        return read_json(runtime.session_dir / "manifest.json")

    def test_build_error_session_has_diagnostics_and_build_log(self) -> None:
        self.source.write_text(
            "void app_create(void) {\n    int x = ;\n}\n", encoding="utf-8"
        )
        runtime, error = self._start_and_capture(BuildError)

        self.assertFalse(runtime.is_running)
        self.assertTrue(runtime.session_dir.is_dir())
        self.assertTrue((runtime.session_dir / "build.log").is_file())
        self.assertTrue((runtime.session_dir / "engine.log").is_file())

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "build_error")
        self.assertEqual(manifest["build"]["status"], "error")
        self.assertEqual(manifest["frame_count"], 0)
        self.assertIs(manifest["truncated"], False)
        self.assertIs(manifest["log_truncated"], False)
        self.assertEqual(manifest["checks"], [])
        self.assertEqual(manifest["error"]["code"], "build_error")
        diagnostics = manifest["error"]["detail"]["diagnostics"]
        self.assertTrue(diagnostics)
        self.assertTrue(diagnostics[0]["file"].endswith("app.c"))
        self.assertEqual(diagnostics[0]["line"], 2)

        build_log = (runtime.session_dir / "build.log").read_text(
            encoding="utf-8"
        )
        self.assertIn("app.c:2", build_log)
        self.assertIn("error:", build_log)
        self.assertIn("# exit_code:", build_log)

        for relative in manifest["artifacts"].values():
            paths = relative if isinstance(relative, list) else [relative]
            for item in paths:
                self.assertTrue((runtime.session_dir / item).is_file(), item)
        self.assertNotIn("frames", manifest["artifacts"])
        self.assertEqual(
            Recording.open(runtime.session_dir).manifest["status"],
            "build_error",
        )

    def test_link_error_session_has_unresolved_symbols(self) -> None:
        self.source.write_text(
            "extern int missing_symbol(void);\n"
            "int main(void) { return missing_symbol(); }\n",
            encoding="utf-8",
        )
        runtime, error = self._start_and_capture(LinkError)

        self.assertTrue(runtime.session_dir.is_dir())
        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "link_error")
        self.assertEqual(manifest["build"]["status"], "error")
        self.assertEqual(manifest["error"]["code"], "link_error")
        self.assertIn(
            "missing_symbol",
            manifest["error"]["detail"]["unresolved_symbols"],
        )
        build_log = (runtime.session_dir / "build.log").read_text(
            encoding="utf-8"
        )
        self.assertIn("undefined reference", build_log.lower())


class EngineNotFoundSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sessions_root = self.root / "user" / "sessions"

    def test_missing_engine_still_writes_a_harness_session(self) -> None:
        missing = self.root / "missing-engine" / "lvgl_engine"
        runtime = Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
            _engine_path=missing,
        )
        with self.assertRaises(EngineNotFound) as caught:
            runtime.start()
        self.addCleanup(runtime.stop)
        error = caught.exception

        self.assertTrue(runtime.session_dir.is_dir())
        manifest = read_json(runtime.session_dir / "manifest.json")
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "engine_not_found")
        self.assertEqual(
            manifest["error"]["detail"]["configure_command"],
            error.configure_command,
        )
        self.assertEqual(
            manifest["error"]["detail"]["build_command"], error.build_command
        )
        self.assertIn("cmake", manifest["error"]["message"])
        self.assertTrue((runtime.session_dir / "build.log").is_file())
        self.assertTrue((runtime.session_dir / "engine.log").is_file())
        self.assertNotIn("frames", manifest["artifacts"])
        Recording.open(runtime.session_dir)


class FakeEngineErrorSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self, **kwargs) -> Runtime:
        return Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
            **kwargs,
        )

    @staticmethod
    def _manifest(runtime: Runtime) -> dict:
        return read_json(runtime.session_dir / "manifest.json")

    def test_malformed_ready_carries_raw_line_and_seq(self) -> None:
        runtime = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_READY": "malformed"}):
            with self.assertRaises(ProtocolError) as caught:
                runtime.start()
        self.addCleanup(runtime.stop)
        error = caught.exception

        self.assertIn('"ready": true', error.raw)
        self.assertEqual(error.seq, 0)
        self.assertIn("ready is missing", str(error))

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "protocol_error")
        self.assertEqual(manifest["error"]["detail"]["raw"], error.raw)
        self.assertEqual(manifest["error"]["detail"]["seq"], 0)

    def test_reply_seq_mismatch_is_typed_and_marks_harness_error(self) -> None:
        runtime = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_REPLY_SEQ_OFFSET": "1"}):
            runtime.start()
            with self.assertRaises(ProtocolError) as caught:
                runtime.tick(16)
            error = caught.exception
            self.assertEqual(error.seq, 2)
            self.assertIn('"ok": true', error.raw)
            self.assertIn("expected 1, got 2", str(error))
            runtime.stop()

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "protocol_error")
        self.assertEqual(manifest["error"]["detail"]["seq"], 2)
        self.assertEqual(manifest["checks"][0]["cmd"], "tick 16")
        self.assertIs(manifest["checks"][0]["ok"], False)
        self.assertIsNone(manifest["checks"][0]["frame_no"])

    def test_reply_missing_fields_is_a_protocol_error_in_the_manifest(
        self,
    ) -> None:
        runtime = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_MISSING_FIELDS": "1"}):
            runtime.start()
            with self.assertRaises(ProtocolError) as caught:
                runtime.pointer("down", 1, 2)
            self.assertIn("missing hit", str(caught.exception))
            runtime.stop()

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "protocol_error")
        self.assertEqual(manifest["checks"][0]["cmd"], "pointer down 1 2")
        self.assertIs(manifest["checks"][0]["ok"], True)

    def test_scenario_error_step_is_kept_in_the_manifest(self) -> None:
        runtime = self._runtime()
        runtime.start()
        with self.assertRaises(ScenarioError) as caught:
            runtime.input(
                [
                    {
                        "at_ms": 0,
                        "device": "pointer",
                        "action": "down",
                        "x": 1,
                        "y": 2,
                    },
                    {
                        "at_ms": 16,
                        "device": "key",
                        "action": "tap",
                        "key": "ENTER",
                    },
                ]
            )
        self.assertEqual(caught.exception.step, 1)
        runtime.stop()

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "scenario_error")
        self.assertEqual(manifest["error"]["detail"]["step"], 1)
        self.assertEqual(
            [check["cmd"] for check in manifest["checks"]], ["quit"]
        )

    def test_play_scenario_validation_failure_is_recorded_on_stop(
        self,
    ) -> None:
        runtime = self._runtime()
        runtime.start()
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(runtime, [{"type": "click_at", "x": 1}])
        self.assertEqual(caught.exception.step, 0)
        runtime.stop()

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "scenario_error")
        self.assertEqual(manifest["error"]["detail"]["step"], 0)

    def test_unknown_key_on_a_live_session_is_a_scenario_error(self) -> None:
        runtime = self._runtime()
        runtime.start()
        with self.assertRaises(ScenarioError) as caught:
            runtime.key("press", "NOT_A_KEY")
        self.assertIn("NOT_A_KEY", str(caught.exception))
        runtime.stop()
        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "scenario_error")

    def test_log_truncation_keeps_tail_and_sets_manifest_flag(self) -> None:
        runtime = self._runtime(max_log_bytes=600)
        with mock.patch.dict(
            os.environ,
            {"FAKE_LOG_LINES": "200", "FAKE_READY": "crash"},
        ):
            with self.assertRaises(RuntimeCrash) as caught:
                runtime.start()
        self.addCleanup(runtime.stop)
        error = caught.exception

        log_path = runtime.session_dir / "engine.log"
        self.assertLessEqual(log_path.stat().st_size, 600)
        last_line = "[fake_engine] crashing before ready"
        self.assertEqual(error.log_tail[-1], last_line)
        self.assertIn(last_line, "\n".join(error.log_tail))

        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "crash")
        self.assertIs(manifest["log_truncated"], True)
        self.assertEqual(manifest["error"]["code"], "crash")
        self.assertEqual(
            manifest["error"]["detail"]["log_tail"][-1], last_line
        )

        recording = Recording.open(runtime.session_dir)
        self.assertEqual(recording.log_tail(3)[-1], last_line)
        self.assertEqual(recording.manifest["log_truncated"], True)
        self.assertEqual(
            runtime.log_tail(3), recording.log().splitlines()[-3:]
        )

    def test_log_truncation_on_a_successful_session_keeps_running(
        self,
    ) -> None:
        runtime = self._runtime(max_log_bytes=600)
        with mock.patch.dict(os.environ, {"FAKE_LOG_LINES": "200"}):
            runtime.start()
            reply = runtime.tick(16)
            runtime.stop()

        self.assertEqual(reply["seq"], 1)
        manifest = self._manifest(runtime)
        self.assertEqual(manifest["status"], "ok")
        self.assertIs(manifest["log_truncated"], True)
        self.assertLessEqual(
            (runtime.session_dir / "engine.log").stat().st_size, 600
        )
        self.assertEqual(
            runtime.log_tail(1)[-1], "[fake_engine] log line 00199"
        )

    def test_runtime_crash_log_tail_contains_the_last_lines(self) -> None:
        runtime = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_READY": "crash"}):
            with self.assertRaises(RuntimeCrash) as caught:
                runtime.start()
        self.addCleanup(runtime.stop)
        error = caught.exception

        lines = (
            (runtime.session_dir / "engine.log")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(runtime.log_tail(2), lines[-2:])
        self.assertEqual(error.log_tail[-2:], lines[-2:])
        self.assertEqual(error.exit_code, 3)


class RecordFalseIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_record_false_writes_no_frames_timeline_or_diffs(self) -> None:
        runtime = Runtime(
            lvgl="9.6",
            app="test_ui",
            build=True,
            record=False,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(runtime.stop)
        runtime.start()
        self.assertEqual(runtime.ready["frames"], 0)
        self.assertNotIn("record", runtime.ready["capabilities"])

        runtime.tick(16)
        runtime.pointer("down", *BUTTON_CENTER)
        runtime.pointer("up", *BUTTON_CENTER)
        runtime.snapshot("no_record")
        runtime.stop()

        session = runtime.session_dir
        self.assertFalse((session / "frames").exists())
        self.assertFalse((session / "timeline.ndjson").exists())
        self.assertFalse((session / "frame_diffs.ndjson").exists())
        self.assertTrue(
            (session / "snapshots" / "001_no_record.png").is_file()
        )

        recording = Recording.open(session)
        manifest = recording.manifest
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["frame_count"], 0)
        self.assertIs(manifest["truncated"], False)
        self.assertIs(manifest["log_truncated"], False)
        self.assertEqual(recording.frames, [])
        self.assertEqual(
            manifest["artifacts"]["snapshots"], ["snapshots/001_no_record.png"]
        )
        self.assertEqual(
            set(manifest["artifacts"]),
            {"manifest", "build_log", "engine_log", "snapshots"},
        )
        for check in manifest["checks"]:
            self.assertEqual(set(check), {"cmd", "ok", "frame_no"})
            self.assertIs(check["ok"], True)
            self.assertEqual(check["frame_no"], 0)
        self.assertEqual(
            [check["cmd"] for check in manifest["checks"]],
            [
                "tick 16",
                "pointer down 112 324",
                "pointer up 112 324",
                "snapshot no_record",
                "quit",
            ],
        )
        with self.assertRaises(FileNotFoundError):
            recording.timeline()
        with self.assertRaises(FileNotFoundError):
            recording.frame_diffs()
        self.assertIn("[app]", recording.log())


class MaxFramesIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_default_values_are_600_frames_and_16_mb(self) -> None:
        runtime = Runtime(
            lvgl="9.6", build=False, sessions_root=self.sessions_root
        )
        self.assertEqual(runtime.max_frames, 600)
        self.assertEqual(runtime._store.max_log_bytes, 16 * 1024 * 1024)

        with mock.patch.dict(
            os.environ,
            {"LVGL_VERIFY_LOOP_MAX_FRAMES": "7", "LVGL_VERIFY_LOOP_MAX_LOG_BYTES": "12345"},
        ):
            configured = Runtime(
                lvgl="9.6", build=False, sessions_root=self.sessions_root
            )
        self.assertEqual(configured.max_frames, 7)
        self.assertEqual(configured._store.max_log_bytes, 12345)

        for kwargs in (
            {"max_frames": 0},
            {"max_frames": True},
            {"max_log_bytes": 0},
            {"max_log_bytes": -1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    Runtime(
                        lvgl="9.6",
                        build=False,
                        sessions_root=self.sessions_root,
                        **kwargs,
                    )
        with mock.patch.dict(os.environ, {"LVGL_VERIFY_LOOP_MAX_FRAMES": "nope"}):
            with self.assertRaises(ValueError):
                Runtime(
                    lvgl="9.6", build=False, sessions_root=self.sessions_root
                )

    def test_engine_reports_the_default_600_frame_cap(self) -> None:
        runtime = Runtime(
            lvgl="9.6",
            app="test_ui",
            build=True,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(runtime.stop)
        runtime.start()
        self.assertEqual(runtime.ready["max_frames"], DEFAULT_MAX_FRAMES)
        self.assertEqual(DEFAULT_MAX_FRAMES, 600)
        self.assertEqual(DEFAULT_MAX_LOG_BYTES, 16 * 1024 * 1024)
        self.assertIs(runtime.ready["truncated"], False)
        runtime.stop()

    def test_cap_stops_frames_but_time_and_commands_keep_working(self) -> None:
        runtime = Runtime(
            lvgl="9.6",
            app="test_ui",
            build=True,
            record_changed_only=False,
            sessions_root=self.sessions_root,
            max_frames=3,
        )
        self.addCleanup(runtime.stop)
        runtime.start()
        self.assertEqual(runtime.ready["frames"], 1)
        self.assertEqual(runtime.ready["max_frames"], 3)

        self.assertEqual(runtime.tick(16)["frames"], 2)
        second = runtime.tick(16)
        self.assertEqual(second["frames"], 3)
        self.assertIs(second["truncated"], False)
        overflow = runtime.tick(16)
        self.assertEqual(overflow["frames"], 3)
        self.assertIs(overflow["truncated"], True)
        self.assertEqual(overflow["t_ms"], 48)

        waited = runtime.wait(frames=2)
        self.assertEqual(waited["frames"], 3)
        self.assertIs(waited["truncated"], True)
        self.assertEqual(waited["t_ms"], 80)

        pointer = runtime.pointer("down", *BUTTON_CENTER)
        self.assertEqual(pointer["frames"], 3)
        self.assertEqual(pointer["hit"], "test_ui_button")
        runtime.mark("after_cap")
        snapshot = runtime.snapshot("after_cap")
        self.assertTrue((runtime.session_dir / snapshot["file"]).is_file())
        runtime.stop()

        session = runtime.session_dir
        self.assertEqual(len(list((session / "frames").glob("*.png"))), 3)
        diff_rows = read_ndjson(session / "frame_diffs.ndjson")
        self.assertEqual([row["frame_no"] for row in diff_rows], [2, 3])
        timeline = Recording.open(session).timeline()
        self.assertEqual(
            [row["frame_no"] for row in timeline if row["type"] == "frame"],
            [1, 2, 3],
        )
        wait_rows = [row for row in timeline if row["type"] == "wait"]
        self.assertEqual(
            [(row["frame_start"], row["frame_end"]) for row in wait_rows],
            [(3, 3)],
        )
        input_rows = [row for row in timeline if row["type"] == "input"]
        self.assertEqual(input_rows[0]["frame_no"], 3)
        end = timeline[-1]
        self.assertEqual(end["type"], "end")
        self.assertEqual(end["frame_count"], 3)
        self.assertEqual(end["t_ms"], 80)
        self.assertIs(end["truncated"], True)

        manifest = Recording.open(session).manifest
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["frame_count"], 3)
        self.assertIs(manifest["truncated"], True)
        self.assertEqual(len(manifest["artifacts"]["frames"]), 3)
        self.assertEqual(manifest["checks"][2]["cmd"], "tick 16")
        self.assertEqual(manifest["checks"][2]["frame_no"], 3)


class ChecksIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_checks_record_execution_only(self) -> None:
        runtime = Runtime(
            lvgl="9.6",
            build=True,
            record_changed_only=False,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(runtime.stop)
        runtime.start()
        runtime.tick(16)
        runtime.pointer("down", *BUTTON_CENTER)
        runtime.wait(ms=16)
        runtime.mark("m")
        runtime.snapshot("s")
        runtime.stop()

        checks = Recording.open(runtime.session_dir).manifest["checks"]
        self.assertEqual(
            checks,
            [
                {"cmd": "tick 16", "ok": True, "frame_no": 2},
                {"cmd": "pointer down 112 324", "ok": True, "frame_no": 2},
                {"cmd": "wait 16", "ok": True, "frame_no": 3},
                {"cmd": "mark m", "ok": True, "frame_no": 3},
                {"cmd": "snapshot s", "ok": True, "frame_no": 3},
                {"cmd": "quit", "ok": True, "frame_no": 3},
            ],
        )
        for check in checks:
            self.assertEqual(set(check), {"cmd", "ok", "frame_no"})


class CliHarnessErrorRecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_cli_tells_runtime_about_a_play_time_scenario_error(self) -> None:
        scenario = self.root / "scenario.json"
        scenario.write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-scenario-v1",
                    "steps": [{"type": "click_at", "x": 1, "y": 2}],
                }
            ),
            encoding="utf-8",
        )
        error = ScenarioError("step 0: bad", step=0)
        fake = FakeRuntime(errors={"pointer": error})
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(cli, "Runtime", return_value=fake),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(["--scenario", str(scenario), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(fake.recorded_errors, [error])


if __name__ == "__main__":
    unittest.main(verbosity=2)
