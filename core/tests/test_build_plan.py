
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from lvgl_ai import BuildError, EngineNotFound, LinkError, paths
from lvgl_ai.control.build import BuildResult, format_build_log
from lvgl_ai.control.build_plan import BUILD_TIMEOUT_S, BuildPlan
from lvgl_ai.control.locks import BuildLock


def build_result(
    returncode: int = 0, *, stdout: str = "", stderr: str = ""
) -> BuildResult:
    return BuildResult(
        command=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=1.0,
    )


class ScriptedRunner:

    def __init__(self, *results: BuildResult | BaseException) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    def __call__(self, command, *, timeout, env=None):
        self.calls.append(
            {"command": list(command), "timeout": timeout, "env": env}
        )
        result = (
            self.results.pop(0)
            if self.results
            else build_result()
        )
        if isinstance(result, BaseException):
            raise result
        return BuildResult(
            command=list(command),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
        )


class BuildPlanCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lvgl_src = self.root / "lvgl-src" / "9.6"
        self.build_dir = self.root / "build" / "lvgl_9_6"
        self.engine_dir = self.root / "core" / "engine"
        self.user_app_dir = self.root / "user" / "app"
        self.zlib_src = self.root / "third_party" / "zlib"
        self.libpng_src = self.root / "third_party" / "libpng"
        for path in (
            self.lvgl_src,
            self.engine_dir,
            self.user_app_dir,
            self.zlib_src,
            self.libpng_src,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def plan(self, runner=None, **overrides) -> BuildPlan:
        options = {
            "lvgl_src": self.lvgl_src,
            "build_dir": self.build_dir,
            "engine_dir": self.engine_dir,
            "user_app_dir": self.user_app_dir,
            "zlib_src": self.zlib_src,
            "libpng_src": self.libpng_src,
            "sdk_dir": self.root / "sdk" / "9.6",
            "ccache": False,
            "missing_tools": lambda: [],
            "runner": runner or ScriptedRunner(),
        }
        options.update(overrides)
        return BuildPlan("9.6", **options)

    def write_cache(
        self,
        *,
        version: str = "9.6",
        lvgl_src: Path | None = None,
        user_app_dir: Path | None = None,
        home: Path | None = None,
        ninja: bool = True,
    ) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        values = {
            "LVGL_AI_LVGL_SRC": self.lvgl_src if lvgl_src is None else lvgl_src,
            "LVGL_AI_LVGL_VERSION": version,
            "LVGL_AI_USER_APP_DIR": (
                self.user_app_dir if user_app_dir is None else user_app_dir
            ),
            "LVGL_AI_ZLIB_SRC": self.zlib_src,
            "LVGL_AI_LIBPNG_SRC": self.libpng_src,
            "CMAKE_HOME_DIRECTORY": (
                self.engine_dir if home is None else home
            ),
        }
        lines = [f"{name}:UNINITIALIZED={value}" for name, value in values.items()]
        (self.build_dir / "CMakeCache.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        if ninja:
            (self.build_dir / "build.ninja").write_text("", encoding="utf-8")

    def built_engine_path(self) -> Path:
        return self.build_dir / paths.engine_filename()

    def write_built_engine(self, data: bytes = b"built") -> Path:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        engine = self.built_engine_path()
        engine.write_bytes(data)
        return engine


class PreflightTest(BuildPlanCase):
    def test_missing_lvgl_source_reports_the_recovery_paths(self) -> None:
        missing = self.root / "missing-lvgl"
        plan = self.plan(lvgl_src=missing)
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        message = str(caught.exception)
        self.assertIn("LVGL source not found", message)
        self.assertIn(str(missing), message)
        self.assertIn("fetch_lvgl.py", message)
        self.assertIn("LVGL_AI_LVGL_SRC", message)
        self.assertIn("--no-build", message)
        self.assertEqual(caught.exception.command, plan.configure_command)

    def test_missing_png_sources_report_the_fetch_command(self) -> None:
        missing = self.root / "missing-zlib"
        plan = self.plan(zlib_src=missing)
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        message = str(caught.exception)
        self.assertIn("PNG encoder source not found", message)
        self.assertIn(str(missing), message)
        self.assertIn("fetch_png.py", message)
        self.assertEqual(caught.exception.command, plan.configure_command)

    def test_missing_tools_are_named_with_the_install_hint(self) -> None:
        plan = self.plan(
            missing_tools=lambda: ["cmake", "ninja", "gcc"]
        )
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        message = str(caught.exception)
        self.assertIn("build tools not found on PATH: cmake, ninja, gcc", message)
        self.assertIn("CMake >= 3.20", message)
        self.assertIn("--no-build", message)
        self.assertEqual(caught.exception.command, plan.configure_command)

    def test_an_injected_build_command_skips_preflight(self) -> None:
        checked: list[str] = []

        def missing_tools() -> list[str]:
            checked.append("called")
            return ["cmake"]

        plan = self.plan(
            lvgl_src=self.root / "missing-lvgl",
            build=["gcc", "app.c"],
            missing_tools=missing_tools,
        )
        self.assertIsNone(plan.preflight())
        self.assertEqual(checked, [], "the default tool check must not run")

    def test_no_build_execution_does_not_run_preflight(self) -> None:
        plan = self.plan(
            lvgl_src=self.root / "missing-lvgl",
            missing_tools=lambda: ["cmake"],
        )
        outcome = plan.execute(build=False)
        self.assertEqual(
            outcome.log_text,
            "# build skipped (build=False)\n"
            f"# engine: {self.built_engine_path()}\n",
        )


class ConfigureTriggerTest(BuildPlanCase):
    def test_build_subprocesses_get_a_writable_temp_dir(self) -> None:
        runner = ScriptedRunner()
        plan = self.plan(runner=runner)
        plan.configure()
        call = runner.calls[0]
        temp_dir = (self.build_dir / ".build-tmp").resolve()
        self.assertEqual(call["env"]["TMP"], str(temp_dir))
        self.assertEqual(call["env"]["TEMP"], str(temp_dir))
        self.assertTrue(temp_dir.is_dir())


    def test_an_absent_cache_requires_configure(self) -> None:
        self.assertTrue(self.plan().needs_configure())

    def test_a_cache_without_build_ninja_requires_configure(self) -> None:
        self.write_cache(ninja=False)
        self.assertTrue(self.plan().needs_configure())

    def test_matching_cache_does_not_require_configure(self) -> None:
        self.write_cache()
        self.assertFalse(self.plan().needs_configure())

    def test_changed_cached_values_require_configure(self) -> None:
        cases = {
            "version": {"version": "9.5"},
            "lvgl source": {"lvgl_src": self.root / "other-lvgl"},
            "user app": {"user_app_dir": self.root / "other-app"},
            "moved checkout": {"home": self.root / "old-checkout" / "core" / "engine"},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                self.write_cache(**overrides)
                self.assertTrue(self.plan().needs_configure())

    def test_a_missing_cache_entry_requires_configure(self) -> None:
        self.write_cache()
        cache = self.build_dir / "CMakeCache.txt"
        kept = [
            line
            for line in cache.read_text(encoding="utf-8").splitlines()
            if not line.startswith("LVGL_AI_LVGL_SRC")
        ]
        cache.write_text("\n".join(kept) + "\n", encoding="utf-8")
        self.assertTrue(self.plan().needs_configure())

    def test_the_plan_engine_directory_participates_in_the_cache_check(self) -> None:
        moved = self.root / "moved" / "core" / "engine"
        self.write_cache()
        self.assertTrue(self.plan(engine_dir=moved).needs_configure())

        self.write_cache(home=moved)
        self.assertFalse(self.plan(engine_dir=moved).needs_configure())

    def test_a_stale_cache_runs_configure_then_build(self) -> None:
        runner = ScriptedRunner()
        plan = self.plan(runner)
        outcome = plan.execute(build=True)

        self.assertEqual(
            [call["command"] for call in runner.calls],
            [plan.configure_command, plan.build_command],
        )
        self.assertEqual(
            [call["timeout"] for call in runner.calls],
            [BUILD_TIMEOUT_S, BUILD_TIMEOUT_S],
        )
        expected = "\n".join(
            [
                "# build mode: source",
                format_build_log(
                    BuildResult(
                        command=plan.configure_command,
                        returncode=0,
                        stdout="",
                        stderr="",
                        duration_ms=1.0,
                    ),
                    "configure",
                ),
                format_build_log(
                    BuildResult(
                        command=plan.build_command,
                        returncode=0,
                        stdout="",
                        stderr="",
                        duration_ms=1.0,
                    ),
                    "build",
                ),
            ]
        )
        self.assertEqual(outcome.log_text, expected)
        self.assertEqual(outcome.engine_path, self.built_engine_path())
        self.assertFalse(outcome.engine_path.exists())

    def test_a_matching_cache_skips_configure_and_records_the_skip(self) -> None:
        self.write_cache()
        runner = ScriptedRunner()
        plan = self.plan(runner)
        outcome = plan.execute(build=True)

        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0]["command"], plan.build_command)
        expected = "\n".join(
            [
                "# build mode: source",
                "# phase: configure\n"
                f"# skipped: cache matches {self.build_dir / 'CMakeCache.txt'}\n",
                format_build_log(
                    BuildResult(
                        command=plan.build_command,
                        returncode=0,
                        stdout="",
                        stderr="",
                        duration_ms=1.0,
                    ),
                    "build",
                ),
            ]
        )
        self.assertEqual(outcome.log_text, expected)


class BuildFailureTest(BuildPlanCase):
    def test_configure_failure_is_a_build_error_with_the_phase_log(self) -> None:
        runner = ScriptedRunner(
            build_result(returncode=1, stdout="CMake Error: no generator\n")
        )
        plan = self.plan(runner)
        with self.assertRaises(BuildError) as caught:
            plan.execute(build=True)
        error = caught.exception
        self.assertEqual(error.command, plan.configure_command)
        self.assertIn("# phase: configure", error.log_text)
        self.assertIn("CMake Error: no generator", error.log_text)
        self.assertIn("build failed:", str(error))
        self.assertEqual(len(runner.calls), 1)

    def test_build_failure_keeps_the_successful_configure_phase(self) -> None:
        runner = ScriptedRunner(
            build_result(),
            build_result(
                returncode=1,
                stdout="app.c:3:5: error: expected ';'\n",
            ),
        )
        plan = self.plan(runner)
        with self.assertRaises(BuildError) as caught:
            plan.execute(build=True)
        error = caught.exception
        self.assertEqual(error.command, plan.build_command)
        self.assertTrue(
            error.log_text.startswith("# build mode: source\n# phase: configure\n")
        )
        self.assertIn("# phase: build\n", error.log_text)
        self.assertEqual(error.first_error["file"], "app.c")
        self.assertEqual(error.first_error["line"], 3)
        self.assertIn("app.c:3:5: expected ';'", str(error))

    def test_build_failure_after_a_skipped_configure_keeps_the_skip_row(self) -> None:
        self.write_cache()
        runner = ScriptedRunner(
            build_result(returncode=1, stderr="ninja: build stopped\n")
        )
        plan = self.plan(runner)
        with self.assertRaises(BuildError) as caught:
            plan.execute(build=True)
        error = caught.exception
        self.assertTrue(
            error.log_text.startswith(
                "# build mode: source\n"
                "# phase: configure\n"
                f"# skipped: cache matches {self.build_dir / 'CMakeCache.txt'}\n"
            )
        )
        self.assertIn("ninja: build stopped", error.log_text)

    def test_link_failure_is_a_link_error_with_unresolved_symbols(self) -> None:
        runner = ScriptedRunner(
            build_result(),
            build_result(
                returncode=1,
                stderr=(
                    "/usr/bin/ld: app.o: undefined reference to `missing_symbol'\n"
                    "collect2: error: ld returned 1 exit status\n"
                ),
            ),
        )
        plan = self.plan(runner)
        with self.assertRaises(LinkError) as caught:
            plan.execute(build=True)
        error = caught.exception
        self.assertEqual(error.command, plan.build_command)
        self.assertIn("missing_symbol", error.unresolved_symbols)
        self.assertIn("undefined reference", str(error))
        self.assertIn("# phase: configure", error.log_text)
        self.assertIn("undefined reference", error.log_text)

    def test_configure_timeout_is_a_build_error(self) -> None:
        runner = ScriptedRunner(
            subprocess.TimeoutExpired(cmd="cmake", timeout=BUILD_TIMEOUT_S)
        )
        plan = self.plan(runner)
        with self.assertRaises(BuildError) as caught:
            plan.execute(build=True)
        error = caught.exception
        self.assertIn("configure timed out after 600s", str(error))
        self.assertEqual(error.command, plan.configure_command)
        self.assertIn("timed out", error.log_text)

    def test_build_timeout_is_a_build_error(self) -> None:
        self.write_cache()
        runner = ScriptedRunner(
            subprocess.TimeoutExpired(cmd="cmake", timeout=BUILD_TIMEOUT_S)
        )
        plan = self.plan(runner)
        with self.assertRaises(BuildError) as caught:
            plan.execute(build=True)
        error = caught.exception
        self.assertIn("build timed out after 600s", str(error))
        self.assertEqual(error.command, plan.build_command)
        self.assertIn("# skipped: cache matches", error.log_text)


class EngineResolutionTest(BuildPlanCase):
    def test_missing_engines_resolve_to_the_expected_build_output(self) -> None:
        self.assertEqual(self.plan().resolve_engine(), self.built_engine_path())

    def test_an_explicit_engine_path_is_never_replaced(self) -> None:
        explicit = self.root / "chosen-engine"
        plan = self.plan(engine_path=explicit)
        self.assertEqual(plan.engine_path, explicit)
        self.assertEqual(plan.resolve_engine(), explicit)

    def test_no_build_execution_names_the_build_engine_in_the_log(self) -> None:
        built = self.write_built_engine()
        runner = ScriptedRunner()
        outcome = self.plan(runner).execute(build=False)
        self.assertEqual(outcome.engine_path, built)
        self.assertEqual(
            outcome.log_text,
            "# build skipped (build=False)\n" f"# engine: {built}\n",
        )
        self.assertEqual(runner.calls, [])

    def test_missing_engine_error_carries_the_recovery_commands(self) -> None:
        plan = self.plan()
        plan.execute(build=False)
        error = plan.missing_engine_error()
        self.assertIsInstance(error, EngineNotFound)
        assert error is not None
        self.assertEqual(error.engine_path, str(self.built_engine_path()))
        self.assertEqual(error.configure_command, plan.configure_command)
        self.assertEqual(error.build_command, plan.build_command)
        self.assertFalse(hasattr(error, "prebuilt_path"))

    def test_engine_not_found_is_none_once_the_engine_exists(self) -> None:
        self.write_built_engine()
        plan = self.plan()
        plan.execute(build=False)
        self.assertIsNone(plan.missing_engine_error())

    def test_an_explicit_engine_path_is_reported_when_missing(self) -> None:
        explicit = self.root / "chosen-engine"
        plan = self.plan(engine_path=explicit)
        plan.execute(build=False)
        error = plan.missing_engine_error()
        assert error is not None
        self.assertEqual(error.engine_path, str(explicit))


class BuildDirIsolationTest(unittest.TestCase):
    def test_default_user_app_keeps_the_version_directory(self) -> None:
        self.assertEqual(
            paths.build_dir_for("9.6"),
            paths.build_dir_for("9.6", paths.USER_APP_DIR),
        )

    def test_exported_app_gets_a_stable_separate_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "sift_watch" / "src" / "app"
            second = root / "coffee" / "src" / "app"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            first_dir = paths.build_dir_for("9.6", first)
            self.assertEqual(first_dir, paths.build_dir_for("9.6", first))
            self.assertIn("_export_", first_dir.name)
            self.assertNotEqual(first_dir, paths.build_dir_for("9.6"))
            self.assertNotEqual(
                first_dir, paths.build_dir_for("9.6", second)
            )


class BuildLockTest(unittest.TestCase):
    def test_second_lock_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with BuildLock(tmp):
                with self.assertRaises(BuildError) as raised:
                    with BuildLock(tmp, timeout=0.2):
                        pass
            self.assertIn("build lock timeout", str(raised.exception))

    def test_lock_is_reusable_after_release(self) -> None:
        acquired: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            with BuildLock(tmp):
                acquired.append("first")
            with BuildLock(tmp, timeout=0.2):
                acquired.append("second")
        self.assertEqual(acquired, ["first", "second"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
