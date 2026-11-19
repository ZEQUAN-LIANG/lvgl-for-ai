from __future__ import annotations

from scripts.tests import support

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

from scripts.tests.fake_runtime import FAKE_PID, FakeRuntime
from control import BuildError, Recording, Runtime, RuntimeCrash
from web.live_session import LiveError
from web.wire import page_config
from scripts.tests.support import symlinked_file
from scripts.tests.web_support import SESSION_ID, WebHarness, make_web_session

SIGINT_DRIVER = support.WEB_SIGINT_DRIVER
APP_C = (
    Path(__file__).resolve().parents[3] / "user" / "app" / "app.c"
)


from scripts.tests.web.test_web_live_session import (
    BlockingRuntime,
    Factory,
    SessionFakeRuntime,
)


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class PageTrackingTest(unittest.TestCase):
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

    def test_a_page_refreshing_at_the_declared_interval_stays_alive(
        self,
    ) -> None:
        interval_s = page_config()["heartbeatMs"] / 1000.0
        self.assertGreater(
            interval_s,
            0,
            "the page must declare a positive heartbeat interval",
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

        status, _, stopped_again = harness.json("POST", "/api/live/stop")
        self.assertEqual(status, 200, stopped_again)
        self.assertFalse(stopped_again["running"])
        self.assertEqual(factory.instances[0].stop_calls, 2)

    def test_start_failure_is_http_500_and_a_retry_creates_a_new_runtime(
        self,
    ) -> None:
        def build(index):
            if index == 0:
                return FakeRuntime(
                    start_error=RuntimeCrash("boom", exit_code=1)
                )
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

    def test_build_failure_detail_keeps_log_tail_and_last_error(self) -> None:
        error = BuildError(
            "build failed: ninja: build stopped",
            log_text="# phase: build\napp.c:3:5: error: boom\n",
            command=["ninja"],
        )
        factory = Factory(lambda index: FakeRuntime(start_error=error))
        harness = self._harness(factory)

        status, _, payload = harness.json("POST", "/api/live/start?mode=test")
        self.assertEqual(status, 500, payload)
        detail = payload["error"]["detail"]["error"]["detail"]
        self.assertEqual(
            detail["log_tail"],
            ["# phase: build", "app.c:3:5: error: boom"],
        )
        self.assertEqual(detail["command"], ["ninja"])

        status, _, live = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertIsNotNone(live["last_error"])
        self.assertEqual(live["last_error"]["code"], "build_error")
        self.assertIsNone(live["session_id"])
        self.assertIsNone(live["session_dir"])

        harness.json("POST", "/api/live/stop")

    def test_live_start_does_not_spawn_a_process(self) -> None:
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
        scenarios = self.root / "user" / "scenarios"
        scenarios.mkdir(parents=True)
        for name in ("coffee", "xiaohongshu"):
            (scenarios / f"{name}.json").write_text(
                json.dumps(
                    {
                        "schema": "lvgl-verify-loop-scenario-v1",
                        "name": name,
                        "app": name,
                        "steps": [{"type": "wait", "ms": 16}],
                    }
                ),
                encoding="utf-8",
            )
        (scenarios / "broken.json").write_text("{broken", encoding="utf-8")
        return scenarios

    def _write_display_scenarios(self) -> Path:
        scenarios = Path(
            tempfile.mkdtemp(prefix="display-scenarios-", dir=self.root)
        )
        documents = {
            "coffee.json": {
                "name": "coffee",
                "app": "coffee",
                "display": {"width": 640, "height": 480},
            },
            "coffee_alt.json": {
                "name": "coffee_alt",
                "app": "coffee",
                "display": {"width": 320, "height": 240},
            },
            "plain.json": {"name": "plain", "app": "plain"},
        }
        for filename, fields in documents.items():
            (scenarios / filename).write_text(
                json.dumps(
                    {
                        "schema": "lvgl-verify-loop-scenario-v1",
                        "steps": [{"type": "wait", "ms": 16}],
                        **fields,
                    }
                ),
                encoding="utf-8",
            )
        return scenarios

    def test_scenario_apps_include_display(self) -> None:
        harness = WebHarness(
            self.root,
            runtime_factory=Factory(lambda index: FakeRuntime()),
            scenarios_dir=self._write_display_scenarios(),
        )
        self.addCleanup(harness.close)

        by_app = {
            entry["app"]: entry for entry in harness.server.app.scenario_apps()
        }
        self.assertEqual(
            by_app["coffee"]["display"], {"width": 640, "height": 480}
        )
        self.assertIsNone(by_app["plain"]["display"])

    def test_symlinked_scenarios_stay_in_the_picker_and_live_display(
        self,
    ) -> None:
        scenarios = Path(
            tempfile.mkdtemp(prefix="linked-scenarios-", dir=self.root)
        )
        target = (
            Path(tempfile.mkdtemp(prefix="linked-target-", dir=self.root))
            / "coffee.json"
        )
        target.write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-scenario-v1",
                    "name": "coffee",
                    "app": "coffee",
                    "display": {"width": 640, "height": 480},
                    "steps": [{"type": "wait", "ms": 16}],
                }
            ),
            encoding="utf-8",
        )
        symlinked_file(self, scenarios / "coffee.json", target)

        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs):
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch("web.live_session.Runtime", CapturingRuntime):
            harness = WebHarness(
                self.root, scenarios_dir=scenarios, repo_root=self.root
            )
            self.addCleanup(harness.close)
            self.addCleanup(lambda: _quiet_stop(harness))

            by_app = {
                entry["app"]: entry
                for entry in harness.server.app.scenario_apps()
            }
            self.assertIn("coffee", by_app)
            self.assertEqual(by_app["coffee"]["scenario"], "coffee.json")
            self.assertEqual(
                by_app["coffee"]["display"], {"width": 640, "height": 480}
            )

            status, _, live = harness.json(
                "POST", "/api/live/start?app=coffee"
            )
            self.assertEqual(status, 200, live)
            self.assertEqual(captured["width"], 640)
            self.assertEqual(captured["height"], 480)
            harness.json("POST", "/api/live/stop")

    def test_live_start_forwards_the_scenario_display(self) -> None:
        captured: dict[str, object] = {}

        class CapturingRuntime(FakeRuntime):
            def __init__(self, **kwargs):
                captured.update(kwargs)
                super().__init__(**kwargs)

        with mock.patch("web.live_session.Runtime", CapturingRuntime):
            harness = WebHarness(
                self.root,
                scenarios_dir=self._write_display_scenarios(),
            )
            self.addCleanup(harness.close)
            self.addCleanup(lambda: _quiet_stop(harness))
            status, _, live = harness.json(
                "POST", "/api/live/start?app=coffee"
            )
            self.assertEqual(status, 200, live)
            self.assertEqual(captured["width"], 640)
            self.assertEqual(captured["height"], 480)
            harness.json("POST", "/api/live/stop")

    def test_live_start_without_a_scenario_display_uses_the_default(
        self,
    ) -> None:
        for query in ("", "?app=plain", "?app=missing"):
            with self.subTest(query=query):
                captured: dict[str, object] = {}

                class CapturingRuntime(FakeRuntime):
                    def __init__(self, _sink=captured, **kwargs):
                        _sink.update(kwargs)
                        super().__init__(**kwargs)

                with mock.patch(
                    "web.live_session.Runtime", CapturingRuntime
                ):
                    harness = WebHarness(
                        self.root,
                        scenarios_dir=self._write_display_scenarios(),
                    )
                    self.addCleanup(harness.close)
                    self.addCleanup(lambda h=harness: _quiet_stop(h))
                    status, _, live = harness.json(
                        "POST", "/api/live/start" + query
                    )
                    self.assertEqual(status, 200, live)
                    self.assertNotIn("width", captured)
                    self.assertNotIn("height", captured)
                    harness.json("POST", "/api/live/stop")

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

        with mock.patch("web.live_session.Runtime", CapturingRuntime):
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

        with mock.patch("web.live_session.Runtime", CapturingRuntime):
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
            status, _, live = harness.json("POST", "/api/live/start?mode=test")
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
        self.assertTrue(
            runtime.tick_event.wait(2.0), "live ticker did not tick"
        )
        self.assertIn(("tick", 33, False), runtime.commands)

        status, _, current = harness.json("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(current["t_ms"], 33)

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
        status, _, live = harness.json("POST", "/api/live/start?mode=test")
        self.assertEqual(status, 200, live)
        self.assertTrue(
            runtime.tick_event.wait(2.0), "live ticker did not tick"
        )
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

    def test_pointer_and_key_input_are_forwarded_to_the_live_runtime(
        self,
    ) -> None:
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

    def test_apps_stay_available_while_live_start_is_building(self) -> None:
        repo = self.root / "repo"
        (repo / "user" / "app").mkdir(parents=True)
        (repo / "user" / "scenarios").mkdir(parents=True)
        shutil.copy2(APP_C, repo / "user" / "app" / "app.c")
        coffee = repo / "user" / "app" / "coffee"
        coffee.mkdir()
        (coffee / "app.json").write_text(
            json.dumps({"entry": "coffee_create", "default": True}),
            encoding="utf-8",
        )

        runtime = BlockingRuntime(self.session)
        harness = WebHarness(
            self.root,
            runtime_factory=Factory(lambda index: runtime),
            repo_root=repo,
            scenarios_dir=repo / "user" / "scenarios",
        )
        self.addCleanup(harness.close)
        self.addCleanup(lambda: _quiet_stop(harness))

        started: list[tuple[int, dict]] = []
        errors: list[BaseException] = []

        def start_live() -> None:
            try:
                status, _, payload = harness.json(
                    "POST", "/api/live/start", timeout=30.0
                )
                started.append((status, payload))
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        starter = threading.Thread(
            target=start_live, name="test-live-http-start"
        )
        starter.start()
        try:
            self.assertTrue(
                runtime.start_entered.wait(2.0),
                "the live start never reached Runtime.start()",
            )
            self.assertTrue(harness.server.app.live.is_starting())
            status, _, payload = harness.json("GET", "/api/apps", timeout=1.0)
            self.assertEqual(status, 200, payload)
            self.assertIn(
                "coffee", {entry["name"] for entry in payload["apps"]}
            )
            self.assertIn("trash", payload)
        finally:
            runtime.start_release.set()
            starter.join(10.0)
            runtime.stop_release.set()
            _quiet_stop(harness)

        self.assertFalse(starter.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][0], 200, started[0][1])
        self.assertTrue(started[0][1]["running"])

    def test_live_errors_keep_http_status_and_json_shape(self) -> None:
        harness = self._harness(Factory(lambda index: FakeRuntime()))
        cases = [
            ("GET", "/api/live", "status", (), 409, "live_not_running"),
            ("POST", "/api/live/stop", "stop", (), 409, "live_starting"),
            ("POST", "/api/live/stop", "stop", (), 500, "live_stop_error"),
            (
                "POST",
                "/api/live/pointer",
                "pointer",
                ({"action": "down", "x": 1, "y": 2},),
                400,
                "invalid_input",
            ),
            (
                "POST",
                "/api/live/key",
                "key",
                ({"action": "press", "key": "ENTER"},),
                500,
                "live_input_error",
            ),
            (
                "POST",
                "/api/live/start?mode=record&app=coffee",
                "start",
                ("record", "coffee"),
                409,
                "live_running",
            ),
        ]
        for method, path, name, args, expected_status, code in cases:
            with self.subTest(code=code):
                error = LiveError(
                    code, f"{code} message", detail={"why": code}
                )
                with mock.patch.object(
                    harness.server.app.live, name, side_effect=error
                ):
                    if method == "POST" and path.endswith(
                        ("/pointer", "/key")
                    ):
                        status, _, payload = harness.json(
                            method, path, payload=args[0]
                        )
                    else:
                        status, _, payload = harness.json(method, path)
                self.assertEqual(status, expected_status, payload)
                self.assertEqual(
                    set(payload),
                    {"error"},
                    payload,
                )
                self.assertEqual(
                    set(payload["error"]),
                    {"code", "message", "detail"},
                    payload,
                )
                self.assertEqual(payload["error"]["code"], code)
                self.assertEqual(payload["error"]["detail"], {"why": code})

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
        harness.server.app.shutdown()
        self.assertEqual(harness.server.app.live.state, "idle")
        self.assertFalse(harness.server.app.live.is_active())


class LiveIndependentEngineTest(unittest.TestCase):
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
            lvgl="9.6", build=False, sessions_root=self.root / "other"
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

        status, _, stopped = harness.json(
            "POST", "/api/live/stop", timeout=60.0
        )
        self.assertEqual(status, 200, stopped)
        self.assertFalse(stopped["running"])

        final = Recording.open(live["session_dir"])
        self.assertEqual(final.manifest["status"], "ok")
        self.assertEqual(final.manifest["frame_count"], len(final.frames))
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
        harness.server.app.live.stop()
    except Exception:  # noqa: BLE001 - cleanup must never mask the test result
        pass
