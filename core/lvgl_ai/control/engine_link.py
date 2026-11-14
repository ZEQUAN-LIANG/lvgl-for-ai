"""EngineLink: one engine process and the ``lvgl-ai-engine-v1`` line protocol.

The link owns process spawn, the stdout/stderr pumps, ``seq`` correlation,
EOF and timeout handling, ``ready`` validation, crash completion and the
quit -> wait -> terminate -> kill shutdown ladder. :class:`Runtime` keeps the
public actions and turns replies into session evidence.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from .engine_guard import clear_engine_pid, write_engine_pid
from .errors import ToolError, ProtocolError, RuntimeCrash
from .session_schema import display_problem

PROTOCOL_VERSION = "lvgl-ai-engine-v1"
QUIT_TIMEOUT_S = 2.0
RECORD_QUIT_TIMEOUT_S = 120.0
ENGINE_NAMES = {"lvgl_engine", "lvgl_engine.exe"}

_EOF = object()

ProcessFactory = Callable[
    [Sequence[str], Optional[Mapping[str, str]], Any],
    "subprocess.Popen[str]",
]
LogSink = Callable[[str], None]
LogTail = Callable[[], list[str]]
CheckHook = Callable[[str, bool, "dict[str, Any] | None", bool], None]


def spawn_engine(
    command: Sequence[str],
    env: Mapping[str, str] | None,
    cwd: Any,
) -> "subprocess.Popen[str]":
    """Spawn the engine with console-window isolation.

    Keep the engine out of the terminal's Ctrl+C group: the documented stop
    path is quit -> wait -> terminate, so the engine must stay alive until
    ``EngineLink.shutdown`` asks it to exit. ``CREATE_NO_WINDOW`` keeps the
    console-subsystem engine from flashing its own console when the parent is
    pythonw (the no-console web launcher).
    """
    isolation: dict[str, Any] = {}
    if os.name == "nt":
        isolation["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        isolation["start_new_session"] = True
    return subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=None if cwd is None else str(cwd),
        env=None if env is None else dict(env),
        **isolation,
    )


class EngineLink:
    """One engine child process behind a strict request/reply protocol.

    ``command`` sends one protocol line and returns the matching reply.
    Non-protocol stdout lines and every stderr line go to ``log``; ``log_tail``
    and ``log_path`` feed :class:`RuntimeCrash`, and ``on_check`` records that
    a command ran (never whether the picture is correct). ``process_factory``
    is the test seam that replaces the real spawn with scripted pipes.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: Any = None,
        timeout: float = 30.0,
        quit_timeout: float = QUIT_TIMEOUT_S,
        log: LogSink | None = None,
        log_tail: LogTail | None = None,
        log_path: str | os.PathLike[str] | None = None,
        on_check: CheckHook | None = None,
        session_id: str | None = None,
        app: str | None = None,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        self._command = list(command)
        self._session_id = session_id
        self._app = app
        self._env = None if env is None else dict(env)
        self._cwd = cwd
        self.timeout = float(timeout)
        self.quit_timeout = float(quit_timeout)
        self._log: LogSink = log if log is not None else (lambda line: None)
        self._log_tail: LogTail = (
            log_tail if log_tail is not None else (lambda: [])
        )
        self._log_path = log_path
        self._on_check: CheckHook = (
            on_check
            if on_check is not None
            else (lambda command, ok, reply, track_check: None)
        )
        self._spawn: ProcessFactory = (
            process_factory if process_factory is not None else spawn_engine
        )
        self._proc: subprocess.Popen[str] | None = None
        self._engine_path = Path(self._command[0]) if self._command else None
        self._lines: queue.Queue[Any] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._seq = 0
        # Set when the engine disappears outside a commanded quit path, for
        # example the human closes the window while a command is in flight.
        self._unexpected_exit = False

    # ---- lifecycle -----------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def is_started(self) -> bool:
        """True while a process object exists, even if it already exited."""
        return self._proc is not None

    @property
    def pid(self) -> int | None:
        """OS process id of the engine, or ``None`` before ``start()``."""
        return None if self._proc is None else self._proc.pid

    @property
    def exit_code(self) -> int | None:
        """Engine exit code once it stopped, or ``None`` while running."""
        return None if self._proc is None else self._proc.poll()

    @property
    def unexpected_exit(self) -> bool:
        """The engine disappeared outside the quit -> terminate path."""
        return self._unexpected_exit

    def start(self) -> None:
        """Spawn the engine and start the stdout/stderr pumps."""
        self._proc = self._spawn(self._command, self._env, self._cwd)
        if (
            self._engine_path is not None
            and self._engine_path.name in ENGINE_NAMES
        ):
            try:
                write_engine_pid(
                    self._engine_path,
                    self._proc.pid,
                    session_id=self._session_id,
                    app=self._app,
                )
            except OSError:
                pass
        self._seq = 0
        self._lines = queue.Queue()
        self._stdout_thread = threading.Thread(
            target=self._pump_stdout, name="engine-stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._pump_stderr, name="engine-stderr", daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def shutdown(self, *, send_quit: bool) -> int | None:
        """Ask the engine to quit, then wait, terminate and finally kill it."""
        proc = self._proc
        if proc is None:
            return None
        try:
            if proc.poll() is None and send_quit:
                try:
                    # A malformed quit reply must not replace the real reason
                    # the session is stopping.
                    self.command("quit", timeout=self.quit_timeout)
                except ToolError:
                    pass
            try:
                proc.wait(timeout=self.quit_timeout)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=self.quit_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=self.quit_timeout)
            exit_code = proc.returncode
            for thread in (self._stdout_thread, self._stderr_thread):
                if thread is not None:
                    thread.join(timeout=self.quit_timeout)
            return exit_code
        finally:
            if (
                self._engine_path is not None
                and self._engine_path.name in ENGINE_NAMES
                and proc.poll() is not None
            ):
                try:
                    clear_engine_pid(self._engine_path, proc.pid)
                except OSError:
                    pass
            self._close_pipes(proc)
            self._proc = None

    @staticmethod
    def _close_pipes(proc: subprocess.Popen[str]) -> None:
        """Close stdin/stdout/stderr so Windows releases every pipe handle."""
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            close = getattr(stream, "close", None)
            if close is None:
                continue
            try:
                close()
            except (OSError, ValueError):
                pass

    # ---- protocol ------------------------------------------------------

    def command(
        self,
        verb: str,
        *args: str,
        timeout: float | None = None,
        track_check: bool = True,
    ) -> dict[str, Any]:
        """Send one command line and return its matching reply."""
        if not self.is_running or self._proc is None or self._proc.stdin is None:
            if self._proc is not None and self._proc.poll() is not None:
                self._unexpected_exit = True
            raise self.crash("engine is not running")
        self._seq += 1
        seq = self._seq
        command = " ".join([verb, *(str(arg) for arg in args)])
        line = f"{seq} {command}"
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._unexpected_exit = True
            self._on_check(command, False, None, True)
            raise self.crash(f"cannot send {line!r}: {exc}") from exc
        try:
            reply = self._await_reply(
                seq, line, self.timeout if timeout is None else timeout
            )
        except (ProtocolError, RuntimeCrash):
            self._on_check(command, False, None, True)
            raise
        self._on_check(command, True, reply, track_check)
        return reply

    def await_ready(
        self,
        timeout: float | None = None,
        *,
        on_frames: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        """Wait for and validate the ``ready`` announcement.

        ``on_frames`` fires as soon as ``ready.frames`` validates, before the
        remaining optional fields are checked; ``Runtime`` mirrors that number
        into its public ``frame_count`` at the same point the old inline
        validator did.
        """
        wait = self.timeout if timeout is None else timeout
        while True:
            item = self._queue_get(wait, "engine did not announce ready")
            if item is _EOF:
                self._unexpected_exit = True
                raise self.crash("engine closed stdout before announcing ready")
            message, raw = item
            if message.get("ready") is True:
                self._validate_ready(message, raw, on_frames)
                return message
            seq = message.get("seq")
            raise ProtocolError(
                f"unexpected protocol line before ready: {raw}",
                raw=raw,
                seq=seq if isinstance(seq, int) and not isinstance(seq, bool) else None,
            )

    def crash(self, message: str) -> RuntimeCrash:
        """Build a crash carrying the current exit code and log tail."""
        return RuntimeCrash(
            message,
            exit_code=self.exit_code,
            log_tail=self._log_tail(),
            log_path=self._log_path,
        )

    def complete_crash(
        self, error: RuntimeCrash, *, exit_code: int | None
    ) -> RuntimeCrash:
        """Fill a crash after shutdown joined the pumps and reaped the process."""
        error.exit_code = exit_code
        error.log_tail = self._log_tail()
        error.log_path = None if self._log_path is None else str(self._log_path)
        return error

    # ---- pumps ---------------------------------------------------------

    def _pump_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            message = _protocol_message(line)
            if message is None:
                self._log(line)
            else:
                self._lines.put((message, line))
        self._lines.put(_EOF)

    def _pump_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for raw in self._proc.stderr:
            line = raw.rstrip("\r\n")
            if line:
                self._log(f"[stderr] {line}")

    # ---- reply plumbing ------------------------------------------------

    def _await_reply(self, seq: int, line: str, timeout: float) -> dict:
        while True:
            item = self._queue_get(timeout, f"engine did not reply to {line!r}")
            if item is _EOF:
                self._unexpected_exit = True
                raise self.crash(f"engine exited before replying to {line!r}")
            message, raw = item
            reply_seq = message.get("seq")
            if reply_seq == seq:
                if message.get("ok") is False:
                    raise ProtocolError(
                        f"engine rejected {line!r}: {message.get('error', 'unknown')}",
                        raw=raw,
                        seq=seq,
                    )
                return message
            if isinstance(reply_seq, int) and reply_seq < seq:
                continue  # late or duplicate reply; keep waiting
            raise ProtocolError(
                f"protocol seq mismatch: expected {seq}, got {reply_seq!r}",
                raw=raw,
                seq=reply_seq if isinstance(reply_seq, int) else None,
            )

    def _queue_get(self, timeout: float, message: str) -> Any:
        try:
            return self._lines.get(timeout=max(0.0, timeout))
        except queue.Empty as exc:
            raise self.crash(message) from exc

    def _validate_ready(
        self,
        message: dict,
        raw: str,
        on_frames: Callable[[int], None] | None,
    ) -> None:
        actual_seq = message.get("seq")
        if not isinstance(actual_seq, int) or isinstance(actual_seq, bool):
            actual_seq = None

        def invalid(text: str, seq: int | None = actual_seq) -> ProtocolError:
            return ProtocolError(text, raw=raw, seq=seq)

        if actual_seq != 0:
            raise invalid(f"ready must carry seq=0, got {message.get('seq')!r}")
        missing = [
            key
            for key in (
                "protocol",
                "lvgl",
                "lvgl_src",
                "display",
                "mode",
                "inputs",
                "capabilities",
            )
            if key not in message
        ]
        if missing:
            raise invalid(f"ready is missing {', '.join(missing)}")
        if message["protocol"] != PROTOCOL_VERSION:
            raise invalid(
                f"unexpected protocol {message['protocol']!r}; "
                f"expected {PROTOCOL_VERSION!r}"
            )
        if not isinstance(message["lvgl"], str) or not isinstance(
            message["lvgl_src"], str
        ):
            raise invalid("ready.lvgl and ready.lvgl_src must be strings")
        if message["inputs"] != ["real", "virtual"]:
            raise invalid(
                f"ready.inputs must be ['real', 'virtual'], got {message['inputs']!r}"
            )
        if display_problem(message["display"], label="ready.display") is not None:
            raise invalid("ready.display must carry positive width and height")
        if not isinstance(message["inputs"], list) or not isinstance(
            message["capabilities"], list
        ):
            raise invalid("ready.inputs and ready.capabilities must be lists")
        if message["mode"] not in ("headless", "window"):
            raise invalid(f"unknown ready.mode {message['mode']!r}")
        frames = message.get("frames")
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 0:
            raise invalid("ready.frames must be the recorded frame count")
        if on_frames is not None:
            on_frames(frames)
        if "max_frames" in message:
            max_frames = message["max_frames"]
            if (
                isinstance(max_frames, bool)
                or not isinstance(max_frames, int)
                or max_frames < 0
            ):
                raise invalid("ready.max_frames must be a non-negative integer")
        if "truncated" in message and not isinstance(message["truncated"], bool):
            raise invalid("ready.truncated must be a boolean")


def _protocol_message(line: str) -> dict | None:
    """Return a protocol payload, or None when the line is user/LVGL log output.

    Recognition is strict: a line must be a JSON object carrying the protocol
    version *and* either ``ready: true`` or a reply shaped as ``seq`` + ``ok``.
    A user ``printf`` that happens to print a JSON object therefore stays in
    engine.log instead of being mistaken for a reply.
    """
    if not line.startswith("{"):
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("protocol") != PROTOCOL_VERSION:
        return None
    if payload.get("ready") is True:
        return payload
    seq = payload.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool) and isinstance(
        payload.get("ok"), bool
    ):
        return payload
    return None
