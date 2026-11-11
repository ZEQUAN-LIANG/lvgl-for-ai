"""``text`` scenario step and per-character keypad input.

The scenario seam expands each printable ASCII character into a keypad press
and release carrying the stable ``CHAR_<code>`` token. The runtime seam checks
that the token reaches the engine; no real LVGL build is required.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from lvgl_ai import Runtime, ScenarioError, play_scenario

FAKE_ENGINE = Path(__file__).with_name("fake_engine.py")


class TextScenarioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()

    def test_text_expands_to_press_release_for_each_ascii_character(self) -> None:
        play_scenario(self.runtime, [{"type": "text", "value": "Hi 1"}])
        self.assertEqual(
            self.runtime.commands,
            [
                ("key", "press", "CHAR_72"),
                ("key", "release", "CHAR_72"),
                ("key", "press", "CHAR_105"),
                ("key", "release", "CHAR_105"),
                ("key", "press", "CHAR_32"),
                ("key", "release", "CHAR_32"),
                ("key", "press", "CHAR_49"),
                ("key", "release", "CHAR_49"),
            ],
        )

    def test_text_value_is_validated_before_any_command(self) -> None:
        cases = [
            ({"type": "text"}, "value must be a string"),
            ({"type": "text", "value": 42}, "value must be a string"),
            ({"type": "text", "value": ""}, "value must not be empty"),
            (
                {"type": "text", "value": "café"},
                "value must contain only printable ASCII characters (32..126); "
                "got 'é'",
            ),
            (
                {"type": "text", "value": "a\nb"},
                "value must contain only printable ASCII characters (32..126); "
                "got '\\n'",
            ),
        ]
        for step, fragment in cases:
            with self.subTest(step=step):
                self.runtime.commands.clear()
                with self.assertRaises(ScenarioError) as caught:
                    play_scenario(
                        self.runtime,
                        [{"type": "wait", "ms": 16}, step],
                    )
                self.assertIn(fragment, str(caught.exception))
                self.assertEqual(caught.exception.step, 1)
                self.assertEqual(self.runtime.commands, [])

    def test_text_accepts_printable_ascii_boundaries(self) -> None:
        play_scenario(self.runtime, [{"type": "text", "value": " ~"}])
        self.assertEqual(
            self.runtime.commands,
            [
                ("key", "press", "CHAR_32"),
                ("key", "release", "CHAR_32"),
                ("key", "press", "CHAR_126"),
                ("key", "release", "CHAR_126"),
            ],
        )


class TextRuntimeTest(unittest.TestCase):
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

    def test_runtime_key_sends_a_stable_char_token_to_the_engine(self) -> None:
        rt = self._runtime()
        rt.start()
        self.addCleanup(rt.stop)

        press = rt.key("press", "CHAR_65")
        release = rt.key("release", "char_122")

        self.assertIs(press["delivered"], True)
        self.assertEqual(press["key"], "CHAR_65")
        self.assertIs(release["delivered"], True)
        self.assertEqual(release["key"], "CHAR_122")

    def test_runtime_key_rejects_non_printable_char_tokens(self) -> None:
        rt = self._runtime()
        cases = [
            (
                "CHAR_31",
                "key CHAR_<code> must be within printable ASCII 32..126; got 31",
            ),
            (
                "CHAR_127",
                "key CHAR_<code> must be within printable ASCII 32..126; got 127",
            ),
            (
                "CHAR_",
                "key must be CHAR_<code> with a printable ASCII code 32..126; "
                "got 'CHAR_'",
            ),
            (
                "CHAR_x",
                "key must be CHAR_<code> with a printable ASCII code 32..126; "
                "got 'CHAR_x'",
            ),
        ]
        for token, fragment in cases:
            with self.subTest(token=token):
                with self.assertRaises(ScenarioError) as caught:
                    rt.key("press", token)
                self.assertIn(fragment, str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
