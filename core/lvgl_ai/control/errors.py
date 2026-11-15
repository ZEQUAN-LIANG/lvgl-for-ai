from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


class ToolError(Exception):
    """Base class for every error raised by lvgl_ai."""


# Public compatibility alias. The base class was named ``LatError`` before the
# naming cleanup; new code should use ``ToolError``.
LatError = ToolError


class BuildError(ToolError):
    """The engine failed to compile."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: Sequence[dict[str, Any]] | None = None,
        log_text: str | None = None,
        command: Sequence[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = list(diagnostics or [])
        self.log_text = log_text
        self.command = list(command or [])

    @property
    def first_error(self) -> dict[str, Any] | None:
        for diagnostic in self.diagnostics:
            if diagnostic.get("severity") in ("fatal error", "error"):
                return diagnostic
        return self.diagnostics[0] if self.diagnostics else None


class LinkError(ToolError):
    """The engine failed to link."""

    def __init__(
        self,
        message: str,
        *,
        unresolved_symbols: Sequence[str] | None = None,
        log_text: str | None = None,
        command: Sequence[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.unresolved_symbols = list(unresolved_symbols or [])
        self.log_text = log_text
        self.command = list(command or [])


class RuntimeCrash(ToolError):
    """The engine process died or stopped answering."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        log_tail: Sequence[str] | None = None,
        log_path: str | Path | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.log_tail = list(log_tail or [])
        self.log_path = None if log_path is None else str(log_path)


class ProtocolError(ToolError):
    """A protocol line was malformed or did not match the command sequence."""

    def __init__(
        self,
        message: str,
        *,
        raw: str | None = None,
        seq: int | None = None,
    ) -> None:
        super().__init__(message)
        self.raw = raw
        self.seq = seq


class ScenarioError(ToolError):
    """An input event or scenario step is invalid.

    ``step`` is the zero-based index inside the event/step list so the caller
    can point at the offending entry without re-reading the script.
    """

    def __init__(self, message: str, *, step: int | None = None) -> None:
        super().__init__(message)
        self.step = step


class EngineNotFound(ToolError):
    """The engine binary is missing.

    Carries the exact configure and build commands so the caller can recover
    without reading the source.
    """

    def __init__(
        self,
        engine_path: str | Path,
        *,
        configure_command: Sequence[str],
        build_command: Sequence[str],
    ) -> None:
        self.engine_path = str(engine_path)
        self.configure_command = list(configure_command)
        self.build_command = list(build_command)
        lines = [f"engine binary not found: {self.engine_path}"]
        if self.configure_command:
            lines.append(f"configure: {_shell_join(self.configure_command)}")
        if self.build_command:
            lines.append(f"build: {_shell_join(self.build_command)}")
        super().__init__("\n".join(lines))


def _shell_join(command: Sequence[str]) -> str:
    parts = []
    for part in command:
        text = str(part)
        parts.append(f'"{text}"' if " " in text else text)
    return " ".join(parts)


EXIT_FAILURE = 1
EXIT_HARNESS = 2


LOG_TAIL_LINES = 40
LOG_TAIL_CHARS = 8192


def _bounded_tail(text: str | None) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()[-LOG_TAIL_LINES:]
    picked: list[str] = []
    used = 0
    for line in reversed(lines):
        if used + len(line) + 1 > LOG_TAIL_CHARS:
            break
        picked.append(line)
        used += len(line) + 1
    picked.reverse()
    return picked


def _build_detail(error: BuildError) -> dict[str, Any]:
    return {
        "diagnostics": error.diagnostics[:20],
        "log_tail": _bounded_tail(error.log_text),
        "command": list(error.command) if error.command else [],
    }


def _link_detail(error: LinkError) -> dict[str, Any]:
    return {
        "unresolved_symbols": error.unresolved_symbols,
        "log_tail": _bounded_tail(error.log_text),
        "command": list(error.command) if error.command else [],
    }


def _crash_detail(error: RuntimeCrash) -> dict[str, Any]:
    return {"exit_code": error.exit_code, "log_tail": error.log_tail[-40:]}


def _protocol_detail(error: ProtocolError) -> dict[str, Any]:
    return {"raw": error.raw, "seq": error.seq}


def _scenario_detail(error: ScenarioError) -> dict[str, Any]:
    return {"step": error.step}


def _engine_not_found_detail(error: EngineNotFound) -> dict[str, Any]:
    return {
        "engine_path": error.engine_path,
        "configure_command": error.configure_command,
        "build_command": error.build_command,
    }


@dataclass(frozen=True)
class ErrorMapping:
    """One row of the error vocabulary.

    The row is the only place that names an error's layer code, manifest
    status and CLI exit code; :func:`dump_error` also uses its detail builder.
    """

    error_type: type[BaseException]
    code: str
    status: str
    exit_code: int
    detail: Callable[[Any], dict[str, Any]] | None = None


ERROR_MAPPINGS: tuple[ErrorMapping, ...] = (
    ErrorMapping(
        BuildError, "build_error", "build_error", EXIT_FAILURE, _build_detail
    ),
    ErrorMapping(
        LinkError, "link_error", "link_error", EXIT_FAILURE, _link_detail
    ),
    ErrorMapping(RuntimeCrash, "crash", "crash", EXIT_FAILURE, _crash_detail),
    ErrorMapping(
        ProtocolError,
        "protocol_error",
        "harness_error",
        EXIT_HARNESS,
        _protocol_detail,
    ),
    ErrorMapping(
        ScenarioError,
        "scenario_error",
        "harness_error",
        EXIT_HARNESS,
        _scenario_detail,
    ),
    ErrorMapping(
        EngineNotFound,
        "engine_not_found",
        "harness_error",
        EXIT_HARNESS,
        _engine_not_found_detail,
    ),
)

UNMAPPED_ERROR_MAPPING = ErrorMapping(
    BaseException, "harness_error", "harness_error", EXIT_HARNESS
)

SESSION_STATUSES = frozenset(
    {"ok"} | {mapping.status for mapping in ERROR_MAPPINGS}
)


def error_mapping(error: BaseException) -> ErrorMapping:
    for mapping in ERROR_MAPPINGS:
        if isinstance(error, mapping.error_type):
            return mapping
    return UNMAPPED_ERROR_MAPPING


def error_code_for(error: BaseException) -> str:
    return error_mapping(error).code


def status_for_error(error: BaseException) -> str:
    return error_mapping(error).status


def exit_code_for(error: BaseException) -> int:
    return error_mapping(error).exit_code


def dump_error(error: BaseException | None) -> dict[str, Any] | None:
    if error is None:
        return None
    detail: dict[str, Any] = {}
    for mapping in ERROR_MAPPINGS:
        if mapping.detail is not None and isinstance(
            error, mapping.error_type
        ):
            detail.update(mapping.detail(error))
    return {
        "code": error_code_for(error),
        "message": str(error),
        "detail": detail,
    }
