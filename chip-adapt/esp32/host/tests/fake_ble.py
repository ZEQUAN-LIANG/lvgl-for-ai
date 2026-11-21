from __future__ import annotations

import asyncio
from typing import Any, Callable


class FakeAdv:
    def __init__(
        self,
        name: str | None,
        service_uuids: list[str] | None = None,
        rssi: int = -50,
    ) -> None:
        self.local_name = name
        self.service_uuids = service_uuids or []
        self.rssi = rssi


class FakeDevice:
    def __init__(self, name: str, address: str = "AA:BB:CC:DD:EE:FF") -> None:
        self.name = name
        self.address = address


class FakeScanner:
    def __init__(
        self,
        devices: list[tuple[FakeDevice, FakeAdv]] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.devices = devices or []
        self.error = error

    async def discover(self, timeout: float = 0.0) -> dict[str, Any]:
        _ = timeout
        if self.error is not None:
            raise self.error
        return {device.address: (device, adv) for device, adv in self.devices}


class FakeClient:
    def __init__(
        self,
        device: FakeDevice,
        *,
        disconnected_callback: Callable[[Any], None] | None = None,
        mtu_size: int = 256,
        connect_error: Exception | None = None,
        write_error: Exception | None = None,
    ) -> None:
        self.device = device
        self.disconnected_callback = disconnected_callback
        self.mtu_size = mtu_size
        self.max_write_without_response_size = max(20, mtu_size - 3)
        self.connect_error = connect_error
        self.write_error = write_error
        self.connected = False
        self.notify_callback: Callable[[Any, bytearray], None] | None = None
        self.writes: list[bytes] = []
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error
        await asyncio.sleep(0)
        self.connected = True

    async def start_notify(
        self, _uuid: str, callback: Callable[[Any, bytearray], None]
    ) -> None:
        self.notify_callback = callback

    async def stop_notify(self, _uuid: str) -> None:
        self.notify_callback = None

    async def write_gatt_char(
        self, _uuid: str, data: bytes, response: bool = True
    ) -> None:
        _ = response
        if self.write_error is not None:
            raise self.write_error
        if not self.connected:
            raise RuntimeError("not connected")
        self.writes.append(bytes(data))

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.connected = False
        if self.disconnected_callback is not None:
            self.disconnected_callback(self)

    def emit(self, data: bytes) -> None:
        if self.notify_callback is not None:
            self.notify_callback(self, bytearray(data))

    def simulate_disconnect(self) -> None:
        self.connected = False
        if self.disconnected_callback is not None:
            self.disconnected_callback(self)
