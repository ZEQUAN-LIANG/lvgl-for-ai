"""Scenario schema, command expansion, and the settings scenario on real LVGL.

Unit tests use ``FakeRuntime`` and never spawn a process. The integration test
plays ``user/scenarios/settings.json`` against the real engine; the demo
button covers x=32..192, y=300..348, so its center is (112, 324).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from lvgl_ai import Recording, Runtime, ScenarioError, play_scenario
from lvgl_ai import paths
from lvgl_ai import scenario as scenario_module
from lvgl_ai.scenario import load_scenario

SETTINGS_SCENARIO = paths.REPO_ROOT / "user" / "scenarios" / "settings.json"
BUTTON_CENTER = (112, 324)


def scenario_file(root: Path, steps: list[dict], **extra) -> Path:
    document = {"schema": "lvgl-ai-scenario-v1", "name": "test", "steps": steps}
    document.update(extra)
    path = root / "scenario.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class ScenarioExpansionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()

    def test_click_at_expands_to_down_wait_up(self) -> None:
        replies = play_scenario(
            self.runtime, [{"type": "click_at", "x": 112, "y": 324}]
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("pointer", "down", 112, 324),
                ("wait", 64),
                ("pointer", "up", 112, 324),
            ],
        )
        self.assertEqual(len(replies), 3)

    def test_click_at_honours_hold_ms(self) -> None:
        play_scenario(
            self.runtime,
            [{"type": "click_at", "x": 1, "y": 2, "hold_ms": 0}],
        )
        self.assertEqual(self.runtime.commands[1], ("wait", 0))

    def test_drag_expands_to_down_moves_up_and_drag_end_snapshot(self) -> None:
        play_scenario(
            self.runtime,
            [{"type": "drag", "from": [0, 0], "to": [100, 40], "steps": 4}],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("pointer", "down", 0, 0),
                ("pointer", "move", 25, 10),
                ("pointer", "move", 50, 20),
                ("pointer", "move", 75, 30),
                ("pointer", "move", 100, 40),
                ("pointer", "up", 100, 40),
                ("snapshot", "drag_end"),
            ],
        )

    def test_drag_defaults_to_eight_moves(self) -> None:
        play_scenario(
            self.runtime,
            [{"type": "drag", "from": [0, 0], "to": [80, 0]}],
        )
        moves = [command for command in self.runtime.commands if command[:2] == ("pointer", "move")]
        self.assertEqual(len(moves), 8)
        self.assertEqual(moves[-1], ("pointer", "move", 80, 0))

    def test_drag_interval_ms_advances_after_each_move(self) -> None:
        play_scenario(
            self.runtime,
            [
                {
                    "type": "drag",
                    "from": [0, 0],
                    "to": [30, 0],
                    "steps": 3,
                    "interval_ms": 16,
                }
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("pointer", "down", 0, 0),
                ("pointer", "move", 10, 0),
                ("wait", 16),
                ("pointer", "move", 20, 0),
                ("wait", 16),
                ("pointer", "move", 30, 0),
                ("wait", 16),
                ("pointer", "up", 30, 0),
                ("snapshot", "drag_end"),
            ],
        )

    def test_drag_interval_ms_zero_keeps_the_old_command_sequence(self) -> None:
        play_scenario(
            self.runtime,
            [
                {
                    "type": "drag",
                    "from": [0, 0],
                    "to": [100, 40],
                    "steps": 4,
                    "interval_ms": 0,
                }
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("pointer", "down", 0, 0),
                ("pointer", "move", 25, 10),
                ("pointer", "move", 50, 20),
                ("pointer", "move", 75, 30),
                ("pointer", "move", 100, 40),
                ("pointer", "up", 100, 40),
                ("snapshot", "drag_end"),
            ],
        )

    def test_pointer_step_sends_one_pointer_command_without_press_synthesis(self) -> None:
        play_scenario(
            self.runtime,
            [
                {"type": "pointer", "action": "move", "x": 12, "y": 34},
                {"type": "pointer", "action": "down", "x": 1, "y": 2},
                {"type": "pointer", "action": "up", "x": 3, "y": 4},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("pointer", "move", 12, 34),
                ("pointer", "down", 1, 2),
                ("pointer", "up", 3, 4),
            ],
        )

    def test_wait_accepts_ms_or_frames(self) -> None:
        play_scenario(
            self.runtime,
            [
                {"type": "wait", "ms": 48},
                {"type": "wait", "frames": 3},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [("wait", 48), ("wait", "frames", 3)],
        )

    def test_key_and_encoder_steps_expand_to_runtime_calls(self) -> None:
        play_scenario(
            self.runtime,
            [
                {"type": "key", "action": "press", "key": "enter"},
                {"type": "key", "action": "release", "key": "ENTER"},
                {"type": "encoder", "action": "turn", "diff": -2},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [
                ("key", "press", "ENTER"),
                ("key", "release", "ENTER"),
                ("encoder", "turn", -2),
            ],
        )

    def test_mark_and_snapshot_are_passed_through(self) -> None:
        play_scenario(
            self.runtime,
            [
                {"type": "mark", "id": "checkpoint"},
                {"type": "snapshot", "label": "after_click"},
            ],
        )
        self.assertEqual(
            self.runtime.commands,
            [("mark", "checkpoint"), ("snapshot", "after_click")],
        )

    def test_path_and_step_list_produce_the_same_commands(self) -> None:
        steps = [
            {"type": "click_at", "x": 112, "y": 324},
            {"type": "wait", "frames": 2},
            {"type": "drag", "from": [10, 10], "to": [20, 30], "steps": 2},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = scenario_file(Path(tmp), steps)
            play_scenario(self.runtime, path)
            from_path = list(self.runtime.commands)
            self.runtime.commands.clear()
            play_scenario(self.runtime, steps)
            from_list = list(self.runtime.commands)
        self.assertEqual(from_path, from_list)
        # click_at: 3 commands; wait: 1; drag: down + 2 moves + up + snapshot.
        self.assertEqual(len(from_path), 3 + 1 + 5)

    def test_play_scenario_does_not_manage_the_runtime_lifecycle(self) -> None:
        play_scenario(self.runtime, [{"type": "wait", "ms": 16}])
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertEqual(self.runtime.stop_calls, 0)

    def test_fake_runtime_start_and_stop_are_idempotent(self) -> None:
        self.assertIs(self.runtime.start(), self.runtime)
        session_id = self.runtime.session_id
        self.runtime.start()
        self.assertTrue(self.runtime.is_running)
        self.assertEqual(self.runtime.session_id, session_id)
        self.runtime.stop()
        self.runtime.stop()
        self.assertFalse(self.runtime.is_running)


class ScenarioValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()

    def assert_scenario_error(self, steps, fragment: str) -> ScenarioError:
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(self.runtime, steps)
        self.assertIn(fragment, str(caught.exception))
        return caught.exception

    def test_invalid_steps_are_rejected_before_any_command_runs(self) -> None:
        error = self.assert_scenario_error(
            [
                {"type": "wait", "ms": 16},
                {"type": "click_at", "x": 1},
            ],
            "step 1",
        )
        self.assertEqual(error.step, 1)
        self.assertEqual(self.runtime.commands, [])

    def test_unknown_step_type_is_rejected(self) -> None:
        self.assert_scenario_error([{"type": "toggle", "id": "demo_button"}], "type")

    def test_key_step_rejects_unknown_key_with_step_index(self) -> None:
        error = self.assert_scenario_error(
            [
                {"type": "wait", "ms": 16},
                {"type": "key", "action": "press", "key": "INSERT"},
            ],
            "step 1",
        )
        self.assertEqual(error.step, 1)
        self.assertIn("INSERT", str(error))

    def test_key_and_encoder_steps_are_validated(self) -> None:
        self.assert_scenario_error(
            [{"type": "key", "action": "tap", "key": "ENTER"}], "action"
        )
        self.assert_scenario_error(
            [{"type": "key", "action": "press"}], "key"
        )
        self.assert_scenario_error(
            [{"type": "encoder", "action": "turn", "diff": 32768}], "diff"
        )

    def test_pointer_step_validates_action_and_coordinates_before_any_command(self) -> None:
        cases = [
            (
                {"type": "pointer", "action": "tap", "x": 1, "y": 2},
                "pointer.action must be one of ['down', 'move', 'up']; got 'tap'",
            ),
            (
                {"type": "pointer", "x": 1, "y": 2},
                "pointer.action must be one of ['down', 'move', 'up']; got None",
            ),
            (
                {"type": "pointer", "action": "move", "y": 2},
                "x is required",
            ),
            (
                {"type": "pointer", "action": "move", "x": -1, "y": 2},
                "x must be >= 0; got -1",
            ),
            (
                {"type": "pointer", "action": "move", "x": 1, "y": True},
                "y must be an integer",
            ),
            (
                {"type": "pointer", "action": "move", "x": 1, "y": 2, "label": "x"},
                "unexpected field(s) label for pointer",
            ),
        ]
        for step, fragment in cases:
            with self.subTest(step=step):
                self.runtime.commands.clear()
                error = self.assert_scenario_error(
                    [{"type": "wait", "ms": 16}, step], fragment
                )
                self.assertEqual(error.step, 1)
                self.assertEqual(self.runtime.commands, [])

    def test_drag_interval_ms_must_be_a_non_negative_integer(self) -> None:
        cases = [
            (-1, "interval_ms must be >= 0; got -1"),
            (True, "interval_ms must be an integer"),
            (1.5, "interval_ms must be an integer"),
            ("16", "interval_ms must be an integer"),
        ]
        for value, fragment in cases:
            with self.subTest(value=value):
                self.runtime.commands.clear()
                error = self.assert_scenario_error(
                    [
                        {"type": "wait", "ms": 16},
                        {
                            "type": "drag",
                            "from": [0, 0],
                            "to": [1, 1],
                            "interval_ms": value,
                        },
                    ],
                    fragment,
                )
                self.assertEqual(error.step, 1)
                self.assertEqual(self.runtime.commands, [])

    def test_unknown_field_is_rejected(self) -> None:
        self.assert_scenario_error(
            [{"type": "mark", "id": "ok", "label": "typo"}], "unexpected field"
        )

    def test_wait_needs_exactly_one_of_ms_and_frames(self) -> None:
        self.assert_scenario_error([{"type": "wait"}], "exactly one")
        self.assert_scenario_error(
            [{"type": "wait", "ms": 1, "frames": 1}], "exactly one"
        )

    def test_negative_and_boolean_coordinates_are_rejected(self) -> None:
        self.assert_scenario_error([{"type": "click_at", "x": -1, "y": 0}], "x")
        self.assert_scenario_error(
            [{"type": "click_at", "x": True, "y": 0}], "x must be an integer"
        )
        self.assert_scenario_error(
            [{"type": "drag", "from": [0, 0], "to": [1]}], "to"
        )

    def test_drag_steps_must_be_positive(self) -> None:
        self.assert_scenario_error(
            [{"type": "drag", "from": [0, 0], "to": [1, 1], "steps": 0}],
            "steps",
        )

    def test_mark_and_snapshot_tokens_are_validated(self) -> None:
        self.assert_scenario_error([{"type": "mark", "id": "bad id"}], "id")
        self.assert_scenario_error(
            [{"type": "snapshot", "label": ""}], "label"
        )

    def test_empty_step_list_is_rejected(self) -> None:
        self.assert_scenario_error([], "must not be empty")

    def test_path_and_unsupported_object_are_rejected(self) -> None:
        self.assert_scenario_error({"steps": []}, "path or a list")


class ScenarioFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.runtime = FakeRuntime()

    def test_missing_file_raises_scenario_error(self) -> None:
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(self.runtime, self.root / "missing.json")
        self.assertIn("cannot read scenario", str(caught.exception))

    def test_invalid_json_raises_scenario_error(self) -> None:
        path = self.root / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(self.runtime, path)
        self.assertIn("invalid JSON", str(caught.exception))

    def test_wrong_schema_is_rejected(self) -> None:
        path = scenario_file(self.root, [{"type": "wait", "ms": 16}])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schema"] = "lvgl-ai-scenario-v0"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(self.runtime, path)
        self.assertIn("lvgl-ai-scenario-v1", str(caught.exception))

    def test_unknown_top_level_field_is_rejected(self) -> None:
        path = scenario_file(self.root, [{"type": "wait", "ms": 16}])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["target"] = "demo_button"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ScenarioError) as caught:
            play_scenario(self.runtime, path)
        self.assertIn("target", str(caught.exception))

    def test_app_is_preserved_in_the_normalized_document(self) -> None:
        path = scenario_file(
            self.root, [{"type": "wait", "ms": 16}], app="coffee"
        )
        self.assertEqual(load_scenario(path)["app"], "coffee")

    def test_invalid_app_is_rejected(self) -> None:
        path = scenario_file(
            self.root, [{"type": "wait", "ms": 16}], app="bad app"
        )
        with self.assertRaises(ScenarioError) as caught:
            load_scenario(path)
        self.assertIn("app", str(caught.exception))

    def test_lvgl_is_preserved_in_the_normalized_document(self) -> None:
        path = scenario_file(
            self.root, [{"type": "wait", "ms": 16}], lvgl="9.4"
        )
        self.assertEqual(load_scenario(path)["lvgl"], "9.4")

    def test_invalid_lvgl_is_rejected(self) -> None:
        for value in (9.4, "bad version", ""):
            with self.subTest(value=value):
                path = scenario_file(
                    self.root,
                    [{"type": "wait", "ms": 16}],
                    lvgl=value,
                )
                with self.assertRaises(ScenarioError) as caught:
                    load_scenario(path)
                self.assertIn("lvgl", str(caught.exception))

    def test_display_is_preserved_in_the_normalized_document(self) -> None:
        path = scenario_file(
            self.root,
            [{"type": "wait", "ms": 16}],
            display={"width": 640, "height": 480},
        )
        self.assertEqual(
            load_scenario(path)["display"], {"width": 640, "height": 480}
        )

    def test_display_is_optional_and_null_keeps_the_engine_default(self) -> None:
        path = scenario_file(self.root, [{"type": "wait", "ms": 16}])
        self.assertNotIn("display", load_scenario(path))
        path = scenario_file(
            self.root, [{"type": "wait", "ms": 16}], display=None
        )
        self.assertNotIn("display", load_scenario(path))

    def test_drag_interval_ms_defaults_to_zero(self) -> None:
        path = scenario_file(
            self.root,
            [{"type": "drag", "from": [0, 0], "to": [1, 1]}],
        )
        self.assertEqual(load_scenario(path)["steps"][0]["interval_ms"], 0)

    def test_display_bounds_are_inclusive(self) -> None:
        for width, height in ((1, 1), (4096, 4096)):
            with self.subTest(width=width, height=height):
                path = scenario_file(
                    self.root,
                    [{"type": "wait", "ms": 16}],
                    display={"width": width, "height": height},
                )
                self.assertEqual(
                    load_scenario(path)["display"],
                    {"width": width, "height": height},
                )

    def test_invalid_scenario_display_is_rejected(self) -> None:
        cases = [
            ("640x480", "display must be an object"),
            ({"width": 640}, "display.height is required"),
            (
                {"width": 640, "height": 480, "depth": 32},
                "display has unexpected field(s) depth",
            ),
            ({"width": 0, "height": 480}, "display.width must be >= 1"),
            ({"width": 640, "height": -1}, "display.height must be >= 1"),
            (
                {"width": 4097, "height": 480},
                "display.width must be <= 4096",
            ),
            (
                {"width": True, "height": 480},
                "display.width must be an integer",
            ),
            (
                {"width": 640.0, "height": 480},
                "display.width must be an integer",
            ),
            (
                {"width": "640", "height": 480},
                "display.width must be an integer",
            ),
        ]
        for display, fragment in cases:
            with self.subTest(display=display):
                path = scenario_file(
                    self.root,
                    [{"type": "wait", "ms": 16}],
                    display=display,
                )
                with self.assertRaises(ScenarioError) as caught:
                    load_scenario(path)
                self.assertIn(fragment, str(caught.exception))


class ScenarioIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.scenarios = self.root / "user" / "scenarios"
        self.scenarios.mkdir(parents=True)

    def _write(self, directory: Path, filename: str, **fields) -> Path:
        path = directory / filename
        path.write_text(
            json.dumps({
                "schema": "lvgl-ai-scenario-v1",
                "steps": [{"type": "wait", "ms": 16}],
                **fields,
            }),
            encoding="utf-8",
        )
        return path

    def test_entries_carry_seven_fields_and_invalid_errors(self) -> None:
        self._write(
            self.scenarios,
            "coffee.json",
            name="coffee",
            app="coffee",
            display={"width": 640, "height": 480},
        )
        self._write(self.scenarios, "plain.json", app="plain")
        bad = self.scenarios / "bad.json"
        bad.write_text("{", encoding="utf-8")

        entries = scenario_module.scenario_index(self.root)
        self.assertEqual(
            [entry["basename"] for entry in entries],
            ["bad.json", "coffee.json", "plain.json"],
        )
        for entry in entries:
            self.assertEqual(
                set(entry),
                {"path", "basename", "app", "name", "display", "valid", "error"},
            )

        by_name = {entry["basename"]: entry for entry in entries}
        self.assertEqual(
            by_name["coffee.json"],
            {
                "path": "user/scenarios/coffee.json",
                "basename": "coffee.json",
                "app": "coffee",
                "name": "coffee",
                "display": {"width": 640, "height": 480},
                "valid": True,
                "error": None,
            },
        )
        self.assertTrue(by_name["plain.json"]["valid"])
        self.assertIsNone(by_name["plain.json"]["name"])
        self.assertIsNone(by_name["plain.json"]["display"])

        self.assertFalse(by_name["bad.json"]["valid"])
        self.assertIsNone(by_name["bad.json"]["app"])
        self.assertIsNone(by_name["bad.json"]["name"])
        self.assertIsNone(by_name["bad.json"]["display"])
        self.assertIn("invalid JSON", by_name["bad.json"]["error"])
        self.assertIn("bad.json", by_name["bad.json"]["error"])

    def test_one_invalid_scenario_does_not_block_the_others(self) -> None:
        self._write(self.scenarios, "good.json", name="good", app="coffee")
        self._write(
            self.scenarios,
            "wrong_schema.json",
            schema="lvgl-ai-scenario-v0",
            app="coffee",
        )
        entries = scenario_module.scenario_index(self.root)
        by_name = {entry["basename"]: entry for entry in entries}
        self.assertTrue(by_name["good.json"]["valid"])
        self.assertFalse(by_name["wrong_schema.json"]["valid"])
        self.assertIn(
            "lvgl-ai-scenario-v1", by_name["wrong_schema.json"]["error"]
        )

    def test_index_accepts_an_independent_scenarios_dir(self) -> None:
        other = Path(self._tmp.name) / "display-scenarios"
        other.mkdir()
        self._write(
            other,
            "coffee.json",
            name="coffee",
            app="coffee",
            display={"width": 320, "height": 240},
        )
        entries = scenario_module.scenario_index(
            self.root, scenarios_dir=other
        )
        self.assertEqual(
            [entry["basename"] for entry in entries], ["coffee.json"]
        )
        self.assertEqual(entries[0]["app"], "coffee")
        self.assertEqual(
            entries[0]["display"], {"width": 320, "height": 240}
        )
        self.assertEqual(Path(entries[0]["path"]).name, "coffee.json")
        self.assertEqual(
            scenario_module.scenario_index(
                self.root, scenarios_dir=other / "missing"
            ),
            [],
        )


class ScenarioFileDragTimeTest(unittest.TestCase):
    def test_drag_interval_ms_scenario_file_emits_waits_between_moves(
        self,
    ) -> None:
        runtime = FakeRuntime()
        with tempfile.TemporaryDirectory() as tmp:
            path = scenario_file(
                Path(tmp),
                [
                    {
                        "type": "drag",
                        "from": [0, 0],
                        "to": [30, 0],
                        "steps": 3,
                        "interval_ms": 16,
                    }
                ],
            )
            play_scenario(runtime, path)

        self.assertEqual(
            runtime.commands,
            [
                ("pointer", "down", 0, 0),
                ("pointer", "move", 10, 0),
                ("wait", 16),
                ("pointer", "move", 20, 0),
                ("wait", 16),
                ("pointer", "move", 30, 0),
                ("wait", 16),
                ("pointer", "up", 30, 0),
                ("snapshot", "drag_end"),
            ],
        )


class ScenarioErrorMappingTest(unittest.TestCase):
    def test_runtime_errors_propagate_unchanged(self) -> None:
        from lvgl_ai import RuntimeCrash

        crash = RuntimeCrash("engine died", exit_code=3)
        runtime = FakeRuntime(errors={"pointer": crash})
        with self.assertRaises(RuntimeCrash) as caught:
            play_scenario(runtime, [{"type": "click_at", "x": 1, "y": 2}])
        self.assertIs(caught.exception, crash)


class SettingsScenarioIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_settings_scenario_runs_on_the_real_engine(self) -> None:
        rt = Runtime(
            lvgl="9.6",
            build=True,
            record_changed_only=False,
            sessions_root=self.sessions_root,
        )
        self.addCleanup(rt.stop)
        rt.start()
        replies = play_scenario(rt, SETTINGS_SCENARIO)
        self.assertEqual(len(replies), 3 + 1 + 1 + 1 + 7)
        rt.stop()

        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.manifest["status"], "ok")
        rows = recording.timeline()
        self.assertEqual(
            [row["type"] for row in rows],
            [
                "frame",
                "input",
                "frame",
                "frame",
                "frame",
                "frame",
                "wait",
                "input",
                "frame",
                "frame",
                "frame",
                "frame",
                "wait",
                "mark",
                "snapshot",
                "input",
                "input",
                "input",
                "input",
                "input",
                "input",
                "snapshot",
                "end",
            ],
        )
        inputs = [row for row in rows if row["type"] == "input"]
        self.assertEqual(
            [(row["action"], row["x"], row["y"]) for row in inputs],
            [
                ("down", 112, 324),
                ("up", 112, 324),
                ("down", 112, 324),
                ("move", 144, 324),
                ("move", 176, 324),
                ("move", 208, 324),
                ("move", 240, 324),
                ("up", 240, 324),
            ],
        )
        wait_rows = [row for row in rows if row["type"] == "wait"]
        self.assertEqual(len(wait_rows), 2)
        self.assertEqual(
            [row["id"] for row in rows if row["type"] == "mark"], ["after_click"]
        )
        snapshots = [row for row in rows if row["type"] == "snapshot"]
        self.assertEqual(
            [(row["label"], row["file"]) for row in snapshots],
            [
                ("after_click", "snapshots/001_after_click.png"),
                ("drag_end", "snapshots/002_drag_end.png"),
            ],
        )
        for row in snapshots:
            self.assertTrue((recording.path / row["file"]).is_file())
        self.assertEqual(len(recording.frames), 9)
        self.assertIn("[app] demo_button clicked", recording.log())

    def test_drag_interval_ms_advances_timeline_input_t_ms(self) -> None:
        rt = Runtime(lvgl="9.6", build=True, sessions_root=self.sessions_root)
        self.addCleanup(rt.stop)
        rt.start()
        path = scenario_file(
            Path(self._tmp.name),
            [
                {
                    "type": "drag",
                    "from": [0, 0],
                    "to": [120, 0],
                    "steps": 4,
                    "interval_ms": 16,
                }
            ],
        )
        play_scenario(rt, path)
        rt.stop()

        rows = Recording.open(rt.session_dir).timeline()
        moves = [
            row
            for row in rows
            if row["type"] == "input" and row["action"] == "move"
        ]
        self.assertEqual([row["t_ms"] for row in moves], [0, 16, 32, 48])
        self.assertGreater(moves[-1]["t_ms"], moves[0]["t_ms"])

    def test_path_and_list_forms_produce_the_same_timeline(self) -> None:
        steps = json.loads(SETTINGS_SCENARIO.read_text(encoding="utf-8"))["steps"]

        def play(source, name: str) -> list[dict]:
            rt = Runtime(
                lvgl="9.6",
                build=True,
                sessions_root=self.sessions_root / name,
            )
            try:
                rt.start()
                play_scenario(rt, source)
            finally:
                rt.stop()
            return Recording.open(rt.session_dir).timeline()

        self.assertEqual(play(SETTINGS_SCENARIO, "path"), play(steps, "list"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
