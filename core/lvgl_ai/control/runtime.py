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
    """Return the CLI flag an old engine rejected before announcing ready."""
    for line in log_tail:
        if "unknown argument" not in line:
            continue
        _, _, argument = line.partition("unknown argument")
        argument = argument.strip().lstrip(":").strip()
        return argument or line.strip()
    return None

# Session options owned by SessionStore; Runtime reads them through
# ``__getattr__`` so no second copy exists and the contract snapshot stays
# unchanged (properties would be recorded as new public members).
_SESSION_OPTIONS = frozenset(
    (
        "app",
        "build",
        "record",
        "live_frame",
        "record_changed_only",
        "mode",
        "lvgl_src",
        "sessions_root",
        "max_log_bytes",
        "session_retention",
        "ready",
    )
)


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


_UNSET = object()


class RuntimeOptions:
    """Production-side options for constructing a ``Runtime``.

    Only options that were provided are forwarded, so callers keep the
    ``Runtime`` defaults they do not set. The private engine/configure/build
    seams are deliberately absent.
    """

    def __init__(
        self,
        lvgl: str | None = _UNSET,
        *,
        app: str | None = _UNSET,
        width: int | None = _UNSET,
        height: int | None = _UNSET,
        build: bool = _UNSET,
        record: bool = _UNSET,
        live_frame: bool = _UNSET,
        record_changed_only: bool = _UNSET,
        headless: bool = _UNSET,
        window: bool = _UNSET,
        sessions_root: str | Path | None = _UNSET,
        timeout: float = _UNSET,
        diff_threshold: int = _UNSET,
        reference: str | Path | None = _UNSET,
        max_frames: int | None = _UNSET,
        max_log_bytes: int | None = _UNSET,
        session_retention: int | None = _UNSET,
    ) -> None:
        values = {
            "lvgl": lvgl,
            "app": app,
            "width": width,
            "height": height,
            "build": build,
            "record": record,
            "live_frame": live_frame,
            "record_changed_only": record_changed_only,
            "headless": headless,
            "window": window,
            "sessions_root": sessions_root,
            "timeout": timeout,
            "diff_threshold": diff_threshold,
            "reference": reference,
            "max_frames": max_frames,
            "max_log_bytes": max_log_bytes,
            "session_retention": session_retention,
        }
        self._kwargs = {
            name: value for name, value in values.items() if value is not _UNSET
        }

    def as_kwargs(self) -> dict[str, Any]:
        """Keyword arguments accepted by ``Runtime(**kwargs)``."""
        return dict(self._kwargs)


