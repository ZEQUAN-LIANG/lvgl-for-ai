from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from control import Recording, Runtime, ScenarioError
import paths
from scripts.tests.support import read_ndjson

ENGINE_DIR = paths.ENGINE_DIR

LV_KEY_NAMES = (
    "UP",
    "DOWN",
    "RIGHT",
    "LEFT",
    "ESC",
    "DEL",
    "BACKSPACE",
    "ENTER",
    "NEXT",
    "PREV",
    "HOME",
    "END",
)


def input_rows(session_dir: Path) -> list[dict]:
    return [
        row
        for row in read_ndjson(session_dir / "timeline.ndjson")
        if row["type"] == "input"
    ]


def focus_lines(session_dir: Path) -> list[str]:
    log_text = (session_dir / "engine.log").read_text(encoding="utf-8")
    return [
        line
        for line in log_text.splitlines()
        if "[app]" in line and line.endswith("focused")
    ]


class KeypadIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self) -> Runtime:
        return Runtime(
            lvgl="9.6", build=True, sessions_root=self.sessions_root
        )

    def test_keypad_enter_clicks_the_focused_button(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        press = rt.key("press", "ENTER")
        release = rt.key("release", "ENTER")
        self.assertIs(press["delivered"], True)
        self.assertIs(release["delivered"], True)

        rows = input_rows(rt.session_dir)
        self.assertEqual(
            [
                (row["device"], row["action"], row["key"], row["delivered"])
                for row in rows
            ],
            [
                ("key", "press", "ENTER", True),
                ("key", "release", "ENTER", True),
            ],
        )
        log_text = (rt.session_dir / "engine.log").read_text(encoding="utf-8")
        self.assertIn("[app] demo_button clicked", log_text)

        self.assertIn("[app] focus group created", log_text)

    def test_every_lv_key_name_reaches_the_keypad_indev(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        names = LV_KEY_NAMES
        for name in names:
            self.assertIs(rt.key("press", name)["delivered"], True)
            self.assertIs(rt.key("release", name)["delivered"], True)

        rows = input_rows(rt.session_dir)
        self.assertEqual(len(rows), len(names) * 2)
        self.assertEqual(
            [(row["action"], row["key"]) for row in rows],
            [
                (action, name)
                for name in names
                for action in ("press", "release")
            ],
        )
        self.assertTrue(all(row["delivered"] is True for row in rows))

    def test_unknown_key_raises_scenario_error_with_step_and_name(
        self,
    ) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        with self.assertRaises(ScenarioError) as caught:
            rt.input(
                [
                    {
                        "at_ms": 0,
                        "device": "key",
                        "action": "press",
                        "key": "UP",
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
        self.assertIn("INSERT", str(caught.exception))

        self.assertEqual(input_rows(rt.session_dir), [])
        self.assertIs(rt.key("press", "UP")["delivered"], True)


class EncoderIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self) -> Runtime:
        return Runtime(
            lvgl="9.6", build=True, sessions_root=self.sessions_root
        )

    def test_encoder_turn_delivers_diff_and_moves_focus_in_sign_order(
        self,
    ) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        plus = rt.encoder("turn", 1)
        minus = rt.encoder("turn", -1)
        self.assertIs(plus["delivered"], True)
        self.assertIs(minus["delivered"], True)

        rows = input_rows(rt.session_dir)
        self.assertEqual(
            [
                (row["device"], row["action"], row["diff"], row["delivered"])
                for row in rows
            ],
            [
                ("encoder", "turn", 1, True),
                ("encoder", "turn", -1, True),
            ],
        )
        self.assertEqual(
            focus_lines(rt.session_dir),
            [
                "[app] panel focused",
                "[app] demo_button focused",
                "[app] title focused",
                "[app] demo_button focused",
            ],
        )

    def test_encoder_diff_is_signed_and_can_repeat(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        replies = rt.input(
            [
                {"at_ms": 0, "device": "encoder", "action": "turn", "diff": 2},
                {
                    "at_ms": 16,
                    "device": "encoder",
                    "action": "turn",
                    "diff": -3,
                },
            ]
        )
        self.assertIs(replies[0]["delivered"], True)
        self.assertIs(replies[1]["delivered"], True)
        rows = input_rows(rt.session_dir)
        self.assertEqual([row["diff"] for row in rows], [2, -3])
        self.assertEqual([row["t_ms"] for row in rows], [0, 16])

    def test_encoder_diff_is_consumed_by_one_read(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()

        rt.encoder("turn", 1)
        rt.tick(16)
        rt.wait(48)

        self.assertEqual(
            focus_lines(rt.session_dir),
            [
                "[app] panel focused",
                "[app] demo_button focused",
                "[app] title focused",
            ],
        )
        rows = input_rows(rt.session_dir)
        self.assertEqual(
            [(row["device"], row["diff"]) for row in rows], [("encoder", 1)]
        )


class KeySequenceDeterminismTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_same_key_sequence_produces_identical_timeline_rows(self) -> None:
        sequence = [
            ("press", "DOWN"),
            ("release", "DOWN"),
            ("press", "ENTER"),
            ("release", "ENTER"),
            ("press", "ESC"),
            ("release", "ESC"),
        ]

        def run_once(name: str) -> list[dict]:
            rt = Runtime(
                lvgl="9.6", build=True, sessions_root=self.root / name
            )
            try:
                rt.start()
                for action, key in sequence:
                    rt.key(action, key)
                rt.encoder("turn", 1)
                rt.tick(16)
            finally:
                rt.stop()
            return Recording.open(rt.session_dir).timeline()

        first = run_once("first")
        second = run_once("second")
        self.assertEqual(first, second)
        self.assertEqual(len(input_rows_from_rows(first)), 7)


def input_rows_from_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["type"] == "input"]


class ToolScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_engine_sources_never_create_a_focus_group(self) -> None:
        offenders = []
        for path in sorted(ENGINE_DIR.glob("*.[ch]")):
            if "lv_group_create" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_ready_capabilities_include_keypad_and_encoder(self) -> None:
        rt = Runtime(lvgl="9.6", build=True, sessions_root=self.sessions_root)
        self.addCleanup(rt.stop)
        rt.start()
        self.assertIn("key", rt.ready["capabilities"])
        self.assertIn("encoder", rt.ready["capabilities"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
