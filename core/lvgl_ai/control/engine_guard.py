"""PID guard for the engine binary of one build directory.

Windows keeps a running PE image locked, so a new link cannot replace
``lvgl_engine.exe`` while a previous engine still runs. ``EngineLink`` writes
``<build_dir>/.engine.pid`` after spawning; the build path calls
:func:`ensure_engine_stopped` and waits for that pid before touching the build
tree. A stale pid is removed; an engine that refuses to exit produces a typed
``BuildError`` instead of an opaque linker failure.
"""

from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

from .errors import BuildError

PID_FILE_NAME = ".engine.pid"
ENGINE_EXIT_WAIT_S = 10.0
ENGINE_TERMINATE_WAIT_S = 5.0
POLL_INTERVAL_S = 0.1

if os.name == "nt":
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
else:
    _PROCESS_QUERY_LIMITED_INFORMATION = 0


def engine_pid_path(engine_path: str | Path) -> Path:
    return Path(engine_path).parent / PID_FILE_NAME


def write_engine_pid(
    engine_path: str | Path,
    pid: int,
    *,
    session_id: str | None = None,
    app: str | None = None,
) -> None:
    path = engine_pid_path(engine_path)
    payload = {
        "pid": int(pid),
        "engine": str(Path(engine_path).expanduser().resolve()),
        "session_id": session_id,
        "app": app,
        "started_at": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def clear_engine_pid(engine_path: str | Path, pid: int) -> None:
    path = engine_pid_path(engine_path)
    payload = read_engine_pid(engine_path)
    if payload is None or payload.get("pid") != int(pid):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def read_engine_pid(engine_path: str | Path) -> dict | None:
    path = engine_pid_path(engine_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        return _windows_pid_alive(int(pid))
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_image(pid: int) -> str | None:
    if os.name == "nt":
        return _windows_process_image(int(pid))
    try:
        return os.path.realpath(f"/proc/{int(pid)}/exe")
    except OSError:
        return None


def ensure_engine_stopped(
    engine_path: str | Path,
    *,
    timeout: float = ENGINE_EXIT_WAIT_S,
    terminate_wait: float = ENGINE_TERMINATE_WAIT_S,
    check_alive: Callable[[int], bool] = pid_alive,
    image_of: Callable[[int], str | None] = process_image,
    terminate: Callable[[int], None] | None = None,
) -> None:
    """Wait for the engine recorded for *engine_path*; terminate as last resort."""
    payload = read_engine_pid(engine_path)
    if payload is None:
        return
    pid = payload.get("pid")
    if not isinstance(pid, int):
        _remove_pid_file(engine_path)
        return
    if not check_alive(pid):
        _remove_pid_file(engine_path)
        return

    expected = os.path.normcase(os.path.abspath(str(Path(engine_path))))
    image = image_of(pid)
    if image is not None:
        actual = os.path.normcase(os.path.abspath(image))
        if actual != expected:
            _remove_pid_file(engine_path)
            return

    if _wait_until_gone(pid, timeout, check_alive):
        _remove_pid_file(engine_path)
        return

    stopper = terminate if terminate is not None else _terminate_pid
    stopper(pid)
    if _wait_until_gone(pid, terminate_wait, check_alive):
        _remove_pid_file(engine_path)
        return

    raise BuildError(
        f"engine is still running: pid {pid} ({engine_path})",
        command=["engine-guard", str(engine_path)],
    )


def _wait_until_gone(
    pid: int, timeout: float, check_alive: Callable[[int], bool]
) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if not check_alive(pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL_S)


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _remove_pid_file(engine_path: str | Path) -> None:
    try:
        engine_pid_path(engine_path).unlink()
    except FileNotFoundError:
        pass


def _windows_pid_alive(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _windows_process_image(pid: int) -> str | None:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)