class RuntimeLike(Protocol):
    """The Runtime surface shared by LiveSession and scenario execution."""

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
    ``lvgl_engine`` before launch. ``record=True`` keeps frames and records
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
    """

    def __init__(
        self,
        lvgl: str | None = None,
        *,
        app: str | None = None,
        width: int | None = None,
        height: int | None = None,
        build: bool = True,
        record: bool = True,
        live_frame: bool = False,
        record_changed_only: bool = True,
        headless: bool = True,
        window: bool = False,
        sessions_root: str | Path | None = None,
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
            raise ValueError("pass either _engine_path or _engine_command, not both")
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
        # ``app`` selects the user app variant through the documented LVGL_AI_DEMO
        # contract. An explicit value wins; otherwise the inherited environment
        # is used and recorded so evidence is self-describing.
        resolved_app = (
            app
            if app is not None
            else (os.environ.get("LVGL_AI_DEMO") or None)
        )
        # ``None`` means the engine default; otherwise both dimensions exist.
        self.width = None if display is None else display[0]
        self.height = None if display is None else display[1]
        resolved_build = bool(build)
        resolved_record = bool(record)
        # Keep one overwritten live.rgba raw preview for the web stream. It
        # works with record=True as well and is never part of the evidence.
        resolved_live_frame = bool(live_frame)
        # Skip PNGs that are pixel-identical to the previous retained frame.
        # frame_no counts retained frames, not ticks.
        resolved_record_changed_only = bool(record_changed_only)
        # ``window=True`` or ``headless=False`` asks for the real window;
        # ``window=True`` wins so callers do not need to pass both.
        self.window = bool(window) or not bool(headless)
        self.headless = not self.window
        resolved_mode = "window" if self.window else "headless"
        self.timeout = float(timeout)
        self.diff_threshold = diff_threshold
        # Full frames are capped so a long animation cannot exhaust disk or
        # context; the manifest and the timeline end row report truncation.
        if max_frames is None:
            max_frames = _env_positive_int("LVGL_AI_MAX_FRAMES", DEFAULT_MAX_FRAMES)
        self.max_frames = _positive_int(
            max_frames, "max_frames", default=DEFAULT_MAX_FRAMES
        )
        # engine.log keeps its tail; RuntimeCrash.log_tail must stay usable.
        if max_log_bytes is None:
            max_log_bytes = _env_positive_int(
                "LVGL_AI_MAX_LOG_BYTES", DEFAULT_MAX_LOG_BYTES
            )
        resolved_max_log_bytes = _positive_int(
            max_log_bytes, "max_log_bytes", default=DEFAULT_MAX_LOG_BYTES
        )
        # Older sessions are pruned right after the new session directory is
        # reserved; None disables pruning for embedders and tests.
        if session_retention is not None and (
            isinstance(session_retention, bool)
            or not isinstance(session_retention, int)
            or session_retention < 0
        ):
            raise ValueError(
                "session_retention must be a non-negative integer or None; "
                f"got {session_retention!r}"
            )
        # The engine runs with cwd=REPO_ROOT, so a relative reference must be
        # anchored to the caller's cwd here, not there.
        self.reference = (
            None if reference is None else Path(reference).expanduser().resolve()
        )
        if self.reference is not None and not self.reference.is_file():
            raise FileNotFoundError(f"reference image not found: {self.reference}")
        # BuildPlan owns preflight, the CMake cache check, configure/build and
        # engine path resolution. An explicit engine path is a test/embedding
        # seam and is never replaced. Runtime mirrors the resolved paths for
        # callers and session evidence.
        self._plan = BuildPlan(
            self.lvgl,
            configure=_configure_command,
            build=_build_command,
            engine_path=_engine_path,
        )
        self.build_dir = self._plan.build_dir
        self.engine_path = self._plan.engine_path
        self._engine_command = list(_engine_command) if _engine_command else None
        resolved_sessions_root = (
            Path(sessions_root).expanduser().resolve()
            if sessions_root is not None
            else paths.sessions_root_from_env()
        )
        # SessionStore owns this session's options and evidence: the
        # directory, manifest, build log, engine log, preview and retention.
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
            mode=resolved_mode,
        )

        self.session_id: str | None = None
        self.session_dir: Path | None = None
        self.engine_log_path: Path | None = None
        self.manifest_path: Path | None = None

        # Process and line-protocol ownership lives in EngineLink; Runtime
        # keeps the public actions and build orchestration, SessionStore owns
        # the session evidence.
        self._link: EngineLink | None = None
        self._session_used = False
        # Newest reserved frame number the engine reported. Recording uses a
        # background encoder, so the PNG for the newest frame may still be
        # queued; stop() drains it before the final manifest is written.
        self.frame_count = 0
        # Current virtual time from the newest engine reply. Static live
        # screens keep frame_count unchanged but t_ms keeps advancing.
        self.t_ms = 0
        # The typed failure that made the session stop early; stop() maps it
        # to the manifest status instead of reporting "ok".
        self._failure: BaseException | None = None

    def __getattr__(self, name: str) -> Any:
        if name in _SESSION_OPTIONS:
            store = self.__dict__.get("_store")
            if store is not None:
                return getattr(store, name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _SESSION_OPTIONS:
            raise AttributeError(
                f"{type(self).__name__!r} attribute {name!r} is read-only; "
                "it is owned by the session store"
            )
        super().__setattr__(name, value)

    # ---- lifecycle -----------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._link is not None and self._link.is_running

    @property
    def pid(self) -> int | None:
        """OS process id of the engine, or ``None`` before ``start()``."""
        return None if self._link is None else self._link.pid

    @property
    def exit_code(self) -> int | None:
        """Engine exit code once it stopped, or ``None`` while running."""
        return None if self._link is None else self._link.exit_code

    @property
    def recording(self) -> Recording:
        """Read-only evidence view of this session; annotations stay writable."""
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
        # The session exists before the build so a build/link failure or a
        # missing engine still leaves build.log + manifest.json behind.
        self._open_session()
        self._store.prune()

        if self.build:
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
            # The plan resolves before composing build.log, so the evidence
            # names the engine that will actually run, not only the
            # source-build path.
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
                    RECORD_QUIT_TIMEOUT_S if self.record else QUIT_TIMEOUT_S
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
                # Keep the attributes truthful when the platform falls back.
                self.window = False
                self.headless = True
            self._store.write_manifest(SessionOutcome.ok())
        except BaseException as exc:
            self._failure = exc
            # The EOF was seen before the process was reaped; fill in the
            # exit code and the complete tail now that both pumps joined.
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
                raise error
            raise
        return self

    def stop(self) -> None:
        if self._link is None or not self._link.is_started:
            self._store.close_log()
            return

        link = self._link
        try:
            exit_code = link.shutdown(send_quit=True)
        finally:
            # Release the evidence handles even when shutdown itself fails;
            # otherwise Windows keeps the session directory undeletable.
            self._store.close_log()
            self._store.discard_preview()

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

    def record_error(self, error: BaseException) -> None:
        """Remember a harness-side failure for the final manifest.

        The CLI (or another loop owner) calls this when an error happened
        outside a Runtime command — for example a scenario that failed
        validation before its first step. ``stop()`` then writes
        ``harness_error`` with this error instead of ``ok``.
        """
        if self.session_dir is None or self._failure is error:
            return
        self._failure = error

    def __enter__(self) -> Runtime:
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.stop()
        return False

    # ---- input and time ------------------------------------------------

    def pointer(self, action: str, x: int, y: int) -> dict[str, Any]:
        """Drive the standard virtual pointer indev at ``(x, y)``.

        The reply carries ``hit`` (object name, ``""`` when unnamed) and
        ``hit_class`` (e.g. ``"lv_button"``) from a real LVGL hit test.
        """
        require_action("pointer", action)
        point_x = require_non_negative_int(x, "x")
        point_y = require_non_negative_int(y, "y")
        reply = self._command("pointer", action, str(point_x), str(point_y))
        self._require_reply(reply, ("hit", "hit_class"), "pointer")
        return reply

    def key(self, action: str, key: str) -> dict[str, Any]:
        """Deliver a key press or release to the standard virtual keypad indev.

        ``key`` is an LVGL ``LV_KEY_*`` name such as ``"ENTER"`` or
        ``"LV_KEY_ENTER"`` (case-insensitive), or a printable ASCII
        ``CHAR_<code>`` token such as ``"CHAR_65"`` for ``A``. Unknown names and
        out-of-range codes raise :class:`ScenarioError` before any command is
        sent. The reply carries ``delivered``: true when LVGL read the keypad
        indev.
        """
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
        """Turn the standard virtual encoder indev by ``diff`` steps.

        Positive turns move focus forward (LVGL ``enc_diff > 0``); negative
        turns move backward. The reply carries ``delivered``: true when LVGL
        read the encoder indev.
        """
        require_action("encoder", action)
        steps = require_int16(diff, "diff")
        reply = self._command("encoder", "turn", str(steps))
        self._require_reply(reply, ("delivered",), "encoder")
        return reply

    def tick(self, ms: int, *, track_check: bool = True) -> dict[str, Any]:
        """Advance virtual time by ``ms`` and record the refreshed frame.

        With ``record_changed_only`` an identical frame is skipped and the
        frame number stays unchanged. ``track_check=False`` is used by the web
        live ticker so repetitive ticks do not grow ``manifest.checks``.
        """
        interval = require_non_negative_int(ms, "ms")
        return self._command(
            "tick", str(interval), track_check=track_check
        )

    def wait(self, ms: int | None = None, *, frames: int | None = None) -> dict[str, Any]:
        """Advance virtual time in 16 ms slices, or by a fixed frame count."""
        if (ms is None) == (frames is None):
            raise ValueError("wait needs exactly one of ms or frames")
        if frames is not None:
            count = require_non_negative_int(frames, "frames")
            return self._command("wait", "frames", str(count))
        interval = require_non_negative_int(ms, "ms")
        return self._command("wait", str(interval))

    def wait_stable(
        self, max_ms: int, stable_frames: int
    ) -> dict[str, Any]:
        """Wait until the picture stops changing, up to ``max_ms``.

        Polls ``wait`` in 16 ms steps (the engine's own wait step) and counts
        consecutive replies whose ``changed`` flag is false. It returns as soon
        as ``stable_frames`` unchanged steps accumulate, or when ``max_ms`` is
        spent. ``changed`` comes from the adapter flush flag and is independent
        of recording and changed-only frame retention, so a skipped frame is
        never mistaken for a stable picture.

        Returns ``waited_ms``, ``stable_frames`` (the achieved streak) and
        ``stable``. An engine without the ``changed`` field is rejected on the
        first poll instead of waiting forever.
        """
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
        """Write ``snapshots/NNN_<label>.png`` and a timeline snapshot row."""
        token = require_token(label, "snapshot label")
        reply = self._command("snapshot", token)
        self._require_reply(reply, ("file",), "snapshot")
        return reply

    def mark(self, mark_id: str) -> dict[str, Any]:
        """Write a timeline mark row with ``id``."""
        token = require_token(mark_id, "mark id")
        return self._command("mark", token)

    def input(self, events) -> list[dict[str, Any]]:
        """Replay a ``lvgl-ai-input-v1`` list, stably sorted by ``at_ms``.

        ``at_ms`` is an offset from the start of this call. Time advances with
        ``wait`` semantics, so frames are recorded while the gesture plays.
        Invalid events raise :class:`ScenarioError` before any command is sent.
        """
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

    # ---- protocol ------------------------------------------------------

    def _engine_command_line(self) -> list[str]:
        assert self.session_dir is not None
        engine_args = [
            "--session", str(self.session_dir),
            "--record" if self.record else "--no-record",
            "--diff-threshold", str(self.diff_threshold),
            "--max-frames", str(self.max_frames),
        ]
        if self.record:
            engine_args.append("--async-encode")
        if self.width is not None and self.height is not None:
            engine_args.extend(
                ["--width", str(self.width), "--height", str(self.height)]
            )
        engine_args.append("--window" if self.window else "--headless")
        if self.live_frame:
            engine_args.append("--live-frame")
        if self.record_changed_only:
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
        """Mirror ``ready.frames`` once it validates, as the inline check did."""
        self.frame_count = frames

    def _record_reply(
        self,
        command: str,
        ok: bool,
        reply: dict | None,
        track_check: bool,
    ) -> None:
        """Account for one command reply; the link never judges the picture."""
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
        """Log that a protocol command ran; never judges the picture."""
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
            seq=seq if isinstance(seq, int) and not isinstance(seq, bool) else None,
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

    # ---- engine log ----------------------------------------------------

    def log_tail(self, n: int = 40) -> list[str]:
        """Last ``n`` lines of engine.log (stdout and stderr)."""
        return self._store.log_tail(n)

    # ---- session -------------------------------------------------------

    def _open_session(self) -> None:
        self._store.create()
        # Public attributes mirror the store so callers (CLI, web, tests) keep
        # reading the same names.
        self.session_id = self._store.session_id
        self.session_dir = self._store.session_dir
        self.engine_log_path = self._store.engine_log_path
        self.manifest_path = self._store.manifest_path


def _build_log_from_error(error: BaseException) -> str:
    log_text = getattr(error, "log_text", None)
    if log_text:
        return log_text
    return f"# build failed\n{error}\n"


def _require_reply_fields(reply: dict[str, Any], fields: tuple[str, ...], verb: str) -> None:
    missing = [field for field in fields if field not in reply]
    if missing:
        raise ProtocolError(
            f"{verb} reply is missing {', '.join(missing)}",
            seq=reply.get("seq") if isinstance(reply.get("seq"), int) else None,
        )
