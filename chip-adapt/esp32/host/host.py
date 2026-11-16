#!/usr/bin/env python3
"""A small ESP32-C6 serial host and control web UI.

It reuses the SiFli host's ``SerialBroker`` (one owner of the COM port) and adds
page switching, Wi-Fi/Bluetooth configuration and system commands on top.  Run
``serve --fake`` to demo the web page without a board; run ``serve --port COMx``
for the real board.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths

ensure_import_paths()

from broker import BrokerError, SerialBroker, ports as serial_ports  # noqa: E402
from command_session import CommandSession  # noqa: E402
from device_control import DeviceController, DeviceError  # noqa: E402
from fake_serial import FakeSerialBackend  # noqa: E402
from page_control import PageController, PageError  # noqa: E402

DEFAULT_HTTP_PORT = 8767
DEFAULT_BAUD = 115200


class HostError(RuntimeError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def default_config() -> dict[str, Any]:
    return {
        "default_baud": DEFAULT_BAUD,
        "ring_buffer_bytes": 256 * 1024,
        "max_read_bytes": 64 * 1024,
        "auto_reconnect": True,
        "reconnect_interval_s": 0.8,
        "reconnect_max_delay_s": 5.0,
        "log_dir": str(HOST_DIR / "logs"),
    }


class HostState:
    def __init__(self, *, fake: bool = False) -> None:
        self.fake = fake
        self.config = default_config()
        Path(self.config["log_dir"]).mkdir(parents=True, exist_ok=True)
        if fake:
            self.broker = SerialBroker(
                self.config, backend_factory=lambda: FakeSerialBackend()
            )
        else:
            self.broker = SerialBroker(self.config)
        self.session = CommandSession(self.broker, timeout_ms=4000)
        self.pages = PageController(self.session)
        self.device = DeviceController(self.session)

    def port_list(self) -> list[dict[str, Any]]:
        if self.fake:
            return [
                {
                    "port": "COM99",
                    "device": "COM99",
                    "description": "Fake ESP32-C6 (demo)",
                    "hwid": "FAKE",
                }
            ]
        return serial_ports()


class HostServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        state: HostState,
    ) -> None:
        super().__init__(address, handler)
        self.state = state


class HostHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ESP32C6Host/0.1"
    server: HostServer

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the host's stdout readable; serial logs are the real evidence.
        return

    # ---------------------------------------------------------------- helpers

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as exc:
            raise HostError("invalid JSON body", code="bad_json") from exc
        if not isinstance(value, dict):
            raise HostError("JSON body must be an object", code="bad_json")
        return value

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code: str, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": code, "message": message}, status)

    def _index(self) -> None:
        data = (HOST_DIR / "web" / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        try:
            since = int(query.get("since", ["0"])[0])
        except ValueError:
            since = 0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                chunk = self.server.state.broker.read_since(
                    since, max_bytes=64 * 1024, timeout_ms=1000
                )
                if chunk["text"]:
                    payload = json.dumps(
                        {
                            "text": chunk["text"],
                            "next": chunk["next"],
                            "truncated": chunk["truncated"],
                        },
                        ensure_ascii=False,
                    )
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    since = int(chunk["next"])
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    # ------------------------------------------------------------------- GET

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._index()
                return
            if path == "/api/health":
                self._json({"ok": True})
                return
            if path == "/api/status":
                state = self.server.state
                status = state.broker.status()
                self._json({"ok": True, "fake": state.fake, "serial": status})
                return
            if path == "/api/ports":
                self._json(
                    {"ok": True, "ports": self.server.state.port_list()}
                )
                return
            if path == "/api/pages":
                data = self.server.state.pages.pages()
                self._json({"ok": True, **data})
                return
            if path == "/api/ui/state":
                self._json(
                    {"ok": True, "page": self.server.state.pages.state()}
                )
                return
            if path == "/api/sys":
                self._json(
                    {"ok": True, "sys": self.server.state.device.sys_info()}
                )
                return
            if path == "/api/wifi":
                self._json(
                    {
                        "ok": True,
                        "wifi": self.server.state.device.wifi_status(),
                    }
                )
                return
            if path == "/api/bt":
                self._json(
                    {"ok": True, "bt": self.server.state.device.bt_status()}
                )
                return
            if path == "/api/stream":
                self._stream()
                return
            self._error("not_found", f"unknown path: {path}", 404)
        except BrokerError as exc:
            self._error(exc.code, str(exc), 409)
        except PageError as exc:
            status = 504 if exc.code == "page_timeout" else 400
            self._error(exc.code, str(exc), status)
        except DeviceError as exc:
            status = 504 if exc.code == "device_timeout" else 400
            self._error(exc.code, str(exc), status)

    # ------------------------------------------------------------------ POST

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        try:
            body = self._body()
            state = self.server.state
            if path == "/api/open":
                port = str(body.get("port") or "")
                if state.fake and not port:
                    port = "COM99"
                if not port:
                    raise HostError("port is required", code="port_required")
                baud = int(body.get("baud") or DEFAULT_BAUD)
                status = state.broker.open(port, baud)
                self._json({"ok": True, "status": status})
                return
            if path == "/api/close":
                status = state.broker.close()
                self._json({"ok": True, "status": status})
                return
            if path == "/api/page":
                name = str(body.get("name") or "")
                page = state.pages.show(name)
                self._json({"ok": True, "page": page})
                return
            if path == "/api/page/next":
                self._json({"ok": True, "page": state.pages.next()})
                return
            if path == "/api/page/prev":
                self._json({"ok": True, "page": state.pages.prev()})
                return
            if path == "/api/ping":
                self._json({"ok": state.pages.ping()})
                return
            if path == "/api/send":
                data = str(body.get("data") or "")
                ending = str(body.get("line_ending") or "lf")
                suffix = {
                    "none": "",
                    "lf": "\n",
                    "cr": "\r",
                    "crlf": "\r\n",
                }.get(ending)
                if suffix is None:
                    raise HostError(
                        f"unsupported line_ending: {ending}",
                        code="line_ending",
                    )
                result = state.broker.send((data + suffix).encode("utf-8"))
                self._json({"ok": True, "send": result})
                return
            if path == "/api/wifi/scan":
                self._json(
                    {"ok": True, "networks": state.device.wifi_scan()}
                )
                return
            if path == "/api/wifi/connect":
                result = state.device.wifi_connect(
                    str(body.get("ssid") or ""),
                    str(body.get("password") or ""),
                )
                self._json({"ok": True, "wifi": result})
                return
            if path == "/api/wifi/disconnect":
                self._json(
                    {"ok": True, "disconnected": state.device.wifi_disconnect()}
                )
                return
            if path == "/api/wifi/auto":
                enabled = bool(body.get("enabled"))
                self._json(
                    {"ok": True, "enabled": state.device.wifi_auto(enabled)}
                )
                return
            if path == "/api/bt/enable":
                enabled = bool(body.get("enabled"))
                self._json(
                    {"ok": True, "enabled": state.device.bt_enable(enabled)}
                )
                return
            if path == "/api/bt/name":
                name = state.device.bt_name(str(body.get("name") or ""))
                self._json({"ok": True, "name": name})
                return
            if path == "/api/bt/discoverable":
                enabled = bool(body.get("enabled"))
                self._json(
                    {
                        "ok": True,
                        "enabled": state.device.bt_discoverable(enabled),
                    }
                )
                return
            if path == "/api/brightness":
                value = state.device.brightness(int(body.get("value") or 0))
                self._json({"ok": True, "value": value})
                return
            if path == "/api/system/reset":
                self._json({"ok": state.device.reset()})
                return
            if path == "/api/serial/auto_reconnect":
                enabled = bool(body.get("enabled"))
                status = state.broker.set_auto_reconnect(enabled)
                self._json({"ok": True, "serial": status})
                return
            self._error("not_found", f"unknown path: {path}", 404)
        except HostError as exc:
            self._error(exc.code, str(exc), exc.status)
        except BrokerError as exc:
            self._error(exc.code, str(exc), 409)
        except PageError as exc:
            status = 504 if exc.code == "page_timeout" else 400
            self._error(exc.code, str(exc), status)
        except DeviceError as exc:
            status = 504 if exc.code == "device_timeout" else 400
            self._error(exc.code, str(exc), status)


# --------------------------------------------------------------------- HTTP CLI


def request_json(
    method: str, url: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            value = json.loads(raw)
        except ValueError:
            value = {"ok": False, "error": "http_error", "message": raw}
        if isinstance(value, dict):
            return value
        return {"ok": False, "error": "http_error", "message": raw}
    except urllib.error.URLError as exc:
        raise SystemExit(f"host not reachable at {url}: {exc.reason}") from exc


def print_result(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    if not payload.get("ok"):
        print(f"error: {payload.get('message') or payload.get('error')}")
        return
    if "pages" in payload:
        current = payload.get("current") or "-"
        print(f"pages: {','.join(payload['pages'])} (current={current})")
    elif "page" in payload:
        print(f"page: {payload['page']}")
    elif "serial" in payload:
        serial = payload["serial"]
        print(
            f"serial: state={serial.get('state')} port={serial.get('port')} "
            f"baud={serial.get('baud')} fake={payload.get('fake')}"
        )
    elif "ports" in payload:
        for item in payload["ports"]:
            print(f"{item.get('port')}: {item.get('description', '')}")
    else:
        print(json.dumps(payload, ensure_ascii=False))


def serve(args: argparse.Namespace) -> int:
    state = HostState(fake=args.fake)
    if args.fake:
        state.broker.open("COM99", args.baud)
    elif args.port:
        try:
            state.broker.open(args.port, args.baud)
        except BrokerError as exc:
            print(f"serial open failed: {exc}")
    server = HostServer((args.host, args.http_port), HostHandler, state)
    url = f"http://{args.host}:{args.http_port}/"
    print(f"ESP32-C6 host: {url}")
    print(f"mode: {'fake (COM99)' if args.fake else 'serial'}")
    print("press Ctrl+C to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.broker.close()
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--url", default=f"http://127.0.0.1:{DEFAULT_HTTP_PORT}"
    )
    parser.add_argument("--json", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve_parser = sub.add_parser(
        "serve", help="start the serial host and web UI"
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument(
        "--http-port", type=int, default=DEFAULT_HTTP_PORT
    )
    serve_parser.add_argument("--port", default="")
    serve_parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    serve_parser.add_argument(
        "--fake", action="store_true", help="use the in-memory demo backend"
    )
    serve_parser.add_argument(
        "--open", action="store_true", help="open the browser"
    )

    pages_parser = sub.add_parser("pages", help="list firmware pages")
    add_common(pages_parser)

    page_parser = sub.add_parser("page", help="switch the firmware page")
    add_common(page_parser)
    group = page_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name")
    group.add_argument("--next", action="store_true", dest="next_page")
    group.add_argument("--prev", action="store_true", dest="prev_page")

    state_parser = sub.add_parser("state", help="read the current page")
    add_common(state_parser)

    send_parser = sub.add_parser("send", help="send a raw line")
    add_common(send_parser)
    send_parser.add_argument("data")
    send_parser.add_argument(
        "--line-ending", choices=("none", "lf", "cr", "crlf"), default="lf"
    )

    ports_parser = sub.add_parser("ports", help="list serial ports")
    add_common(ports_parser)

    status_parser = sub.add_parser("status", help="show the serial state")
    add_common(status_parser)

    ping_parser = sub.add_parser("ping", help="check the firmware console")
    add_common(ping_parser)

    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args)

    base = args.url.rstrip("/")
    if args.command == "pages":
        payload = request_json("GET", f"{base}/api/pages")
    elif args.command == "page":
        if args.next_page:
            payload = request_json("POST", f"{base}/api/page/next")
        elif args.prev_page:
            payload = request_json("POST", f"{base}/api/page/prev")
        else:
            payload = request_json(
                "POST", f"{base}/api/page", {"name": args.name}
            )
    elif args.command == "state":
        payload = request_json("GET", f"{base}/api/ui/state")
    elif args.command == "send":
        payload = request_json(
            "POST",
            f"{base}/api/send",
            {"data": args.data, "line_ending": args.line_ending},
        )
    elif args.command == "ports":
        payload = request_json("GET", f"{base}/api/ports")
    elif args.command == "status":
        payload = request_json("GET", f"{base}/api/status")
    elif args.command == "ping":
        payload = request_json("POST", f"{base}/api/ping")
    else:
        parser.error(f"unknown command: {args.command}")
        return 2

    print_result(payload, as_json=args.json)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
