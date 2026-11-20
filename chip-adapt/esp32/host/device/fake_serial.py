"""In-memory serial backend for demos and tests.

It emulates the firmware command set so the host and web page can be exercised
without an ESP32 connected.  It is not a second protocol client: the shared
``SerialBroker`` still owns the read/write loop.
"""

from __future__ import annotations

import queue
import threading
import time
from urllib.parse import unquote

from paths import ensure_import_paths

ensure_import_paths()

from serial_backend import SerialBackend  # noqa: E402


class FakeSerialBackend(SerialBackend):
    def __init__(self) -> None:
        self.is_open = False
        self.port = ""
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._lock = threading.Lock()
        self._buffer = b""
        self._pages = ["home", "status", "about"]
        self._current = 0
        self._started = time.monotonic()
        self._brightness = 42
        self._wifi_state = "disconnected"
        self._wifi_ssid = ""
        self._wifi_ip = ""
        self._wifi_rssi = 0
        self._wifi_security = ""
        self._wifi_auto = True
        self._wifi_networks = [
            {"ssid": "Waveshare-2.4G", "rssi": -48, "security": "WPA2"},
            {"ssid": "ESP32-C6-Lab", "rssi": -63, "security": "WPA2"},
            {"ssid": "TP-LINK_5G", "rssi": -71, "security": "WPA2"},
            {"ssid": "Cafe-Guest", "rssi": -83, "security": "OPEN"},
        ]
        self._bt_enabled = False
        self._bt_name = "C6-Demo"
        self._bt_discoverable = False
        self._bt_connected = 0

    def open(self, port: str, baud: int, *, read_timeout_ms: int = 50) -> None:
        self.port = port
        self.is_open = True
        self._emit("@READY app=perf_monitor pages=" + ",".join(self._pages) + "\n")

    def close(self) -> None:
        self.is_open = False

    def read(self, max_bytes: int = 4096) -> bytes:
        try:
            return self._queue.get(timeout=0.05)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        with self._lock:
            self._buffer += bytes(data)
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                command = line.decode("ascii", "replace").strip()
                if command:
                    self._handle(command)
        return len(data)

    def reset(self, pulse_ms: int = 100) -> None:
        _ = pulse_ms

    def set_rts(self, value: bool) -> None:
        _ = value

    def set_dtr(self, value: bool) -> None:
        _ = value

    def _emit(self, text: str) -> None:
        self._queue.put(text.encode("utf-8", "replace"))

    def _log(self, text: str) -> None:
        self._emit(text)

    def _handle(self, command: str) -> None:
        if command == "pages":
            self._emit("@PAGES " + ",".join(self._pages) + "\n")
            return
        if command == "state":
            self._emit(f"@STATE page={self._pages[self._current]}\n")
            return
        if command == "ping":
            self._emit("@PONG\n")
            return
        if command == "page next":
            self._current = (self._current + 1) % len(self._pages)
            self._emit(f"@OK PAGE {self._pages[self._current]}\n")
            return
        if command == "page prev":
            self._current = (self._current + len(self._pages) - 1) % len(
                self._pages
            )
            self._emit(f"@OK PAGE {self._pages[self._current]}\n")
            return
        if command.startswith("page "):
            name = command[len("page ") :].strip()
            if name not in self._pages:
                self._emit(f"@ERR PAGE unknown={name}\n")
                return
            self._current = self._pages.index(name)
            self._emit(f"@OK PAGE {name}\n")
            return
        if command == "sys info":
            self._emit(
                "@SYS INFO chip=ESP32-C6|flash=4MB|"
                f"heap={183 + int(time.monotonic() - self._started) % 17}KB|"
                f"uptime={int(time.monotonic() - self._started)}s|"
                f"app=perf_monitor|page={self._pages[self._current]}|"
                f"brightness={self._brightness}\n"
            )
            return
        if command == "sys reset":
            self._started = time.monotonic()
            self._wifi_state = "disconnected"
            self._wifi_ip = ""
            self._wifi_rssi = 0
            self._bt_enabled = False
            self._bt_discoverable = False
            self._emit("@OK SYS RESET\n")
            return
        if command.startswith("brightness "):
            raw = command[len("brightness ") :].strip()
            try:
                value = max(0, min(100, int(raw)))
            except ValueError:
                self._emit("@ERR BRIGHTNESS range\n")
                return
            self._brightness = value
            self._emit(f"@OK BRIGHTNESS {value}\n")
            return
        if command == "wifi status":
            auto = "on" if self._wifi_auto else "off"
            self._emit(
                "@WIFI STATUS "
                f"state={self._wifi_state}|ssid={self._wifi_ssid}|"
                f"ip={self._wifi_ip}|rssi={self._wifi_rssi}|"
                f"security={self._wifi_security}|auto={auto}\n"
            )
            return
        if command == "wifi scan":
            self._log("[wifi] scan start\n")
            time.sleep(0.35)
            self._log(f"[wifi] scan done {len(self._wifi_networks)} networks\n")
            entries = ";".join(
                f"{item['ssid']}|{item['rssi']}|{item['security']}"
                for item in self._wifi_networks
            )
            self._emit(f"@WIFI SCAN {entries}\n")
            return
        if command.startswith("wifi connect "):
            self._wifi_connect(command)
            return
        if command == "wifi disconnect":
            self._wifi_state = "disconnected"
            self._wifi_ip = ""
            self._wifi_rssi = 0
            self._emit("@OK WIFI DISCONNECT\n")
            return
        if command.startswith("wifi auto "):
            value = command[len("wifi auto ") :].strip()
            self._wifi_auto = value == "on"
            self._emit(f"@OK WIFI AUTO {value}\n")
            return
        if command == "bt status":
            self._emit(
                "@BT STATUS "
                f"enabled={'on' if self._bt_enabled else 'off'}|"
                f"name={self._bt_name}|"
                f"discoverable={'on' if self._bt_discoverable else 'off'}|"
                f"connected={self._bt_connected}\n"
            )
            return
        if command in ("bt on", "bt off"):
            self._bt_enabled = command == "bt on"
            if not self._bt_enabled:
                self._bt_discoverable = False
                self._bt_connected = 0
            self._log(f"[bt] {'enabled' if self._bt_enabled else 'disabled'}\n")
            self._emit(f"@OK BT {'on' if self._bt_enabled else 'off'}\n")
            return
        if command.startswith("bt name "):
            name = unquote(command[len("bt name ") :].strip())
            if not name:
                self._emit("@ERR BT NAME empty\n")
                return
            self._bt_name = name
            self._emit(f"@OK BT NAME {name}\n")
            return
        if command.startswith("bt discoverable "):
            value = command[len("bt discoverable ") :].strip()
            self._bt_discoverable = value == "on"
            if self._bt_discoverable:
                self._bt_enabled = True
            self._emit(f"@OK BT DISCOVERABLE {value}\n")
            return
        self._emit(f"@ERR CMD unknown={command}\n")

    def _wifi_connect(self, command: str) -> None:
        parts = command.split(" ", 3)
        if len(parts) < 3:
            self._emit("@ERR WIFI CONNECT reason=missing-ssid\n")
            return
        ssid = unquote(parts[2])
        password = unquote(parts[3]) if len(parts) > 3 else ""
        if not ssid:
            self._emit("@ERR WIFI CONNECT reason=empty-ssid\n")
            return
        self._log(f"[wifi] connecting to {ssid}\n")
        time.sleep(0.6)
        match = next(
            (item for item in self._wifi_networks if item["ssid"] == ssid), None
        )
        self._wifi_state = "connected"
        self._wifi_ssid = ssid
        self._wifi_ip = "192.168.1.42"
        self._wifi_rssi = int(match["rssi"]) if match else -60
        self._wifi_security = str(match["security"]) if match else "WPA2"
        if not password and self._wifi_security != "OPEN":
            self._log("[wifi] auth failed (empty password)\n")
            self._wifi_state = "disconnected"
            self._wifi_ip = ""
            self._wifi_rssi = 0
            self._emit("@ERR WIFI CONNECT reason=auth-failed\n")
            return
        self._log(f"[wifi] got ip {self._wifi_ip}\n")
        self._emit(
            "@OK WIFI CONNECT "
            f"ssid={ssid}|ip={self._wifi_ip}|rssi={self._wifi_rssi}\n"
        )
