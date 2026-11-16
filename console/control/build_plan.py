"""BuildPlan: preflight, configure, build and engine path resolution.

One plan is one LVGL version's source build. It resolves the LVGL source tree,
build directory and user app directories, decides whether the CMake cache still
matches, and runs configure/build into ``build.log`` text with typed
:class:`~control.errors.BuildError` /
:class:`~control.errors.LinkError` failures.

:class:`~control.runtime.Runtime` uses :meth:`BuildPlan.execute` for the
whole flow; the phase methods remain available for callers that need their own
failure mapping. Both share command construction, the cache check and engine
path resolution.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import paths
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
from .engine_guard import ensure_engine_stopped
from .errors import BuildError, EngineNotFound, LinkError
from .locks import build_lock
from .prebuilt import (
    HostSdk,
    PREBUILT_MARKER,
    PrebuiltBuild,
    compiler_mismatch_message,
    resolve_compiler,
    versions_match,
)

BUILD_TIMEOUT_S = 600.0

BUILD_MODES = ("auto", "source", "prebuilt")

Runner = Callable[..., BuildResult]
ToolsCheck = Callable[[], Sequence[str]]


@dataclass(frozen=True)
class BuildOutcome:
    engine_path: Path
    log_text: str


class BuildPlan:
    def __init__(
        self,
        version: str,
        *,
        lvgl_src: str | Path | None = None,
        build_dir: str | Path | None = None,
        engine_dir: str | Path | None = None,
        user_app_dir: str | Path | None = None,
        zlib_src: str | Path | None = None,
        libpng_src: str | Path | None = None,
        ccache: bool | None = None,
        configure: Sequence[str] | None = None,
        build: Sequence[str] | None = None,
        engine_path: str | Path | None = None,
        missing_tools: ToolsCheck | None = None,
        runner: Runner | None = None,
        build_mode: str = "auto",
        sdk_dir: str | Path | None = None,
        compiler: str | Path | None = None,
        compiler_version: str | None = None,
    ) -> None:
        if build_mode not in BUILD_MODES:
            raise ValueError(
                f"build_mode must be one of {', '.join(BUILD_MODES)}; "
                f"got {build_mode!r}"
            )
        self.version = version
        self.lvgl_src = (
            Path(lvgl_src)
            if lvgl_src is not None
            else paths.lvgl_src_for(version)
        )
        self.user_app_dir = (
            Path(user_app_dir)
            if user_app_dir is not None
            else paths.apps_dir_from_env()
        )
        self.build_dir = (
            Path(build_dir)
            if build_dir is not None
            else paths.build_dir_for(version, self.user_app_dir)
        )
        self.engine_dir = (
            Path(engine_dir) if engine_dir is not None else paths.ENGINE_DIR
        )
        self.zlib_src = (
            Path(zlib_src) if zlib_src is not None else paths.zlib_src()
        )
        self.libpng_src = (
            Path(libpng_src) if libpng_src is not None else paths.libpng_src()
        )
        self.sdk_dir = (
            Path(sdk_dir)
            if sdk_dir is not None
            else paths.sdk_dir_for(version)
        )
        self._build_explicit = build is not None
        self._engine_explicit = engine_path is not None
        self._missing_tools = missing_tools
        self._runner = runner
        self._compiler = None if compiler is None else str(compiler)
        self._compiler_version = compiler_version
        self._prebuilt: PrebuiltBuild | None = None
        # An explicit build command is an embedding/test toolchain and always
        # uses the source-plan execution path.
        self.mode = self._select_mode(build_mode)
        if self._build_explicit:
            self.mode = "source"

        uses_ccache = ccache_available() if ccache is None else bool(ccache)
        if self.mode == "prebuilt":
            self.configure_command = []
            self.build_command = [
                sys.executable,
                "-I",
                str(paths.entrypoint_path("cli.py")),
                "--build",
                "--prebuilt",
            ]
        else:
            self.configure_command = (
                list(configure)
                if configure is not None
                else configure_command(
                    self.engine_dir,
                    self.build_dir,
                    lvgl_src=self.lvgl_src,
                    lvgl_version=version,
                    user_app_dir=self.user_app_dir,
                    ccache=uses_ccache,
                    zlib_src=self.zlib_src,
                    libpng_src=self.libpng_src,
                )
            )
            self.build_command = (
                list(build)
                if build is not None
                else build_command(self.build_dir)
            )
        self.engine_path = (
            Path(engine_path)
            if engine_path is not None
            else self.built_engine_path
        )

    def _select_mode(self, requested: str) -> str:
        if requested != "auto":
            return requested
        if self.lvgl_src.is_dir():
            return "source"
        if self.sdk_dir.is_dir():
            return "prebuilt"
        return "source"

    @property
    def built_engine_path(self) -> Path:
        return self.build_dir / paths.engine_filename()

    @property
    def cache_path(self) -> Path:
        return self.build_dir / "CMakeCache.txt"

    def preflight(self) -> None:
        if self._build_explicit:
            return
        if self.mode == "prebuilt":
            self._resolve_prebuilt().preflight()
            return
        check = (
            self._missing_tools
            if self._missing_tools is not None
            else missing_build_tools
        )
        missing_tools = list(check())
        png_sources = (self.zlib_src, self.libpng_src)
        if (
            not self.lvgl_src.is_dir()
            or missing_tools
            or any(not path.is_dir() for path in png_sources)
        ):
            message = build_environment_message(
                lvgl_src=self.lvgl_src,
                lvgl_version=self.version,
                missing_tools=missing_tools,
                png_sources=png_sources,
            )
            if (
                not self.lvgl_src.is_dir()
                and (self.sdk_dir / "manifest.json").is_file()
            ):
                message += (
                    f" A host SDK exists at {self.sdk_dir}; pass --prebuilt "
                    "to build without LVGL source."
                )
            raise BuildError(message, command=list(self.configure_command))

    def needs_configure(self) -> bool:
        return cache_needs_configure(
            self.build_dir,
            lvgl_src=self.lvgl_src,
            lvgl_version=self.version,
            user_app_dir=self.user_app_dir,
            engine_dir=self.engine_dir,
            zlib_src=self.zlib_src,
            libpng_src=self.libpng_src,
        )

    def configure(self) -> str:
        return self._run_command(self.configure_command, "configure")

    def build(self) -> str:
        return self._run_command(self.build_command, "build")

    def execute(self, *, build: bool) -> BuildOutcome:
        if build and self.mode == "prebuilt" and not self._build_explicit:
            log_text = self._run_prebuilt()
        else:
            log_text = self._run_build() if build else None
        engine_path = self.resolve_engine()
        if log_text is None:
            log_text = (
                f"# build skipped (build=False)\n# engine: {engine_path}\n"
            )
        return BuildOutcome(engine_path=engine_path, log_text=log_text)

    def resolve_engine(self) -> Path:
        if not self._engine_explicit:
            self.engine_path = self.built_engine_path
        return self.engine_path

    def missing_engine_error(self) -> EngineNotFound | None:
        self.resolve_engine()
        if self.engine_path.is_file():
            return None
        return EngineNotFound(
            self.engine_path,
            configure_command=self.configure_command,
            build_command=self.build_command,
        )

    def _run_build(self) -> str:
        self.preflight()
        parts: list[str] = ["# build mode: source"]
        with build_lock(self.build_dir):
            try:
                ensure_engine_stopped(self.build_dir / paths.engine_filename())
                marker = self.build_dir / PREBUILT_MARKER
                if marker.is_file():
                    # A prebuilt engine is newer than the CMake objects; remove
                    # it so Ninja actually relinks the source build.
                    marker.unlink()
                    engine = self.built_engine_path
                    if engine.is_file():
                        engine.unlink()
                    parts.append(
                        "# mode switch: removed the prebuilt engine before "
                        "the source build\n"
                    )
                if self.needs_configure():
                    parts.append(self.configure())
                else:
                    parts.append(
                        "# phase: configure\n"
                        f"# skipped: cache matches {self.cache_path}\n"
                    )
                parts.append(self.build())
            except (BuildError, LinkError) as exc:
                exc.log_text = "\n".join([*parts, exc.log_text or ""])
                raise
        return "\n".join(parts)

    def _resolve_prebuilt(self) -> PrebuiltBuild:
        if self._prebuilt is not None:
            return self._prebuilt
        sdk = HostSdk.load(self.sdk_dir, expected_version=self.version)
        compiler, compiler_version = resolve_compiler(
            override=self._compiler,
            version=self._compiler_version,
        )
        if not versions_match(sdk.compiler_version, compiler_version):
            raise BuildError(
                compiler_mismatch_message(
                    expected=sdk.compiler_version,
                    found=compiler_version,
                    compiler=compiler,
                ),
                command=[compiler, "--version"],
            )
        self._prebuilt = PrebuiltBuild(
            sdk,
            compiler=compiler,
            compiler_version=compiler_version,
            user_app_dir=self.user_app_dir,
            engine_dir=self.engine_dir,
            build_dir=self.build_dir,
            engine_path=self.built_engine_path,
        )
        return self._prebuilt

    def _run_prebuilt(self) -> str:
        plan = self._resolve_prebuilt()
        plan.preflight()
        parts: list[str] = [plan.log_header()]
        with build_lock(self.build_dir):
            try:
                ensure_engine_stopped(self.built_engine_path)
                plan.object_dir.mkdir(parents=True, exist_ok=True)
                for step in plan.steps:
                    if step.object_path.is_file():
                        parts.append(
                            f"# cached: {step.source} -> {step.object_path.name}\n"
                        )
                        continue
                    parts.append(self._run_command(step.command, "compile"))
                parts.append(self._run_command(plan.link_command, "link"))
                plan.install_runtime_dlls()
            except (BuildError, LinkError) as exc:
                exc.log_text = "\n".join([*parts, exc.log_text or ""])
                raise
            plan.prune_objects()
            plan.write_marker()
        return "\n".join(parts)

    def _run_command(self, command: Sequence[str], phase: str) -> str:
        runner = self._runner if self._runner is not None else run_capture
        temp_dir = (self.build_dir / ".build-tmp").resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        for name in ("TMP", "TEMP", "TMPDIR"):
            env[name] = str(temp_dir)
        try:
            result = runner(list(command), timeout=BUILD_TIMEOUT_S, env=env)
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
