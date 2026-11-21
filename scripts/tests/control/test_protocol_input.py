from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control import Recording, Runtime, ScenarioError

from scripts.tests import support  # noqa: F401,E402

FAKE_ENGINE = support.FAKE_ENGINE


class ProtocolAndInputTest(unittest.TestCase):
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

    def test_user_printf_json_is_logged_not_treated_as_reply(self) -> None:
        rt = self._runtime()
        with mock.patch.dict(os.environ, {"FAKE_DECOY": "1"}):
            rt.start()
            self.addCleanup(rt.stop)
            reply = rt.tick(16)
            self.assertEqual(
                reply["seq"],
                1,
                "a printf line that looks like a reply must not consume a seq",
            )
            self.assertEqual(reply["t_ms"], 16)
            log_text = Recording.open(rt.session_dir).log()
            self.assertIn('{"seq": 99, "ok": true}', log_text)
            self.assertIn('{"ready": true, "seq": 0}', log_text)
            self.assertIn('{"seq": 1, "ok": true}', log_text)
            rt.stop()

    def test_commands_carry_incrementing_seq(self) -> None:
        rt = self._runtime()
        rt.start()
        self.addCleanup(rt.stop)
        replies = [
            rt.pointer("down", 112, 324),
            rt.mark("checkpoint"),
            rt.snapshot("after_click"),
            rt.tick(16),
            rt.wait(48),
            rt.wait(frames=2),
        ]
        self.assertEqual(
            [reply["seq"] for reply in replies],
            [1, 2, 3, 4, 5, 6],
            "each command reply must echo the next seq",
        )
        self.assertEqual(
            [reply["t_ms"] for reply in replies],
            [0, 0, 0, 16, 64, 96],
            "tick and wait must advance virtual time in 16 ms semantics",
        )
        self.assertEqual(
            replies[2]["file"],
            "snapshots/001_after_click.png",
            "snapshot must write the numbered evidence file",
        )
        rt.stop()

    def test_invalid_input_events_raise_scenario_error_with_step_index(
        self,
    ) -> None:
        rt = self._runtime()
        cases = [
            [{"at_ms": 0, "device": "pointer", "action": "down", "x": 1}],
            [
                {
                    "at_ms": True,
                    "device": "pointer",
                    "action": "down",
                    "x": 1,
                    "y": 2,
                }
            ],
            [
                {
                    "at_ms": 0,
                    "device": "mouse",
                    "action": "down",
                    "x": 1,
                    "y": 2,
                }
            ],
            [
                {
                    "at_ms": 0,
                    "device": "pointer",
                    "action": "tap",
                    "x": 1,
                    "y": 2,
                }
            ],
            [{"at_ms": 0, "device": "key", "action": "press"}],
            [{"at_ms": 0, "device": "encoder", "action": "turn"}],
            [
                {
                    "at_ms": 0,
                    "device": "key",
                    "action": "press",
                    "key": "ENTER",
                    "x": 1,
                }
            ],
            [
                {
                    "at_ms": -1,
                    "device": "pointer",
                    "action": "down",
                    "x": 1,
                    "y": 2,
                }
            ],
        ]
        for events in cases:
            with self.subTest(events=events):
                with self.assertRaises(ScenarioError) as caught:
                    rt.input(events)
                self.assertIn("step 0", str(caught.exception))

    def test_invalid_event_mid_list_reports_its_index(self) -> None:
        rt = self._runtime()
        with self.assertRaises(ScenarioError) as caught:
            rt.input(
                [
                    {
                        "at_ms": 0,
                        "device": "pointer",
                        "action": "down",
                        "x": 1,
                        "y": 2,
                    },
                    {"at_ms": 16, "device": "key", "action": "press"},
                ]
            )
        self.assertIn("step 1", str(caught.exception))

    def test_events_with_equal_at_ms_keep_input_order(self) -> None:
        rt = self._runtime()
        rt.start()
        self.addCleanup(rt.stop)
        replies = rt.input(
            [
                {
                    "at_ms": 0,
                    "device": "key",
                    "action": "press",
                    "key": "ENTER",
                },
                {"at_ms": 0, "device": "key", "action": "press", "key": "UP"},
            ]
        )
        self.assertEqual(
            [reply["key"] for reply in replies],
            ["ENTER", "UP"],
            "events with equal at_ms must keep their input order",
        )
        self.assertEqual(
            [reply["t_ms"] for reply in replies],
            [0, 0],
            "equal at_ms events must not advance virtual time",
        )
        rt.stop()

    def test_key_names_and_encoder_steps_are_delivered(self) -> None:
        rt = self._runtime()
        rt.start()
        self.addCleanup(rt.stop)
        reply = rt.key("press", "up")
        self.assertTrue(reply["delivered"])
        self.assertEqual(
            reply["key"],
            "UP",
            "key names must be canonicalized before they reach the engine",
        )
        reply = rt.key("release", "UP")
        self.assertTrue(reply["delivered"])
        down = rt.encoder("turn", -1)
        self.assertTrue(down["delivered"])
        self.assertEqual(down["diff"], -1)
        up = rt.encoder("turn", 2)
        self.assertTrue(up["delivered"])
        self.assertEqual(up["diff"], 2)
        rt.stop()

    def test_unknown_key_in_input_events_fails_before_any_command(
        self,
    ) -> None:
        rt = self._runtime()
        rt.start()
        self.addCleanup(rt.stop)
        with self.assertRaises(ScenarioError) as caught:
            rt.input(
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
                        "action": "press",
                        "key": "INSERT",
                    },
                ]
            )
        self.assertEqual(caught.exception.step, 1)
        self.assertIn("step 1", str(caught.exception))
        self.assertIn("INSERT", str(caught.exception))
        rt.stop()

        checks = Recording.open(rt.session_dir).manifest["checks"]
        self.assertEqual(
            [check["cmd"] for check in checks],
            ["quit"],
            "an invalid event list must send no command; only shutdown runs",
        )

    def test_key_and_encoder_argument_ranges_are_validated(self) -> None:
        rt = self._runtime()
        with self.assertRaises(ScenarioError) as caught:
            rt.key("press", "NOT_A_KEY")
        self.assertIn("NOT_A_KEY", str(caught.exception))
        with self.assertRaises(ValueError):
            rt.key("tap", "ENTER")
        with self.assertRaises(ValueError):
            rt.encoder("turn", 32768)
        with self.assertRaises(ValueError):
            rt.encoder("push", 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
