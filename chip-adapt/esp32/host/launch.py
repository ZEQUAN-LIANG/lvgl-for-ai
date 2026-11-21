"""One-click launcher: run the ESP32-C6 host, then open the PERF TAPE GUI.

The host owns the BLE and UART links and serves the local HTTP API; the
PERF TAPE panel is only a client of that API, so both have to run before
the panel can talk to the board.  This module starts the host in its own
process when nothing answers on the port, waits for it to come up, and
then runs the GUI in this process.

Running it from an existing host is fine: a reachable host is reused and
left running when the window closes.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

from perf_gui import DEFAULT_URL, HostClient, PerfGui  # noqa: E402

DEFAULT_PORT = int(urlparse(DEFAULT_URL).port or 8767)
START_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.4
STOP_TIMEOUT_S = 8.0
LOG_NAME = "launcher-host.log"


def probe(url: str, timeout: float = 1.5) -> Optional[dict[str, Any]]:
    """Return the host's ``/api/status`` payload, or ``None``.

    The ``transport`` field tells our host apart from an unrelated service
    that happens to hold the port.
    """

    try:
        with urllib.request.urlopen(
            url + "/api/status", timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if isinstance(payload, dict) and payload.get("transport"):
        return payload
    return None


def windowed_python() -> str:
    """Prefer ``pythonw`` so no console window flashes for the host."""

    executable = Path(sys.executable)
    candidate = executable.with_name("pythonw.exe")
    if candidate.is_file():
        return str(candidate)
    return str(executable)


def open_host_log() -> Any:
    log_dir = HOST_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return (log_dir / LOG_NAME).open("ab")


def start_host(args: argparse.Namespace) -> tuple[subprocess.Popen, Any]:
    """Spawn ``host.py serve`` and return the process plus its log handle."""

    command = [
        windowed_python(),
        "-I",
        str(HOST_DIR / "host.py"),
        "serve",
        "--http-port",
        str(args.port),
    ]
    if args.fake:
        command.append("--fake")
    if args.transport:
        command.extend(["--transport", args.transport])
    log = open_host_log()
    process = subprocess.Popen(
        command,
        cwd=str(HOST_DIR),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return process, log


def wait_for_host(
    url: str, process: Optional[subprocess.Popen], timeout: float
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe(url) is not None:
            return True
        if process is not None and process.poll() is not None:
            return False
        time.sleep(POLL_INTERVAL_S)
    return False


def stop_host(process: Optional[subprocess.Popen]) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=STOP_TIMEOUT_S)


def message_box(text: str, title: str = "PERF TAPE") -> None:
    """Surface a failure even though the launcher has no console."""

    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:  # noqa: BLE001 - best effort on a GUI host
        pass


def run_gui(
    url: str, *, tray: bool, note: str, smoke_ms: int = 0
) -> int:
    root = tk.Tk()
    app = PerfGui(root, HostClient(url), tray_enabled=tray)
    app.append_log(note, "ok")
    app.append_log(f"panel ready · {url}", "dim")
    if smoke_ms > 0:
        root.after(smoke_ms, lambda: app.quit(close_link=False))
    root.mainloop()
    return 0


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the ESP32-C6 host and open the PERF TAPE GUI."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"host HTTP port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="start the host in fake mode (no board needed)",
    )
    parser.add_argument(
        "--transport",
        choices=("dual", "ble", "serial"),
        default="",
        help="links for a host this launcher starts (default: dual)",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="close the window instead of hiding to the tray",
    )
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=START_TIMEOUT_S,
        help=f"seconds to wait for the host (default: {START_TIMEOUT_S})",
    )
    parser.add_argument("--smoke-ms", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    url = f"http://127.0.0.1:{args.port}"
    process: Optional[subprocess.Popen] = None
    log: Any = None
    try:
        if probe(url) is not None:
            note = "launcher: reusing the running host"
        else:
            process, log = start_host(args)
            if not wait_for_host(url, process, args.start_timeout):
                message_box(
                    "The ESP32 host did not come up on "
                    f"{url}.\n\nSee the log:\n{HOST_DIR / 'logs' / LOG_NAME}"
                )
                stop_host(process)
                return 1
            note = "launcher: host started"
        return run_gui(
            url,
            tray=not args.no_tray,
            note=note,
            smoke_ms=args.smoke_ms,
        )
    finally:
        stop_host(process)
        if log is not None:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
