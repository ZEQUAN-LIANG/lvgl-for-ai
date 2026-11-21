from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

HOST_DIR = Path(__file__).resolve().parent
VENDOR_DIR = HOST_DIR / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

try:
    import serial
    from serial.tools import list_ports as serial_list_ports
except ImportError as exc:
    raise RuntimeError(
        "pyserial is missing. Run: python -m pip install --target "
        f"{VENDOR_DIR} --no-deps pyserial==3.5"
    ) from exc


class SerialError(RuntimeError):
    status = 409

    def __init__(self, message: str, *, code: str = "serial_error") -> None:
        super().__init__(message)
        self.code = code


def _com_number(port: str) -> int:
    match = re.search(r"(\d+)$", port)
    return int(match.group(1)) if match else 9999


def normalize_port(port: str) -> str:
    value = str(port or "").strip()
    if not value:
        raise SerialError("port is empty", code="port_empty")
    if os.name == "nt":
        upper = value.upper()
        if upper.isdigit():
            upper = f"COM{upper}"
        if not re.fullmatch(r"COM\d+", upper):
            raise SerialError(
                f"invalid Windows serial port: {value!r}",
                code="port_invalid",
            )
        return upper
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise SerialError("invalid serial port name", code="port_invalid")
    return value


def list_ports() -> list[dict[str, Any]]:
    ports: list[dict[str, Any]] = []
    for info in serial_list_ports.comports():
        device = str(info.device)
        ports.append(
            {
                "port": device,
                "device": device,
                "description": info.description or "",
                "hwid": info.hwid or "",
                "vid": info.vid,
                "pid": info.pid,
                "manufacturer": info.manufacturer or "",
                "product": info.product or "",
                "serial_number": info.serial_number or "",
            }
        )
    ports.sort(key=lambda item: _com_number(item["port"]))
    return ports


def pick_port(port: str | None = None) -> str:
    if port:
        return normalize_port(port)
    ports = [item["port"] for item in list_ports()]
    if not ports:
        raise SerialError("no serial ports found", code="no_ports")
    if len(ports) > 1:
        raise SerialError(
            "multiple serial ports found; pass an explicit port: "
            + ", ".join(ports),
            code="multiple_ports",
        )
    return ports[0]


def _map_open_error(port: str, exc: Exception) -> SerialError:
    message = str(exc)
    lowered = message.lower()
    if isinstance(exc, PermissionError) or "access is denied" in lowered:
        return SerialError(
            f"{port} is busy or access was denied",
            code="port_busy",
        )
    if isinstance(exc, FileNotFoundError) or "could not open port" in lowered:
        return SerialError(
            f"{port} does not exist or is not available",
            code="port_not_found",
        )
    if "invalid argument" in lowered or "invalid port" in lowered:
        return SerialError(
            f"invalid serial port: {port}",
            code="port_invalid",
        )
    return SerialError(
        f"cannot open {port}: {message}",
        code="port_open_failed",
    )


class SerialBackend:
    is_open: bool = False
    port: str = ""

    def open(self, port: str, baud: int, *, read_timeout_ms: int = 50) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def read(self, max_bytes: int = 4096) -> bytes:
        raise NotImplementedError

    def write(self, data: bytes) -> int:
        raise NotImplementedError

    def reset(self, pulse_ms: int = 100) -> None:
        raise NotImplementedError

    def set_rts(self, value: bool) -> None:
        raise NotImplementedError

    def set_dtr(self, value: bool) -> None:
        raise NotImplementedError


class PyserialBackend(SerialBackend):
    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self.port = ""
        self.baud = 0
        self.is_open = False

    def open(self, port: str, baud: int, *, read_timeout_ms: int = 50) -> None:
        self.close()
        port = normalize_port(port)
        try:
            handle = serial.Serial(
                port=port,
                baudrate=int(baud),
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=max(0.001, int(read_timeout_ms) / 1000.0),
                write_timeout=1.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except (serial.SerialException, OSError, ValueError) as exc:
            raise _map_open_error(port, exc) from exc

        try:
            handle.rts = False
            handle.dtr = False
            handle.reset_input_buffer()
            handle.reset_output_buffer()
        except (serial.SerialException, OSError):
            handle.close()
            raise

        self._serial = handle
        self.port = port
        self.baud = int(baud)
        self.is_open = True

    def close(self) -> None:
        handle = self._serial
        self._serial = None
        self.is_open = False
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

    def _require(self) -> serial.Serial:
        handle = self._serial
        if handle is None or not handle.is_open:
            raise SerialError("serial port is not open", code="not_open")
        return handle

    def read(self, max_bytes: int = 4096) -> bytes:
        handle = self._require()
        try:
            return handle.read(max(1, int(max_bytes)))
        except (serial.SerialException, OSError) as exc:
            raise SerialError(
                f"read failed on {self.port}: {exc}",
                code="read_failed",
            ) from exc

    def write(self, data: bytes) -> int:
        handle = self._require()
        payload = bytes(data)
        try:
            written = handle.write(payload)
            handle.flush()
            return int(written)
        except (serial.SerialException, OSError) as exc:
            raise SerialError(
                f"write failed on {self.port}: {exc}",
                code="write_failed",
            ) from exc

    def set_rts(self, value: bool) -> None:
        handle = self._require()
        try:
            handle.rts = bool(value)
        except (serial.SerialException, OSError) as exc:
            raise SerialError(
                f"RTS control failed on {self.port}: {exc}",
                code="line_control_failed",
            ) from exc

    def set_dtr(self, value: bool) -> None:
        handle = self._require()
        try:
            handle.dtr = bool(value)
        except (serial.SerialException, OSError) as exc:
            raise SerialError(
                f"DTR control failed on {self.port}: {exc}",
                code="line_control_failed",
            ) from exc

    def reset(self, pulse_ms: int = 100) -> None:
        self.set_rts(True)
        time.sleep(max(10, int(pulse_ms)) / 1000.0)
        self.set_rts(False)


def create_backend() -> SerialBackend:
    return PyserialBackend()
