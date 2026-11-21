from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from control.errors import ScenarioError, dump_error
from control.recording import Recording
from control.runtime import Runtime, RuntimeLike
from control.session_schema import PREVIEW_FILE
from .transport import LiveFrame, LiveFrameHub
from .urls import frame_url

IDLE = "idle"
STARTING = "starting"
RUNNING = "running"
STOPPING = "stopping"
LIVE_KINDS = ("record", "test")

LIVE_INPUT_STEP_MS = 16
LIVE_TEST_TICK_MS = 33
LIVE_TEST_INTERVAL_S = 0.033
LIVE_TICK_MS = 33
LIVE_TICK_INTERVAL_S = 0.033
TICK_PROFILE = {
    "test": (LIVE_TEST_TICK_MS, LIVE_TEST_INTERVAL_S),
    "record": (LIVE_TICK_MS, LIVE_TICK_INTERVAL_S),
}


class LiveError(Exception):
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
    if kind not in LIVE_KINDS:
        raise LiveError("invalid_live_mode", f"unknown live mode: {kind}")


def empty_live_status() -> dict[str, Any]:
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
    def __init__(
        self,
        sessions_root: str | Path,
        *,
        runtime_factory: Callable[[], RuntimeLike] | None = None,
        lvgl: str | None = None,
        build: bool = True,
    ) -> None:
        self.sessions_root = Path(sessions_root).expanduser().resolve()
        self.lvgl = lvgl
        self.build = bool(build)
        self._runtime_factory = runtime_factory or self._default_runtime
        self._lock = threading.RLock()
        self._state = IDLE
        self._runtime: RuntimeLike | None = None
        self._test = False
        self._app: str | None = None
        self._display: tuple[int, int] | None = None
        self._hub: LiveFrameHub | None = None
        self._ticker: threading.Thread | None = None
        self._ticker_stop: threading.Event | None = None
        self._test_root: Path | None = None
        self._last_error: dict[str, Any] | None = None

    @property
    def state(self) -> str:
        return self._state

    def is_starting(self) -> bool:
        return self._state == STARTING

    def is_active(self) -> bool:
        with self._lock:
            return self._is_active_locked()

    def _is_active_locked(self) -> bool:
        if self._state == STARTING:
            return True
        return self._runtime is not None and bool(self._runtime.is_running)

    def _is_active_snapshot(self) -> bool:
        if self._state == STARTING:
            return True
        runtime = self._runtime
        return runtime is not None and bool(runtime.is_running)

    def selected_app(self, requested: str | None) -> str | None:
        if self._is_active_snapshot():
            return self._app
        return requested or self._app

    def forget_app(self, name: Any) -> None:
        with self._lock:
            if self._app == name and not self._is_active_locked():
                self._app = None

    def _default_runtime(self) -> RuntimeLike:
        sessions_root = self.sessions_root
        if self._test:
            self.sessions_root.mkdir(parents=True, exist_ok=True)
            self._test_root = Path(
                tempfile.mkdtemp(prefix=".live-test-", dir=self.sessions_root)
            )
            sessions_root = self._test_root
        display: dict[str, int] = {}
        if self._display is not None:
            display["width"], display["height"] = self._display
        return Runtime(
            lvgl=self.lvgl,
            app=self._app,
            build=self.build,
            record=not self._test,
            live_frame=True,
            record_changed_only=True,
            headless=True,
            sessions_root=sessions_root,
            **display,
        )

    def start(
        self,
        kind: str = "record",
        app: str | None = None,
        *,
        display: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        validate_live_kind(kind)
        with self._lock:
            if self._is_active_locked():
                raise LiveError(
                    "live_running", "a live session is already running"
                )
            self._stop_ticker()
            self._state = STARTING
            runtime: RuntimeLike | None = None
            try:
                if self._runtime is not None and not self._runtime.is_running:
                    self._retire_locked()
                self._test = kind == "test"
                self._app = app
                self._display = display
                self._hub = LiveFrameHub()
                runtime = self._runtime_factory()
                self._runtime = runtime
                runtime.start()
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
        with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise LiveError("live_not_running", "no live session")
            if self._state == STARTING:
                raise LiveError(
                    "live_starting", "the live session is still starting"
                )
            self._stop_ticker()
            self._state = STOPPING
            hub = self._hub
            self._hub = None
            if hub is not None:
                hub.close()
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
                self._discard_test_root()
                self._runtime = None
            self._state = IDLE
        return self.status()

    def _retire_locked(self) -> None:
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

    def _status_for(self, runtime: RuntimeLike) -> dict[str, Any]:
        session_id = runtime.session_id
        session_dir = runtime.session_dir
        payload = empty_live_status()
        t_ms = _t_ms_value(runtime)
        payload.update(
            running=bool(runtime.is_running),
            pid=runtime.pid,
            mode=runtime.mode,
            session_id=session_id,
            session_dir=None if session_dir is None else str(session_dir),
            app=runtime.app,
            t_ms=t_ms,
            test=self._test,
        )
        size = _display_size(runtime.ready)
        if size is not None:
            payload["width"], payload["height"] = size
        if session_dir is None:
            return payload

        path = Path(session_dir)
        frame_total = 0
        latest: dict[str, Any] | None = None
        try:
            recording = Recording.open(path)
            latest = recording.latest_frame()
            frame_total = len(recording.frames)
            manifest = recording.manifest
            payload["status"] = manifest["status"]
            payload["error"] = manifest["error"]
            payload["mode"] = manifest.get("mode", payload["mode"])
        except (FileNotFoundError, ValueError, OSError):
            pass

        payload["frame_count"] = frame_total
        if latest is not None:
            filename = latest["file"].rsplit("/", 1)[-1]
            payload["latest_frame"] = {
                "file": latest["file"],
                "url": frame_url(session_id or path.name, filename),
                "frame_no": latest["frame_no"],
                "t_ms": latest["t_ms"],
            }
        else:
            count = runtime.frame_count
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
            ):
                count = 0
            payload["frame_count"] = count
        return payload

    def open_stream(self) -> LiveStream:
        with self._lock:
            runtime = self._runtime
            hub = self._hub
            if runtime is None or hub is None or not runtime.is_running:
                raise LiveError("live_not_running", "no live session")
            return LiveStream(hub)

    def wait_frame(
        self, after_seq: int, timeout: float | None = None
    ) -> LiveFrame | None:
        return self.open_stream().wait_frame(after_seq, timeout)

    @staticmethod
    def _read_live_frame(
        runtime: RuntimeLike,
    ) -> tuple[int, int, int, bytes] | None:
        session_dir = runtime.session_dir
        if session_dir is None:
            return None
        size = _display_size(runtime.ready)
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
        self, runtime: RuntimeLike, hub: LiveFrameHub
    ) -> LiveFrame | None:
        frame = self._read_live_frame(runtime)
        if frame is None:
            return None
        width, height, t_ms, pixels = frame
        return hub.publish(width, height, t_ms, pixels)

    @staticmethod
    def _live_file_stat(runtime: RuntimeLike) -> tuple[int, int] | None:
        session_dir = runtime.session_dir
        if session_dir is None:
            return None
        try:
            stat = (Path(session_dir) / PREVIEW_FILE).stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _start_ticker_locked(self) -> None:
        self._stop_ticker()
        stop = threading.Event()
        self._ticker_stop = stop

        runtime = self._runtime
        if runtime is not None and not callable(runtime.tick):
            raise TypeError("live runtime must provide tick()")
        last_stat = (
            self._live_file_stat(runtime) if runtime is not None else None
        )

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
                    if runtime is not None and runtime.is_running:
                        tick_ms, interval = TICK_PROFILE[
                            "test" if self._test else "record"
                        ]
                        before = runtime.frame_count
                        try:
                            runtime.tick(tick_ms, track_check=False)
                        except Exception:  # noqa: BLE001 - keep the page alive
                            pass
                        else:
                            after = runtime.frame_count
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

        thread = threading.Thread(target=loop, name="live-ticker", daemon=True)
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

    def _running_runtime(self) -> RuntimeLike:
        runtime = self._runtime
        if runtime is None or not runtime.is_running:
            raise LiveError("live_not_running", "no live session")
        return runtime

    def pointer(self, payload: dict[str, Any]) -> dict[str, Any]:
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
                if action != "move":
                    runtime.wait(ms=LIVE_INPUT_STEP_MS)
            except Exception as exc:  # noqa: BLE001 - keep the HTTP layer alive
                raise LiveError("live_input_error", str(exc)) from exc
        return {"reply": reply}

    def key(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action not in ("press", "release"):
            raise LiveError(
                "invalid_input", "key action must be press or release"
            )
        key = payload.get("key")
        if not isinstance(key, str) or not key:
            raise LiveError("invalid_input", "key must be a non-empty string")
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
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _display_size(ready: Any) -> tuple[int, int] | None:
    display = (ready or {}).get("display") or {}
    width = display.get("width")
    height = display.get("height")
    if _positive_int(width) and _positive_int(height):
        return width, height
    return None


def _t_ms_value(runtime: RuntimeLike) -> int:
    t_ms = runtime.t_ms
    if isinstance(t_ms, bool) or not isinstance(t_ms, int) or t_ms < 0:
        return 0
    return t_ms


def _input_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LiveError(
            "invalid_input", f"{name} must be a non-negative integer"
        )
    return value
