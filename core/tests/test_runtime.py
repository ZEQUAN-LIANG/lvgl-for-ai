"""Scaffold and minimal runtime lifecycle.

Integration tests use the real engine and a temporary session root. The only
unit-level test avoids the engine by pointing Runtime at a missing binary.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lvgl_ai import EngineNotFound, ProtocolError, Runtime, RuntimeCrash
from support import distinct_rgb, read_png_rgb

SESSION_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
FAKE_ENGINE = Path(__file__).with_name("fake_engine.py")


class RuntimeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_start_writes_ready_session_manifest_logs_and_first_frame(self) -> None:
        rt = Runtime(lvgl="9.6", build=True, sessions_root=self.sessions_root)
        self.addCleanup(rt.stop)
        rt.start()

        self.assertTrue(rt.is_running)
        ready = rt.ready
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["seq"], 0)
        self.assertEqual(ready["protocol"], "lvgl-ai-engine-v1")
        self.assertEqual(ready["lvgl"], "9.6.0")
        self.assertEqual(Path(ready["lvgl_src"]), rt.lvgl_src)
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
        self.assertEqual(manifest["schema"], "lvgl-ai-session-v1")
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
        self.assertGreaterEqual(len(colors), 2, "frame must not be a solid color")

        log_text = engine_log.read_text(encoding="utf-8")
        self.assertIn("[app] app_create", log_text)
        self.assertIn("[app] panel_create", log_text)
        self.assertIn("[demo_asset]", log_text)

        rt.stop()
        self.assertFalse(rt.is_running)
        final_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(final_manifest["status"], "ok")
        self.assertGreaterEqual(final_manifest["frame_count"], 1)

    def test_app_is_forwarded_as_demo_and_recorded_in_the_manifest(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            app="xiaohongshu",
            build=True,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(rt.stop)
        rt.start()

        log_text = (rt.session_dir / "engine.log").read_text(encoding="utf-8")
        self.assertIn("[app] apps=coffee,xiaohongshu,spectrum", log_text)
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
        self.assertTrue(rt.record)
        self.assertEqual(rt.mode, "headless")
        rt.stop()  # stop before start is a no-op

        with rt as active:
            self.assertIs(active, rt)
            self.assertTrue(rt.is_running)
            session_id = rt.session_id
            rt.start()  # second start must not spawn a second session
            self.assertEqual(rt.session_id, session_id)
            self.assertTrue(rt.is_running)

        self.assertFalse(rt.is_running)
        rt.stop()  # second stop is a no-op
        with self.assertRaises(RuntimeError):
            rt.start()  # one Runtime instance owns exactly one session

    def test_sessions_root_env_override(self) -> None:
        env_root = Path(self._tmp.name) / "env-sessions"
        with mock.patch.dict(os.environ, {"LVGL_AI_SESSIONS_ROOT": str(env_root)}):
            rt = Runtime(lvgl="9.6", build=True)
            self.addCleanup(rt.stop)
            rt.start()
            self.assertEqual(rt.session_dir.parent, env_root.resolve())
            self.assertEqual(rt.session_dir.parent, rt.sessions_root)
            self.assertTrue(rt.session_dir.is_dir())
            rt.stop()

    def test_engine_missing_raises_engine_not_found_with_commands(self) -> None:
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


class RuntimeProcessSeamTest(unittest.TestCase):
    """Unit tests with a fake engine process; no LVGL build is involved."""

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

    def test_fake_engine_ready_and_quit(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        self.assertTrue(rt.is_running)
        self.assertEqual(rt.ready["seq"], 0)
        self.assertEqual(rt.ready["protocol"], "lvgl-ai-engine-v1")
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
            "[fake_engine] crashing before ready", "\n".join(caught.exception.log_tail)
        )
        manifest = json.loads(
            (rt.session_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "crash")
        self.assertEqual(manifest["error"]["code"], "crash")
        rt.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
