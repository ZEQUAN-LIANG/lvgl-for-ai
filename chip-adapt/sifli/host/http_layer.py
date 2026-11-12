"""HTTP plumbing shared by the host server handler.

JSON framing, request-body limits, origin checks, static-file resolution,
SSE framing and the exception-to-status mapping live here so the handler can
stay focused on routes and broker operations.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse

from broker import BrokerError
from build_flash import BuildFlashError
from serial_backend import SerialError

MAX_BODY = 4 * 1024 * 1024
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
ACTORS = {"web", "cli", "ai", "system", "external"}


def json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def read_json_body(
    stream: BinaryIO,
    content_length: str | None,
) -> dict[str, Any]:
    length = int(content_length or 0)
    if length > MAX_BODY:
        raise ValueError("request body is too large")
    raw = stream.read(length) if length else b""
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def origin_allowed(origin: str | None, server_port: int) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    return host in LOCAL_HOSTS and parsed.port == server_port


def actor_from(value: str | None) -> str:
    raw = (value or "web").strip().lower()
    return raw if raw in ACTORS else "external"


def safe_join(root: Path, relative: str) -> Path | None:
    root = root.resolve()
    candidate = (root / relative.lstrip("/\\")).resolve()
    if candidate == root or root in candidate.parents:
        return candidate
    return None


def content_type_for(path: Path) -> str:
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def query_int(
    query: dict[str, list[str]],
    name: str,
    default: int,
) -> int:
    values = query.get(name)
    if not values:
        return default
    return int(values[0])


def error_response(exc: BaseException) -> tuple[int, dict[str, Any]]:
    """Map an exception raised by a route to ``(status, JSON payload)``."""

    if isinstance(exc, (BrokerError, SerialError)):
        return 409, {"ok": False, "code": exc.code, "error": str(exc)}
    if isinstance(exc, BuildFlashError):
        return 400, {"ok": False, "code": exc.code, "error": str(exc)}
    if isinstance(exc, (ValueError, KeyError)):
        return 400, {"ok": False, "code": "bad_request", "error": str(exc)}
    return 500, {"ok": False, "code": "internal_error", "error": str(exc)}


class SseWriter:
    """Write Server-Sent Event frames to a handler's response stream."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def start(self) -> None:
        self._stream.write(b"retry: 1000\n\n")
        self._stream.flush()

    def send(self, payload: Any, *, event: str | None = None) -> None:
        frame = b""
        if event:
            frame += f"event: {event}\n".encode("ascii")
        frame += b"data: " + json_bytes(payload) + b"\n\n"
        self._stream.write(frame)
        self._stream.flush()

    def ping(self) -> None:
        self._stream.write(b": ping\n\n")
        self._stream.flush()
