from __future__ import annotations

from scripts.tests import support

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control import (
    EngineNotFound,
    ProtocolError,
    Recording,
    Runtime,
    RuntimeCrash,
    ScenarioError,
)
from control.engine_link import EngineLink
from scripts.tests.support import distinct_rgb, read_png_rgb

SESSION_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
FAKE_ENGINE = support.FAKE_ENGINE


class RuntimeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_start_writes_ready_session_manifest_logs_and_first_frame(
        self,
    ) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="test_ui",
            build=True,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(rt.stop)
        rt.start()

        self.assertTrue(rt.is_running)
        ready = rt.ready
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["seq"], 0)
        self.assertEqual(ready["protocol"], "lvgl-verify-loop-engine-v1")
        self.assertEqual(ready["lvgl"], "9.6.0")
        self.assertEqual(Path(ready["lvgl_src"]), rt._store.lvgl_src)
        self.assertEqual(ready["display"]["width"], 800)
        self.assertEqual(ready["display"]["height"], 600)
        self.assertEqual(ready["mode"], "headless")
        self.assertEqual(ready["inputs"], ["real", "virtual"])
        self.assertEqual(
            ready["capabilities"],
            [
                "pointer",
                "key",
                "encoder",
                "tick",
                "wait",
                "snapshot",
                "mark",
                "record",
            ],
        )
        self.assertGreaterEqual(ready["frames"], 1)

        self.assertRegex(rt.session_id, SESSION_ID_RE)
        self.assertEqual(rt.session_dir, self.sessions_root / rt.session_id)
        self.assertTrue(rt.session_dir.is_dir())

        manifest_path = rt.session_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "lvgl-verify-loop-session-v1")
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["id"], rt.session_id)

        self.assertTrue((rt.session_dir / "build.log").is_file())
        engine_log = rt.session_dir / "engine.log"
        self.assertTrue(engine_log.is_file())

        frame_path = rt.session_dir / "frames" / "000001.png"
        self.assertTrue(frame_path.is_file())
        width, height, _ = read_png_rgb(frame_path)
        self.assertEqual((width, height), (800, 600))
        colors = distinct_rgb(frame_path)
        self.assertGreaterEqual(
            len(colors), 2, "frame must not be a solid color"
        )

        log_text = engine_log.read_text(encoding="utf-8")
        self.assertIn("[app] app_create", log_text)
        self.assertIn("[app] app=test_ui", log_text)
        self.assertIn("[app] panel_create", log_text)

        rt.stop()
        self.assertFalse(rt.is_running)
        final_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(final_manifest["status"], "ok")
        self.assertGreaterEqual(final_manifest["frame_count"], 1)

    def test_custom_display_size_drives_frames_and_manifest(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            build=True,
            width=640,
            height=480,
            record_changed_only=False,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(rt.stop)
        rt.start()
        rt.tick(16)

        self.assertEqual(
            (
                rt.ready["display"]["width"],
                rt.ready["display"]["height"],
            ),
            (640, 480),
        )
        frame_path = rt.session_dir / "frames" / "000001.png"
        width, height, _ = read_png_rgb(frame_path)
        self.assertEqual((width, height), (640, 480))
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["display"], {"width": 640, "height": 480})
        diff_rows = [
            json.loads(line)
            for line in (rt.session_dir / "frame_diffs.ndjson")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertTrue(diff_rows)
        self.assertEqual(
            (diff_rows[0]["width"], diff_rows[0]["height"]), (640, 480)
        )

    def test_app_is_forwarded_as_demo_and_recorded_in_the_manifest(
        self,
    ) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="xiaohongshu",
            build=True,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(rt.stop)
        rt.start()

        log_text = (rt.session_dir / "engine.log").read_text(encoding="utf-8")
        app_line = next(
            line
            for line in log_text.splitlines()
            if line.startswith("[app] apps=")
        )
        names = app_line.removeprefix("[app] apps=").split(",")
        for name in ("coffee", "xiaohongshu", "spectrum"):
            self.assertIn(name, names)
        self.assertIn("[app] app=xiaohongshu", log_text)
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["app"], "xiaohongshu")

    def test_invalid_app_is_rejected_before_spawn(self) -> None:
        with self.assertRaises(ValueError):
            Runtime(lvgl="9.6", app="bad app")

    def test_context_manager_start_stop_are_idempotent(self) -> None:
        rt = Runtime(lvgl="9.6", build=True, sessions_root=self.sessions_root)
        self.assertFalse(rt.is_running)
        self.assertTrue(rt._store.record)
        self.assertEqual(rt.mode, "headless")
        rt.stop()

        with rt as active:
            self.assertIs(active, rt)
            self.assertTrue(rt.is_running)
            session_id = rt.session_id
            rt.start()
            self.assertEqual(rt.session_id, session_id)
            self.assertTrue(rt.is_running)

        self.assertFalse(rt.is_running)
        rt.stop()
        with self.assertRaises(RuntimeError):
            rt.start()

    def test_sessions_root_env_override(self) -> None:
        env_root = Path(self._tmp.name) / "env-sessions"
        with mock.patch.dict(
            os.environ, {"LVGL_VERIFY_LOOP_SESSIONS_ROOT": str(env_root)}
        ):
            rt = Runtime(lvgl="9.6", build=True)
            self.addCleanup(rt.stop)
            rt.start()
            self.assertEqual(rt.session_dir.parent, env_root.resolve())
            self.assertEqual(rt.session_dir.parent, rt._store.sessions_root)
            self.assertTrue(rt.session_dir.is_dir())
            rt.stop()

    def test_engine_missing_raises_engine_not_found_with_commands(
        self,
    ) -> None:
        missing = Path(self._tmp.name) / "missing-engine" / "lvgl_engine"
        rt = Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
            _engine_path=missing,
        )
        with self.assertRaises(EngineNotFound) as caught:
            rt.start()

        error = caught.exception
        self.assertFalse(rt.is_running)
        self.assertTrue(error.configure_command)
        self.assertTrue(error.build_command)
        message = str(error)
        self.assertIn("cmake", message.lower())
        self.assertIn("--build", message)
        self.assertIn(str(missing), message)


class RuntimeSessionOptionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_session_options_are_stored_once(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="coffee",
            build=False,
            record=False,
            live_frame=True,
            record_changed_only=True,
            sessions_root=self.sessions_root,
            max_log_bytes=12345,
            session_retention=None,
        )
        self.addCleanup(rt.stop)
        store = rt._store

        self.assertEqual(store.app, "coffee")
        self.assertIs(store.build, False)
        self.assertIs(store.record, False)
        self.assertIs(store.live_frame, True)
        self.assertIs(store.record_changed_only, True)
        self.assertEqual(store.mode, "headless")
        self.assertEqual(store.sessions_root, self.sessions_root.resolve())
        self.assertEqual(store.max_log_bytes, 12345)
        self.assertIsNone(store.retention)
        self.assertIsInstance(store.lvgl_src, Path)

    def test_runtime_like_readouts_are_read_only(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="coffee",
            build=False,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(rt.stop)

        self.assertEqual(rt.app, "coffee")
        self.assertEqual(rt.mode, "headless")
        self.assertIsNone(rt.ready)
        for name in ("app", "mode", "ready"):
            with self.subTest(option=name):
                with self.assertRaises(AttributeError):
                    setattr(rt, name, "overridden")


class RuntimeSessionSurfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_pure_store_options_are_not_re_exposed(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="coffee",
            build=False,
            record=False,
            live_frame=True,
            record_changed_only=True,
            sessions_root=self.sessions_root,
            max_log_bytes=12345,
            session_retention=None,
        )
        self.addCleanup(rt.stop)

        for name in (
            "build",
            "record",
            "live_frame",
            "record_changed_only",
            "lvgl_src",
            "sessions_root",
            "max_log_bytes",
            "session_retention",
        ):
            with self.subTest(option=name):
                self.assertFalse(hasattr(rt, name))

        self.assertEqual(rt._store.app, "coffee")
        self.assertIs(rt._store.build, False)
        self.assertIs(rt._store.record, False)
        self.assertIs(rt._store.live_frame, True)
        self.assertIs(rt._store.record_changed_only, True)
        self.assertEqual(rt._store.max_log_bytes, 12345)
        self.assertIsNone(rt._store.retention)
        self.assertIsInstance(rt._store.lvgl_src, Path)
        self.assertEqual(rt._store.sessions_root, self.sessions_root.resolve())

    def test_runtime_like_readouts_survive(self) -> None:
        rt = Runtime(lvgl="9.6", build=False, sessions_root=self.sessions_root)
        self.addCleanup(rt.stop)

        self.assertIsNone(rt.app)
        self.assertEqual(rt.mode, "headless")
        self.assertIsNone(rt.ready)

    def test_store_retention_has_one_public_name(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
            session_retention=None,
        )
        self.addCleanup(rt.stop)

        self.assertIsNone(rt._store.retention)
        self.assertFalse(hasattr(rt._store, "session_retention"))


class RuntimeProcessSeamTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self) -> Runtime:
        return Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )

    def test_display_dimensions_are_forwarded_and_reported(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            build=False,
            width=640,
            height=480,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )
        self.addCleanup(rt.stop)
        rt.start()

        self.assertEqual(rt.width, 640)
        self.assertEqual(rt.height, 480)
        self.assertEqual(
            (
                rt.ready["display"]["width"],
                rt.ready["display"]["height"],
            ),
            (640, 480),
        )
        rt.stop()

    def test_width_and_height_must_be_given_together(self) -> None:
        with self.assertRaises(ValueError) as missing_height:
            Runtime(lvgl="9.6", width=640)
        self.assertIn("together", str(missing_height.exception))
        with self.assertRaises(ValueError) as missing_width:
            Runtime(lvgl="9.6", height=480)
        self.assertIn("together", str(missing_width.exception))

    def test_invalid_display_dimensions_are_rejected(self) -> None:
        cases = [
            {"width": 0, "height": 480},
            {"width": 640, "height": -1},
            {"width": True, "height": 480},
            {"width": 640, "height": 1.5},
            {"width": "640", "height": 480},
            {"width": 4097, "height": 480},
        ]
        for case in cases:
            with self.subTest(**case):
                with self.assertRaises(ValueError):
                    Runtime(lvgl="9.6", **case)
        for dimensions in ((1, 1), (4096, 4096)):
            with self.subTest(dimensions=dimensions):
                rt = Runtime(
                    lvgl="9.6", width=dimensions[0], height=dimensions[1]
                )
                self.assertEqual((rt.width, rt.height), dimensions)

    def test_fake_engine_ready_and_quit(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        self.assertTrue(rt.is_running)
        self.assertEqual(rt.ready["seq"], 0)
        self.assertEqual(rt.ready["protocol"], "lvgl-verify-loop-engine-v1")
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["input"], ["real", "virtual"])
        self.assertIsNone(manifest["error"])
        self.assertIn(
            "build skipped",
            (rt.session_dir / "build.log").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "[fake_engine] started",
            (rt.session_dir / "engine.log").read_text(encoding="utf-8"),
        )

        rt.stop()
        self.assertFalse(rt.is_running)
        final = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(final["status"], "ok")

    def test_malformed_ready_is_protocol_error(self) -> None:
        rt = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_READY": "malformed"}):
            with self.assertRaises(ProtocolError):
                rt.start()

        self.assertFalse(rt.is_running)
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "protocol_error")
        rt.stop()

    def test_crash_before_ready_is_runtime_crash(self) -> None:
        rt = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_READY": "crash"}):
            with self.assertRaises(RuntimeCrash) as caught:
                rt.start()

        self.assertIn(
            "[fake_engine] crashing before ready",
            "\n".join(caught.exception.log_tail),
        )
        self.assertIn(
            "engine closed stdout before announcing ready",
            str(caught.exception),
        )
        self.assertNotIn(
            "engine 产物早于当前 Runtime，请用 --build 重建",
            str(caught.exception),
        )
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "crash")
        self.assertEqual(manifest["error"]["code"], "crash")
        rt.stop()

    def test_window_fallback_writes_the_ready_mode_back_to_the_store(
        self,
    ) -> None:
        rt = Runtime(
            lvgl="9.6",
            build=False,
            window=True,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )
        self.addCleanup(rt.stop)
        rt.start()

        self.assertEqual(rt.ready["mode"], "headless")
        self.assertEqual(rt.mode, "headless")
        self.assertEqual(rt._store.mode, "headless")
        self.assertIs(rt.window, False)
        self.assertIs(rt.headless, True)
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["mode"], "headless")

    def test_reserved_frames_are_not_the_manifest_frame_count(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        rt.tick(16)
        rt.tick(16)
        reserved = rt.frame_count
        self.assertEqual(reserved, 3)

        rt.stop()

        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.frames, [])
        self.assertEqual(
            recording.manifest["frame_count"], len(recording.frames)
        )
        self.assertEqual(recording.manifest["frame_count"], 0)
        self.assertEqual(rt.frame_count, reserved)

    def test_live_only_session_counts_no_recorded_frames(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="coffee",
            build=False,
            record=False,
            live_frame=True,
            record_changed_only=True,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )
        self.addCleanup(rt.stop)
        rt.start()
        rt.tick(16)
        reserved = rt.frame_count
        self.assertGreaterEqual(reserved, 2)

        rt.stop()

        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.frames, [])
        self.assertEqual(recording.manifest["frame_count"], 0)
        self.assertIs(recording.manifest["record_changed_only"], True)
        self.assertEqual(recording.manifest["app"], "coffee")

    def test_stale_engine_unknown_argument_crash_is_actionable(self) -> None:
        rt = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_UNKNOWN_ARG": "1"}):
            with self.assertRaises(RuntimeCrash) as caught:
                rt.start()

        error = caught.exception
        message = str(error)
        self.assertIn(
            "engine 产物早于当前 Runtime，请用 --build 重建", message
        )
        self.assertIn("--record-changed-only", message)
        self.assertEqual(error.exit_code, 2)
        self.assertTrue(
            any("unknown argument" in line for line in error.log_tail)
        )
        self.assertIsNotNone(error.log_path)
        self.assertTrue(Path(error.log_path).is_file())

        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "crash")
        self.assertEqual(manifest["error"]["code"], "crash")
        self.assertIn(
            "engine 产物早于当前 Runtime，请用 --build 重建",
            manifest["error"]["message"],
        )
        self.assertEqual(manifest["error"]["detail"]["exit_code"], 2)
        self.assertTrue(
            any(
                "unknown argument" in line
                for line in manifest["error"]["detail"]["log_tail"]
            )
        )
        rt.stop()

    def test_stop_writes_a_crash_manifest_when_shutdown_raises(self) -> None:
        rt = self._runtime()
        rt.start()
        link = rt._link
        self.assertIsNotNone(link)

        def boom(*args: object, **kwargs: object) -> int | None:
            proc = link._proc
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
            raise RuntimeCrash("shutdown boom")

        with mock.patch.object(EngineLink, "shutdown", side_effect=boom):
            with self.assertRaises(RuntimeCrash):
                rt.stop()

        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "crash")
        self.assertEqual(manifest["error"]["code"], "crash")
        self.assertIn(
            "engine did not exit cleanly", manifest["error"]["message"]
        )
        self.assertIn("shutdown boom", manifest["error"]["message"])
        self.addCleanup(rt.stop)

    def test_shutdown_failure_does_not_replace_an_existing_failure(
        self,
    ) -> None:
        rt = self._runtime()
        rt.start()
        link = rt._link
        self.assertIsNotNone(link)
        rt.record_error(ScenarioError("scenario boom"))

        def boom(*args: object, **kwargs: object) -> int | None:
            proc = link._proc
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
            raise RuntimeCrash("shutdown boom")

        with mock.patch.object(EngineLink, "shutdown", side_effect=boom):
            with self.assertRaises(RuntimeCrash):
                rt.stop()

        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "harness_error")
        self.assertEqual(manifest["error"]["code"], "scenario_error")
        self.assertIn("scenario boom", manifest["error"]["message"])
        self.addCleanup(rt.stop)


if __name__ == "__main__":
    unittest.main(verbosity=2)
