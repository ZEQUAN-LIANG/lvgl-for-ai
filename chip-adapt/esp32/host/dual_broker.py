"""SerialBroker variant for the UART + BLE dual link."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths

ensure_import_paths()

from broker import SerialBroker  # noqa: E402
from dual_backend import DualBackend  # noqa: E402


class DualBroker(SerialBroker):
    """Keep the serial broker contract while ``DualBackend`` picks a link.

    ``_resolve_port`` returns the literal ``"dual"`` so ``open()`` does not
    try to normalize a COM port.  The real serial port is reported in
    ``status()["links"]["serial"]["port"]`` and preserved for flashing.
    """

    def __init__(
        self,
        config: dict[str, Any],
        *,
        backend_factory: Callable[[], Any] | None = None,
    ) -> None:
        factory = backend_factory or (lambda: DualBackend(config))
        super().__init__(config, backend_factory=factory)

    @property
    def transport(self) -> str:
        return "dual"

    def _resolve_port(self, port: str | None) -> str:
        _ = port
        return "dual"

    def link_status(self) -> dict[str, Any]:
        with self._lock:
            backend = self._backend
        if backend is None or not hasattr(backend, "link_status"):
            return {
                "active": "none",
                "ble": {},
                "serial": {"open": False, "port": "", "baud": 0},
            }
        try:
            return backend.link_status()
        except Exception:  # noqa: BLE001 - status is best effort
            return {
                "active": "none",
                "ble": {},
                "serial": {"open": False, "port": "", "baud": 0},
            }

    def status(self) -> dict[str, Any]:
        result = super().status()
        result["transport"] = "dual"
        result["links"] = self.link_status()
        return result

    def detach_for_flash(self) -> dict[str, Any]:
        links = self.link_status()
        serial_port = str(
            (links.get("serial") or {}).get("port") or ""
        )
        result = super().detach_for_flash()
        result["serial_port"] = serial_port
        return result
