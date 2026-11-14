"""Live session state machine: Runtime delegation and stream ownership.

Split from ``test_web_live.py`` so the HTTP adapter tests stay readable.
"""


from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fake_runtime import FAKE_PID, FakeRuntime
from lvgl_ai import BuildError, Recording, Runtime, RuntimeCrash, ScenarioError
from lvgl_ai.web.live_session import LiveError, LiveSession
from lvgl_ai.web.wire import page_config
from support import symlinked_file
from web_support import SESSION_ID, WebHarness, make_web_session

SIGINT_DRIVER = Path(__file__).with_name("web_sigint_driver.py")
APP_C = Path(__file__).resolve().parent.parent.parent / "user" / "app" / "app.c"


class SessionFakeRuntime(FakeRuntime):
    """FakeRuntime that points at a real fixture session directory."""

    def __init__(self, session_dir: str | Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_path = Path(session_dir)

    def start(self) -> SessionFakeRuntime:
        super().start()
        self.session_id = self._session_path.name
        self.session_dir = self._session_path
        self.manifest_path = self._session_path / "manifest.json"
        self.engine_log_path = self._session_path / "engine.log"
        return self


class Factory:
    """Build a fresh runtime per live start, recording every instance."""

    def __init__(self, builder) -> None:
        self.builder = builder
        self.instances = []
        self.calls = 0

    def __call__(self):
        runtime = self.builder(self.calls)
        self.calls += 1
        self.instances.append(runtime)
        return runtime


class BlockingRuntime(SessionFakeRuntime):
    """Pause inside start/stop so the state machine is observable."""

    def __init__(self, session_dir: str | Path) -> None:
        super().__init__(session_dir)
        self.start_entered = threading.Event()
        self.start_release = threading.Event()
        self.stop_entered = threading.Event()
        self.stop_release = threading.Event()

    def start(self) -> BlockingRuntime:
        self.start_entered.set()
        if not self.start_release.wait(5.0):
            raise AssertionError("test did not release start")
        return super().start()

    def stop(self) -> None:
        self.stop_entered.set()
        if not self.stop_release.wait(5.0):
            raise AssertionError("test did not release stop")
        super().stop()


class StreamRuntime(FakeRuntime):
    """Writes one raw preview frame at startup."""

    def __init__(self, session_dir: str | Path) -> None:
        super().__init__(record=False)
        self._session = Path(session_dir)
        self.ready = {"display": {"width": 2, "height": 1}}
        self.frame_count = 1
        self.t_ms = 0

    def start(self) -> StreamRuntime:
        super().start()
        self.session_id = self._session.name
        self.session_dir = self._session
        self._session.mkdir(parents=True, exist_ok=True)
        (self._session / "live.rgba").write_bytes(bytes([10, 20, 30, 255]) * 2)
        return self


class LiveSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root)

    def _session(self, factory) -> LiveSession:
        session = LiveSession(
            self.root / "sessions", runtime_factory=factory
        )
        self.addCleanup(_quiet_stop_session, session)
        return session

    def test_state_transitions_are_observable(self) -> None:
        runtime = BlockingRuntime(self.session)
        session = self._session(lambda: runtime)
        self.assertEqual(session.state, "idle")
        self.assertFalse(session.is_starting())
        self.assertFalse(session.is_active())

        errors: list[BaseException] = []

        def do_start() -> None:
            try:
                session.start("record", "coffee")
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        starter = threading.Thread(target=do_start, name="test-live-start")
        starter.start()
        self.assertTrue(runtime.start_entered.wait(2.0))
        self.assertEqual(session.state, "starting")
        self.assertTrue(session.is_starting())
        runtime.start_release.set()
        starter.join(5.0)
        self.assertFalse(starter.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(session.state, "running")
        self.assertTrue(session.is_active())

        status = session.status()
        self.assertTrue(status["running"])
        self.assertFalse(status["starting"])
        self.assertEqual(status["session_id"], SESSION_ID)
        self.assertEqual(status["frame_count"], 3)
        self.assertEqual(status["status"], "ok")

        def do_stop() -> None:
            try:
                session.stop()
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        stopper = threading.Thread(target=do_stop, name="test-live-stop")
        stopper.start()
        self.assertTrue(runtime.stop_entered.wait(2.0))
        self.assertEqual(session.state, "stopping")
        runtime.stop_release.set()
        stopper.join(5.0)
        self.assertFalse(stopper.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(session.state, "idle")
        self.assertFalse(session.is_active())
        stopped = session.status()
        self.assertFalse(stopped["running"])
        # A recording keeps its finished session visible for replay.
        self.assertEqual(stopped["session_id"], SESSION_ID)

    def test_start_failure_after_engine_start_keeps_the_session_active(self) -> None:
        runtime = FakeRuntime()

        class TickerFailingSession(LiveSession):
            def _start_ticker_locked(self) -> None:
                raise RuntimeError("ticker boom")

        session = TickerFailingSession(
            self.root / "sessions", runtime_factory=lambda: runtime
        )
        self.addCleanup(_quiet_stop_session, session)
        with self.assertRaises(LiveError) as raised:
            session.start("record", "coffee")
        self.assertEqual(raised.exception.code, "live_start_error")
        self.assertTrue(raised.exception.detail["live"]["running"])
        self.assertEqual(session.state, "idle")
        # The engine is still running, so a retry (and app mutation) must still
        # be refused, exactly like the old bridge-based check.
        self.assertTrue(session.is_active())
        with self.assertRaises(LiveError) as conflict:
            session.start("record", "coffee")
        self.assertEqual(conflict.exception.code, "live_running")

    def test_second_start_keeps_the_running_ticker(self) -> None:
        runtime = FakeRuntime()
        session = self._session(lambda: runtime)
        session.start("record")

        ticker = session._ticker
        self.assertIsNotNone(ticker)
        self.assertTrue(ticker.is_alive())

        before = runtime.t_ms
        with self.assertRaises(LiveError) as raised:
            session.start("record")
        self.assertEqual(raised.exception.code, "live_running")

        self.assertIs(session._ticker, ticker)
        self.assertTrue(ticker.is_alive())
        deadline = time.monotonic() + 2.0
        while runtime.t_ms == before and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreater(runtime.t_ms, before)

    def test_concurrent_start_has_one_winner(self) -> None:
        runtime = FakeRuntime()
        session = self._session(lambda: runtime)
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            try:
                session.start("record")
                result = "started"
            except LiveError as exc:
                result = exc.code
            with outcomes_lock:
                outcomes.append(result)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5.0)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sorted(outcomes), ["live_running", "started"])
        self.assertIsNotNone(session._ticker)
        self.assertTrue(session._ticker.is_alive())

    def test_selected_app_does_not_wait_for_a_ticker_tick(self) -> None:
        class SlowTickRuntime(FakeRuntime):
            def __init__(self) -> None:
                super().__init__()
                self.tick_entered = threading.Event()
                self.tick_release = threading.Event()

            def tick(self, ms, *, track_check=True):
                self.tick_entered.set()
                if not self.tick_release.wait(5.0):
                    raise AssertionError("tick was not released")
                return {
                    "seq": 1,
                    "frames": 0,
                    "t_ms": ms,
                    "truncated": False,
                }

        runtime = SlowTickRuntime()
        session = self._session(lambda: runtime)
        self.addCleanup(runtime.tick_release.set)
        session.start("test", "coffee")
        self.assertTrue(runtime.tick_entered.wait(2.0), "ticker did not tick")

        seen: dict[str, str | None] = {}

        def read_app() -> None:
            seen["app"] = session.selected_app("xiaohongshu")

        reader = threading.Thread(target=read_app, name="test-live-selected")
        reader.start()
        reader.join(0.2)
        self.assertFalse(
            reader.is_alive(), "page rendering must not wait for a tick"
        )
        self.assertEqual(seen["app"], "coffee")

        runtime.tick_release.set()
        session.stop()

    def test_status_blocks_while_start_holds_the_live_lock(self) -> None:
        runtime = BlockingRuntime(self.session)
        session = self._session(lambda: runtime)
        starter = threading.Thread(
            target=session.start, args=("record", None), name="test-live-start"
        )
        starter.start()
        self.assertTrue(runtime.start_entered.wait(2.0))

        seen: dict[str, dict] = {}

        def read_status() -> None:
            seen["status"] = session.status()

        reader = threading.Thread(target=read_status, name="test-live-status")
        reader.start()
        reader.join(0.1)
        self.assertTrue(
            reader.is_alive(), "status must block while starting"
        )
        runtime.start_release.set()
        starter.join(5.0)
        reader.join(5.0)
        self.assertFalse(reader.is_alive())
        self.assertTrue(seen["status"]["running"])
        self.assertFalse(seen["status"]["starting"])

        runtime.stop_release.set()
        session.stop()

    def test_pointer_and_key_forward_and_validate(self) -> None:
        runtime = FakeRuntime()
        session = self._session(lambda: runtime)
        with self.assertRaises(LiveError) as missing:
            session.pointer({"action": "down", "x": 1, "y": 2})
        self.assertEqual(missing.exception.code, "live_not_running")

        session.start("record", None)
        reply = session.pointer({"action": "down", "x": 12, "y": 34})
        self.assertEqual(reply["reply"]["hit"], "fake_button")
        self.assertIn(("pointer", "down", 12, 34), runtime.commands)
        self.assertIn(("wait", 16), runtime.commands)

        before_move = len(runtime.commands)
        session.pointer({"action": "move", "x": 20, "y": 40})
        self.assertIn(("pointer", "move", 20, 40), runtime.commands[before_move:])
        self.assertNotIn(("wait", 16), runtime.commands[before_move:])

        session.key({"action": "press", "key": "ENTER"})
        self.assertIn(("key", "press", "ENTER"), runtime.commands)

        with self.assertRaises(LiveError) as bad_action:
            session.pointer({"action": "bogus", "x": 1, "y": 2})
        self.assertEqual(bad_action.exception.code, "invalid_input")
        with self.assertRaises(LiveError) as bad_x:
            session.pointer({"action": "down", "x": -1, "y": 2})
        self.assertEqual(bad_x.exception.code, "invalid_input")
        with self.assertRaises(LiveError) as bad_key:
            session.key({"action": "press", "key": ""})
        self.assertEqual(bad_key.exception.code, "invalid_input")

        failed = FakeRuntime(errors={"key": ScenarioError("bad key")})
        failing = self._session(lambda: failed)
        failing.start("record", None)
        with self.assertRaises(LiveError) as key_error:
            failing.key({"action": "press", "key": "NOPE"})
        self.assertEqual(key_error.exception.code, "invalid_key")
        failing.stop()

    def test_selected_app_follows_the_live_priority_rule(self) -> None:
        runtime = FakeRuntime()
        session = self._session(lambda: runtime)
        session.start("record", "coffee")
        self.assertEqual(session.selected_app("xiaohongshu"), "coffee")
        # Deleting the selected app while running must not clear it.
        session.forget_app("coffee")
        self.assertEqual(session.selected_app(None), "coffee")
        session.stop()
        self.assertEqual(session.selected_app("xiaohongshu"), "xiaohongshu")
        self.assertEqual(session.selected_app(None), "coffee")
        session.forget_app("coffee")
        self.assertIsNone(session.selected_app(None))

    def test_test_mode_uses_a_private_root_and_removes_it_on_stop(self) -> None:
        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch(
            "lvgl_ai.web.live_session.Runtime", CapturingRuntime
        ):
            session = LiveSession(self.root / "sessions")
            self.addCleanup(_quiet_stop_session, session)
            session.start("test", "coffee")
            test_root = Path(str(captured["sessions_root"]))
            self.assertNotEqual(test_root, (self.root / "sessions").resolve())
            self.assertEqual(test_root.parent, (self.root / "sessions").resolve())
            self.assertTrue(test_root.is_dir())
            self.assertIs(captured["record"], False)
            self.assertEqual(captured["app"], "coffee")
            session.stop()
            self.assertFalse(test_root.exists())
            status = session.status()
            self.assertIsNone(status["session_id"])
            self.assertFalse(status["running"])

            captured.clear()
            record_root = self.root / "sessions"
            record_root.mkdir(exist_ok=True)
            session.start("record", None)
            self.assertEqual(
                Path(str(captured["sessions_root"])), record_root.resolve()
            )
            self.assertIs(captured["record"], True)
            session.stop()
            self.assertTrue(record_root.is_dir())

    def test_live_start_forwards_display_to_the_default_runtime(self) -> None:
        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch(
            "lvgl_ai.web.live_session.Runtime", CapturingRuntime
        ):
            session = LiveSession(self.root / "sessions")
            self.addCleanup(_quiet_stop_session, session)
            session.start("test", "coffee", display=(640, 480))
            self.assertEqual(captured["width"], 640)
            self.assertEqual(captured["height"], 480)
            session.stop()

    def test_default_runtime_receives_exactly_the_live_options(self) -> None:
        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch(
            "lvgl_ai.web.live_session.Runtime", CapturingRuntime
        ):
            session = LiveSession(self.root / "sessions")
            self.addCleanup(_quiet_stop_session, session)
            session.start("test", "coffee", display=(640, 480))

        self.assertEqual(
            set(captured),
            {
                "lvgl",
                "app",
                "build",
                "record",
                "live_frame",
                "record_changed_only",
                "headless",
                "sessions_root",
                "width",
                "height",
            },
        )
        self.assertIs(captured["record"], False)
        self.assertEqual((captured["width"], captured["height"]), (640, 480))

    def test_live_options_reach_the_session_store_unchanged(self) -> None:
        instances: list[Runtime] = []

        class StoreRuntime(Runtime):
            """Real Runtime + SessionStore, without spawning an engine."""

            def __init__(self, **kwargs: object) -> None:
                super().__init__(**kwargs)
                instances.append(self)

            def start(self) -> StoreRuntime:
                self._session_used = True
                return self

            def stop(self) -> None:
                self._store.close_log()
                self._store.discard_preview()

        with mock.patch("lvgl_ai.web.live_session.Runtime", StoreRuntime):
            session = LiveSession(self.root / "sessions", lvgl="9.4", build=False)
            self.addCleanup(_quiet_stop_session, session)
            session.start("test", "coffee", display=(640, 480))

        self.assertEqual(len(instances), 1)
        runtime = instances[0]
        self.assertEqual((runtime.width, runtime.height), (640, 480))
        store = runtime._store
        self.assertEqual(store.app, "coffee")
        self.assertIs(store.build, False)
        self.assertIs(store.record, False)
        self.assertIs(store.live_frame, True)
        self.assertIs(store.record_changed_only, True)
        self.assertEqual(store.mode, "headless")
        self.assertEqual(store.max_log_bytes, 16 * 1024 * 1024)
        self.assertEqual(store.retention, 10)
        self.assertEqual(
            store.sessions_root.parent, (self.root / "sessions").resolve()
        )
        self.assertEqual(store.lvgl_src.name, "9.4")

        session.stop()
        self.assertFalse(store.sessions_root.exists())

    def test_start_requires_a_runtime_tick(self) -> None:
        class NoTickRuntime(FakeRuntime):
            @property
            def tick(self):
                raise AttributeError("tick")

        session = self._session(lambda: NoTickRuntime())
        with self.assertRaises(LiveError) as raised:
            session.start("record", None)
        self.assertEqual(raised.exception.code, "live_start_error")
        self.assertEqual(session.state, "idle")

    def test_start_failure_discards_the_test_root_and_closes_the_stream(
        self,
    ) -> None:
        captured: dict[str, object] = {}

        class FailingRuntime(FakeRuntime):
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)
                super().__init__(**kwargs)

            def start(self) -> FailingRuntime:
                raise RuntimeCrash("boom", exit_code=1)

        with mock.patch(
            "lvgl_ai.web.live_session.Runtime", FailingRuntime
        ):
            session = LiveSession(self.root / "sessions")
            with self.assertRaises(LiveError) as raised:
                session.start("test", "coffee")
            error = raised.exception
            self.assertEqual(error.code, "live_start_error")
            self.assertEqual(error.detail["error"]["code"], "crash")
            self.assertFalse(error.detail["live"]["running"])
            self.assertTrue(error.detail["live"]["test"])
            self.assertEqual(session.state, "idle")
            self.assertFalse(session.is_starting())
            self.assertFalse(Path(str(captured["sessions_root"])).exists())
            with self.assertRaises(LiveError) as no_stream:
                session.open_stream()
            self.assertEqual(no_stream.exception.code, "live_not_running")

    def test_stream_handle_stays_bound_to_one_hub(self) -> None:
        runtime = StreamRuntime(self.session)
        session = self._session(lambda: runtime)
        session.start("test", None)
        stream = session.open_stream()
        frame = stream.wait_frame(0, timeout=2.0)
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual((frame.width, frame.height), (2, 1))
        self.assertEqual(frame.seq, 1)
        # The hub must carry the exact RGBA bytes the engine wrote to live.rgba.
        self.assertEqual(frame.pixels, bytes([10, 20, 30, 255]) * 2)
        self.assertIsNone(session.wait_frame(frame.seq, timeout=0.01))

        session.stop()
        self.assertTrue(stream.closed)
        self.assertIsNone(stream.wait_frame(frame.seq, timeout=0.1))
        with self.assertRaises(LiveError) as no_stream:
            session.open_stream()
        self.assertEqual(no_stream.exception.code, "live_not_running")

    def test_status_reads_frames_and_manifest_through_recording(self) -> None:
        runtime = SessionFakeRuntime(self.session)
        session = self._session(lambda: runtime)
        session.start("record", None)
        status = session.status()

        self.assertTrue(status["running"])
        self.assertEqual(status["pid"], FAKE_PID)
        self.assertEqual(status["session_id"], SESSION_ID)
        self.assertEqual(status["frame_count"], 3)
        self.assertEqual(status["status"], "ok")
        self.assertIsNone(status["error"])
        self.assertTrue(status["latest_frame"]["url"].endswith("/000003.png"))
        self.assertIn(f"/frames/{SESSION_ID}/", status["latest_frame"]["url"])
        session.stop()
        self.assertFalse(session.status()["running"])

    def test_status_before_start_is_empty_and_safe(self) -> None:
        session = self._session(lambda: FakeRuntime())
        status = session.status()
        self.assertFalse(status["running"])
        self.assertFalse(status["starting"])
        self.assertIsNone(status["pid"])
        self.assertIsNone(status["session_id"])
        self.assertEqual(status["frame_count"], 0)
        self.assertIsNone(status["latest_frame"])

    def test_test_mode_status_has_no_png_frame_url(self) -> None:
        runtime = FakeRuntime()
        session = self._session(lambda: runtime)
        session.start("test", None)
        status = session.status()
        self.assertTrue(status["running"])
        self.assertTrue(status["test"])
        self.assertIsNone(status["latest_frame"])
        self.assertEqual(status["frame_count"], 0)
        session.stop()


def _quiet_stop_session(session: LiveSession) -> None:
    try:
        session.stop()
    except Exception:  # noqa: BLE001 - cleanup must never mask the test result
        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
