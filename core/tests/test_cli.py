"""Thin CLI: flag mapping, --json, exit codes, idle and the real scenario run.

Unit tests replace ``cli.Runtime`` with ``FakeRuntime``; the integration tests
below run the real engine into a temporary session root.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cli
from fake_runtime import FakeRuntime
from lvgl_ai import (
    BuildError,
    EngineNotFound,
    LinkError,
    ProtocolError,
    Recording,
    Runtime,
    RuntimeCrash,
    ScenarioError,
    play_scenario,
)
from lvgl_ai import paths

TOOL_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = TOOL_ROOT / "cli.py"
SIGINT_DRIVER = Path(__file__).with_name("sigint_idle_driver.py")
SETTINGS_SCENARIO = paths.REPO_ROOT / "user" / "scenarios" / "settings.json"


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def one_json(text: str) -> dict:
    lines = text.splitlines()
    if len(lines) != 1:
        raise AssertionError(f"expected exactly one stdout line, got {lines!r}")
    return json.loads(lines[0])


class CliUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _patch_runtime(self, **kwargs) -> tuple[FakeRuntime, mock.MagicMock]:
        fake = FakeRuntime(**kwargs)
        patcher = mock.patch.object(cli, "Runtime", return_value=fake)
        factory = patcher.start()
        self.addCleanup(patcher.stop)
        return fake, factory

    def _scenario(self, **extra) -> Path:
        document = {
            "schema": "lvgl-ai-scenario-v1",
            "name": "unit",
            "steps": [
                {"type": "click_at", "x": 112, "y": 324},
                {"type": "wait", "ms": 16},
                {"type": "mark", "id": "done"},
                {"type": "snapshot", "label": "after_click"},
            ],
        }
        document.update(extra)
        path = self.root / "scenario.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_defaults_map_to_recording_runtime(self) -> None:
        fake, factory = self._patch_runtime()
        code, out, err = run_cli([])

        factory.assert_called_once_with(
            lvgl=None, build=True, record=True
        )
        self.assertEqual(code, 0)
        self.assertEqual(fake.start_calls, 1)
        self.assertEqual(fake.stop_calls, 1)
        self.assertEqual(fake.commands, [])
        self.assertEqual(out.strip(), str(fake.session_dir))
        self.assertEqual(err, "")

    def test_record_defaults_on_and_no_record_disables_it(self) -> None:
        cases = [([], True), (["--record"], True), (["--no-record"], False)]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                fake = FakeRuntime()
                with mock.patch.object(cli, "Runtime", return_value=fake) as factory:
                    code, _, _ = run_cli(argv)
                self.assertEqual(code, 0)
                factory.assert_called_once_with(
                    lvgl=None, build=True, record=expected
                )

    def test_record_changed_only_is_opt_in(self) -> None:
        fake = FakeRuntime()
        with mock.patch.object(cli, "Runtime", return_value=fake) as factory:
            code, _, _ = run_cli(["--record-changed-only"])
        self.assertEqual(code, 0)
        factory.assert_called_once_with(
            lvgl=None,
            build=True,
            record=True,
            record_changed_only=True,
        )

    def test_no_build_maps_to_build_false_and_default_stays_true(self) -> None:
        cases = [([], True), (["--build"], True), (["--no-build"], False)]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                fake = FakeRuntime()
                with mock.patch.object(cli, "Runtime", return_value=fake) as factory:
                    code, _, _ = run_cli(argv)
                self.assertEqual(code, 0)
                factory.assert_called_once_with(
                    lvgl=None, build=expected, record=True
                )

    def test_scenario_is_played_and_json_reports_the_session(self) -> None:
        fake, _ = self._patch_runtime()
        code, out, err = run_cli(
            ["--scenario", str(self._scenario()), "--json"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        payload = one_json(out)
        self.assertEqual(payload["session_id"], fake.session_id)
        self.assertEqual(payload["manifest_path"], str(fake.manifest_path))
        self.assertIsNone(payload["error"])
        self.assertEqual(
            fake.commands,
            [
                ("pointer", "down", 112, 324),
                ("wait", 64),
                ("pointer", "up", 112, 324),
                ("wait", 16),
                ("mark", "done"),
                ("snapshot", "after_click"),
            ],
        )

    def test_app_flag_is_forwarded_and_reported(self) -> None:
        fake, factory = self._patch_runtime(app="coffee")
        code, out, err = run_cli(["--app", "coffee", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        factory.assert_called_once_with(
            lvgl=None, build=True, record=True, app="coffee"
        )
        self.assertEqual(one_json(out)["app"], "coffee")

    def test_scenario_app_is_used_when_the_flag_is_omitted(self) -> None:
        _, factory = self._patch_runtime(app="xiaohongshu")
        code, _, _ = run_cli(
            ["--scenario", str(self._scenario(app="xiaohongshu"))]
        )

        self.assertEqual(code, 0)
        factory.assert_called_once_with(
            lvgl=None,
            build=True,
            record=True,
            app="xiaohongshu",
        )

    def test_app_flag_overrides_the_scenario_app(self) -> None:
        _, factory = self._patch_runtime(app="xiaohongshu")
        code, _, _ = run_cli(
            [
                "--scenario",
                str(self._scenario(app="coffee")),
                "--app",
                "xiaohongshu",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(factory.call_args.kwargs["app"], "xiaohongshu")

    def test_invalid_app_is_a_harness_error(self) -> None:
        code, _, err = run_cli(["--app", "bad app"])
        self.assertEqual(code, 2)
        self.assertIn("app must match", err)

    def test_build_link_and_crash_map_to_exit_1(self) -> None:
        cases = [
            BuildError("compile failed"),
            LinkError("undefined symbol"),
            RuntimeCrash("engine died", exit_code=3),
            RuntimeCrash("engine not running"),
        ]
        for error in cases:
            with self.subTest(error=type(error).__name__):
                fake, _ = self._patch_runtime(start_error=error)
                code, out, err = run_cli(["--json"])
                self.assertEqual(code, 1)
                payload = one_json(out)
                self.assertIsNotNone(payload["error"])
                self.assertIn(str(error), err)

    def test_harness_errors_map_to_exit_2(self) -> None:
        cases = [
            EngineNotFound(
                "missing/lvgl_engine",
                configure_command=["cmake", "-S", "engine"],
                build_command=["cmake", "--build", "build"],
            ),
            ProtocolError("bad seq", raw="{", seq=1),
            ScenarioError("step 0: bad", step=0),
            FileNotFoundError("scenario.json"),
        ]
        for error in cases:
            with self.subTest(error=type(error).__name__):
                fake, _ = self._patch_runtime(start_error=error)
                code, out, err = run_cli(["--json"])
                self.assertEqual(code, 2)
                payload = one_json(out)
                self.assertIsNotNone(payload["error"])
                self.assertIn(str(error), err)

    def test_play_time_errors_keep_their_exit_layer(self) -> None:
        cases = [
            (RuntimeCrash("engine died"), 1),
            (ScenarioError("step 0: bad", step=0), 2),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                fake, _ = self._patch_runtime(errors={"pointer": error})
                code, out, _ = run_cli(
                    ["--scenario", str(self._scenario()), "--json"]
                )
                self.assertEqual(code, expected)
                payload = one_json(out)
                self.assertEqual(payload["session_id"], fake.session_id)
                self.assertIsNotNone(payload["error"])

    def test_idle_and_scenario_are_mutually_exclusive(self) -> None:
        code, out, err = run_cli(["--idle", "--scenario", "x.json"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("not allowed with", err)

    def test_interrupt_before_the_session_starts_is_a_harness_error(self) -> None:
        fake, _ = self._patch_runtime(start_error=KeyboardInterrupt())
        code, out, err = run_cli(["--idle", "--json"])

        self.assertEqual(code, 2)
        payload = one_json(out)
        self.assertIsNone(payload["session_id"])
        self.assertIsNone(payload["manifest_path"])
        self.assertEqual(payload["error"]["code"], "harness_error")
        self.assertIn("interrupted before the session started", err)
        self.assertEqual(fake.start_calls, 1)
        self.assertEqual(fake.stop_calls, 1)

    def test_idle_engine_exit_is_a_runtime_crash(self) -> None:
        fake, _ = self._patch_runtime()
        fake.exit_code = 3
        with mock.patch.object(cli, "_wait_for_interrupt", return_value=None):
            code, out, err = run_cli(["--idle", "--json"])

        self.assertEqual(code, 1)
        payload = one_json(out)
        self.assertEqual(payload["session_id"], fake.session_id)
        self.assertEqual(payload["error"]["code"], "crash")
        self.assertIn("engine exited with 3", err)

    def test_idle_stops_cleanly_on_keyboard_interrupt(self) -> None:
        fake, _ = self._patch_runtime()
        with mock.patch.object(
            cli, "_wait_for_interrupt", side_effect=KeyboardInterrupt
        ):
            code, out, err = run_cli(["--idle", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(fake.start_calls, 1)
        self.assertEqual(fake.stop_calls, 1)
        self.assertEqual(fake.commands, [])
        self.assertEqual(one_json(out)["session_id"], fake.session_id)
        self.assertIn("idle", err)

    def test_unreadable_scenario_with_app_is_recorded_after_startup(self) -> None:
        path = self.root / "bad-encoding.json"
        path.write_bytes(b"\xff\xfe\x00")
        fake, _ = self._patch_runtime(app="coffee")
        code, out, err = run_cli(
            ["--scenario", str(path), "--app", "coffee", "--json"]
        )

        self.assertEqual(code, 2)
        payload = one_json(out)
        self.assertEqual(payload["session_id"], fake.session_id)
        self.assertEqual(payload["error"]["code"], "harness_error")
        self.assertEqual(fake.start_calls, 1)
        self.assertIsInstance(fake.recorded_errors[-1], UnicodeDecodeError)
        self.assertTrue(err)

    def test_unreadable_scenario_without_app_keeps_the_old_pre_start_error(
        self,
    ) -> None:
        path = self.root / "bad-encoding.json"
        path.write_bytes(b"\xff\xfe\x00")
        fake, _ = self._patch_runtime()
        with self.assertRaises(UnicodeDecodeError):
            run_cli(["--scenario", str(path), "--json"])
        self.assertEqual(fake.start_calls, 0)

    def test_missing_scenario_file_is_a_harness_error_after_startup(self) -> None:
        fake, _ = self._patch_runtime()
        code, out, _ = run_cli(
            ["--scenario", str(self.root / "missing.json"), "--json"]
        )
        self.assertEqual(code, 2)
        payload = one_json(out)
        self.assertEqual(payload["session_id"], fake.session_id)
        self.assertEqual(payload["error"]["code"], "scenario_error")

    def test_python_isolated_help_works_from_another_directory(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(CLI_PATH), "--help"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: cli.py", result.stdout)


class CliRealEngineIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_cli_scenario_timeline_matches_the_library_path(self) -> None:
        library_root = self.root / "library"
        rt = Runtime(lvgl="9.6", build=True, sessions_root=library_root)
        rt.start()
        play_scenario(rt, SETTINGS_SCENARIO)
        rt.stop()
        library_rows = Recording.open(rt.session_dir).timeline()

        cli_root = self.root / "cli"
        env = dict(os.environ)
        env["LVGL_AI_SESSIONS_ROOT"] = str(cli_root)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(CLI_PATH),
                "--lvgl", "9.6",
                "--record",
                "--scenario", str(SETTINGS_SCENARIO),
                "--json",
            ],
            cwd=str(paths.REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = one_json(result.stdout)
        self.assertTrue(Path(payload["manifest_path"]).is_file())
        recording = Recording.open(payload["manifest_path"])
        self.assertEqual(recording.manifest["status"], "ok")
        self.assertEqual(recording.timeline(), library_rows)

    def test_idle_session_finishes_its_manifest_on_interrupt(self) -> None:
        sessions_root = self.root / "idle"
        with mock.patch.dict(
            os.environ, {"LVGL_AI_SESSIONS_ROOT": str(sessions_root)}
        ), mock.patch.object(
            cli, "_wait_for_interrupt", side_effect=KeyboardInterrupt
        ):
            code, out, err = run_cli(["--idle", "--json"])

        self.assertEqual(code, 0, err)
        payload = one_json(out)
        self.assertIsNone(payload["error"])
        recording = Recording.open(payload["manifest_path"])
        self.assertEqual(recording.manifest["status"], "ok")
        self.assertEqual(recording.manifest["id"], payload["session_id"])
        self.assertGreaterEqual(len(recording.frames), 1)
        self.assertEqual(recording.timeline()[-1]["type"], "end")
        self.assertIn("[app] app_create", recording.log())

    def test_idle_stops_on_a_real_os_sigint(self) -> None:
        sessions_root = self.root / "sigint"
        result = subprocess.run(
            [sys.executable, "-I", str(SIGINT_DRIVER), str(sessions_root)],
            cwd=str(paths.REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = one_json(result.stdout)
        recording = Recording.open(payload["manifest_path"])
        self.assertEqual(recording.manifest["status"], "ok")
        self.assertIsNone(recording.manifest["error"])
        self.assertEqual(recording.timeline()[-1]["type"], "end")
        self.assertIn("[app] app_create", recording.log())


if __name__ == "__main__":
    unittest.main(verbosity=2)
