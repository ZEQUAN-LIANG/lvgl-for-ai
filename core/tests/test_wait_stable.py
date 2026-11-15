from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fake_runtime import FakeRuntime
from lvgl_ai import ProtocolError, Runtime, ScenarioError, play_scenario

FAKE_ENGINE = Path(__file__).with_name("fake_engine.py")


class WaitStableRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(
        self,
        changed: str | None,
        *,
        record_changed_only: bool = False,
        name: str = "run",
        wait_frames: str | None = None,
    ) -> Runtime:
        rt = Runtime(
            lvgl="9.6",
            build=False,
            record_changed_only=record_changed_only,
            sessions_root=self.sessions_root / name,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )
        self.addCleanup(rt.stop)
        env = {} if changed is None else {"FAKE_WAIT_CHANGED": changed}
        if wait_frames is not None:
            env["FAKE_WAIT_FRAMES"] = wait_frames
        with mock.patch.dict(os.environ, env):
            rt.start()
        return rt

    def test_wait_stable_returns_after_consecutive_unchanged_frames(
        self,
    ) -> None:
        rt = self._runtime("never")
        result = rt.wait_stable(max_ms=64, stable_frames=2)
        self.assertEqual(
            result,
            {"waited_ms": 32, "stable_frames": 2, "stable": True},
        )
        self.assertEqual(rt.t_ms, 32)

    def test_wait_stable_returns_at_max_ms_while_frames_keep_changing(
        self,
    ) -> None:
        rt = self._runtime("always")
        result = rt.wait_stable(max_ms=48, stable_frames=1)
        self.assertEqual(result["waited_ms"], 48)
        self.assertEqual(result["stable_frames"], 0)
        self.assertIs(result["stable"], False)
        self.assertEqual(rt.t_ms, 48)

    def test_wait_stable_times_out_when_changes_reset_the_streak(self) -> None:
        rt = self._runtime("flaky")
        result = rt.wait_stable(max_ms=64, stable_frames=2)
        self.assertEqual(result["waited_ms"], 64)
        self.assertLess(result["stable_frames"], 2)
        self.assertIs(result["stable"], False)

    def test_wait_stable_waits_the_remaining_partial_step(self) -> None:
        rt = self._runtime("always")
        result = rt.wait_stable(max_ms=20, stable_frames=1)
        self.assertEqual(result["waited_ms"], 20)
        self.assertEqual(rt.t_ms, 20)

    def test_wait_stable_without_changed_field_reports_old_engine_hint(
        self,
    ) -> None:
        rt = self._runtime(None)
        with self.assertRaises(ProtocolError) as caught:
            rt.wait_stable(max_ms=64, stable_frames=1)
        message = str(caught.exception)
        self.assertIn("changed", message)
        self.assertIn("--build", message)
        self.assertEqual(rt.t_ms, 16)

    def test_wait_stable_uses_changed_not_retained_frames(self) -> None:
        changing = self._runtime(
            "always",
            record_changed_only=True,
            name="changed-without-retention",
            wait_frames="hold",
        )
        result = changing.wait_stable(max_ms=48, stable_frames=1)
        self.assertIs(result["stable"], False)
        self.assertEqual(result["waited_ms"], 48)
        self.assertEqual(result["stable_frames"], 0)
        self.assertEqual(changing.frame_count, 1)

        static = self._runtime(
            "never",
            record_changed_only=False,
            name="retention-without-change",
        )
        result = static.wait_stable(max_ms=48, stable_frames=2)
        self.assertIs(result["stable"], True)
        self.assertEqual(result["waited_ms"], 32)
        self.assertEqual(result["stable_frames"], 2)
        self.assertGreater(static.frame_count, 1)

    def test_wait_stable_validates_parameters_before_sending(self) -> None:
        rt = Runtime(lvgl="9.6", build=False)
        cases = [
            ({"max_ms": -1, "stable_frames": 1}, "max_ms"),
            (
                {"max_ms": True, "stable_frames": 1},
                "max_ms must be an integer",
            ),
            ({"max_ms": 16, "stable_frames": 0}, "stable_frames must be >= 1"),
            (
                {"max_ms": 16, "stable_frames": True},
                "stable_frames must be an integer",
            ),
        ]
        for kwargs, fragment in cases:
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError) as caught:
                    rt.wait_stable(**kwargs)
                self.assertIn(fragment, str(caught.exception))


class WaitStableScenarioTest(unittest.TestCase):
    def test_wait_stable_step_calls_runtime_wait_stable(self) -> None:
        runtime = FakeRuntime()
        replies = play_scenario(
            runtime,
            [{"type": "wait_stable", "max_ms": 100, "stable_frames": 3}],
        )
        self.assertEqual(runtime.commands, [("wait_stable", 100, 3)])
        self.assertEqual(len(replies), 1)

    def test_wait_stable_step_is_validated_before_any_command(self) -> None:
        cases = [
            (
                {"type": "wait_stable", "stable_frames": 2},
                "max_ms is required",
            ),
            (
                {"type": "wait_stable", "max_ms": 16},
                "stable_frames is required",
            ),
            (
                {"type": "wait_stable", "max_ms": -1, "stable_frames": 1},
                "max_ms must be >= 0",
            ),
            (
                {"type": "wait_stable", "max_ms": 16, "stable_frames": 0},
                "stable_frames must be >= 1",
            ),
            (
                {"type": "wait_stable", "max_ms": 16, "stable_frames": True},
                "stable_frames must be an integer",
            ),
            (
                {
                    "type": "wait_stable",
                    "max_ms": 16,
                    "stable_frames": 1,
                    "frames": 1,
                },
                "unexpected field",
            ),
        ]
        for step, fragment in cases:
            with self.subTest(step=step):
                runtime = FakeRuntime()
                with self.assertRaises(ScenarioError) as caught:
                    play_scenario(
                        runtime,
                        [{"type": "wait", "ms": 16}, step],
                    )
                self.assertIn(fragment, str(caught.exception))
                self.assertEqual(caught.exception.step, 1)
                self.assertEqual(runtime.commands, [])


class WaitStableEngineIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_static_screen_is_stable_with_and_without_changed_only(
        self,
    ) -> None:
        for flag in (False, True):
            with self.subTest(record_changed_only=flag):
                rt = Runtime(
                    lvgl="9.6",
                    app="coffee",
                    build=True,
                    record_changed_only=flag,
                    sessions_root=self.sessions_root / str(flag),
                )
                self.addCleanup(rt.stop)
                rt.start()
                result = rt.wait_stable(max_ms=64, stable_frames=2)
                self.assertIs(result["stable"], True)
                self.assertEqual(result["stable_frames"], 2)
                self.assertEqual(result["waited_ms"], 32)

                rt.pointer("down", 112, 324)
                changed = rt.wait(ms=16)
                self.assertIs(changed["changed"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
