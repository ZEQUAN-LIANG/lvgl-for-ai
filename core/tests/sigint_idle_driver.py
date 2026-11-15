
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import cli


def wait_for_session(root: Path, timeout: float = 120.0) -> Path | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for manifest in root.glob("*/manifest.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") == "ok" and data.get("frame_count", 0) >= 1:
                return manifest.parent
        time.sleep(0.1)
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: sigint_idle_driver.py SESSIONS_ROOT", file=sys.stderr)
        return 2
    root = Path(argv[1])
    root.mkdir(parents=True, exist_ok=True)
    os.environ["LVGL_AI_SESSIONS_ROOT"] = str(root)

    def watcher() -> None:
        if wait_for_session(root) is None:
            return
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)

    threading.Thread(target=watcher, daemon=True).start()
    return cli.main(["--idle", "--json"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
