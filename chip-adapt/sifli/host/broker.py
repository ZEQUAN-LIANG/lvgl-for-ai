"""Serial broker: one owner of the COM port, many readers.

The broker keeps a bounded byte ring keyed by a monotonically increasing
sequence number.  The web UI, CLI and an AI agent all read the same stream by
cursor, so none of them can steal bytes from another reader.  Writes are
serialized through the broker as well.

Locking boundaries:

* ``_lifecycle`` serializes open/close/release calls.
* ``_lock`` protects state, the ring buffer and the log handle.  ``_cond`` is
  that same lock's condition variable and wakes cursor readers.
* ``SerialLog`` and ``RingBuffer`` never lock; the broker holds ``_lock``.
"""

from __future__ import annotations

import base64
import re
import threading
import time
from typing import Any, Callable

from ring_buffer import RingBuffer
from serial_backend import (
    SerialBackend,
    SerialError,
    create_backend,
    list_ports,
    normalize_port,
    pick_port,
)
from serial_log import SerialLog
from timeutil import now_iso as _now_iso


class BrokerError(RuntimeError):
    def __init__(self, message: str, *, code: str = "broker_error") -> None:
        super().__init__(message)
        self.code = code


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


MATCH_WINDOW_MAX = 256 * 1024
MATCH_OVERLAP_BYTES = 128 * 1024


