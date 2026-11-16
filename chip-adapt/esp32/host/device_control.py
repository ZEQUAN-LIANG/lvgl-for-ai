"""Wi-Fi, Bluetooth and system commands over the same serial console.

The firmware is expected to implement the line protocol documented in the host
README.  Values are URL-encoded when they can contain spaces (SSID, password,
Bluetooth name); responses use ``|`` between fields and ``;`` between scan
results so the parser stays simple.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from command_session import CommandError, CommandSession


class DeviceError(RuntimeError):
    def __init__(self, message: str, *, code: str = "device_error") -> None:
        super().__init__(message)
        self.code = code


def _payload(line: str, prefix: str) -> str:
    if not line.startswith(prefix):
        return ""
    return line[len(prefix) :].strip()


def _kv(line: str, prefix: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in _payload(line, prefix).split("|"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _bool(value: Any) -> bool:
    return str(value).lower() in ("1", "on", "true", "yes")


class DeviceController:
    def __init__(self, session: CommandSession) -> None:
        self._session = session

    def _exchange(
        self,
        command: str,
        pattern: str,
        *,
        timeout_ms: int | None = None,
        private: bool = False,
    ) -> str:
        try:
            return self._session.exchange(
                command, pattern, timeout_ms=timeout_ms, private=private
            )
        except CommandError as exc:
            raise DeviceError(str(exc), code="device_timeout") from exc

    # --------------------------------------------------------------- system

    def sys_info(self) -> dict[str, Any]:
        line = self._exchange("sys info", r"@SYS INFO[^\r\n]*")
        data: dict[str, Any] = _kv(line, "@SYS INFO")
        raw_uptime = str(data.get("uptime", "")).rstrip("s")
        try:
            data["uptime_s"] = int(raw_uptime)
        except ValueError:
            data["uptime_s"] = 0
        return data

    def brightness(self, value: int) -> int:
        value = max(0, min(100, int(value)))
        line = self._exchange(f"brightness {value}", r"@OK BRIGHTNESS[^\r\n]*")
        payload = _payload(line, "@OK BRIGHTNESS")
        try:
            return int(payload)
        except ValueError:
            return value

    def reset(self) -> bool:
        line = self._exchange("sys reset", r"@OK SYS RESET")
        return line == "@OK SYS RESET"

    # ----------------------------------------------------------------- wifi

    def wifi_status(self) -> dict[str, Any]:
        line = self._exchange("wifi status", r"@WIFI STATUS[^\r\n]*")
        data: dict[str, Any] = _kv(line, "@WIFI STATUS")
        try:
            data["rssi"] = int(data.get("rssi", 0))
        except ValueError:
            data["rssi"] = 0
        data["auto"] = _bool(data.get("auto"))
        return data

    def wifi_scan(self) -> list[dict[str, Any]]:
        line = self._exchange(
            "wifi scan", r"@WIFI SCAN[^\r\n]*", timeout_ms=10000
        )
        payload = _payload(line, "@WIFI SCAN")
        networks: list[dict[str, Any]] = []
        for item in payload.split(";"):
            parts = item.split("|")
            if len(parts) < 3:
                continue
            ssid, rssi, security = parts[0], parts[1], parts[2]
            try:
                value = int(rssi)
            except ValueError:
                value = 0
            networks.append(
                {"ssid": ssid, "rssi": value, "security": security}
            )
        return networks

    def wifi_connect(self, ssid: str, password: str) -> dict[str, Any]:
        if not ssid:
            raise DeviceError("SSID is empty", code="wifi_ssid_empty")
        command = f"wifi connect {quote(ssid, safe='')}"
        if password:
            command += f" {quote(password, safe='')}"
        line = self._exchange(
            command,
            r"@(OK|ERR) WIFI CONNECT[^\r\n]*",
            timeout_ms=15000,
            private=True,
        )
        if line.startswith("@ERR"):
            detail = _payload(line, "@ERR WIFI CONNECT")
            raise DeviceError(
                f"Wi-Fi connect failed: {detail}", code="wifi_connect_failed"
            )
        data: dict[str, Any] = _kv(line, "@OK WIFI CONNECT")
        try:
            data["rssi"] = int(data.get("rssi", 0))
        except ValueError:
            data["rssi"] = 0
        return data

    def wifi_disconnect(self) -> bool:
        line = self._exchange("wifi disconnect", r"@OK WIFI DISCONNECT")
        return line == "@OK WIFI DISCONNECT"

    def wifi_auto(self, enabled: bool) -> bool:
        value = "on" if enabled else "off"
        line = self._exchange(f"wifi auto {value}", r"@OK WIFI AUTO[^\r\n]*")
        return _payload(line, "@OK WIFI AUTO") == value

    # ----------------------------------------------------------- bluetooth

    def bt_status(self) -> dict[str, Any]:
        line = self._exchange("bt status", r"@BT STATUS[^\r\n]*")
        data: dict[str, Any] = _kv(line, "@BT STATUS")
        data["enabled"] = _bool(data.get("enabled"))
        data["discoverable"] = _bool(data.get("discoverable"))
        try:
            data["connected"] = int(data.get("connected", 0))
        except ValueError:
            data["connected"] = 0
        return data

    def bt_enable(self, enabled: bool) -> bool:
        value = "on" if enabled else "off"
        line = self._exchange(f"bt {value}", r"@OK BT[^\r\n]*")
        return _payload(line, "@OK BT") == value

    def bt_name(self, name: str) -> str:
        if not name:
            raise DeviceError("Bluetooth name is empty", code="bt_name_empty")
        line = self._exchange(
            f"bt name {quote(name, safe='')}", r"@OK BT NAME[^\r\n]*"
        )
        return _payload(line, "@OK BT NAME")

    def bt_discoverable(self, enabled: bool) -> bool:
        value = "on" if enabled else "off"
        line = self._exchange(
            f"bt discoverable {value}", r"@OK BT DISCOVERABLE[^\r\n]*"
        )
        return _payload(line, "@OK BT DISCOVERABLE") == value
