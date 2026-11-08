"""Error vocabulary seam: one table drives code, status, exit code and detail.

``lvgl_ai.control.errors.ERROR_MAPPINGS`` is the single mapping consumed by the
manifest writer (``status_for_error``), the ``--json`` error shape
(``dump_error``) and the CLI exit code (``exit_code_for``). A new error type
therefore needs one row, not four ``isinstance`` chains.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

import cli
from fake_runtime import FakeRuntime
from lvgl_ai.control import errors
from lvgl_ai.control.errors import (
    ERROR_MAPPINGS,
    SESSION_STATUSES,
    BuildError,
    EngineNotFound,
    ErrorMapping,
    LatError,
    LinkError,
    ProtocolError,
    RuntimeCrash,
    ScenarioError,
    ToolError,
    dump_error,
    error_code_for,
    exit_code_for,
    status_for_error,
)

EXPECTED_ROWS = [
    (BuildError, "build_error", "build_error", 1),
    (LinkError, "link_error", "link_error", 1),
    (RuntimeCrash, "crash", "crash", 1),
    (ProtocolError, "protocol_error", "harness_error", 2),
    (ScenarioError, "scenario_error", "harness_error", 2),
    (EngineNotFound, "engine_not_found", "harness_error", 2),
]


def engine_not_found() -> EngineNotFound:
    return EngineNotFound(
        "missing/lvgl_engine",
        configure_command=["cmake", "-S", "engine"],
        build_command=["cmake", "--build", "build"],
    )


def sample_errors() -> list[BaseException]:
    return [
        BuildError("compile failed"),
        LinkError("undefined symbol"),
        RuntimeCrash("engine died", exit_code=3),
        ProtocolError("bad seq", raw="{", seq=1),
        ScenarioError("step 0: bad", step=0),
        engine_not_found(),
    ]


class ErrorMappingTableTest(unittest.TestCase):
    def test_lat_error_is_a_compatibility_alias_for_tool_error(self) -> None:
        self.assertIs(LatError, ToolError)

    def test_table_has_the_frozen_rows_in_priority_order(self) -> None:
        self.assertEqual(
            [
                (
                    mapping.error_type,
                    mapping.code,
                    mapping.status,
                    mapping.exit_code,
                )
                for mapping in ERROR_MAPPINGS
            ],
            EXPECTED_ROWS,
        )

    def test_code_status_and_exit_code_derive_from_the_same_row(self) -> None:
        for mapping, error in zip(ERROR_MAPPINGS, sample_errors()):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(error_code_for(error), mapping.code)
                self.assertEqual(status_for_error(error), mapping.status)
                self.assertEqual(exit_code_for(error), mapping.exit_code)

    def test_unknown_errors_fall_back_to_harness_error_exit_2(self) -> None:
        for error in (
            ValueError("other"),
            ToolError("base"),
            FileNotFoundError("missing.json"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(error_code_for(error), "harness_error")
                self.assertEqual(status_for_error(error), "harness_error")
                self.assertEqual(exit_code_for(error), 2)
                self.assertEqual(
                    dump_error(error),
                    {
                        "code": "harness_error",
                        "message": str(error),
                        "detail": {},
                    },
                )

    def test_session_statuses_are_ok_plus_the_table_statuses(self) -> None:
        self.assertEqual(
            SESSION_STATUSES,
            frozenset({"ok"} | {mapping.status for mapping in ERROR_MAPPINGS}),
        )
        self.assertEqual(
            SESSION_STATUSES,
            {"ok", "build_error", "link_error", "crash", "harness_error"},
        )

    def _cli_exit_code(self, error: BaseException) -> tuple[int, dict]:
        fake = FakeRuntime(start_error=error)
        out = io.StringIO()
        with mock.patch.object(cli, "Runtime", return_value=fake), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--json"])
        return code, json.loads(out.getvalue().splitlines()[0])

    def test_cli_exit_codes_read_the_shared_table(self) -> None:
        for mapping, error in zip(ERROR_MAPPINGS, sample_errors()):
            with self.subTest(error=type(error).__name__):
                code, _payload = self._cli_exit_code(error)
                self.assertEqual(code, mapping.exit_code)
        code, payload = self._cli_exit_code(ValueError("other"))
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "harness_error")

    def test_adding_a_row_updates_every_consumer(self) -> None:
        class FancyError(ToolError):
            pass

        row = ErrorMapping(
            FancyError,
            "fancy_error",
            "harness_error",
            1,
            lambda error: {"fancy": True},
        )
        table = ERROR_MAPPINGS + (row,)
        with mock.patch.object(errors, "ERROR_MAPPINGS", table):
            error = FancyError("fancy failed")
            self.assertEqual(error_code_for(error), "fancy_error")
            self.assertEqual(status_for_error(error), "harness_error")
            self.assertEqual(exit_code_for(error), 1)
            code, payload = self._cli_exit_code(error)
            self.assertEqual(code, 1)
            self.assertEqual(payload["error"]["code"], "fancy_error")
            self.assertEqual(
                dump_error(error),
                {
                    "code": "fancy_error",
                    "message": "fancy failed",
                    "detail": {"fancy": True},
                },
            )


class DumpErrorShapeTest(unittest.TestCase):
    def test_build_error_keeps_the_first_20_diagnostics(self) -> None:
        diagnostics = [
            {"file": "app.c", "line": index, "severity": "error"}
            for index in range(25)
        ]
        error = BuildError("compile failed", diagnostics=diagnostics)
        self.assertEqual(
            dump_error(error),
            {
                "code": "build_error",
                "message": "compile failed",
                "detail": {"diagnostics": diagnostics[:20]},
            },
        )

    def test_link_error_keeps_unresolved_symbols(self) -> None:
        error = LinkError("link failed", unresolved_symbols=["missing_symbol"])
        self.assertEqual(
            dump_error(error),
            {
                "code": "link_error",
                "message": "link failed",
                "detail": {"unresolved_symbols": ["missing_symbol"]},
            },
        )

    def test_runtime_crash_keeps_the_last_40_log_lines(self) -> None:
        error = RuntimeCrash(
            "engine died",
            exit_code=3,
            log_tail=[f"line {index}" for index in range(45)],
        )
        self.assertEqual(
            dump_error(error),
            {
                "code": "crash",
                "message": "engine died",
                "detail": {
                    "exit_code": 3,
                    "log_tail": [f"line {index}" for index in range(5, 45)],
                },
            },
        )

    def test_protocol_and_scenario_details(self) -> None:
        protocol = ProtocolError("bad seq", raw='{"seq": 9}', seq=9)
        self.assertEqual(
            dump_error(protocol),
            {
                "code": "protocol_error",
                "message": "bad seq",
                "detail": {"raw": '{"seq": 9}', "seq": 9},
            },
        )
        scenario = ScenarioError("step 2: bad", step=2)
        self.assertEqual(
            dump_error(scenario),
            {
                "code": "scenario_error",
                "message": "step 2: bad",
                "detail": {"step": 2},
            },
        )

    def test_engine_not_found_detail_has_no_prebuilt_path(self) -> None:
        error = engine_not_found()
        self.assertEqual(
            dump_error(error),
            {
                "code": "engine_not_found",
                "message": str(error),
                "detail": {
                    "engine_path": "missing/lvgl_engine",
                    "configure_command": ["cmake", "-S", "engine"],
                    "build_command": ["cmake", "--build", "build"],
                },
            },
        )

    def test_none_dumps_to_none(self) -> None:
        self.assertIsNone(dump_error(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
