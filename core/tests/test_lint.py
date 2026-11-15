"""Unit tests for core/tools/lint.py.

No external tool runs: subprocess calls are mocked, so the suite works on a
machine without ruff, clang-format or cppcheck.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

TOOL_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = TOOL_ROOT / "tools"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import lint


class FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)

    def isatty(self) -> bool:
        return False


def make_finding(path: str = "core/x.py") -> lint.Finding:
    return lint.Finding(
        tool="ruff",
        path=path,
        line=1,
        column=1,
        code="F401",
        message="imported but unused",
    )


class DiscoveryTest(unittest.TestCase):
    def test_excluded_directories(self) -> None:
        relatives = (
            "chip-adapt/vendor/sifli-sdk/x.c",
            "build/obj/x.c",
            "release/pkg/x.py",
            "sessions/s1/x.py",
            "core/engine/freetype/x.c",
            "core/lvgl_ai/assets/vendor/x.c",
            "chip-adapt/sifli/host/.cache/x.py",
            "user/.trash/x.c",
            "core/engine/lv_conf.h",
        )
        for relative in relatives:
            with self.subTest(relative=relative):
                self.assertTrue(lint.is_excluded(Path(relative)))

    def test_repo_owned_paths_are_kept(self) -> None:
        relatives = (
            "core/engine/main.c",
            "core/tools/lint.py",
            "user/app/coffee/coffee_ui.c",
            "chip-adapt/sifli/templates/src/main.c",
        )
        for relative in relatives:
            with self.subTest(relative=relative):
                self.assertFalse(lint.is_excluded(Path(relative)))

    def test_generated_asset_header(self) -> None:
        path = TOOL_ROOT.parent / "user/app/coffee/coffee_font_12.h"
        self.assertTrue(lint.is_generated(path))

    def test_intro_layout_data_table_is_generated(self) -> None:
        path = TOOL_ROOT.parent / "user/app/intro/intro_layout.c"
        self.assertTrue(lint.is_generated(path))

    def test_hand_written_source_is_not_generated(self) -> None:
        self.assertFalse(
            lint.is_generated(TOOL_ROOT / "engine" / "main.c")
        )

    def test_discovers_repo_files_and_skips_generated(self) -> None:
        diagnostics: list[str] = []
        discovery = lint.discover(None, diagnostics)
        python_paths = {lint.rel_path(path) for path in discovery.python}
        c_paths = {lint.rel_path(path) for path in discovery.c}
        self.assertIn("core/tools/lint.py", python_paths)
        self.assertIn("core/engine/main.c", c_paths)
        self.assertIn("user/app/coffee/coffee_ui.c", c_paths)
        self.assertNotIn(
            "user/app/coffee/coffee_font_12.h", c_paths
        )
        self.assertNotIn("user/app/intro/intro_layout.c", c_paths)
        self.assertGreater(discovery.generated, 0)
        for path in python_paths:
            self.assertFalse(
                path.startswith("chip-adapt/vendor/"), path
            )

    def test_explicit_excluded_path_is_reported(self) -> None:
        diagnostics: list[str] = []
        discovery = lint.discover(
            ["user/app/coffee/coffee_font_12.h"], diagnostics
        )
        self.assertEqual(discovery.c, [])
        self.assertTrue(
            any("generated" in line for line in diagnostics), diagnostics
        )


class CommandTest(unittest.TestCase):
    def test_ruff_command_order(self) -> None:
        argv = lint._ruff_command(["ruff"], "check", "--no-fix")
        self.assertEqual(argv[:2], ["ruff", "check"])
        self.assertIn("--force-exclude", argv)
        self.assertIn("--config", argv)
        self.assertTrue(
            argv[argv.index("--config") + 1].endswith("pyproject.toml")
        )

    def test_cppcheck_default_flags(self) -> None:
        argv = lint._cppcheck_argv(
            ["cppcheck"], [Path("core/engine/main.c")], "9.6", False
        )
        self.assertIn("--inline-suppr", argv)
        self.assertIn("--error-exitcode=7", argv)
        self.assertIn("-DLV_CONF_INCLUDE_SIMPLE", argv)
        self.assertIn("-DLV_LVGL_H_INCLUDE_SIMPLE", argv)
        self.assertIn("-D_WIN32", argv)
        self.assertNotIn("-DLVGL_MAJOR_8=1", argv)
        self.assertNotIn("--addon=misra", argv)
        self.assertTrue(any("lodepng" in part for part in argv))
        self.assertTrue(any("main.c" in part for part in argv))

    def test_cppcheck_lvgl8_uses_extra_lodepng(self) -> None:
        argv = lint._cppcheck_argv(["cppcheck"], [], "8.4", False)
        self.assertIn("-DLVGL_MAJOR_8=1", argv)
        self.assertTrue(any("extra" in part and "png" in part for part in argv))
        self.assertFalse(any("lodepng" in part for part in argv))

    def test_cppcheck_misra_is_opt_in(self) -> None:
        argv = lint._cppcheck_argv(["cppcheck"], [], "9.6", True)
        self.assertIn("--addon=misra", argv)
        self.assertIn("--addon-python=%s" % sys.executable, argv)

    def test_format_rejects_cppcheck(self) -> None:
        self.assertIsNone(lint.parse_tools("cppcheck", allow_cppcheck=False))
        self.assertEqual(
            lint.parse_tools("all", allow_cppcheck=False),
            ["ruff", "clang-format"],
        )
        self.assertEqual(
            lint.parse_tools("all", allow_cppcheck=True),
            ["ruff", "clang-format", "cppcheck"],
        )

    def test_adapter_filter_follows_version(self) -> None:
        files = [
            Path("core/engine/adapter_8x.c"),
            Path("core/engine/adapter_9x.c"),
            Path("core/engine/main.c"),
        ]
        kept = lint._filter_adapters(files, "9.6", [])
        self.assertEqual(
            [path.name for path in kept],
            ["adapter_9x.c", "main.c"],
        )
        kept = lint._filter_adapters(files, "8.4", [])
        self.assertEqual(
            [path.name for path in kept],
            ["adapter_8x.c", "main.c"],
        )


class ParserTest(unittest.TestCase):
    def test_ruff_json(self) -> None:
        payload = [
            {
                "filename": str(lint.REPO_ROOT / "core" / "x.py"),
                "location": {"row": 4, "column": 2},
                "code": "F401",
                "message": "unused",
                "fix": {"applicability": "safe"},
            }
        ]
        findings = lint._parse_ruff(payload)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "core/x.py")
        self.assertEqual(findings[0].line, 4)
        self.assertTrue(findings[0].fixable)

    def test_clang_format_diagnostic_with_drive_letter(self) -> None:
        stderr = (
            "C:/repo/core/engine/main.c:12:5: error: code should be "
            "clang-formatted [-Wclang-format-violations]\n"
        )
        findings = lint._parse_clang_format(stderr)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 12)
        self.assertEqual(findings[0].column, 5)

    def test_cppcheck_template_with_pipe_in_message(self) -> None:
        stderr = (
            "core\\engine\\main.c|9|3|warning|unusedVariable|"
            "unused: a | b\n"
        )
        findings = lint._parse_cppcheck(stderr)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "core/engine/main.c")
        self.assertEqual(findings[0].code, "unusedVariable")
        self.assertEqual(findings[0].message, "unused: a | b")

    def test_empty_output_yields_no_finding(self) -> None:
        self.assertEqual(lint._parse_ruff([]), [])
        self.assertEqual(lint._parse_clang_format(""), [])
        self.assertEqual(lint._parse_cppcheck(""), [])


class HookTest(unittest.TestCase):
    def run_hook(self, data: bytes) -> int:
        with mock.patch.object(sys, "stdin", FakeStdin(data)):
            with mock.patch("sys.stderr", io.StringIO()):
                return lint.cmd_hook()

    def payload(self, path: str) -> bytes:
        return json.dumps(
            {"cwd": str(lint.REPO_ROOT), "tool_input": {"file_path": path}}
        ).encode("utf-8")

    def test_invalid_json_exits_zero(self) -> None:
        self.assertEqual(self.run_hook(b"not json"), 0)

    def test_excluded_path_exits_zero(self) -> None:
        self.assertEqual(self.run_hook(self.payload(".scratch/x.py")), 0)

    def test_generated_file_exits_zero(self) -> None:
        path = "user/app/coffee/coffee_font_12.h"
        self.assertEqual(self.run_hook(self.payload(path)), 0)

    def test_python_finding_exits_two(self) -> None:
        result = lint.ToolResult(
            name="ruff", status="findings", findings=[make_finding()]
        )
        empty = lint.ToolResult(name="ruff-format", status="ok")
        with mock.patch.object(
            lint, "run_ruff_check", return_value=result
        ), mock.patch.object(
            lint, "run_ruff_format", return_value=empty
        ):
            code = self.run_hook(self.payload("core/tools/lint.py"))
        self.assertEqual(code, 2)

    def test_missing_tool_exits_zero(self) -> None:
        skipped = lint.ToolResult(
            name="ruff", status="skipped", error="not found"
        )
        with mock.patch.object(
            lint, "run_ruff_check", return_value=skipped
        ), mock.patch.object(
            lint, "run_ruff_format", return_value=skipped
        ):
            code = self.run_hook(self.payload("core/tools/lint.py"))
        self.assertEqual(code, 0)

    def test_findings_are_capped(self) -> None:
        findings = [make_finding("core/x.py") for _ in range(25)]
        result = lint.ToolResult(
            name="ruff", status="findings", findings=findings
        )
        empty = lint.ToolResult(name="ruff-format", status="ok")
        capture = io.StringIO()
        with mock.patch.object(
            lint, "run_ruff_check", return_value=result
        ), mock.patch.object(
            lint, "run_ruff_format", return_value=empty
        ):
            with mock.patch.object(sys, "stdin", FakeStdin(
                self.payload("core/tools/lint.py")
            )), mock.patch("sys.stderr", capture):
                code = lint.cmd_hook()
        self.assertEqual(code, 2)
        self.assertIn("5 more omitted", capture.getvalue())

    def test_engine_header_checks_engine_sources(self) -> None:
        empty = lint.ToolResult(name="clang-format", status="ok")
        cpp = lint.ToolResult(name="cppcheck", status="ok")
        with mock.patch.object(
            lint, "run_clang_format", return_value=empty
        ), mock.patch.object(
            lint, "run_cppcheck", return_value=cpp
        ) as mocked:
            code = self.run_hook(self.payload("core/engine/adapter.h"))
        self.assertEqual(code, 0)
        self.assertTrue(mocked.called)
        self.assertGreater(len(mocked.call_args.args[0]), 1)

    def test_user_app_source_skips_cppcheck(self) -> None:
        empty = lint.ToolResult(name="clang-format", status="ok")
        with mock.patch.object(
            lint, "run_clang_format", return_value=empty
        ), mock.patch.object(lint, "run_cppcheck") as mocked:
            code = self.run_hook(self.payload("user/app/coffee/coffee_ui.c"))
        self.assertEqual(code, 0)
        self.assertFalse(mocked.called)


class ReportTest(unittest.TestCase):
    def test_report_shape_and_sorting(self) -> None:
        results = [
            lint.ToolResult(
                name="ruff",
                status="findings",
                files=2,
                findings=[
                    make_finding("core/b.py"),
                    make_finding("core/a.py"),
                ],
            )
        ]
        report = lint.build_report(
            command="check",
            results=results,
            discovery=lint.Discovery(
                python=[Path("a")], c=[Path("b")], generated=3
            ),
            diagnostics=["note"],
            started=time.monotonic(),
            lvgl="9.6",
        )
        self.assertEqual(report["schema"], "lvgl-ai-lint-v1")
        self.assertFalse(report["ok"])
        self.assertEqual(
            [item["path"] for item in report["findings"]],
            ["core/a.py", "core/b.py"],
        )
        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["by_tool"]["ruff"], 2)
        self.assertEqual(report["files"]["skipped_generated"], 3)
        self.assertEqual(report["diagnostics"], ["note"])

    def test_clean_report_is_ok(self) -> None:
        clean = lint.ToolResult(name="ruff", status="ok")
        report = lint.build_report(
            command="check",
            results=[clean],
            discovery=lint.Discovery(),
            diagnostics=[],
            started=time.monotonic(),
            lvgl="9.6",
        )
        self.assertTrue(report["ok"])


class ExitCodeTest(unittest.TestCase):
    def make_args(self, **overrides: object) -> argparse.Namespace:
        values = {
            "json": False,
            "tools": "ruff",
            "files": None,
            "lvgl": "9.6",
            "cppcheck_user_app": False,
            "misra": False,
            "skip_missing": False,
            "timeout": 5.0,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_check(
        self, args: argparse.Namespace, result: lint.ToolResult
    ) -> int:
        with mock.patch.object(
            lint, "discover", return_value=lint.Discovery()
        ), mock.patch.object(
            lint, "run_ruff_check", return_value=result
        ), mock.patch("sys.stdout", io.StringIO()), mock.patch(
            "sys.stderr", io.StringIO()
        ):
            return lint.cmd_check(args)

    def test_clean_is_zero(self) -> None:
        result = lint.ToolResult(name="ruff", status="ok")
        self.assertEqual(self.run_check(self.make_args(), result), 0)

    def test_findings_is_one(self) -> None:
        result = lint.ToolResult(
            name="ruff", status="findings", findings=[make_finding()]
        )
        self.assertEqual(self.run_check(self.make_args(), result), 1)

    def test_tool_error_is_two(self) -> None:
        result = lint.ToolResult(
            name="ruff", status="error", error="boom"
        )
        self.assertEqual(self.run_check(self.make_args(), result), 2)

    def test_missing_tool_skip_flag(self) -> None:
        with mock.patch.object(lint, "resolve_tool", return_value=None):
            hard = lint.run_ruff_check([], skip_missing=False, timeout=1)
            soft = lint.run_ruff_check([], skip_missing=True, timeout=1)
        self.assertEqual(hard.status, "error")
        self.assertEqual(soft.status, "skipped")

    def test_cppcheck_exit_seven_is_findings(self) -> None:
        proc = mock.Mock(
            returncode=7,
            stderr="core/engine/main.c|1|1|warning|id|msg\n",
            stdout="",
        )
        with mock.patch.object(
            lint, "resolve_tool", return_value=["cppcheck"]
        ), mock.patch.object(
            lint, "tool_version", return_value="Cppcheck 2.20"
        ), mock.patch.object(
            lint, "_cppcheck_prerequisites", return_value=[]
        ), mock.patch.object(
            lint, "run_command", return_value=proc
        ):
            result = lint.run_cppcheck(
                [Path("core/engine/main.c")],
                version="9.6",
                misra=False,
                skip_missing=False,
                timeout=5,
                diagnostics=[],
            )
        self.assertEqual(result.status, "findings")
        self.assertEqual(len(result.findings), 1)

    def test_ruff_exit_two_is_harness_error(self) -> None:
        proc = mock.Mock(returncode=2, stderr="bad config", stdout="")
        with mock.patch.object(
            lint, "resolve_tool", return_value=["ruff"]
        ), mock.patch.object(
            lint, "tool_version", return_value="ruff 0.17.5"
        ), mock.patch.object(lint, "run_command", return_value=proc):
            result = lint.run_ruff_check(
                [Path("core/tools/lint.py")],
                skip_missing=False,
                timeout=5,
            )
        self.assertEqual(result.status, "error")
        self.assertIn("bad config", result.error)


class ReleaseExclusionTest(unittest.TestCase):
    def test_lint_is_excluded_from_release(self) -> None:
        import release

        self.assertIn("tools/lint.py", release.CORE_RELEASE_EXCLUDE_FILES)


if __name__ == "__main__":
    unittest.main()
