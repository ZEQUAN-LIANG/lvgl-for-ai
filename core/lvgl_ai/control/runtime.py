"""Runtime: one LVGL engine process == one session.

The Python layer is the only control layer. This module keeps the public
actions and lifecycle; :class:`~lvgl_ai.control.build_plan.BuildPlan` owns
preflight, configure/build and engine path resolution,
:class:`~lvgl_ai.control.engine_link.EngineLink` owns the process and the line
protocol, and :class:`~lvgl_ai.control.session.SessionStore` owns the session
evidence files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from .. import paths
from .build_plan import BuildPlan
from .errors import ProtocolError, RuntimeCrash, ScenarioError
from .retention import DEFAULT_SESSION_LIMIT
from .input import (
    TOKEN_PATTERN,
    is_token,
    normalize_input_events,
    require_action,
    require_display_pair,
    require_int16,
    require_integer,
    require_non_negative_int,
    require_token,
    resolve_key,
)
from .recording import Recording
from .engine_link import RECORD_QUIT_TIMEOUT_S, QUIT_TIMEOUT_S, EngineLink
from .session import DEFAULT_MAX_LOG_BYTES, SessionOutcome, SessionStore

DEFAULT_MAX_FRAMES = 600
WAIT_STABLE_STEP_MS = 16

STALE_ENGINE_HINT = "engine 产物早于当前 Runtime，请用 --build 重建"


def _stale_engine_argument(log_tail: list[str]) -> str | None:
    for line in log_tail:
        if "unknown argument" not in line:
            continue
        _, _, argument = line.partition("unknown argument")
        argument = argument.strip().lstrip(":").strip()
        return argument or line.strip()
    return None


def _positive_int(value: object, name: str, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer; got {value!r}")
    return value


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer; got {raw!r}") from exc
    return _positive_int(value, name, default=default)


class RuntimeLike(Protocol):
    session_id: str | None
    session_dir: Path | None
    engine_log_path: Path | None
    manifest_path: Path | None
    ready: dict[str, Any] | None
    app: str | None
    mode: str
    frame_count: int
    t_ms: int
    pid: int | None
    exit_code: int | None
    is_running: bool

    def start(self) -> Any: ...

    def stop(self) -> None: ...

    def log_tail(self, n: int = 40) -> list[str]: ...

    def record_error(self, error: BaseException) -> None: ...

    def tick(self, ms: int, *, track_check: bool = True) -> dict[str, Any]: ...

    def wait(
        self, ms: int | None = None, *, frames: int | None = None
    ) -> dict[str, Any]: ...

    def pointer(self, action: str, x: int, y: int) -> dict[str, Any]: ...

    def key(self, action: str, key: str) -> dict[str, Any]: ...

    def encoder(self, action: str, diff: int) -> dict[str, Any]: ...

    def mark(self, mark_id: str) -> dict[str, Any]: ...

    def snapshot(self, label: str) -> dict[str, Any]: ...


class Runtime:
    """An LVGL engine process and its session directory.

    One instance owns exactly one session; create a new Runtime for another
    run. ``build=True`` (the default) reconfigures when needed and rebuilds
    ``lvgl_engine`` before launch; ``build_mode`` is ``auto`` (source when
    ``lvgl-src`` exists, otherwise the prebuilt SDK), ``source`` or
    ``prebuilt``. ``record=True`` keeps frames and records
    only frames whose pixels differ from the previous retained frame;
    ``record_changed_only=False`` is an internal test seam that keeps
    identical frames too. Frame numbers stay contiguous and ``max_frames``
    counts retained frames. ``live_frame=True``
    writes an overwritten ``live.rgba`` raw preview for the web stream; it can
    be combined with ``record=True`` and is never an evidence artifact.
    ``record=False`` with ``live_frame=True`` keeps only that preview file, so
    a test session shows frames without recording evidence.
    ``app`` selects the user app variant by setting ``LVGL_AI_DEMO`` for the
    engine and is recorded in the manifest; ``None`` inherits the environment.
    ``width``/``height`` set the display size at startup and must be provided
    together; ``None`` keeps the engine default (800x600) and is recorded from
    the engine's ``ready`` message.
    ``window=True`` asks the engine for a Win32 GDI window; real mouse and
    keyboard input then work alongside the virtual indevs. ``headless`` stays
    the default, and non-Windows engines fall back to headless.

    Session options are constructor keywords only. ``SessionStore`` owns
    their values after construction; Runtime exposes just ``app`` / ``mode`` /
    ``ready`` for the :class:`RuntimeLike` surface.
    """

    def __init__(
        self,
        lvgl: str | None = None,
        *,
        app: str | None = None,
        width: int | None = None,
        height: int | None = None,
        build: bool = True,
        build_mode: str | None = None,
        record: bool = True,
        live_frame: bool = False,
        record_changed_only: bool = True,
        headless: bool = True,
        window: bool = False,
        sessions_root: str | Path | None = None,
        scenario: str | Path | None = None,
        timeout: float = 30.0,
        diff_threshold: int = 10,
        reference: str | Path | None = None,
        max_frames: int | None = None,
        max_log_bytes: int | None = None,
        session_retention: int | None = DEFAULT_SESSION_LIMIT,
        _engine_path: str | Path | None = None,
        _engine_command: list[str] | None = None,
        _configure_command: list[str] | None = None,
        _build_command: list[str] | None = None,
    ) -> None:
        if _engine_path is not None and _engine_command is not None:
            raise ValueError(
                "pass either _engine_path or _engine_command, not both"
            )
        if app is not None and not is_token(app):
            raise ValueError(f"app must match {TOKEN_PATTERN}; got {app!r}")
        display = require_display_pair(width, height)
        if (
            isinstance(diff_threshold, bool)
            or not isinstance(diff_threshold, int)
            or not 0 <= diff_threshold <= 255
        ):
            raise ValueError(
                f"diff_threshold must be an integer 0..255; got {diff_threshold!r}"
            )

        self.lvgl = lvgl or paths.lvgl_version_from_env()
        resolved_app = (
            app
            if app is not None
            else (os.environ.get("LVGL_AI_DEMO") or None)
        )
        self.width = None if display is None else display[0]
        self.height = None if display is None else display[1]
        resolved_build = bool(build)
        resolved_record = bool(record)
        resolved_live_frame = bool(live_frame)
        resolved_record_changed_only = bool(record_changed_only)
        self.window = bool(window) or not bool(headless)
        self.headless = not self.window
        resolved_mode = "window" if self.window else "headless"
        self.timeout = float(timeout)
        self.diff_threshold = diff_threshold
        if max_frames is None:
            max_frames = _env_positive_int(
                "LVGL_AI_MAX_FRAMES", DEFAULT_MAX_FRAMES
            )
        self.max_frames = _positive_int(
            max_frames, "max_frames", default=DEFAULT_MAX_FRAMES
        )
        if max_log_bytes is None:
            max_log_bytes = _env_positive_int(
                "LVGL_AI_MAX_LOG_BYTES", DEFAULT_MAX_LOG_BYTES
            )
        resolved_max_log_bytes = _positive_int(
            max_log_bytes, "max_log_bytes", default=DEFAULT_MAX_LOG_BYTES
        )
        if session_retention is not None and (
            isinstance(session_retention, bool)
            or not isinstance(session_retention, int)
            or session_retention < 0
        ):
            raise ValueError(
                "session_retention must be a non-negative integer or None; "
                f"got {session_retention!r}"
            )
        self.reference = (
            None
            if reference is None
            else Path(reference).expanduser().resolve()
        )
        if self.reference is not None and not self.reference.is_file():
            raise FileNotFoundError(
                f"reference image not found: {self.reference}"
            )
        self._plan = BuildPlan(
            self.lvgl,
            configure=_configure_command,
            build=_build_command,
            engine_path=_engine_path,
            build_mode=build_mode or "auto",
        )
        self.build_dir = self._plan.build_dir
        self.engine_path = self._plan.engine_path
        self.build_mode = self._plan.mode
        self._engine_command = (
            list(_engine_command) if _engine_command else None
        )
        resolved_sessions_root = (
            Path(sessions_root).expanduser().resolve()
            if sessions_root is not None
            else paths.sessions_root_from_env()
        )
        self._store = SessionStore(
            resolved_sessions_root,
            record=resolved_record,
            live_frame=resolved_live_frame,
            build=resolved_build,
            retention=session_retention,
            max_log_bytes=resolved_max_log_bytes,
            app=resolved_app,
            record_changed_only=resolved_record_changed_only,
            lvgl_src=self._plan.lvgl_src,
            scenario=scenario,
            mode=resolved_mode,
        )

        self.session_id: str | None = None
        self.session_dir: Path | None = None
        self.engine_log_path: Path | None = None
        self.manifest_path: Path | None = None

        self._link: EngineLink | None = None
        self._session_used = False
        self.frame_count = 0
        self.t_ms = 0
        self._failure: BaseException | None = None

    @property
    def app(self) -> str | None:
        return self._store.app

    @property
    def mode(self) -> str:
        return self._store.mode

    @property
    def ready(self) -> dict[str, Any] | None:
        return self._store.ready

    @property
    def is_running(self) -> bool:
        return self._link is not None and self._link.is_running

    @property
    def pid(self) -> int | None:
        return None if self._link is None else self._link.pid

    @property
    def exit_code(self) -> int | None:
        return None if self._link is None else self._link.exit_code

    @property
    def recording(self) -> Recording:
        if self.session_dir is None:
            raise RuntimeError("no session yet; call start() first")
        return Recording.open(self.session_dir)

    def start(self) -> Runtime:
        if self.is_running:
            return self
        if self._session_used:
            raise RuntimeError(
                "this Runtime instance already ran a session; "
                "create a new Runtime for another session"
            )

        self._session_used = True
        self._open_session()
        self._store.prune()

        if self._store.build:
            try:
                outcome = self._plan.execute(build=True)
            except BaseException as exc:
                self._failure = exc
                self._store.write_build_log(_build_log_from_error(exc))
                self._store.write_manifest(
                    SessionOutcome.from_failure(exc), build_status="error"
                )
                self._store.close_log()
                raise
        else:
            outcome = self._plan.execute(build=False)
        self.engine_path = outcome.engine_path
        self._store.write_build_log(outcome.log_text)

        error = (
            None
            if self._engine_command is not None
            else self._plan.missing_engine_error()
        )
        if error is not None:
            self._failure = error
            self._store.write_manifest(SessionOutcome.from_failure(error))
            self._store.close_log()
            raise error

        try:
            self._link = EngineLink(
                self._engine_command_line(),
                env=self._engine_env(),
                cwd=str(paths.REPO_ROOT),
                timeout=self.timeout,
                log=self._store.append_log,
                log_tail=self._store.log_tail,
                log_path=self._store.engine_log_path,
                on_check=self._record_reply,
                quit_timeout=(
                    RECORD_QUIT_TIMEOUT_S
                    if self._store.record
                    else QUIT_TIMEOUT_S
                ),
                session_id=self.session_id,
                app=self.app,
            )
            self._link.start()
            ready = self._link.await_ready(
                self.timeout, on_frames=self._set_ready_frames
            )
            self._store.note_ready(ready)
            self._store.note_mode(ready.get("mode", self.mode))
            if self.mode != "window":
                if self.window:
                    self._store.append_log(
                        "[harness] window requested but the engine reported "
                        f"mode={self.mode}; continuing headless"
                    )
                self.window = False
                self.headless = True
            self._store.write_manifest(SessionOutcome.ok())
        except BaseException as exc:
            self._failure = exc
            exit_code = (
                None
                if self._link is None
                else self._link.shutdown(send_quit=False)
            )
            self._store.discard_preview()
            error = exc
            if isinstance(exc, RuntimeCrash) and self._link is not None:
                self._link.complete_crash(exc, exit_code=exit_code)
                stale_argument = _stale_engine_argument(exc.log_tail)
                if stale_argument is not None:
                    error = RuntimeCrash(
                        f"{STALE_ENGINE_HINT}: {stale_argument}",
                        exit_code=exc.exit_code,
                        log_tail=exc.log_tail,
                        log_path=exc.log_path,
                    )
                    self._failure = error
            try:
                self._store.write_manifest(SessionOutcome.from_failure(error))
            finally:
                self._store.close_log()
            if error is not exc:
                raise error from exc
            raise
        return self

    def stop(self) -> None:
        if self._link is None or not self._link.is_started:
            self._store.close_log()
            return

        link = self._link
        shutdown_error: BaseException | None = None
        exit_code: int | None = None
        try:
            exit_code = link.shutdown(send_quit=True)
        except BaseException as exc:
            shutdown_error = exc
            exit_code = link.exit_code
        finally:
            self._store.close_log()
            self._store.discard_preview()

        if shutdown_error is not None and self._failure is None:
            self._failure = RuntimeCrash(
                f"engine did not exit cleanly: {shutdown_error}",
                exit_code=exit_code,
                log_tail=self._store.log_tail(),
                log_path=self.engine_log_path,
            )

        if self.session_dir is not None:
            outcome = SessionOutcome.resolve(
                self._failure,
                exit_code=exit_code,
                unexpected_exit=link.unexpected_exit,
                make_crash=lambda message: link.complete_crash(
                    RuntimeCrash(message), exit_code=exit_code
                ),
            )
            self._store.write_manifest(outcome)

        if shutdown_error is not None:
            raise shutdown_error

    def record_error(self, error: BaseException) -> None:
        if self.session_dir is None or self._failure is error:
            return
        self._failure = error

    def __enter__(self) -> Runtime:
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.stop()
        return False

    def pointer(self, action: str, x: int, y: int) -> dict[str, Any]:
        require_action("pointer", action)
        point_x = require_non_negative_int(x, "x")
        point_y = require_non_negative_int(y, "y")
        reply = self._command("pointer", action, str(point_x), str(point_y))
        self._require_reply(reply, ("hit", "hit_class"), "pointer")
        return reply

    def key(self, action: str, key: str) -> dict[str, Any]:
        require_action("key", action)
        try:
            canonical, code = resolve_key(key)
        except ScenarioError as exc:
            self._failure = exc
            raise
        reply = self._command("key", action, str(code), canonical)
        self._require_reply(reply, ("delivered",), "key")
        return reply

    def encoder(self, action: str, diff: int) -> dict[str, Any]:
        require_action("encoder", action)
        steps = require_int16(diff, "diff")
        reply = self._command("encoder", "turn", str(steps))
        self._require_reply(reply, ("delivered",), "encoder")
        return reply

    def tick(self, ms: int, *, track_check: bool = True) -> dict[str, Any]:
        interval = require_non_negative_int(ms, "ms")
        return self._command("tick", str(interval), track_check=track_check)

    def wait(
        self, ms: int | None = None, *, frames: int | None = None
    ) -> dict[str, Any]:
        if (ms is None) == (frames is None):
            raise ValueError("wait needs exactly one of ms or frames")
        if frames is not None:
            count = require_non_negative_int(frames, "frames")
            return self._command("wait", "frames", str(count))
        interval = require_non_negative_int(ms, "ms")
        return self._command("wait", str(interval))

    def wait_stable(self, max_ms: int, stable_frames: int) -> dict[str, Any]:
        limit = require_non_negative_int(max_ms, "max_ms")
        target = require_integer(stable_frames, "stable_frames", minimum=1)
        waited_ms = 0
        stable_count = 0
        while waited_ms < limit and stable_count < target:
            step = min(WAIT_STABLE_STEP_MS, limit - waited_ms)
            reply = self.wait(ms=step)
            waited_ms += step
            if self._wait_changed(reply):
                stable_count = 0
            else:
                stable_count += 1
        return {
            "waited_ms": waited_ms,
            "stable_frames": stable_count,
            "stable": stable_count >= target,
        }

    def snapshot(self, label: str) -> dict[str, Any]:
        token = require_token(label, "snapshot label")
        reply = self._command("snapshot", token)
        self._require_reply(reply, ("file",), "snapshot")
        return reply

    def mark(self, mark_id: str) -> dict[str, Any]:
        token = require_token(mark_id, "mark id")
        return self._command("mark", token)

    def input(self, events) -> list[dict[str, Any]]:
        try:
            ordered = normalize_input_events(events)
        except ScenarioError as exc:
            self._failure = exc
            raise
        replies: list[dict[str, Any]] = []
        elapsed = 0
        for event in ordered:
            delay = event["at_ms"] - elapsed
            if delay > 0:
                self.wait(ms=delay)
                elapsed += delay
            replies.append(self._dispatch_input_event(event))
        return replies

    def _dispatch_input_event(self, event: dict[str, Any]) -> dict[str, Any]:
        device = event["device"]
        if device == "pointer":
            return self.pointer(event["action"], event["x"], event["y"])
        if device == "key":
            return self.key(event["action"], event["key"])
        return self.encoder("turn", event["diff"])

    def _engine_command_line(self) -> list[str]:
        assert self.session_dir is not None
        engine_args = [
            "--session",
            str(self.session_dir),
            "--record" if self._store.record else "--no-record",
            "--diff-threshold",
            str(self.diff_threshold),
            "--max-frames",
            str(self.max_frames),
        ]
        if self._store.record:
            engine_args.append("--async-encode")
        if self.width is not None and self.height is not None:
            engine_args.extend(
                ["--width", str(self.width), "--height", str(self.height)]
            )
        engine_args.append("--window" if self.window else "--headless")
        if self._store.live_frame:
            engine_args.append("--live-frame")
        if self._store.record_changed_only:
            engine_args.append("--record-changed-only")
        if self.reference is not None:
            engine_args.extend(["--reference", str(self.reference)])
        if self._engine_command is None:
            return [str(self.engine_path), *engine_args]
        return [*self._engine_command, *engine_args]

    def _engine_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.app is not None:
            env["LVGL_AI_DEMO"] = self.app
        # A multi-version release stores the FreeType DLL once under
        # ``sdk/common/lib`` instead of next to every engine.  Windows finds
        # it through PATH for ``--no-build`` runs; rebuilt engines also get a
        # local copy from ``install_runtime_dlls``.
        shared_lib = paths.shared_sdk_lib_dir()
        if shared_lib is not None:
            env["PATH"] = str(shared_lib) + os.pathsep + env.get("PATH", "")
        return env

    def _command(
        self,
        verb: str,
        *args: str,
        timeout: float | None = None,
        track_failure: bool = True,
        track_check: bool = True,
    ) -> dict:
        if self._link is None:
            raise RuntimeCrash(
                "engine is not running",
                exit_code=None,
                log_tail=self.log_tail(),
                log_path=self.engine_log_path,
            )
        try:
            reply = self._link.command(
                verb,
                *args,
                timeout=timeout if timeout is not None else self.timeout,
                track_check=track_check,
            )
        except ProtocolError as exc:
            if track_failure:
                self._failure = exc
            raise
        except RuntimeCrash as exc:
            if track_failure:
                self._failure = exc
            raise
        return reply

    def _set_ready_frames(self, frames: int) -> None:
        self.frame_count = frames

    def _record_reply(
        self,
        command: str,
        ok: bool,
        reply: dict | None,
        track_check: bool,
    ) -> None:
        if reply is not None and reply.get("truncated") is True:
            self._store.note_truncated()
        self._record_check(
            command,
            ok,
            None if reply is None else reply.get("frames"),
            None if reply is None else reply.get("t_ms"),
            append=track_check,
        )

    def _record_check(
        self,
        command: str,
        ok: bool,
        frame_no: Any,
        t_ms: Any = None,
        *,
        append: bool = True,
    ) -> None:
        if isinstance(frame_no, bool) or not isinstance(frame_no, int):
            frame_no = None
        else:
            self.frame_count = frame_no
        if not isinstance(t_ms, bool) and isinstance(t_ms, int):
            self.t_ms = t_ms
        if append:
            self._store.append_check(command, ok, frame_no)

    def _wait_changed(self, reply: dict[str, Any]) -> bool:
        changed = reply.get("changed")
        if isinstance(changed, bool):
            return changed
        if "changed" in reply:
            message = f"wait reply.changed must be a boolean; got {changed!r}"
        else:
            message = f"wait reply is missing changed; {STALE_ENGINE_HINT}"
        seq = reply.get("seq")
        error = ProtocolError(
            message,
            seq=seq
            if isinstance(seq, int) and not isinstance(seq, bool)
            else None,
        )
        self._failure = error
        raise error

    def _require_reply(
        self, reply: dict[str, Any], fields: tuple[str, ...], verb: str
    ) -> None:
        try:
            _require_reply_fields(reply, fields, verb)
        except ProtocolError as exc:
            self._failure = exc
            raise

    def log_tail(self, n: int = 40) -> list[str]:
        return self._store.log_tail(n)

    def _open_session(self) -> None:
        self._store.create()
        self.session_id = self._store.session_id
        self.session_dir = self._store.session_dir
        self.engine_log_path = self._store.engine_log_path
        self.manifest_path = self._store.manifest_path


def _build_log_from_error(error: BaseException) -> str:
    log_text = getattr(error, "log_text", None)
    if log_text:
        return log_text
    return f"# build failed\n{error}\n"


def _require_reply_fields(
    reply: dict[str, Any], fields: tuple[str, ...], verb: str
) -> None:
    missing = [field for field in fields if field not in reply]
    if missing:
        raise ProtocolError(
            f"{verb} reply is missing {', '.join(missing)}",
            seq=reply.get("seq")
            if isinstance(reply.get("seq"), int)
            else None,
        )
