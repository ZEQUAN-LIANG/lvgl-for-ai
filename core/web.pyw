#!/usr/bin/env pythonw
"""Windows no-console launcher for the web viewer.

Double-click this file (or run ``pythonw -I core/web.pyw``) to start the
server without a console window, open the page in the default browser, and
stop the server when the last browser page closes. A bare launch (no flags,
as when ``open-web.vbs`` or a double-click starts it) reuses a viewer that is
already listening on the default address: the page is opened and this process
exits. Explicit flags keep the normal startup path. ``web.py`` remains the
console entry point for development and automation.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``python -I`` / ``pythonw -I`` does not add the script directory to sys.path.
TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai.web import launcher  # noqa: E402
from web import main  # noqa: E402


def _show_error(message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "LVGL AI Web", 0x10)
    except Exception:  # noqa: BLE001 - a missing message box is not fatal
        pass


def _run() -> int:
    try:
        # A bare double-click means "show me the viewer": reuse a running one.
        # Explicit flags keep the existing startup path and its error dialogs.
        if not sys.argv[1:] and launcher.reuse_running_viewer():
            return 0
        code = main(["--open", "--exit-on-close", *sys.argv[1:]])
    except Exception as exc:  # noqa: BLE001 - no console to print to
        _show_error(f"网页端启动失败：{exc}")
        return 1
    if code:
        _show_error(
            "网页端启动失败：端口可能被占用，或构建环境不可用。"
            "请检查 127.0.0.1:8765 后重试。"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(_run())
