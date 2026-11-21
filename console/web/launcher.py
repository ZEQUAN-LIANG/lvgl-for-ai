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
