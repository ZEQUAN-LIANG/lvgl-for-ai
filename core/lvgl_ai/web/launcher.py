"""Warm-start decision for the no-console web viewer.

``LVGL-AI-Viewer.exe`` only starts ``web.pyw`` hidden. The decision to reuse a
viewer that is already listening or to start a new server lives here, next to
the server address constants and the shared page URL, so the check, the
browser URL and the bound address cannot drift and the behavior can be tested
without Windows or a browser.

The check uses a TCP connection rather than binding the port: the server sets
``SO_REUSEADDR`` (``allow_reuse_address``), so a second bind can succeed on
Windows even while the viewer is running.
"""

from __future__ import annotations

import socket
import webbrowser

from .webapp import DEFAULT_HOST, DEFAULT_PORT
from .urls import page_url

CONNECT_TIMEOUT_S = 0.25


def port_is_open(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = CONNECT_TIMEOUT_S,
) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def reuse_running_viewer(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = CONNECT_TIMEOUT_S,
) -> bool:
    if not port_is_open(host, port, timeout):
        return False
    if not webbrowser.open(page_url(host, port)):
        raise OSError("could not open the browser")
    return True
