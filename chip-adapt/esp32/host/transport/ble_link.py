"""BLE transport for the ESP32-C6 host.

The link speaks the same newline-delimited protocol as the USB serial link,
using the Nordic UART Service (NUS) UUIDs.  It owns a dedicated asyncio loop
thread for ``bleak`` and exposes a small blocking API to ``DualBackend``.
"""

from __future__ import annotations

import asyncio
import queue
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

from serial_backend import SerialError  # noqa: E402

DEFAULT_BLE_NAME = "LVGL-C6-PERF"
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

DEFAULT_SCAN_TIMEOUT_S = 5.0
DEFAULT_CONNECT_TIMEOUT_S = 12.0
DEFAULT_WRITE_TIMEOUT_S = 2.0
MIN_CHUNK = 20
MAX_CHUNK = 253


def _abs_path(path: Path) -> str:
    return str(path.resolve())


def _uuid_matches(uuids: Any) -> bool:
    if not uuids:
        return False
    wanted = NUS_SERVICE_UUID.lower()
    return any(str(item).lower() == wanted for item in uuids)


class BleLink:
    """Blocking facade over one bleak connection.

    ``open()`` scans, connects and subscribes.  ``read()`` drains the
    notification queue and raises ``SerialError`` after a disconnect.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        scanner_factory: Callable[[], Any] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or {}
        self._scanner_factory = scanner_factory
        self._client_factory = client_factory
        self._bleak: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_ready = threading.Event()
        self._client: Any = None
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._write_lock = threading.Lock()
        self._name = str(self.config.get("ble_name") or DEFAULT_BLE_NAME)
        self._address = ""
        self._mtu = 23
        self._chunk = MIN_CHUNK
        self._ready = False
        self._disconnected = False
        self._subscribed = False
        self._last_error = ""
        self._scan_timeout_s = float(
            self.config.get(
                "ble_scan_timeout_s", DEFAULT_SCAN_TIMEOUT_S
            )
        )
        self._connect_timeout_s = float(
            self.config.get(
                "ble_connect_timeout_s", DEFAULT_CONNECT_TIMEOUT_S
            )
        )
        self._write_timeout_s = float(
            self.config.get("ble_write_timeout_s", DEFAULT_WRITE_TIMEOUT_S)
        )
        self._read_timeout_ms = int(
            self.config.get("read_timeout_ms", 50)
        )

    # ------------------------------------------------------------------ status

    @property
    def ready(self) -> bool:
        return bool(self._ready and self._client is not None)

    @property
    def name(self) -> str:
        return self._name

    @property
    def address(self) -> str:
        return self._address

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "name": self._name,
            "address": self._address,
            "mtu": self._mtu,
            "chunk": self._chunk,
            "subscribed": self._subscribed,
            "last_error": self._last_error,
        }

    # ------------------------------------------------------------------- bleak

    def _load_bleak(self) -> Any:
        if self._bleak is not None:
            return self._bleak
        vendor = HOST_DIR / "vendor" / "ble"
        if not vendor.is_dir():
            raise SerialError(
                "bleak is not installed; run "
                "chip-adapt/esp32/host/scripts/bootstrap.ps1",
                code="ble_dependency_missing",
            )
        path = _abs_path(vendor)
        if path not in sys.path:
            sys.path.insert(0, path)
        try:
            import bleak  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise SerialError(
                f"bleak import failed: {exc}",
                code="ble_dependency_missing",
            ) from exc
        self._bleak = bleak
        return bleak

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        self._loop.run_forever()

    def _ensure_loop(self) -> None:
        if self._loop is not None and self._loop_thread is not None:
            if self._loop_thread.is_alive():
                return
        self._loop_ready.clear()
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="ble-link-loop",
            daemon=True,
        )
        self._loop_thread.start()
        if not self._loop_ready.wait(2.0):
            raise SerialError(
                "BLE event loop did not start", code="ble_loop_failed"
            )

    # -------------------------------------------------------------------- open

    def open(
        self,
        name: str | None = None,
        baud: int | None = None,
        *,
        read_timeout_ms: int | None = None,
    ) -> None:
        _ = baud
        if read_timeout_ms is not None:
            self._read_timeout_ms = int(read_timeout_ms)
        target = str(name or self._name).strip()
        if not target:
            raise SerialError("BLE device name is empty", code="ble_name_empty")
        self._name = target
        if self._scanner_factory is None or self._client_factory is None:
            self._load_bleak()
        self._ensure_loop()
        assert self._loop is not None
        self._disconnected = False
        self._last_error = ""
        self._queue = queue.Queue()
        timeout = self._scan_timeout_s + self._connect_timeout_s + 2.0
        future = asyncio.run_coroutine_threadsafe(
            self._async_open(target), self._loop
        )
        try:
            future.result(timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - hardware boundary
            future.cancel()
            self._last_error = str(exc)
            self.close()
            if isinstance(exc, SerialError):
                raise
            raise SerialError(
                f"BLE connect failed: {exc}", code="ble_connect_failed"
            ) from exc

    async def _async_open(self, target: str) -> None:
        device = await self._find_device(target)
        client = self._make_client(device)
        try:
            await asyncio.wait_for(
                client.connect(), timeout=self._connect_timeout_s
            )
            await client.start_notify(NUS_TX_UUID, self._on_notify)
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise
        self._client = client
        self._address = str(getattr(device, "address", "") or "")
        mtu = int(getattr(client, "mtu_size", 0) or 0)
        self._mtu = mtu if mtu >= 23 else 23
        self._chunk = max(
            MIN_CHUNK, min(self._mtu - 3, MAX_CHUNK)
        )
        self._ready = True
        self._subscribed = True

    async def _find_device(self, target: str) -> Any:
        found = await self._discover()
        candidates: list[tuple[int, int, Any]] = []
        wanted_name = target.lower()
        for device, name, uuids, rssi in _iter_discovered(found):
            name_match = bool(name and name.lower() == wanted_name)
            service_match = _uuid_matches(uuids)
            if not name_match and not service_match:
                continue
            candidates.append(
                (0 if name_match else 1, -int(rssi or -999), device)
            )
        if not candidates:
            raise SerialError(
                f"BLE device not found: {target}", code="ble_not_found"
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    async def _discover(self) -> Any:
        if self._scanner_factory is not None:
            scanner = self._scanner_factory()
            return await scanner.discover(timeout=self._scan_timeout_s)
        assert self._bleak is not None
        # Do not filter by service UUID at the OS layer: Windows sometimes
        # reports a stale or differently encoded UUID in the advertisement
        # (or omits it from the scan response), which made a live device
        # invisible.  Match the name/UUID in ``_find_device`` instead.
        return await self._bleak.BleakScanner.discover(
            timeout=self._scan_timeout_s,
            return_adv=True,
        )

    def _make_client(self, device: Any) -> Any:
        if self._client_factory is not None:
            return self._client_factory(
                device, disconnected_callback=self._on_disconnect
            )
        assert self._bleak is not None
        return self._bleak.BleakClient(
            device,
            disconnected_callback=self._on_disconnect,
            winrt={"use_cached_services": False},
        )

    # --------------------------------------------------------------- callbacks

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        if data:
            self._queue.put(bytes(data))

    def _on_disconnect(self, _client: Any) -> None:
        self._ready = False
        self._subscribed = False
        self._disconnected = True
        self._last_error = "BLE disconnected"

    # -------------------------------------------------------------------- read

    def read(self, max_bytes: int = 4096) -> bytes:
        _ = max_bytes
        try:
            data = self._queue.get(timeout=self._read_timeout_s())
        except queue.Empty:
            if not self.ready:
                raise SerialError(
                    "BLE link is not connected", code="ble_disconnected"
                ) from None
            return b""
        return data

    def _read_timeout_s(self) -> float:
        return max(0.001, self._read_timeout_ms / 1000.0)

    # ------------------------------------------------------------------- write

    def write(self, data: bytes) -> int:
        payload = bytes(data)
        if not payload:
            return 0
        with self._write_lock:
            if not self.ready or self._client is None or self._loop is None:
                raise SerialError(
                    "BLE link is not connected", code="ble_disconnected"
                )
            offset = 0
            while offset < len(payload):
                chunk = payload[offset : offset + self._chunk]
                future = asyncio.run_coroutine_threadsafe(
                    self._client.write_gatt_char(
                        NUS_RX_UUID, chunk, response=True
                    ),
                    self._loop,
                )
                try:
                    future.result(timeout=self._write_timeout_s)
                except Exception as exc:  # noqa: BLE001 - hardware boundary
                    self._ready = False
                    self._last_error = str(exc)
                    raise SerialError(
                        f"BLE write failed: {exc}", code="ble_write_failed"
                    ) from exc
                offset += len(chunk)
            return len(payload)

    # ------------------------------------------------------------------- close

    def close(self) -> None:
        loop = self._loop
        client = self._client
        if loop is not None and loop.is_running() and client is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._async_close(client), loop
                )
                future.result(timeout=5.0)
            except Exception:
                pass
        self._client = None
        self._ready = False
        self._subscribed = False
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=2.0)
        if loop is not None:
            try:
                loop.close()
            except RuntimeError:
                pass
        self._loop = None
        self._loop_thread = None

    async def _async_close(self, client: Any) -> None:
        try:
            await client.stop_notify(NUS_TX_UUID)
        except Exception:
            pass
        try:
            await client.disconnect()
        except Exception:
            pass


def _iter_discovered(found: Any):
    """Normalize bleak's discover() return shapes and fake scanners."""

    if isinstance(found, dict):
        for value in found.values():
            if isinstance(value, tuple) and len(value) == 2:
                device, adv = value
            else:
                device, adv = value, None
            name = getattr(adv, "local_name", None) or getattr(
                device, "name", None
            )
            uuids = getattr(adv, "service_uuids", None) or []
            rssi = getattr(adv, "rssi", -999)
            yield device, name, uuids, rssi
        return
    for item in found or []:
        if isinstance(item, tuple) and len(item) == 2:
            device, adv = item
        else:
            device, adv = item, None
        name = getattr(adv, "local_name", None) or getattr(
            device, "name", None
        )
        uuids = getattr(adv, "service_uuids", None) or []
        rssi = getattr(adv, "rssi", -999)
        yield device, name, uuids, rssi