class SerialBroker:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        backend_factory: Callable[[], SerialBackend] = create_backend,
    ) -> None:
        self.config = config
        self._backend_factory = backend_factory
        self._backend: SerialBackend | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)

        self._ring = RingBuffer(
            int(config.get("ring_buffer_bytes", 2 * 1024 * 1024))
        )
        self._total_rx = 0
        self._total_tx = 0

        self._port = ""
        self._baud = int(config.get("default_baud", 1_000_000))
        self._state = "closed"
        self._last_error: str | None = None
        self._opened_at: str | None = None
        self._closed_at: str | None = None
        self._read_timeout_ms = 50
        self._lifecycle = threading.RLock()
        self._wanted = False
        self._auto_reconnect = bool(config.get("auto_reconnect", True))
        self._reconnect_thread: threading.Thread | None = None
        self._reconnect_interval = max(
            0.1, float(config.get("reconnect_interval_s", 0.8))
        )
        self._reconnect_max_delay = max(
            self._reconnect_interval,
            float(config.get("reconnect_max_delay_s", 5.0)),
        )

        self._log: SerialLog | None = None

    @property
    def is_open(self) -> bool:
        return self._backend is not None and self._state == "open"

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def current_seq(self) -> int:
        with self._lock:
            return self._ring.next_seq

    def status(self) -> dict[str, Any]:
        with self._lock:
            log = self._log
            return {
                "state": self._state,
                "open": self.is_open,
                "port": self._port,
                "baud": self._baud,
                "opened_at": self._opened_at,
                "closed_at": self._closed_at,
                "last_error": self._last_error,
                "total_rx": self._total_rx,
                "total_tx": self._total_tx,
                "first_seq": self._ring.first_seq,
                "next_seq": self._ring.next_seq,
                "buffered_bytes": self._ring.buffered,
                "buffer_capacity": self._ring.capacity,
                "log_dir": str(log.dir) if log else "",
                "log_path": str(log.log_path) if log else "",
                "events_path": str(log.events_path) if log else "",
                "reader_alive": bool(self._reader and self._reader.is_alive()),
                "wanted": self._wanted,
                "auto_reconnect": self._auto_reconnect,
                "reconnecting": bool(
                    self._state == "reconnecting"
                    or (
                        self._reconnect_thread is not None
                        and self._reconnect_thread.is_alive()
                    )
                ),
            }

    def open(
        self,
        port: str | None = None,
        baud: int | None = None,
    ) -> dict[str, Any]:
        with self._lifecycle:
            self._wanted = True
            self.close(manual=False)
            selected = pick_port(port)
            rate = int(
                baud
                or self._baud
                or self.config.get("default_baud", 1_000_000)
            )
            backend = self._backend_factory()
            with self._lock:
                self._state = "opening"
                self._last_error = None
                self._port = selected
                self._baud = rate
            try:
                backend.open(
                    selected,
                    rate,
                    read_timeout_ms=self._read_timeout_ms,
                )
            except Exception as exc:  # noqa: BLE001 - hardware boundary
                code = exc.code if isinstance(exc, SerialError) else "open_failed"
                with self._cond:
                    self._state = "error"
                    self._last_error = str(exc)
                    self._cond.notify_all()
                self._ensure_reconnect_thread()
                raise BrokerError(str(exc), code=code) from exc

            with self._cond:
                self._backend = backend
                self._state = "open"
                self._opened_at = _now_iso()
                self._closed_at = None
                self._log = SerialLog.create(
                    self.config["log_dir"],
                    port=selected,
                    baud=rate,
                    opened_at=self._opened_at,
                    event_seq=self._log.event_seq if self._log else 0,
                )
                self._stop.clear()
                self._reader = threading.Thread(
                    target=self._reader_loop,
                    name=f"serial-reader-{selected}",
                    daemon=True,
                )
                self._reader.start()
                self._cond.notify_all()
                return self.status()

    def close(self, *, manual: bool = True) -> dict[str, Any]:
        with self._lifecycle:
            with self._cond:
                if manual:
                    self._wanted = False
                backend = self._backend
                reader = self._reader
                self._backend = None
                self._reader = None
                self._stop.set()
                self._state = "closing"
                self._cond.notify_all()

            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    pass
            if reader is not None and reader is not threading.current_thread():
                reader.join(timeout=0.5)

            with self._cond:
                self._state = "closed"
                self._closed_at = _now_iso()
                if self._log is not None:
                    self._log.close()
                self._cond.notify_all()
                return self.status()

    def _release(self) -> dict[str, Any]:
        with self._lifecycle:
            with self._lock:
                was_open = self.is_open
                port = self._port
                baud = self._baud
                self._wanted = False
            self.close(manual=False)
            return {"was_open": was_open, "port": port, "baud": baud}

    def detach_for_flash(self) -> dict[str, Any]:
        return self._release()

    def reattach(self) -> dict[str, Any]:
        with self._lock:
            port = self._port
            baud = self._baud
        if not port:
            return self.status()
        return self.open(port, baud)

    def handoff_to_flasher(self) -> dict[str, Any]:
        """Release the port to the official Web Flasher.

        Auto-reconnect is deliberately not armed: the browser needs a user
        gesture to select the port, and a retry loop would grab it first.
        """

        return self._release()

    def set_auto_reconnect(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self._auto_reconnect = bool(enabled)
        if self._auto_reconnect:
            self._ensure_reconnect_thread()
        return self.status()

    def _reconnect_requested_locked(self) -> bool:
        return bool(self._wanted and self._auto_reconnect and not self.is_open)

    def _ensure_reconnect_thread(self) -> None:
        with self._lock:
            if not self._reconnect_requested_locked():
                return
            if (
                self._reconnect_thread is not None
                and self._reconnect_thread.is_alive()
            ):
                return
            thread = threading.Thread(
                target=self._reconnect_loop,
                name="serial-reconnect",
                daemon=True,
            )
            self._reconnect_thread = thread
            thread.start()

    def _reconnect_loop(self) -> None:
        current = threading.current_thread()
        delay = self._reconnect_interval
        try:
            while True:
                with self._lock:
                    if not self._reconnect_requested_locked():
                        break
                    port = self._port
                    baud = self._baud
                    self._state = "reconnecting"
                if not port:
                    break
                try:
                    self.open(port, baud)
                    break
                except BrokerError as exc:
                    with self._cond:
                        if self._wanted:
                            self._last_error = str(exc)
                            self._state = "reconnecting"
                        self._cond.notify_all()
                    time.sleep(delay)
                    delay = min(delay * 1.5, self._reconnect_max_delay)
        finally:
            with self._lock:
                if self._reconnect_thread is current:
                    self._reconnect_thread = None

    def _reader_loop(self) -> None:
        current = threading.current_thread()
        while not self._stop.is_set():
            with self._lock:
                if self._reader is not current:
                    break
                backend = self._backend
            if backend is None:
                break
            try:
                data = backend.read(4096)
            except Exception as exc:  # noqa: BLE001 - hardware boundary
                with self._cond:
                    if self._reader is not current:
                        break
                    if not self._stop.is_set():
                        self._last_error = str(exc)
                        self._state = "error"
                    self._cond.notify_all()
                self._ensure_reconnect_thread()
                break
            if not data:
                continue
            with self._cond:
                if self._reader is not current:
                    break
                self._ring.append(data)
                self._total_rx += len(data)
                if self._log is not None:
                    self._log.write_rx(data)
                self._cond.notify_all()

    def wait_for_data(self, since: int, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_s)
        with self._cond:
            while self._ring.next_seq <= since:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def read_since(
        self,
        since: int = 0,
        *,
        max_bytes: int | None = None,
        timeout_ms: int = 0,
    ) -> dict[str, Any]:
        limit = min(
            int(max_bytes or self.config.get("max_read_bytes", 256 * 1024)),
            int(self.config.get("max_read_bytes", 256 * 1024)),
        )
        if timeout_ms > 0:
            self.wait_for_data(int(since), timeout_ms / 1000.0)

        with self._lock:
            chunk = self._ring.read(since, limit)
            data = chunk.pop("data")
            return {
                **chunk,
                "data_b64": _b64(data),
                "text": _text(data),
                "bytes": len(data),
                "buffered_bytes": self._ring.buffered,
            }

    def send(self, data: bytes, *, source: str = "api") -> dict[str, Any]:
        payload = bytes(data)
        with self._lock:
            backend = self._backend
            if backend is None or not self.is_open:
                raise BrokerError("serial port is not open", code="not_open")
        try:
            written = backend.write(payload)
        except SerialError as exc:
            raise BrokerError(str(exc), code=exc.code) from exc
        with self._cond:
            self._total_tx += written
            if self._log is not None:
                self._log.write_event("tx", payload, source=source)
        return {"bytes": written, "total_tx": self._total_tx}

    def reset(self, pulse_ms: int = 100) -> dict[str, Any]:
        with self._lock:
            backend = self._backend
            if backend is None or not self.is_open:
                raise BrokerError("serial port is not open", code="not_open")
        try:
            backend.reset(pulse_ms)
        except SerialError as exc:
            raise BrokerError(str(exc), code=exc.code) from exc
        with self._cond:
            if self._log is not None:
                self._log.write_event(
                    "reset",
                    b"",
                    source="api",
                    extra={"pulse_ms": int(pulse_ms)},
                )
        return {"ok": True, "pulse_ms": int(pulse_ms)}

    def expect(
        self,
        pattern: str,
        *,
        since: int = 0,
        timeout_ms: int = 5_000,
        regex: bool = False,
        ignore_case: bool = False,
    ) -> dict[str, Any]:
        if not pattern:
            raise BrokerError("pattern is empty", code="pattern_empty")
        flags = re.IGNORECASE if ignore_case else 0
        expression = pattern if regex else re.escape(pattern)
        try:
            compiled = re.compile(expression, flags)
        except re.error as exc:
            raise BrokerError(
                f"invalid regular expression: {exc}",
                code="pattern_invalid",
            ) from exc

        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        cursor = max(0, int(since))
        window = ""
        while True:
            remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
            chunk = self.read_since(
                cursor,
                max_bytes=self.config.get("max_read_bytes", 256 * 1024),
                timeout_ms=min(remaining_ms, 1000) if remaining_ms else 1,
            )
            text = chunk["text"]
            if text:
                window += text
                if len(window) > MATCH_WINDOW_MAX:
                    window = window[-MATCH_OVERLAP_BYTES:]
            cursor = chunk["next"]
            match = compiled.search(window)
            if match:
                return {
                    "ok": True,
                    "matched": match.group(0),
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "text": window,
                    "next": cursor,
                    "next_seq": chunk["next_seq"],
                    "truncated": chunk["truncated"],
                }
            if time.monotonic() >= deadline:
                return {
                    "ok": False,
                    "matched": "",
                    "text": window,
                    "next": cursor,
                    "next_seq": chunk["next_seq"],
                    "timed_out": True,
                    "truncated": chunk["truncated"],
                }


def ports() -> list[dict[str, Any]]:
    return list_ports()


def normalize(port: str) -> str:
    return normalize_port(port)
