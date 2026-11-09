"""One live Runtime, its raw preview hub, ticker and lifecycle state.

``LiveSession`` is the internal seam for the web live preview. It owns the
single ``Runtime``, the temporary session root used by test mode, the
``LiveFrameHub`` and its publisher thread, the selected app, and the
idle -> starting -> running -> stopping state machine.

It raises :class:`LiveError` (code / message / detail) and carries no HTTP
semantics; ``WebApp`` maps the code to a status and stays a composition root.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..control.errors import ScenarioError, dump_error
from ..control.recording import Recording
from ..control.runtime import Runtime
from ..control.session_schema import PREVIEW_FILE, TIMELINE_FILE
from .transport import LiveFrame, LiveFrameHub
from .urls import frame_url

IDLE = "idle"
STARTING = "starting"
RUNNING = "running"
STOPPING = "stopping"
LIVE_KINDS = ("record", "test")

# One virtual frame per browser input event. LVGL only reads indevs and draws
# inside a tick, so the live session must advance time after forwarding input.
LIVE_INPUT_STEP_MS = 16
# Both modes advance one 33 ms frame (about 30 fps). Recording hands PNG
# encoding to the engine's worker pool, so its ticker can share the test
# preview's cadence.
LIVE_TEST_TICK_MS = 33
LIVE_TEST_INTERVAL_S = 0.033
LIVE_TICK_MS = 33
LIVE_TICK_INTERVAL_S = 0.033
# kind -> (virtual ms per tick, wall-clock seconds between ticks)
TICK_PROFILE = {
    "test": (LIVE_TEST_TICK_MS, LIVE_TEST_INTERVAL_S),
    "record": (LIVE_TICK_MS, LIVE_TICK_INTERVAL_S),
}


class LiveError(Exception):
    """A live-session domain error; the HTTP adapter maps ``code``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


def validate_live_kind(kind: str) -> None:
    """Reject an unknown mode before any lock, ticker or runtime is touched."""
    if kind not in LIVE_KINDS:
        raise LiveError(
            "invalid_live_mode", f"unknown live mode: {kind}"
        )


def empty_live_status() -> dict[str, Any]:
    """The live status shape before any session exists."""
    return {
        "running": False,
        "pid": None,
        "mode": None,
        "session_id": None,
        "session_dir": None,
        "app": None,
        "status": None,
        "error": None,
        "frame_count": 0,
        "t_ms": 0,
        "width": None,
        "height": None,
        "latest_frame": None,
        "test": False,
    }


class LiveStream:
    """A reader bound to the hub of one running live session.

    The handler captures one stream when the response starts. A later
    session's hub must not take over the same HTTP response, so the binding
    never follows a restart.
    """

    def __init__(self, hub: LiveFrameHub) -> None:
        self._hub = hub

    @property
    def closed(self) -> bool:
        return self._hub.closed

    def wait_frame(
        self, after_seq: int, timeout: float | None = None
    ) -> LiveFrame | None:
        return self._hub.wait_next(after_seq, timeout)


