
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from lvgl_ai import Runtime, ScenarioError, play_scenario
from lvgl_ai.control.input import (
    DEVICE_ACTIONS,
    ENCODER_ACTIONS,
    INT16_MAX,
    INT16_MIN,
    KEY_ACTIONS,
    POINTER_ACTIONS,
    TOKEN_PATTERN,
    integer_problem,
    is_token,
    normalize_input_events,
    point_problem,
    require_action,
    require_int16,
    require_non_negative_int,
    require_token,
    runtime_action_problem,
    step_action_problem,
    token_problem,
)
from lvgl_ai.control.keys import resolve_key

FAKE_ENGINE = Path(__file__).with_name("fake_engine.py")
KEY_EXPECTED = "UP, DOWN, RIGHT, LEFT, ESC, DEL, BACKSPACE, ENTER, NEXT, PREV, HOME, END"


class VocabularyTableTest(unittest.TestCase):
    def test_device_action_table_is_the_single_source(self) -> None:
        self.assertEqual(POINTER_ACTIONS, ("down", "move", "up"))
        self.assertEqual(KEY_ACTIONS, ("press", "release"))
        self.assertEqual(ENCODER_ACTIONS, ("turn",))
        self.assertEqual(
            DEVICE_ACTIONS,
            {
                "pointer": POINTER_ACTIONS,
                "key": KEY_ACTIONS,
                "encoder": ENCODER_ACTIONS,
            },
        )

    def test_token_syntax_and_length_cap(self) -> None:
        for value in ("coffee", "x-y_z", "A", "A" * 64, "9"):
            with self.subTest(value=value):
                self.assertTrue(is_token(value))
                self.assertIsNone(token_problem(value, "app"))
        for value in ("", "bad app", "A" * 65, "咖啡", "a.b", None, 7, True):
            with self.subTest(value=value):
                self.assertFalse(is_token(value))
                self.assertEqual(
                    token_problem(value, "app"),
                    f"app must match {TOKEN_PATTERN}",
                )
        self.assertEqual(TOKEN_PATTERN, "[A-Za-z0-9_-]+")

    def test_integer_ranges_share_one_rule(self) -> None:
        self.assertIsNone(integer_problem(0, "x", minimum=0))
        self.assertEqual(
            integer_problem(-1, "x", minimum=0), "x must be >= 0; got -1"
        )
        self.assertEqual(
            integer_problem(32768, "diff", maximum=INT16_MAX),
            "diff must be <= 32767; got 32768",
        )
        for value in (True, False, 1.5, "1", None):
            with self.subTest(value=value):
                self.assertEqual(
                    integer_problem(value, "x"), "x must be an integer"
                )

    def test_int16_bounds_are_inclusive(self) -> None:
        for value in (INT16_MIN, INT16_MAX, 0, -1):
            with self.subTest(value=value):
                self.assertIsNone(
                    integer_problem(
                        value,
                        "diff",
                        minimum=INT16_MIN,
                        maximum=INT16_MAX,
                    )
                )
        self.assertEqual(INT16_MIN, -32768)
        self.assertEqual(INT16_MAX, 32767)

    def test_point_rule(self) -> None:
        for value in ([0, 0], [800, 600]):
            with self.subTest(value=value):
                self.assertIsNone(point_problem(value, "from"))
        for value in ([-1, 0], [1], [1, 2, 3], [True, 0], (1, 2), "1,2", None):
            with self.subTest(value=value):
                self.assertEqual(
                    point_problem(value, "from"),
                    "from must be [x, y] with non-negative integers",
                )

    def test_scenario_and_runtime_action_messages(self) -> None:
        self.assertIsNone(step_action_problem("key", "press"))
        self.assertEqual(
            step_action_problem("key", "tap"),
            "key.action must be one of ['press', 'release']; got 'tap'",
        )
        self.assertEqual(
            step_action_problem("encoder", "push"),
            "encoder.action must be one of ['turn']; got 'push'",
        )
        self.assertEqual(
            step_action_problem("encoder", "push", quoted=True),
            "encoder.action must be 'turn'; got 'push'",
        )
        self.assertEqual(
            runtime_action_problem("pointer", "tap"),
            "pointer action must be down, move or up; got 'tap'",
        )
        self.assertEqual(
            runtime_action_problem("key", "tap"),
            "key action must be press or release; got 'tap'",
        )
        self.assertEqual(
            runtime_action_problem("encoder", "push"),
            "encoder action must be turn; got 'push'",
        )

    def test_raising_helpers_keep_runtime_value_error_messages(self) -> None:
        self.assertEqual(require_action("pointer", "down"), "down")
        self.assertEqual(require_action("key", "release"), "release")
        self.assertEqual(require_action("encoder", "turn"), "turn")
        for device, action, message in (
            ("pointer", "tap", "pointer action must be down, move or up; got 'tap'"),
            ("key", "tap", "key action must be press or release; got 'tap'"),
            ("encoder", "push", "encoder action must be turn; got 'push'"),
        ):
            with self.subTest(device=device), self.assertRaises(
                ValueError
            ) as caught:
                require_action(device, action)
            self.assertEqual(str(caught.exception), message)

        self.assertEqual(require_int16(-32768, "diff"), -32768)
        self.assertEqual(require_int16(32767, "diff"), 32767)
        for value, message in (
            (32768, "diff must be within -32768..32767; got 32768"),
            (-32769, "diff must be within -32768..32767; got -32769"),
            (True, "diff must be an integer"),
        ):
            with self.subTest(value=value), self.assertRaises(
                ValueError
            ) as caught:
                require_int16(value, "diff")
            self.assertEqual(str(caught.exception), message)

        self.assertEqual(require_non_negative_int(0, "x"), 0)
        with self.assertRaises(ValueError) as caught:
            require_non_negative_int(-1, "x")
        self.assertEqual(str(caught.exception), "x must be >= 0; got -1")

        self.assertEqual(require_token("checkpoint", "mark id"), "checkpoint")
        with self.assertRaises(ValueError) as caught:
            require_token("bad id", "mark id")
        self.assertEqual(
            str(caught.exception),
            f"mark id must match {TOKEN_PATTERN}",
        )

    def test_key_aliases_resolve_through_the_shared_table(self) -> None:
        for alias in ("ENTER", "enter", "Enter", "LV_KEY_ENTER", "lv_key_enter"):
            with self.subTest(alias=alias):
                self.assertEqual(resolve_key(alias), ("ENTER", 10))
        with self.assertRaises(ScenarioError) as caught:
            resolve_key("INSERT", step=2)
        self.assertEqual(caught.exception.step, 2)
        self.assertEqual(
            str(caught.exception),
            f"step 2: unknown key 'INSERT'; expected one of {KEY_EXPECTED}",
        )


class ScenarioVocabularyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()

    def _error(self, steps) -> ScenarioError:
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(self.runtime, steps)
        return caught.exception

    def test_encoder_int16_boundaries_are_inclusive(self) -> None:
        play_scenario(
            self.runtime,
            [
                {"type": "encoder", "action": "turn", "diff": INT16_MIN},
                {"type": "encoder", "action": "turn", "diff": INT16_MAX},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("encoder", "turn", -32768),
                ("encoder", "turn", 32767),
            ],
        )

    def test_encoder_int16_overflow_keeps_the_step_prefix(self) -> None:
        cases = [
            (-32769, "step 1: diff must be >= -32768; got -32769"),
            (32768, "step 1: diff must be <= 32767; got 32768"),
        ]
        for diff, message in cases:
            with self.subTest(diff=diff):
                self.runtime.commands.clear()
                error = self._error(
                    [
                        {"type": "wait", "ms": 16},
                        {"type": "encoder", "action": "turn", "diff": diff},
                    ]
                )
                self.assertEqual(str(error), message)
                self.assertEqual(error.step, 1)
                self.assertEqual(self.runtime.commands, [])

    def test_key_aliases_and_token_rules_are_shared(self) -> None:
        play_scenario(
            self.runtime,
            [
                {"type": "key", "action": "press", "key": "lv_key_enter"},
                {"type": "key", "action": "press", "key": "Enter"},
                {"type": "key", "action": "press", "key": "ENTER"},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("key", "press", "ENTER"),
                ("key", "press", "ENTER"),
                ("key", "press", "ENTER"),
            ],
        )

        for key, message in (
            ("bad key", "step 0: key.key must match [A-Za-z0-9_-]+"),
            ("a" * 65, "step 0: key.key must match [A-Za-z0-9_-]+"),
            (
                "INSERT",
                f"step 0: unknown key 'INSERT'; expected one of {KEY_EXPECTED}",
            ),
        ):
            with self.subTest(key=key):
                self.runtime.commands.clear()
                error = self._error(
                    [{"type": "key", "action": "press", "key": key}]
                )
                self.assertEqual(str(error), message)
                self.assertEqual(error.step, 0)
                self.assertEqual(self.runtime.commands, [])

    def test_action_messages_keep_scenario_wording(self) -> None:
        for step, message in (
            (
                {"type": "key", "action": "tap", "key": "ENTER"},
                "step 0: key.action must be one of ['press', 'release']; "
                "got 'tap'",
            ),
            (
                {"type": "encoder", "action": "push", "diff": 1},
                "step 0: encoder.action must be one of ['turn']; got 'push'",
            ),
        ):
            with self.subTest(step=step):
                self.assertEqual(str(self._error([step])), message)

    def test_mark_and_snapshot_tokens_accept_64_and_reject_65(self) -> None:
        label = "a" * 64
        play_scenario(
            self.runtime,
            [
                {"type": "mark", "id": label},
                {"type": "snapshot", "label": label},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [("mark", label), ("snapshot", label)],
        )

        for step, message in (
            (
                {"type": "mark", "id": "a" * 65},
                "step 0: id must match [A-Za-z0-9_-]+",
            ),
            (
                {"type": "snapshot", "label": ""},
                "step 0: label must match [A-Za-z0-9_-]+",
            ),
        ):
            with self.subTest(step=step):
                self.runtime.commands.clear()
                error = self._error([step])
                self.assertEqual(str(error), message)
                self.assertEqual(self.runtime.commands, [])

    def test_input_events_share_the_same_vocabulary(self) -> None:
        events = normalize_input_events(
            [
                {
                    "at_ms": 0,
                    "device": "encoder",
                    "action": "turn",
                    "diff": INT16_MIN,
                },
                {
                    "at_ms": 16,
                    "device": "encoder",
                    "action": "turn",
                    "diff": INT16_MAX,
                },
            ]
        )
        self.assertEqual([event["diff"] for event in events], [-32768, 32767])

        cases = [
            (
                [{"at_ms": 0, "device": "pointer", "action": "tap", "x": 1, "y": 2}],
                "step 0: pointer.action must be one of ['down', 'move', 'up']; "
                "got 'tap'",
            ),
            (
                [{"at_ms": 0, "device": "key", "action": "tap", "key": "ENTER"}],
                "step 0: key.action must be one of ['press', 'release']; "
                "got 'tap'",
            ),
            (
                [{"at_ms": 0, "device": "encoder", "action": "push", "diff": 1}],
                "step 0: encoder.action must be 'turn'; got 'push'",
            ),
            (
                [
                    {
                        "at_ms": 0,
                        "device": "encoder",
                        "action": "turn",
                        "diff": 32768,
                    }
                ],
                "step 0: diff must be <= 32767; got 32768",
            ),
            (
                [
                    {
                        "at_ms": 0,
                        "device": "key",
                        "action": "press",
                        "key": "bad key",
                    }
                ],
                "step 0: key.key must match [A-Za-z0-9_-]+",
            ),
            (
                [
                    {
                        "at_ms": -1,
                        "device": "pointer",
                        "action": "down",
                        "x": 1,
                        "y": 2,
                    }
                ],
                "step 0: at_ms must be >= 0; got -1",
            ),
        ]
        for event_list, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ScenarioError) as caught:
                    normalize_input_events(event_list)
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(caught.exception.step, 0)


class RuntimeVocabularyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self) -> Runtime:
        return Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
        )

    def test_runtime_actions_and_arguments_keep_their_messages(self) -> None:
        runtime = self._runtime()
        cases = [
            (lambda: runtime.pointer("tap", 1, 2), "pointer action must be down, move or up; got 'tap'"),
            (lambda: runtime.pointer("down", -1, 2), "x must be >= 0; got -1"),
            (lambda: runtime.pointer("down", 1, True), "y must be an integer"),
            (lambda: runtime.key("tap", "ENTER"), "key action must be press or release; got 'tap'"),
            (lambda: runtime.encoder("push", 1), "encoder action must be turn; got 'push'"),
            (lambda: runtime.encoder("turn", 32768), "diff must be within -32768..32767; got 32768"),
            (lambda: runtime.encoder("turn", -32769), "diff must be within -32768..32767; got -32769"),
            (lambda: runtime.tick(-1), "ms must be >= 0; got -1"),
            (lambda: runtime.wait(), "wait needs exactly one of ms or frames"),
            (lambda: runtime.wait(ms=1, frames=1), "wait needs exactly one of ms or frames"),
            (lambda: runtime.wait(ms=-1), "ms must be >= 0; got -1"),
            (lambda: runtime.wait(frames=-1), "frames must be >= 0; got -1"),
            (lambda: runtime.snapshot("bad label"), "snapshot label must match [A-Za-z0-9_-]+"),
            (lambda: runtime.mark("bad id"), "mark id must match [A-Za-z0-9_-]+"),
        ]
        for call, message in cases:
            with self.subTest(message=message), self.assertRaises(
                ValueError
            ) as caught:
                call()
            self.assertEqual(str(caught.exception), message)

    def test_runtime_accepts_int16_boundaries(self) -> None:
        runtime = Runtime(
            lvgl="9.6",
            build=False,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )
        self.addCleanup(runtime.stop)
        runtime.start()
        low = runtime.encoder("turn", INT16_MIN)
        high = runtime.encoder("turn", INT16_MAX)
        runtime.stop()

        self.assertIs(low["delivered"], True)
        self.assertEqual(low["diff"], INT16_MIN)
        self.assertIs(high["delivered"], True)
        self.assertEqual(high["diff"], INT16_MAX)

    def test_app_token_rule_is_shared(self) -> None:
        Runtime(
            lvgl="9.6",
            build=False,
            app="a" * 64,
            sessions_root=self.sessions_root,
        )
        with self.assertRaises(ValueError) as caught:
            Runtime(
                lvgl="9.6",
                build=False,
                app="a" * 65,
                sessions_root=self.sessions_root,
            )
        self.assertEqual(
            str(caught.exception),
            f"app must match {TOKEN_PATTERN}; got {'a' * 65!r}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
