"""UART + BLE dual link backend for the ESP32-C6 host.

BLE is preferred when connected; the USB serial link is the automatic
fallback.  Both links feed one byte queue so the shared ``SerialBroker`` keeps
a single ring buffer, cursor and log across link switches.
"""

from __future__ import annotations

import queue
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

TRANSPORT_DIR = Path(__file__).resolve().parent
HOST_DIR = TRANSPORT_DIR.parent
for _path in (TRANSPORT_DIR, HOST_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from paths import ensure_import_paths

ensure_import_paths()

from ble_link import DEFAULT_BLE_NAME, BleLink  # noqa: E402
from serial_backend import (  # noqa: E402
    SerialBackend,
    SerialError,
    create_backend,
    list_ports,
)

_MIN_BACKOFF_S = 0.5
_MAX_BACKOFF_S = 5.0
_ESP32_PORT_RE = re.compile(
    r"usb|jtag|ch340|cp210|ftdi|silicon labs|espressif",
    re.IGNORECASE,
)


def preferred_serial_port() -> str:
    """Return the most likely ESP32 USB serial port, or ``""``.

    Explicit user configuration is handled by the caller; this helper only
    looks at the operating system's port list.
    """

    try:
        ports = list_ports()
    except Exception:  # noqa: BLE001 - hardware boundary
        return ""
    if not ports:
        return ""
    preferred = [
        item
        for item in ports
        if _ESP32_PORT_RE.search(
            f"{item.get('description', '')} {item.get('hwid', '')}"
        )
        or item.get("vid") == 0x303A
    ]
    if preferred:
        return str(preferred[0].get("port") or "")
    if len(ports) == 1:
        return str(ports[0].get("port") or "")
    return ""


class DualBackend(SerialBackend):
    """One ``SerialBackend`` that multiplexes BLE and USB serial."""

    transport = "dual"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        serial_factory: Callable[[], SerialBackend] = create_backend,
        ble_factory: Callable[[], BleLink] | None = None,
    ) -> None:
        self.config = config or {}
        self._serial_factory = serial_factory
        self._ble_factory = ble_factory or (lambda: BleLink(self.config))
        self._serial: SerialBackend | None = None
        self._ble: BleLink | None = None
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._write_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

        self._open = False
        self._serial_open = False
        self._serial_port = ""
        self._serial_error = ""
        self._ble_error = ""
        self._baud = int(self.config.get("default_baud", 115200))
        self._read_timeout_ms = 50
        self._link_wait_s = float(self.config.get("link_wait_s", 0.5))
        self._serial_enabled = bool(
            self.config.get("serial_enabled", True)
        )
        self._ble_enabled = bool(self.config.get("ble_enabled", True))
        self._explicit_serial = str(
            self.config.get("serial_port") or ""
        ).strip()
        self._ble_name = str(
            self.config.get("ble_name") or DEFAULT_BLE_NAME
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            ble = self._ble.status() if self._ble is not None else {}
            if self._ble_error and not ble.get("last_error"):
                ble["last_error"] = self._ble_error
            serial = {
                "open": self._serial_open,
                "port": self._serial_port,
                "baud": self._baud,
                "last_error": self._serial_error,
            }
            active = "none"
            if ble.get("ready"):
                active = "ble"
            elif self._serial_open:
                active = "serial"
            return {
                "active": active,
                "ble": ble,
                "serial": serial,
            }

    def link_status(self) -> dict[str, Any]:
        return self.status()

    def has_link(self) -> bool:
        return self.status()["active"] != "none"

    def open(
        self,
        port: str | None = None,
        baud: int | None = None,
        *,
        read_timeout_ms: int = 50,
    ) -> None:
        if not self._serial_enabled and not self._ble_enabled:
            raise SerialError(
                "both UART and BLE are disabled", code="no_link"
            )
        self.close()
        _ = port
        self._baud = int(baud or self._baud or 115200)
        self._read_timeout_ms = int(read_timeout_ms)
        self._open = True
        self._stop.clear()
        self._queue = queue.Queue()
        with self._lock:
            self._serial_error = ""
            self._ble_error = ""
        if self._serial_enabled:
            self._start(self._serial_loop, "dual-serial")
        if self._ble_enabled:
            self._start(self._ble_loop, "dual-ble")
        with self._cond:
            self._cond.wait_for(
                lambda: self._serial_open
                or (self._ble is not None and self._ble.ready)
                or self._stop.is_set(),
                timeout=max(0.0, self._link_wait_s),
            )

    def _start(self, target: Callable[[], None], name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _serial_loop(self) -> None:
        backoff = _MIN_BACKOFF_S
        while not self._stop.is_set():
            backend = self._serial
            if backend is None:
                selected = self._choose_serial_port()
                if not selected:
                    with self._lock:
                        self._serial_error = "no serial port found"
                    self._stop.wait(1.0)
                    continue
                candidate = self._serial_factory()
                try:
                    candidate.open(
                        selected,
                        self._baud,
                        read_timeout_ms=self._read_timeout_ms,
                    )
                except Exception as exc:  # noqa: BLE001 - hardware boundary
                    with self._lock:
                        self._serial_error = str(exc)
                    try:
                        candidate.close()
                    except Exception:
                        pass
                    backoff = self._wait_backoff(backoff)
                    continue
                with self._cond:
                    self._serial = candidate
                    self._serial_open = True
                    self._serial_port = selected
                    self._serial_error = ""
                    self._cond.notify_all()
                backoff = _MIN_BACKOFF_S
                continue

            try:
                data = backend.read(4096)
            except Exception as exc:  # noqa: BLE001 - hardware boundary
                with self._lock:
                    self._serial_error = str(exc)
                    self._serial_open = False
                    self._serial = None
                    self._serial_port = ""
                try:
                    backend.close()
                except Exception:
                    pass
                backoff = self._wait_backoff(backoff)
                continue
            if data:
                self._queue.put(data)
        with self._lock:
            backend = self._serial
            self._serial = None
            self._serial_open = False
        if backend is not None:
            try:
                backend.close()
            except Exception:
                pass

    def _choose_serial_port(self) -> str:
        if self._explicit_serial:
            return self._explicit_serial
        return preferred_serial_port()

    def _ble_loop(self) -> None:
        backoff = _MIN_BACKOFF_S
        while not self._stop.is_set():
            ble = self._ble
            if ble is None:
                ble = self._ble_factory()
                with self._lock:
                    self._ble = ble
            if not ble.ready:
                try:
                    ble.open(
                        self._ble_name,
                        self._baud,
                        read_timeout_ms=self._read_timeout_ms,
                    )
                except SerialError as exc:
                    with self._lock:
                        self._ble_error = str(exc)
                    if exc.code == "ble_dependency_missing":
                        with self._cond:
                            self._cond.notify_all()
                        return
                    backoff = self._wait_backoff(backoff)
                    continue
                except Exception as exc:  # noqa: BLE001 - hardware boundary
                    with self._lock:
                        self._ble_error = str(exc)
                    backoff = self._wait_backoff(backoff)
                    continue
                with self._cond:
                    self._ble_error = ""
                    self._cond.notify_all()
                backoff = _MIN_BACKOFF_S
            try:
                data = ble.read(4096)
            except Exception as exc:  # noqa: BLE001 - hardware boundary
                with self._lock:
                    self._ble_error = str(exc)
                try:
                    ble.close()
                except Exception:
                    pass
                backoff = self._wait_backoff(backoff)
                continue
            if data:
                self._queue.put(data)
        ble = self._ble
        if ble is not None:
            try:
                ble.close()
            except Exception:
                pass

    def read(self, max_bytes: int = 4096) -> bytes:
        _ = max_bytes
        try:
            return self._queue.get(
                timeout=max(0.001, self._read_timeout_ms / 1000.0)
            )
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        payload = bytes(data)
        if not payload:
            return 0
        with self._write_lock:
            ble = self._ble
            if ble is not None and ble.ready:
                try:
                    return ble.write(payload)
                except SerialError as exc:
                    with self._lock:
                        self._ble_error = str(exc)
                    # Fall back only before any bytes reached the peer: a partial
                    # multi-chunk write must not be replayed on UART.
                    if exc.code != "ble_disconnected":
                        raise
            with self._lock:
                serial = self._serial
                serial_open = self._serial_open
            if serial is not None and serial_open:
                try:
                    return serial.write(payload)
                except SerialError as exc:
                    with self._lock:
                        self._serial_error = str(exc)
                        self._serial_open = False
                    raise
            raise SerialError("no active UART or BLE link", code="no_link")

    def reset(self, pulse_ms: int = 100) -> None:
        with self._lock:
            serial = self._serial
        if serial is not None and self._serial_open:
            serial.reset(pulse_ms)

    def set_rts(self, value: bool) -> None:
        with self._lock:
            serial = self._serial
        if serial is not None and self._serial_open:
            serial.set_rts(value)

    def set_dtr(self, value: bool) -> None:
        with self._lock:
            serial = self._serial
        if serial is not None and self._serial_open:
            serial.set_dtr(value)

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        with self._lock:
            serial = self._serial
            ble = self._ble
            self._serial = None
            self._ble = None
            self._serial_open = False
            self._open = False
        for backend in (serial, ble):
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    pass
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=2.0)
        self._threads = []
        self._drain_queue()

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _wait_backoff(self, delay: float) -> float:
        self._stop.wait(delay)
        return min(_MAX_BACKOFF_S, max(_MIN_BACKOFF_S, delay * 1.5))
