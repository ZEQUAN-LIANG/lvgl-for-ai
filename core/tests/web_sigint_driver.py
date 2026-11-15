from __future__ import annotations

import contextlib
import io
import json
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_ROOT = TESTS_DIR.parent
for path in (TOOL_ROOT, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import web


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(method: str, url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                url, data=b"" if method == "POST" else None, method=method
            ),
            timeout=timeout,
        ) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: web_sigint_driver.py SESSIONS_ROOT", file=sys.stderr)
        return 2
    root = Path(argv[1])
    root.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    outcome: dict = {}

    def watcher() -> None:
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            try:
                status, _ = request("GET", base + "/")
                if status == 200:
                    break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.1)
        else:
            outcome["error"] = "server did not start"
            return
        status, body = request("POST", base + "/api/live/start", timeout=120.0)
        if status != 200:
            outcome["error"] = f"live start returned {status}: {body!r}"
            return
        live = json.loads(body)
        outcome["session_dir"] = live["session_dir"]
        outcome["pid"] = live["pid"]
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)

    threading.Thread(target=watcher, daemon=True).start()
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            code = web.main(
                [
                    "--port",
                    str(port),
                    "--sessions-root",
                    str(root),
                    "--lvgl",
                    "9.6",
                ]
            )
    except KeyboardInterrupt:
        code = 0
    outcome["exit_code"] = code
    print(json.dumps(outcome), flush=True)
    return 0 if "session_dir" in outcome else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
