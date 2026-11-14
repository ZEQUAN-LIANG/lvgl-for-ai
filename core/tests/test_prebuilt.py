"""Prebuilt build selection, command construction and error mapping.

Everything drives ``BuildPlan`` through its scripted runner seam, so no
compiler, CMake, Ninja or LVGL source is required.  The SDK fixture is a
validated ``lvgl-ai-host-sdk-v1`` manifest with real hashes over dummy library
bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lvgl_ai.control import prebuilt
from lvgl_ai.control.build import BuildResult
from lvgl_ai.control.build_plan import BuildPlan
from lvgl_ai.control.errors import BuildError, LinkError
from lvgl_ai.control.prebuilt import REQUIRED_LIBS, versions_match

LIB_NAMES = list(REQUIRED_LIBS)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class WritingRunner:
    """Scripted runner that creates the output file each command writes."""

    def __init__(self, *, fail_on: str | None = None, stderr: str = "") -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.stderr = stderr

    def __call__(self, command, *, timeout, env=None):  # noqa: ANN001
        command = list(command)
        self.calls.append(command)
        phase = None
        if "-c" in command:
            phase = "compile"
        elif "-o" in command and any("--start-group" in part for part in command):
            phase = "link"
        if self.fail_on is not None and self.fail_on == phase:
            return BuildResult(
                command=command,
                returncode=1,
                stdout="",
                stderr=self.stderr,
                duration_ms=1.0,
            )
        output = None
        if phase == "compile":
            output = Path(command[command.index("-o") + 1])
        elif phase == "link":
            output = Path(command[command.index("-o") + 1])
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"object" if phase == "compile" else b"engine")
        return BuildResult(
            command=command,
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )

    def compile_calls(self) -> list[list[str]]:
        return [call for call in self.calls if "-c" in call]

    def link_calls(self) -> list[list[str]]:
        return [
            call for call in self.calls
            if any("--start-group" in part for part in call)
        ]


class PrebuiltCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.user_app = self.root / "user" / "app"
        self.user_app.mkdir(parents=True)
        (self.user_app / "app.c").write_text(
            '#include "lvgl.h"\nvoid app_create(void) {}\n',
            encoding="utf-8",
        )
        (self.user_app / "app.h").write_text(
            "#define APP_OK 1\n", encoding="utf-8"
        )
        self.engine_dir = self.root / "core" / "engine"
        self.engine_dir.mkdir(parents=True)
        (self.engine_dir / "main.c").write_text(
            "void app_create(void);\nint main(void) { app_create(); return 0; }\n",
            encoding="utf-8",
        )
        (self.engine_dir / "engine.h").write_text(
            "/* engine */\n", encoding="utf-8"
        )
        self.lvgl_src = self.root / "lvgl-src" / "9.6"
        self.build_dir = self.root / "build" / "lvgl_9_6"
        self.sdk_dir = self.make_sdk()

    def make_sdk(
        self, *, version: str = "9.6", compiler_version: str = "15.2.0"
    ) -> Path:
        sdk = self.root / "sdk" / version
        (sdk / "lib").mkdir(parents=True)
        (sdk / "include" / "lvgl").mkdir(parents=True)
        hashes = {}
        for index, name in enumerate(LIB_NAMES):
            data = f"library-{name}-{index}".encode()
            (sdk / "lib" / name).write_bytes(data)
            hashes[name] = sha256(data)
        (sdk / "lv_conf.h").write_text("#define LV_CONF_H 1\n", encoding="utf-8")
        manifest = {
            "schema": "lvgl-ai-host-sdk-v1",
            "lvgl_version": version,
            "lvgl_tag": "v9.6.0",
            "platform": "win64",
            "tool_version": "0.1.0",
            "compiler": {"id": "mingw-w64-gcc", "version": compiler_version},
            "defines": [
                "LV_CONF_INCLUDE_SIMPLE",
                "LV_KCONFIG_IGNORE",
                "LV_LVGL_H_INCLUDE_SIMPLE",
            ],
            "cflags": ["-std=gnu11", "-O2", "-Wall", "-Wextra"],
            "include_dirs": [".", "include", "include/lvgl"],
            "libs": list(LIB_NAMES),
            "link_flags": ["-lgdi32", "-luser32", "-static-libgcc"],
            "lv_conf_sha256": sha256((sdk / "lv_conf.h").read_bytes()),
            "sha256": hashes,
        }
        (sdk / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return sdk

    def plan(self, runner=None, *, mode="prebuilt", **overrides) -> BuildPlan:
        options = {
            "lvgl_src": self.lvgl_src,
            "build_dir": self.build_dir,
            "engine_dir": self.engine_dir,
            "user_app_dir": self.user_app,
            "zlib_src": self.root / "third_party" / "zlib",
            "libpng_src": self.root / "third_party" / "libpng",
            "sdk_dir": self.sdk_dir,
            "build_mode": mode,
            "compiler": self.root / "fake-gcc",
            "compiler_version": "15.2.0",
            "missing_tools": lambda: [],
            "runner": runner or WritingRunner(),
        }
        options.update(overrides)
        return BuildPlan("9.6", **options)


class SelectionTest(PrebuiltCase):
    def test_auto_prefers_source_when_the_tree_exists(self) -> None:
        self.lvgl_src.mkdir(parents=True)
        self.assertEqual(self.plan(mode="auto").mode, "source")

    def test_auto_uses_the_sdk_when_the_source_tree_is_missing(self) -> None:
        self.assertEqual(self.plan(mode="auto").mode, "prebuilt")

    def test_auto_keeps_the_source_error_when_neither_exists(self) -> None:
        plan = self.plan(mode="auto", sdk_dir=self.root / "missing-sdk")
        self.assertEqual(plan.mode, "source")

    def test_explicit_prebuilt_wins_over_an_existing_source_tree(self) -> None:
        self.lvgl_src.mkdir(parents=True)
        self.assertEqual(self.plan(mode="prebuilt").mode, "prebuilt")

    def test_explicit_source_wins_over_an_existing_sdk(self) -> None:
        plan = self.plan(mode="source")
        self.assertEqual(plan.mode, "source")
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        self.assertIn("LVGL source not found", str(caught.exception))

    def test_missing_sdk_reports_the_export_command(self) -> None:
        plan = self.plan(sdk_dir=self.root / "missing-sdk")
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        message = str(caught.exception)
        self.assertIn("host SDK not found", message)
        self.assertIn("export_sdk.py", message)

    def test_missing_sdk_hint_is_added_to_the_source_error(self) -> None:
        plan = self.plan(mode="source")
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        self.assertIn("--prebuilt", str(caught.exception))

    def test_missing_engine_recovery_names_the_prebuilt_build(self) -> None:
        plan = self.plan()
        plan.execute(build=False)
        error = plan.missing_engine_error()
        assert error is not None
        self.assertEqual(error.configure_command, [])
        self.assertIn("--prebuilt", error.build_command)
        self.assertIn("build:", str(error))
        self.assertNotIn("configure:", str(error))


class ManifestTest(PrebuiltCase):
    def test_library_hash_mismatch_is_rejected(self) -> None:
        (self.sdk_dir / "lib" / "liblvgl.a").write_bytes(b"tampered")
        with self.assertRaises(BuildError) as caught:
            self.plan().preflight()
        self.assertIn("hash mismatch", str(caught.exception))
        self.assertIn("liblvgl.a", str(caught.exception))

    def test_sdk_version_mismatch_is_rejected(self) -> None:
        self.sdk_dir = self.make_sdk(version="9.4")
        with self.assertRaises(BuildError) as caught:
            self.plan().preflight()
        self.assertIn("version mismatch", str(caught.exception))

    def test_missing_library_is_rejected(self) -> None:
        (self.sdk_dir / "lib" / "libengine.a").unlink()
        with self.assertRaises(BuildError) as caught:
            self.plan().preflight()
        self.assertIn("library not found", str(caught.exception))

    def test_compiler_mismatch_is_a_build_error(self) -> None:
        plan = self.plan(compiler_version="14.2.0")
        with self.assertRaises(BuildError) as caught:
            plan.preflight()
        message = str(caught.exception)
        self.assertIn("compiler mismatch", message)
        self.assertIn("14.2.0", message)

    def test_absolute_include_dir_is_rejected(self) -> None:
        path = self.sdk_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["include_dirs"] = [".", str(self.root)]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(BuildError) as caught:
            self.plan().preflight()
        self.assertIn("must be relative", str(caught.exception))

    def test_no_c_sources_is_a_build_error(self) -> None:
        for path in self.user_app.glob("*.c"):
            path.unlink()
        with self.assertRaises(BuildError) as caught:
            self.plan().preflight()
        self.assertIn("no C sources", str(caught.exception))

    def test_shared_sdk_payload_is_resolved(self) -> None:
        common = self.root / "sdk" / "common"
        (common / "lib").mkdir(parents=True)
        (common / "include").mkdir(parents=True)
        (common / "include" / "shared.h").write_text(
            "#define SHARED 1\n", encoding="utf-8"
        )
        (self.sdk_dir / "lib" / "libfreetype.dll.a").replace(
            common / "lib" / "libfreetype.dll.a"
        )
        (common / "lib" / "libfreetype.dll").write_bytes(b"dll")
        path = self.sdk_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["libs"] = [
            name for name in manifest["libs"] if name != "libfreetype.dll.a"
        ]
        manifest["runtime_dlls"] = []
        manifest["shared_root"] = "common"
        manifest["shared_libs"] = ["libfreetype.dll.a"]
        manifest["shared_runtime_dlls"] = ["libfreetype.dll"]
        manifest["shared_include_dirs"] = ["include"]
        path.write_text(json.dumps(manifest), encoding="utf-8")

        sdk = prebuilt.HostSdk.load(self.sdk_dir, expected_version="9.6")
        self.assertIn(
            common / "lib" / "libfreetype.dll.a", sdk.lib_paths
        )
        self.assertIn(
            common / "lib" / "libfreetype.dll", sdk.runtime_dll_paths
        )
        self.assertIn(common / "include", sdk.include_paths)
        self.assertTrue(sdk.manifest_sha256)

    def test_shared_root_cannot_escape_the_sdk_parent(self) -> None:
        path = self.sdk_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["shared_root"] = ".."
        manifest["shared_libs"] = ["libfreetype.dll.a"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(BuildError) as caught:
            prebuilt.HostSdk.load(self.sdk_dir, expected_version="9.6")
        self.assertIn("must be a file name", str(caught.exception))


class CompilerResolutionTest(unittest.TestCase):
    def test_bundled_compiler_wins_over_env_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundled = Path(raw) / "gcc.exe"
            bundled.write_bytes(b"")
            with mock.patch.object(
                prebuilt, "_bundled_compiler", return_value=bundled
            ), mock.patch.object(
                prebuilt.shutil, "which", return_value="/path/gcc"
            ), mock.patch.dict(
                os.environ, {"LVGL_AI_GCC": "/env/gcc"}
            ):
                compiler, version = prebuilt.resolve_compiler(version="15.2.0")
        self.assertEqual(compiler, str(bundled))
        self.assertEqual(version, "15.2.0")

    def test_environment_wins_when_no_bundled_compiler_exists(self) -> None:
        missing = Path("missing-bundled-gcc")
        with mock.patch.object(
            prebuilt, "_bundled_compiler", return_value=missing
        ), mock.patch.object(
            prebuilt.shutil, "which", return_value="/path/gcc"
        ), mock.patch.dict(
            os.environ, {"LVGL_AI_GCC": "/env/gcc"}
        ):
            compiler, _ = prebuilt.resolve_compiler(version="15.2.0")
        self.assertEqual(compiler, "/env/gcc")

    def test_path_is_the_last_resort(self) -> None:
        missing = Path("missing-bundled-gcc")
        with mock.patch.object(
            prebuilt, "_bundled_compiler", return_value=missing
        ), mock.patch.object(
            prebuilt.shutil, "which", return_value="/path/gcc"
        ), mock.patch.dict(os.environ, {"LVGL_AI_GCC": ""}):
            compiler, _ = prebuilt.resolve_compiler(version="15.2.0")
        self.assertEqual(compiler, "/path/gcc")

    def test_no_compiler_is_a_build_error(self) -> None:
        with mock.patch.object(
            prebuilt, "_bundled_compiler", return_value=Path("missing")
        ), mock.patch.object(
            prebuilt.shutil, "which", return_value=None
        ), mock.patch.dict(os.environ, {"LVGL_AI_GCC": ""}):
            with self.assertRaises(BuildError) as caught:
                prebuilt.resolve_compiler(version="15.2.0")
        self.assertIn("C compiler not found", str(caught.exception))

    def test_unknown_versions_do_not_match(self) -> None:
        self.assertTrue(versions_match("15.2", "15.2.0"))
        self.assertFalse(versions_match("unknown", "15.2.0"))
        self.assertFalse(versions_match("15.2.0", "unknown"))
        self.assertFalse(versions_match("", "15.2.0"))


class CommandTest(PrebuiltCase):
    def test_compile_commands_carry_sdk_flags_and_include_order(self) -> None:
        runner = WritingRunner()
        outcome = self.plan(runner).execute(build=True)

        compile_calls = runner.compile_calls()
        self.assertEqual(len(compile_calls), 2)
        main_call, app_call = compile_calls
        self.assertTrue(main_call[2].endswith("main.c"))
        self.assertTrue(app_call[2].endswith("app.c"))

        for call in (main_call, app_call):
            joined = " ".join(call)
            for define in (
                "LV_CONF_INCLUDE_SIMPLE",
                "LV_KCONFIG_IGNORE",
                "LV_LVGL_H_INCLUDE_SIMPLE",
            ):
                self.assertIn(f"-D{define}", joined)
            self.assertIn("-std=gnu11", joined)
            self.assertIn("-O2", joined)
            sdk_root = self.sdk_dir
            self.assertLess(
                joined.index(f"-I{sdk_root} "),
                joined.index(f"-I{sdk_root / 'include'} "),
            )
            self.assertLess(
                joined.index(f"-I{sdk_root / 'include'} "),
                joined.index(f"-I{sdk_root / 'include' / 'lvgl'}"),
            )

        self.assertIn(f"-I{self.user_app.parent}", " ".join(app_call))
        self.assertIn(f"-I{self.user_app}", " ".join(app_call))
        self.assertIn(f"-I{self.engine_dir}", " ".join(main_call))
        self.assertIn("# build mode: prebuilt", outcome.log_text)
        self.assertIn("# phase: compile", outcome.log_text)
        self.assertIn("# phase: link", outcome.log_text)

    def test_link_command_uses_the_manifest_library_order(self) -> None:
        runner = WritingRunner()
        self.plan(runner).execute(build=True)

        link = runner.link_calls()[0]
        start = link.index("-Wl,--start-group")
        end = link.index("-Wl,--end-group")
        linked = link[start + 1 : end]
        self.assertEqual(
            linked,
            [str(self.sdk_dir / "lib" / name) for name in LIB_NAMES],
        )
        self.assertEqual(link[end + 1 :], ["-lgdi32", "-luser32", "-static-libgcc"])
        self.assertTrue(Path(link[link.index("-o") + 1]).name.startswith("lvgl_engine"))
        self.assertTrue((self.build_dir / "prebuilt.json").is_file())

    def test_unchanged_objects_are_reused(self) -> None:
        first = WritingRunner()
        self.plan(first).execute(build=True)
        self.assertEqual(len(first.compile_calls()), 2)

        second = WritingRunner()
        self.plan(second).execute(build=True)
        self.assertEqual(second.compile_calls(), [])
        self.assertEqual(len(second.link_calls()), 1)

    def test_changed_source_invalidates_its_object(self) -> None:
        self.plan(WritingRunner()).execute(build=True)
        (self.user_app / "app.c").write_text(
            "void app_create(void) { /* changed */ }\n", encoding="utf-8"
        )
        runner = WritingRunner()
        self.plan(runner).execute(build=True)
        compiled = runner.compile_calls()
        self.assertEqual(len(compiled), 1)
        self.assertTrue(compiled[0][2].endswith("app.c"))

    def test_source_build_removes_the_prebuilt_engine(self) -> None:
        self.plan(WritingRunner()).execute(build=True)
        engine = self.build_dir / "lvgl_engine.exe"
        self.assertTrue(engine.is_file())
        self.assertTrue((self.build_dir / "prebuilt.json").is_file())

        self.lvgl_src.mkdir(parents=True)
        (self.root / "third_party" / "zlib").mkdir(parents=True)
        (self.root / "third_party" / "libpng").mkdir(parents=True)
        runner = WritingRunner()
        plan = self.plan(runner, mode="source")
        outcome = plan.execute(build=True)
        self.assertFalse(engine.is_file())
        self.assertFalse((self.build_dir / "prebuilt.json").is_file())
        self.assertIn("mode switch", outcome.log_text)


class ErrorMappingTest(PrebuiltCase):
    def test_compile_error_reports_file_line_and_column(self) -> None:
        runner = WritingRunner(
            fail_on="compile",
            stderr="app.c:3:5: error: expected ';' before '}' token\n",
        )
        with self.assertRaises(BuildError) as caught:
            self.plan(runner).execute(build=True)
        error = caught.exception
        self.assertEqual(error.first_error["file"], "app.c")
        self.assertEqual(error.first_error["line"], 3)
        self.assertEqual(error.first_error["column"], 5)
        self.assertIn("app.c:3:5", str(error))
        self.assertIn("# command: ", error.log_text)
        self.assertIn("expected ';'", error.log_text)
        self.assertIn("# build mode: prebuilt", error.log_text)

    def test_link_error_lists_unresolved_symbols(self) -> None:
        runner = WritingRunner(
            fail_on="link",
            stderr=(
                "C:/mingw/bin/ld.exe: app.o: undefined reference to "
                "`missing_symbol'\ncollect2.exe: error: ld returned 1 exit status\n"
            ),
        )
        with self.assertRaises(LinkError) as caught:
            self.plan(runner).execute(build=True)
        error = caught.exception
        self.assertIn("missing_symbol", error.unresolved_symbols)
        self.assertIn("undefined reference", str(error))
        self.assertIn("# command: ", error.log_text)
        self.assertIn("undefined reference", error.log_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
