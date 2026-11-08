"""Live web adapter: Runtime delegation, independent engine process, HTTP routes.

``LiveSession`` owns one ``Runtime``, the raw preview hub, the ticker, the
temporary test-session root and the idle -> starting -> running -> stopping
state machine. The unit tests replace the process boundary with
``FakeRuntime``; the integration test starts the real engine through HTTP.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fake_runtime import FAKE_PID, FakeRuntime
from lvgl_ai import Recording, Runtime, RuntimeCrash, ScenarioError
from lvgl_ai.web.live_session import LiveError, LiveSession
from lvgl_ai.web.wire import page_config
from web_support import SESSION_ID, WebHarness, make_web_session

SIGINT_DRIVER = Path(__file__).with_name("web_sigint_driver.py")


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
            record_root.mkdir()
            session.start("record", None)
            self.assertEqual(
                Path(str(captured["sessions_root"])), record_root.resolve()
            )
            self.assertIs(captured["record"], True)
            session.stop()
            self.assertTrue(record_root.is_dir())

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


class FakeClock:
    """Controllable monotonic clock for the page heartbeat/grace rules."""

    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class PageTrackingTest(unittest.TestCase):
    """The --exit-on-close decision, driven by real page beacons and a clock."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.clock = FakeClock()
        self.harness = WebHarness(
            self._tmp.name,
            runtime_factory=lambda: FakeRuntime(),
            page_clock=self.clock,
        )
        self.addCleanup(self.harness.close)
        self.app = self.harness.server.app

    def _beacon(self, action: str, page_id: str) -> None:
        status, _, payload = self.harness.json(
            "POST", f"/api/page/{action}", payload={"id": page_id}
        )
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])

    def test_exit_waits_for_every_page_and_the_close_grace(self) -> None:
        self._beacon("open", "page-a")
        self._beacon("open", "page-b")
        self.assertFalse(
            self.app.should_exit_on_close(),
            "the server must stay alive while a page is open",
        )

        self.clock.advance(0.5)
        self._beacon("close", "page-a")
        self.assertFalse(
            self.app.should_exit_on_close(),
            "one page is still open, so the server must stay alive",
        )

        self.clock.advance(1.6)
        self._beacon("close", "page-b")
        self.assertFalse(
            self.app.should_exit_on_close(),
            "the last page close starts the grace period, not an instant exit",
        )
        self.clock.advance(0.3)
        self.assertFalse(
            self.app.should_exit_on_close(),
            "the server must keep running until the close grace elapses",
        )
        self.clock.advance(0.3)
        self.assertTrue(
            self.app.should_exit_on_close(),
            "the last page closed and the grace elapsed, so exit now",
        )

    def test_never_seen_page_does_not_exit(self) -> None:
        self.assertFalse(self.app.should_exit_on_close())

    def test_stale_page_is_pruned(self) -> None:
        self._beacon("open", "stale")
        self.clock.advance(121.0)
        self.assertTrue(
            self.app.should_exit_on_close(),
            "a page that stopped heartbeating must not keep the server alive",
        )

    def test_a_page_refreshing_at_the_declared_interval_stays_alive(self) -> None:
        interval_s = page_config()["heartbeatMs"] / 1000.0
        self.assertGreater(
            interval_s, 0, "the page must declare a positive heartbeat interval"
        )
        self._beacon("open", "live-page")
        for _ in range(10):
            self.clock.advance(interval_s)
            self.assertFalse(
                self.app.should_exit_on_close(),
                "the declared heartbeat interval must stay below the server TTL",
            )
            self._beacon("open", "live-page")
        self.clock.advance(121.0)
        self.assertTrue(
            self.app.should_exit_on_close(),
            "a page that stops refreshing must go stale after the TTL",
        )

    def test_page_beacons_accept_and_validate_ids(self) -> None:
        status, _, payload = self.harness.json(
            "POST", "/api/page/open", payload={"id": "page-1"}
        )
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])
        status, _, payload = self.harness.json(
            "POST", "/api/page/close", payload={"id": "page-1"}
        )
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])

        status, _, payload = self.harness.json(
            "POST", "/api/page/open", payload={"id": "bad id"}
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_page")

        status, _, _ = self.harness.request("GET", "/api/page/open")
        self.assertEqual(status, 405)


class LiveHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root, app="coffee")

    def _harness(self, factory: Factory) -> WebHarness:
        harness = WebHarness(self.root, runtime_factory=factory)
        self.addCleanup(harness.close)
        self.addCleanup(lambda: _quiet_stop(harness))
        return harness

    def test_start_status_stop_go_through_one_runtime(self) -> None:
        factory = Factory(lambda index: SessionFakeRuntime(self.session))
        harness = self._harness(factory)

        status, _, live = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertFalse(live["running"])
        self.assertFalse(live["starting"])
        self.assertIsNone(live["session_id"])

        status, _, started = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 200, started)
        self.assertTrue(started["running"])
        self.assertEqual(started["pid"], FAKE_PID)
        self.assertEqual(started["session_id"], SESSION_ID)
        self.assertEqual(factory.calls, 1)
        self.assertEqual(factory.instances[0].start_calls, 1)

        status, _, current = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertTrue(current["running"])
        self.assertEqual(current["frame_count"], 3)

        status, _, conflict = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 409, conflict)
        self.assertEqual(conflict["error"]["code"], "live_running")
        self.assertEqual(factory.calls, 1)

        status, _, stopped = harness.json("POST", "/api/live/stop")
        self.assertEqual(status, 200, stopped)
        self.assertFalse(stopped["running"])
        self.assertEqual(factory.instances[0].stop_calls, 1)

        # Stop is idempotent: Runtime.stop() is a no-op after the process is
        # gone, and it can still finish the manifest of an engine that exited.
        status, _, stopped_again = harness.json("POST", "/api/live/stop")
        self.assertEqual(status, 200, stopped_again)
        self.assertFalse(stopped_again["running"])
        self.assertEqual(factory.instances[0].stop_calls, 2)

    def test_start_failure_is_http_500_and_a_retry_creates_a_new_runtime(self) -> None:
        def build(index):
            if index == 0:
                return FakeRuntime(start_error=RuntimeCrash("boom", exit_code=1))
            return FakeRuntime()

        factory = Factory(build)
        harness = self._harness(factory)

        status, _, payload = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 500, payload)
        self.assertEqual(payload["error"]["code"], "live_start_error")
        self.assertEqual(payload["error"]["detail"]["error"]["code"], "crash")
        self.assertEqual(factory.calls, 1)

        status, _, live = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertFalse(live["running"])
        self.assertFalse(live["starting"])

        status, _, retried = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 200, retried)
        self.assertTrue(retried["running"])
        self.assertEqual(factory.calls, 2)
        harness.json("POST", "/api/live/stop")

    def test_live_start_does_not_spawn_a_process(self) -> None:
        """The web adapter reaches the engine only through the Runtime seam."""
        factory = Factory(lambda index: FakeRuntime())
        harness = self._harness(factory)
        with mock.patch(
            "subprocess.Popen",
            side_effect=AssertionError("web live must use the Runtime seam"),
        ):
            status, _, live = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 200, live)
        self.assertTrue(live["running"])
        self.assertEqual(factory.instances[0].start_calls, 1)
        harness.json("POST", "/api/live/stop")

    def test_live_page_has_start_and_stop_controls(self) -> None:
        harness = self._harness(Factory(lambda index: FakeRuntime()))
        status, _, html = harness.html("/")
        self.assertEqual(status, 200)
        self.assertIn('id="live-record"', html)
        self.assertIn('id="live-test"', html)
        self.assertIn('id="live-canvas"', html)
        self.assertIn('id="app-manage"', html)
        self.assertIn('id="app-manager"', html)
        self.assertIn('id="record-controls"', html)
        self.assertIn("/api/page/open", html)
        self.assertIn("/api/page/close", html)
        self.assertIn("pagehide", html)
        self.assertIn('id="mode-note"', html)
        self.assertIn("测试/录制中不能标注", html)

    def _write_scenarios(self) -> Path:
        scenarios = self.root / "scenarios"
        scenarios.mkdir()
        for name in ("coffee", "xiaohongshu"):
            (scenarios / f"{name}.json").write_text(
                json.dumps(
                    {
                        "schema": "lvgl-ai-scenario-v1",
                        "name": name,
                        "app": name,
                        "steps": [{"type": "wait", "ms": 16}],
                    }
                ),
                encoding="utf-8",
            )
        (scenarios / "broken.json").write_text("{broken", encoding="utf-8")
        return scenarios

    def test_live_page_lists_apps_declared_by_scenarios(self) -> None:
        scenarios = self._write_scenarios()
        harness = WebHarness(
            self.root,
            runtime_factory=Factory(lambda index: FakeRuntime()),
            scenarios_dir=scenarios,
        )
        self.addCleanup(harness.close)

        status, _, html = harness.html("/")
        self.assertEqual(status, 200)
        self.assertIn('id="live-app"', html)
        self.assertIn('value="coffee" selected', html)
        self.assertIn('value="xiaohongshu"', html)
        self.assertNotIn('value="broken"', html)
        self.assertNotIn('<option value="">', html)

    def test_page_query_preselects_app(self) -> None:
        scenarios = self._write_scenarios()
        harness = WebHarness(
            self.root,
            runtime_factory=Factory(lambda index: FakeRuntime()),
            scenarios_dir=scenarios,
        )
        self.addCleanup(harness.close)

        status, _, html = harness.html("/?app=xiaohongshu")
        self.assertEqual(status, 200)
        self.assertIn('value="xiaohongshu" selected', html)
        self.assertNotIn('value="coffee" selected', html)

    def test_page_invalid_app_query_is_400(self) -> None:
        harness = self._harness(Factory(lambda index: FakeRuntime()))
        status, _, payload = harness.json("GET", "/?app=bad%20app")
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_app")

    def test_active_live_app_wins_over_query_app(self) -> None:
        scenarios = self._write_scenarios()
        factory = Factory(lambda index: FakeRuntime())
        harness = WebHarness(
            self.root, runtime_factory=factory, scenarios_dir=scenarios
        )
        self.addCleanup(harness.close)
        self.addCleanup(lambda: _quiet_stop(harness))

        status, _, live = harness.json(
            "POST", "/api/live/start?mode=test&app=coffee"
        )
        self.assertEqual(status, 200, live)
        self.assertTrue(live["running"])

        status, _, html = harness.html("/?app=xiaohongshu")
        self.assertEqual(status, 200)
        self.assertIn('value="coffee" selected', html)
        self.assertNotIn('value="xiaohongshu" selected', html)
        self.assertEqual(factory.calls, 1)
        harness.json("POST", "/api/live/stop")

    def test_live_start_forwards_app_to_the_default_runtime(self) -> None:
        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs):
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch("lvgl_ai.web.live_session.Runtime", CapturingRuntime):
            harness = WebHarness(self.root)
            self.addCleanup(harness.close)
            self.addCleanup(lambda: _quiet_stop(harness))
            status, _, live = harness.json(
                "POST", "/api/live/start?app=coffee"
            )
            self.assertEqual(status, 200, live)
            self.assertEqual(captured["app"], "coffee")
            self.assertEqual(live["app"], "coffee")
            harness.json("POST", "/api/live/stop")

    def test_default_live_runtime_uses_changed_only_for_record_and_test(
        self,
    ) -> None:
        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs):
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch("lvgl_ai.web.live_session.Runtime", CapturingRuntime):
            harness = WebHarness(self.root)
            self.addCleanup(harness.close)
            self.addCleanup(lambda: _quiet_stop(harness))

            status, _, live = harness.json("POST", "/api/live/start")
            self.assertEqual(status, 200, live)
            self.assertIs(captured.get("record_changed_only"), True)
            self.assertIs(captured.get("record"), True)
            self.assertIs(captured.get("live_frame"), True)
            self.assertIs(captured.get("headless"), True)
            harness.json("POST", "/api/live/stop")

            captured.clear()
            status, _, live = harness.json(
                "POST", "/api/live/start?mode=test"
            )
            self.assertEqual(status, 200, live)
            self.assertIs(captured.get("record_changed_only"), True)
            self.assertIs(captured.get("record"), False)
            self.assertIs(captured.get("live_frame"), True)
            self.assertIs(captured.get("headless"), True)
            harness.json("POST", "/api/live/stop")

    def test_live_ticker_advances_without_input_and_stops(self) -> None:
        class TickingRuntime(FakeRuntime):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.t_ms = 0
                self.frame_count = 1
                self.tick_calls = 0
                self.tick_event = threading.Event()

            def tick(self, ms, *, track_check=True):
                self.tick_calls += 1
                self.t_ms += ms
                self.commands.append(("tick", ms, track_check))
                self.tick_event.set()
                return {
                    "seq": len(self.commands),
                    "frames": self.frame_count,
                    "t_ms": self.t_ms,
                    "truncated": False,
                }

        runtime = TickingRuntime()
        harness = self._harness(Factory(lambda index: runtime))

        status, _, live = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 200, live)
        self.assertTrue(runtime.tick_event.wait(2.0), "live ticker did not tick")
        self.assertIn(("tick", 100, False), runtime.commands)

        status, _, current = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(current["t_ms"], 100)

        calls = runtime.tick_calls
        status, _, _ = harness.json("POST", "/api/live/stop")
        self.assertEqual(status, 200)
        time.sleep(0.25)
        self.assertEqual(runtime.tick_calls, calls)

    def test_test_mode_ticker_uses_33ms(self) -> None:
        class TickingRuntime(FakeRuntime):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.t_ms = 0
                self.frame_count = 1
                self.tick_event = threading.Event()

            def tick(self, ms, *, track_check=True):
                self.t_ms += ms
                self.commands.append(("tick", ms, track_check))
                self.tick_event.set()
                return {
                    "seq": len(self.commands),
                    "frames": self.frame_count,
                    "t_ms": self.t_ms,
                    "truncated": False,
                }

        runtime = TickingRuntime()
        harness = self._harness(Factory(lambda index: runtime))
        status, _, live = harness.json(
            "POST", "/api/live/start?mode=test"
        )
        self.assertEqual(status, 200, live)
        self.assertTrue(runtime.tick_event.wait(2.0), "live ticker did not tick")
        self.assertIn(("tick", 33, False), runtime.commands)
        harness.json("POST", "/api/live/stop")

    def test_live_start_rejects_invalid_app(self) -> None:
        factory = Factory(lambda index: FakeRuntime())
        harness = self._harness(factory)
        status, _, payload = harness.json(
            "POST", "/api/live/start?app=bad%20app"
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_app")
        self.assertEqual(factory.calls, 0)

    def test_sessions_list_reports_manifest_app(self) -> None:
        harness = self._harness(Factory(lambda index: FakeRuntime()))
        status, _, payload = harness.json("GET", "/api/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(payload["sessions"][0]["app"], "coffee")

    def test_pointer_and_key_input_are_forwarded_to_the_live_runtime(self) -> None:
        factory = Factory(lambda index: FakeRuntime())
        harness = self._harness(factory)

        status, _, payload = harness.json(
            "POST",
            "/api/live/pointer",
            payload={"action": "down", "x": 12, "y": 34},
        )
        self.assertEqual(status, 409, payload)

        status, _, live = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 200, live)
        runtime = factory.instances[0]

        status, _, payload = harness.json(
            "POST",
            "/api/live/pointer",
            payload={"action": "down", "x": 12, "y": 34},
        )
        self.assertEqual(status, 200, payload)
        self.assertIn(("pointer", "down", 12, 34), runtime.commands)
        # Pointer state alone does not render; the web adapter must tick.
        self.assertIn(("wait", 16), runtime.commands)

        before_move = len(runtime.commands)
        status, _, payload = harness.json(
            "POST",
            "/api/live/pointer",
            payload={"action": "move", "x": 20, "y": 40},
        )
        self.assertEqual(status, 200, payload)
        move_commands = runtime.commands[before_move:]
        self.assertIn(("pointer", "move", 20, 40), move_commands)
        # Drag moves are left to the ticker instead of rendering per event.
        self.assertNotIn(("wait", 16), move_commands)

        status, _, payload = harness.json(
            "POST",
            "/api/live/key",
            payload={"action": "press", "key": "ENTER"},
        )
        self.assertEqual(status, 200, payload)
        self.assertIn(("key", "press", "ENTER"), runtime.commands)
        self.assertIn(("wait", 16), runtime.commands)

        status, _, payload = harness.json(
            "POST",
            "/api/live/pointer",
            payload={"action": "down", "x": -1, "y": 0},
        )
        self.assertEqual(status, 400, payload)

        harness.json("POST", "/api/live/stop")

    def test_shutdown_stops_the_running_live_runtime(self) -> None:
        factory = Factory(lambda index: SessionFakeRuntime(self.session))
        harness = self._harness(factory)
        status, _, live = harness.json("POST", "/api/live/start")
        self.assertEqual(status, 200, live)

        harness.server.app.shutdown()

        self.assertFalse(factory.instances[0].is_running)
        self.assertEqual(factory.instances[0].stop_calls, 1)

    def test_shutdown_without_live_is_a_noop(self) -> None:
        harness = self._harness(Factory(lambda index: FakeRuntime()))
        harness.server.app.shutdown()  # must not raise


class LiveIndependentEngineTest(unittest.TestCase):
    """The live session must own its own Runtime and engine PID."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_live_engine_is_an_independent_process_from_the_server_and_other_runtimes(
        self,
    ) -> None:
        def build(index):
            return Runtime(
                lvgl="9.6",
                build=True,
                sessions_root=self.root / f"web-{index}",
            )

        factory = Factory(build)
        harness = WebHarness(self.root, runtime_factory=factory)
        self.addCleanup(harness.close)
        self.addCleanup(lambda: _quiet_stop(harness))

        status, _, live = harness.json(
            "POST", "/api/live/start", timeout=180.0
        )
        self.assertEqual(status, 200, live)
        self.assertTrue(live["running"])
        pid = live["pid"]
        self.assertIsInstance(pid, int)
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(factory.instances[0].pid, pid)
        self.assertTrue(Path(live["session_dir"]).is_dir())
        self.assertGreaterEqual(live["frame_count"], 1)

        recording = Recording.open(live["session_dir"])
        self.assertEqual(recording.manifest["status"], "ok")

        other = Runtime(
            lvgl="9.6", build=True, sessions_root=self.root / "other"
        )
        self.addCleanup(other.stop)
        other.start()
        self.assertIsNotNone(other.pid)
        self.assertNotEqual(other.pid, pid)
        other.stop()

        status, _, live_now = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertTrue(live_now["running"])
        self.assertEqual(live_now["pid"], pid)

        status, _, stopped = harness.json("POST", "/api/live/stop", timeout=60.0)
        self.assertEqual(status, 200, stopped)
        self.assertFalse(stopped["running"])

        final = Recording.open(live["session_dir"])
        self.assertEqual(final.manifest["status"], "ok")
        self.assertEqual(
            final.manifest["frame_count"], len(final.frames)
        )
        self.assertGreaterEqual(final.manifest["frame_count"], 1)


class LiveShutdownIntegrationTest(unittest.TestCase):
    def test_sigint_on_the_web_launcher_stops_live_and_finishes_the_manifest(
        self,
    ) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sessions_root = Path(tmp.name) / "sessions"
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SIGINT_DRIVER),
                str(sessions_root),
            ],
            cwd=tmp.name,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        recording = Recording.open(payload["session_dir"])
        self.assertEqual(recording.manifest["status"], "ok")
        self.assertIsNone(recording.manifest["error"])
        self.assertGreaterEqual(len(recording.frames), 1)
        self.assertEqual(
            recording.manifest["frame_count"], len(recording.frames)
        )
        self.assertEqual(recording.timeline()[-1]["type"], "end")


def _quiet_stop(harness: WebHarness) -> None:
    try:
        harness.server.app.stop_live()
    except Exception:  # noqa: BLE001 - cleanup must never mask the test result
        pass


def _quiet_stop_session(session: LiveSession) -> None:
    try:
        session.stop()
    except Exception:  # noqa: BLE001 - cleanup must never mask the test result
        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
