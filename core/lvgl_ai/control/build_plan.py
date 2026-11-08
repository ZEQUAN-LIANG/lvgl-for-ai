"""BuildPlan: preflight, configure, build and engine path resolution.

One plan is one LVGL version's source build. It resolves the LVGL source tree,
build directory and user app directories, decides whether the CMake cache still
matches, and runs configure/build into ``build.log`` text with typed
:class:`~lvgl_ai.control.errors.BuildError` /
:class:`~lvgl_ai.control.errors.LinkError` failures.

:class:`~lvgl_ai.control.runtime.Runtime` uses :meth:`BuildPlan.execute` for the
whole flow; the phase methods remain available for callers that need their own
failure mapping. Both share command construction, the cache check and engine
path resolution.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .. import paths
from .build import (
    BuildResult,
    build_command,
    build_environment_message,
    build_failure,
    ccache_available,
    configure_command,
    format_build_log,
    missing_build_tools,
    needs_configure as cache_needs_configure,
    run_capture,
)
from .errors import BuildError, EngineNotFound, LinkError

BUILD_TIMEOUT_S = 600.0

Runner = Callable[..., BuildResult]
ToolsCheck = Callable[[], Sequence[str]]


@dataclass(frozen=True)
class BuildOutcome:
    """The engine to launch and the ``build.log`` text for one session."""

    engine_path: Path
    log_text: str


class BuildPlan:
    """One version's build: preflight -> configure if stale -> build -> engine.

    ``lvgl_src``, ``build_dir``, ``engine_dir`` and the user directories are
    resolved once from :mod:`lvgl_ai.paths` unless the caller passes explicit
    paths. ``configure`` / ``build`` replace the generated commands for
    embedding and tests; an explicit build command also skips the source-build
    preflight. ``engine_path`` is the test/embedding override and is never
    replaced by the build output. ``runner`` and ``missing_tools`` are seams
    for scripted tests.
    """

    def __init__(
        self,
        version: str,
        *,
        lvgl_src: str | Path | None = None,
        build_dir: str | Path | None = None,
        engine_dir: str | Path | None = None,
        user_app_dir: str | Path | None = None,
        user_asset_dir: str | Path | None = None,
        ccache: bool | None = None,
        configure: Sequence[str] | None = None,
        build: Sequence[str] | None = None,
        engine_path: str | Path | None = None,
        missing_tools: ToolsCheck | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.version = version
        self.lvgl_src = (
            Path(lvgl_src) if lvgl_src is not None else paths.lvgl_src_for(version)
        )
        self.build_dir = (
            Path(build_dir) if build_dir is not None else paths.build_dir_for(version)
        )
        self.engine_dir = (
            Path(engine_dir) if engine_dir is not None else paths.ENGINE_DIR
        )
        self.user_app_dir = (
            Path(user_app_dir)
            if user_app_dir is not None
            else paths.USER_APP_DIR
        )
        self.user_asset_dir = (
            Path(user_asset_dir)
            if user_asset_dir is not None
            else paths.USER_ASSET_DIR
        )
        self._build_explicit = build is not None
        self._engine_explicit = engine_path is not None
        self._missing_tools = missing_tools
        self._runner = runner

        uses_ccache = ccache_available() if ccache is None else bool(ccache)
        self.configure_command = (
            list(configure)
            if configure is not None
            else configure_command(
                self.engine_dir,
                self.build_dir,
                lvgl_src=self.lvgl_src,
                lvgl_version=version,
                user_app_dir=self.user_app_dir,
                user_asset_dir=self.user_asset_dir,
                ccache=uses_ccache,
            )
        )
        self.build_command = (
            list(build) if build is not None else build_command(self.build_dir)
        )
        self.engine_path = (
            Path(engine_path)
            if engine_path is not None
            else self.built_engine_path
        )

    # ---- paths ---------------------------------------------------------

    @property
    def built_engine_path(self) -> Path:
        """Where a source build writes the engine."""
        return self.build_dir / paths.engine_filename()

    @property
    def cache_path(self) -> Path:
        return self.build_dir / "CMakeCache.txt"

    # ---- preflight and cache -------------------------------------------

    def preflight(self) -> None:
        """Fail fast with an actionable error before spawning CMake.

        A caller-supplied build command is an embedding/test toolchain, so the
        default CMake/GCC prerequisite check does not apply to it.
        """
        if self._build_explicit:
            return
        check = (
            self._missing_tools
            if self._missing_tools is not None
            else missing_build_tools
        )
        missing_tools = list(check())
        if not self.lvgl_src.is_dir() or missing_tools:
            raise BuildError(
                build_environment_message(
                    lvgl_src=self.lvgl_src,
                    lvgl_version=self.version,
                    missing_tools=missing_tools,
                ),
                command=list(self.configure_command),
            )

    def needs_configure(self) -> bool:
        """True when the CMake cache is missing, incomplete or stale."""
        return cache_needs_configure(
            self.build_dir,
            lvgl_src=self.lvgl_src,
            lvgl_version=self.version,
            user_app_dir=self.user_app_dir,
            user_asset_dir=self.user_asset_dir,
            engine_dir=self.engine_dir,
        )

    # ---- configure and build -------------------------------------------

    def configure(self) -> str:
        """Run CMake configure and return its phase log."""
        return self._run_step(self.configure_command, "configure")

    def build(self) -> str:
        """Run the engine build and return its phase log."""
        return self._run_step(self.build_command, "build")

    def execute(self, *, build: bool) -> BuildOutcome:
        """Run the plan for one session and resolve the engine to launch.

        ``build=False`` skips preflight/configure/build and only resolves the
        source-build engine. Failures keep the successful phase logs in
        ``log_text``.
        """
        log_text = self._run_build() if build else None
        engine_path = self.resolve_engine()
        if log_text is None:
            log_text = (
                "# build skipped (build=False)\n"
                f"# engine: {engine_path}\n"
            )
        return BuildOutcome(engine_path=engine_path, log_text=log_text)

    # ---- engine resolution ---------------------------------------------

    def resolve_engine(self) -> Path:
        """Return the explicit engine override or the source-build output."""
        if not self._engine_explicit:
            self.engine_path = self.built_engine_path
        return self.engine_path

    def missing_engine_error(self) -> EngineNotFound | None:
        """The typed missing-engine error, or ``None`` when it exists.

        The error carries the exact configure/build commands so the caller can
        recover from a missing ``--no-build`` engine.
        """
        self.resolve_engine()
        if self.engine_path.is_file():
            return None
        return EngineNotFound(
            self.engine_path,
            configure_command=self.configure_command,
            build_command=self.build_command,
        )

    # ---- internals -----------------------------------------------------

    def _run_build(self) -> str:
        self.preflight()
        parts: list[str] = []
        try:
            if self.needs_configure():
                parts.append(self.configure())
            else:
                parts.append(
                    "# phase: configure\n"
                    f"# skipped: cache matches {self.cache_path}\n"
                )
            parts.append(self.build())
        except (BuildError, LinkError) as exc:
            # Keep the successful phases in build.log; the failing phase's
            # output is already in exc.log_text.
            exc.log_text = "\n".join([*parts, exc.log_text or ""])
            raise
        return "\n".join(parts)

    def _run_step(self, command: Sequence[str], phase: str) -> str:
        runner = self._runner if self._runner is not None else run_capture
        try:
            result = runner(list(command), timeout=BUILD_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise BuildError(
                f"{phase} timed out after {BUILD_TIMEOUT_S:.0f}s",
                command=list(command),
                log_text=str(exc),
            ) from exc
        log_text = format_build_log(result, phase)
        if result.returncode != 0:
            raise build_failure(result, log_text)
        return log_text