class LiveSession:
    """Own exactly one live Runtime and everything around its lifetime."""

    def __init__(
        self,
        sessions_root: str | Path,
        *,
        runtime_factory: Callable[[], Runtime] | None = None,
        lvgl: str | None = None,
        build: bool = True,
    ) -> None:
        self.sessions_root = Path(sessions_root).expanduser().resolve()
        self.lvgl = lvgl
        self.build = bool(build)
        self._runtime_factory = runtime_factory or self._default_runtime
        self._lock = threading.RLock()
        self._state = IDLE
        self._runtime: Runtime | None = None
        self._test = False
        self._app: str | None = None
        self._display: tuple[int, int] | None = None
        self._hub: LiveFrameHub | None = None
        self._ticker: threading.Thread | None = None
        self._ticker_stop: threading.Event | None = None
        self._test_root: Path | None = None
        self._last_error: dict[str, Any] | None = None

    # ---- state ---------------------------------------------------------

    @property
    def state(self) -> str:
        """A lock-free snapshot for tests; callers that need ordering block."""
        return self._state

    def is_starting(self) -> bool:
        """``True`` while ``start()`` has not finished; never blocks."""
        return self._state == STARTING

    def is_active(self) -> bool:
        """Whether a session is starting or its Runtime is still running."""
        with self._lock:
            return self._is_active_locked()

    def _is_active_locked(self) -> bool:
        # Startup is active before a runtime exists; after that the runtime's
        # own flag is authoritative (it stays True if a later start step
        # fails, exactly like the old bridge-based check).
        if self._state == STARTING:
            return True
        return self._runtime is not None and bool(
            getattr(self._runtime, "is_running", False)
        )

    def _is_active_snapshot(self) -> bool:
        """Lock-free read for ``GET /``: page rendering must not wait on ticks."""
        if self._state == STARTING:
            return True
        runtime = self._runtime
        return runtime is not None and bool(
            getattr(runtime, "is_running", False)
        )

    def selected_app(self, requested: str | None) -> str | None:
        """Keep the running session authoritative over a URL request.

        Deliberately lock-free: the old page path read the bridge fields
        directly, so opening a replay page never waited for a live tick or a
        stop that was finishing the engine.
        """
        if self._is_active_snapshot():
            return self._app
        return requested or self._app

    def forget_app(self, name: Any) -> None:
        """Drop a deleted app from the picker unless a session still owns it."""
        with self._lock:
            if self._app == name and not self._is_active_locked():
                self._app = None

    # ---- lifecycle -----------------------------------------------------

    def _default_runtime(self) -> Runtime:
        sessions_root = self.sessions_root
        if self._test:
            # A test session is a recording with record=False: the engine
            # keeps only the overwritten live.rgba preview, and the private
            # root is discarded on stop so no replay session is left behind.
            # Keep it under the sessions root: the engine already has write
            # access there, while %TEMP% may be blocked for child processes.
            self.sessions_root.mkdir(parents=True, exist_ok=True)
            self._test_root = Path(
                tempfile.mkdtemp(
                    prefix=".live-test-", dir=self.sessions_root
                )
            )
            sessions_root = self._test_root
        options = dict(
            lvgl=self.lvgl,
            app=self._app,
            build=self.build,
            record=not self._test,
            live_frame=True,
            record_changed_only=True,
            headless=True,
            sessions_root=sessions_root,
        )
        if self._display is not None:
            options["width"], options["height"] = self._display
        return Runtime(**options)

    def start(
        self,
        kind: str = "record",
        app: str | None = None,
        *,
        display: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        validate_live_kind(kind)
        self._stop_ticker()
        with self._lock:
            if self._is_active_locked():
                raise LiveError(
                    "live_running", "a live session is already running"
                )
            self._state = STARTING
            runtime: Runtime | None = None
            try:
                # An engine may have exited on its own (crash) or a previous
                # start may have failed. Let Runtime finish that session's
                # manifest before replacing it.
                if self._runtime is not None and not getattr(
                    self._runtime, "is_running", False
                ):
                    self._retire_locked()
                self._test = kind == "test"
                self._app = app
                self._display = display
                self._hub = LiveFrameHub()
                runtime = self._runtime_factory()
                self._runtime = runtime
                runtime.start()
                # The engine writes the startup frame before announcing ready;
                # publish it so a stream connected before the first changed
                # tick still has something to draw.
                self._publish_locked(runtime, self._hub)
                self._start_ticker_locked()
                self._last_error = None
                self._state = RUNNING
            except Exception as exc:  # noqa: BLE001 - map every failure layer
                live = None if runtime is None else self._status_for(runtime)
                error_payload = dump_error(exc)
                self._last_error = error_payload
                hub = self._hub
                self._hub = None
                if hub is not None:
                    hub.close()
                self._discard_test_root()
                if self._test:
                    self._runtime = None
                self._state = IDLE
                raise LiveError(
                    "live_start_error",
                    str(exc),
                    detail={"error": error_payload, "live": live},
                ) from exc
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_ticker()
        with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise LiveError("live_not_running", "no live session")
            if self._state == STARTING:
                raise LiveError(
                    "live_starting", "the live session is still starting"
                )
            self._state = STOPPING
            # Wake stream handlers before the runtime stops; a test session's
            # private root is deleted after this and handlers only hold bytes.
            hub = self._hub
            self._hub = None
            if hub is not None:
                hub.close()
            # Runtime.stop() is idempotent and also writes the final manifest
            # when the engine exited between two requests.
            try:
                runtime.stop()
            except Exception as exc:  # noqa: BLE001 - keep the HTTP layer alive
                self._state = IDLE
                raise LiveError(
                    "live_stop_error",
                    str(exc),
                    detail={"error": dump_error(exc)},
                ) from exc
            if self._test:
                # A test session leaves no replay evidence: drop its private
                # root and reset the runtime so /api/live reports the empty
                # state instead of a session id.
                self._discard_test_root()
                self._runtime = None
            self._state = IDLE
        return self.status()

    def _retire_locked(self) -> None:
        """Finish a non-running Runtime and discard a test session root."""
        runtime = self._runtime
        if runtime is None:
            return
        hub = self._hub
        self._hub = None
        if hub is not None:
            hub.close()
        runtime.stop()
        if self._test:
            self._discard_test_root()
        self._runtime = None

    def _discard_test_root(self) -> None:
        root = self._test_root
        self._test_root = None
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)

    # ---- status --------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            runtime = self._runtime
            payload = (
                self._status_for(runtime)
                if runtime is not None
                else empty_live_status()
            )
            payload["starting"] = self._state == STARTING
            payload["last_error"] = self._last_error
            return payload

    def _status_for(self, runtime: Runtime) -> dict[str, Any]:
        session_id = getattr(runtime, "session_id", None)
        session_dir = getattr(runtime, "session_dir", None)
        payload = empty_live_status()
        t_ms = _t_ms_value(runtime)
        payload.update(
            running=bool(getattr(runtime, "is_running", False)),
            pid=getattr(runtime, "pid", None),
            mode=getattr(runtime, "mode", None),
            session_id=session_id,
            session_dir=None if session_dir is None else str(session_dir),
            app=getattr(runtime, "app", None),
            t_ms=t_ms,
            test=self._test,
        )
        size = _display_size(getattr(runtime, "ready", None))
        if size is not None:
            payload["width"], payload["height"] = size
        if session_dir is None:
            return payload

        path = Path(session_dir)
        frames: list[Path] = []
        try:
            recording = Recording.open(path)
            frames = recording.frames
            manifest = recording.manifest
            payload["status"] = manifest["status"]
            payload["error"] = manifest["error"]
            payload["mode"] = manifest.get("mode", payload["mode"])
        except (FileNotFoundError, ValueError, OSError):
            # The manifest is written after the engine announces ready; while
            # the session is still starting there may be nothing to read yet.
            pass

        # Changed-only recording counts retained frames, not wall-clock ticks.
        payload["frame_count"] = len(frames)
        if frames:
            latest = frames[-1]
            relative = latest.relative_to(path).as_posix()
            stem = latest.stem
            frame_no = int(stem) if stem.isdigit() else None
            payload["latest_frame"] = {
                "file": relative,
                "url": frame_url(session_id or path.name, latest.name),
                "frame_no": frame_no,
                "t_ms": _latest_frame_t_ms(path, relative),
            }
        else:
            # No frame history (test mode, or a recording before its first
            # frame): the engine-reported change counter is still useful to
            # the page HUD. Test-mode pixels arrive through /api/live/stream,
            # not a latest_frame URL.
            count = getattr(runtime, "frame_count", 0)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                count = 0
            payload["frame_count"] = count
        return payload

    # ---- raw preview stream -------------------------------------------

    def open_stream(self) -> LiveStream:
        """Bind a stream reader to the current running session or raise."""
        with self._lock:
            runtime = self._runtime
            hub = self._hub
            if (
                runtime is None
                or hub is None
                or not getattr(runtime, "is_running", False)
            ):
                raise LiveError("live_not_running", "no live session")
            return LiveStream(hub)

    def wait_frame(
        self, after_seq: int, timeout: float | None = None
    ) -> LiveFrame | None:
        """Wait on the current session's hub (callers that stream use a handle)."""
        return self.open_stream().wait_frame(after_seq, timeout)

    @staticmethod
    def _read_live_frame(
        runtime: Runtime,
    ) -> tuple[int, int, int, bytes] | None:
        """Read the newest ``live.rgba`` plus dimensions and virtual time."""
        session_dir = getattr(runtime, "session_dir", None)
        if session_dir is None:
            return None
        size = _display_size(getattr(runtime, "ready", None))
        if size is None:
            return None
        width, height = size
        try:
            pixels = (Path(session_dir) / PREVIEW_FILE).read_bytes()
        except OSError:
            return None
        if len(pixels) != width * height * 4:
            return None
        return width, height, _t_ms_value(runtime), pixels

    def _publish_locked(
        self, runtime: Runtime, hub: LiveFrameHub
    ) -> LiveFrame | None:
        """Publish the current raw frame; return the hub frame or ``None``."""
        frame = self._read_live_frame(runtime)
        if frame is None:
            return None
        width, height, t_ms, pixels = frame
        return hub.publish(width, height, t_ms, pixels)

    @staticmethod
    def _live_file_stat(runtime: Runtime) -> tuple[int, int] | None:
        session_dir = getattr(runtime, "session_dir", None)
        if session_dir is None:
            return None
        try:
            stat = (Path(session_dir) / PREVIEW_FILE).stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _start_ticker_locked(self) -> None:
        """Advance the live runtime and publish raw preview frames.

        The ticker never appends ticks to ``manifest.checks``.
        """
        self._stop_ticker()
        stop = threading.Event()
        self._ticker_stop = stop

        runtime = self._runtime
        last_stat = self._live_file_stat(runtime) if runtime is not None else None

        def loop() -> None:
            nonlocal last_stat
            next_at = time.monotonic()
            while not stop.is_set():
                interval = LIVE_TICK_INTERVAL_S
                publish_args = None
                with self._lock:
                    if stop.is_set():
                        return
                    runtime = self._runtime
                    if runtime is not None and getattr(
                        runtime, "is_running", False
                    ):
                        tick = getattr(runtime, "tick", None)
                        if tick is not None:
                            tick_ms, interval = TICK_PROFILE[
                                "test" if self._test else "record"
                            ]
                            before = getattr(runtime, "frame_count", 0)
                            try:
                                tick(tick_ms, track_check=False)
                            except Exception:  # noqa: BLE001 - keep the page alive
                                pass
                            else:
                                after = getattr(
                                    runtime, "frame_count", before
                                )
                                hub = self._hub
                                stat = self._live_file_stat(runtime)
                                changed = stat is not None and stat != last_stat
                                if after != before:
                                    changed = True
                                if changed and hub is not None:
                                    frame = self._read_live_frame(runtime)
                                    if frame is not None:
                                        width, height, t_ms, pixels = frame
                                        publish_args = (
                                            hub,
                                            width,
                                            height,
                                            t_ms,
                                            pixels,
                                        )
                                        last_stat = stat
                if publish_args is not None:
                    hub, width, height, t_ms, pixels = publish_args
                    try:
                        hub.publish(width, height, t_ms, pixels)
                    except ValueError:
                        pass
                next_at += interval
                now = time.monotonic()
                if next_at < now:
                    next_at = now
                if stop.wait(next_at - now):
                    return

        thread = threading.Thread(
            target=loop, name="live-ticker", daemon=True
        )
        self._ticker = thread
        thread.start()

    def _stop_ticker(self) -> None:
        stop = self._ticker_stop
        thread = self._ticker
        self._ticker_stop = None
        self._ticker = None
        if stop is not None:
            stop.set()
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=1.0)

    # ---- input ---------------------------------------------------------

    def _running_runtime(self) -> Runtime:
        runtime = self._runtime
        if runtime is None or not getattr(runtime, "is_running", False):
            raise LiveError("live_not_running", "no live session")
        return runtime

    def pointer(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Forward a pointer action to the live Runtime.

        Recording runs headless in this process; the browser is the input
        surface. Coordinates are display pixels, the same space as the frames.
        """
        action = payload.get("action")
        if action not in ("down", "move", "up"):
            raise LiveError(
                "invalid_input", "pointer action must be down, move or up"
            )
        x = _input_int(payload.get("x"), "x")
        y = _input_int(payload.get("y"), "y")
        with self._lock:
            runtime = self._running_runtime()
            try:
                reply = runtime.pointer(action, x, y)
                # Pointer state alone does not render. Down/up still advance
                # one 16 ms frame so a click is processed even when it lands
                # between ticker ticks; drag moves are coalesced and left to
                # the ticker, otherwise every mousemove would render a frame.
                if action != "move":
                    runtime.wait(ms=LIVE_INPUT_STEP_MS)
            except Exception as exc:  # noqa: BLE001 - keep the HTTP layer alive
                raise LiveError("live_input_error", str(exc)) from exc
        return {"reply": reply}

    def key(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Forward a keypad press/release to the live Runtime."""
        action = payload.get("action")
        if action not in ("press", "release"):
            raise LiveError(
                "invalid_input", "key action must be press or release"
            )
        key = payload.get("key")
        if not isinstance(key, str) or not key:
            raise LiveError(
                "invalid_input", "key must be a non-empty string"
            )
        with self._lock:
            runtime = self._running_runtime()
            try:
                reply = runtime.key(action, key)
                runtime.wait(ms=LIVE_INPUT_STEP_MS)
            except ScenarioError as exc:
                raise LiveError("invalid_key", str(exc)) from exc
            except Exception as exc:  # noqa: BLE001 - keep the HTTP layer alive
                raise LiveError("live_input_error", str(exc)) from exc
        return {"reply": reply}


def _positive_int(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value > 0
    )


def _display_size(ready: Any) -> tuple[int, int] | None:
    """The ready display size, or ``None`` when it is missing or invalid."""
    display = (ready or {}).get("display") or {}
    width = display.get("width")
    height = display.get("height")
    if _positive_int(width) and _positive_int(height):
        return width, height
    return None


def _t_ms_value(runtime: Runtime) -> int:
    t_ms = getattr(runtime, "t_ms", 0)
    if isinstance(t_ms, bool) or not isinstance(t_ms, int) or t_ms < 0:
        return 0
    return t_ms


def _input_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LiveError(
            "invalid_input", f"{name} must be a non-negative integer"
        )
    return value


def _latest_frame_t_ms(session_dir: Path, frame_file: str) -> int | None:
    """Read the newest matching frame row from the tail of timeline.ndjson.

    Live sessions are polled every few seconds; reading the whole timeline on
    each poll would grow with the recording. Async recording writes frame rows
    as soon as a raw frame is queued, so the newest published PNG can trail
    the file end by the encoder backlog; 256 KiB covers max_frames and input
    rows for the supported display sizes.
    """
    path = session_dir / TIMELINE_FILE
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            chunk = min(size, 262144)
            handle.seek(size - chunk)
            data = handle.read()
    except OSError:
        return None
    for line in reversed(data.splitlines()):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if row.get("type") == "frame" and row.get("file") == frame_file:
            t_ms = row.get("t_ms")
            if isinstance(t_ms, int) and not isinstance(t_ms, bool):
                return t_ms
            return None
    return None
