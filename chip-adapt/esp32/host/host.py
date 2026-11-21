#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
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
from command_session import CommandError, CommandSession  # noqa: E402
from device_control import DeviceController, DeviceError  # noqa: E402
from dual_broker import DualBroker  # noqa: E402
from fake_serial import FakeSerialBackend  # noqa: E402
import flasher_web  # noqa: E402
from flash_control import (  # noqa: E402
    DEFAULT_FLASH_BAUD,
    FlashController,
    FlashError,
)
from jobs import TERMINAL_STATUSES, JobManager  # noqa: E402
from page_control import PageController, PageError  # noqa: E402
from perf_control import PerfController, PerfError  # noqa: E402

DEFAULT_HTTP_PORT = 8767
DEFAULT_BAUD = 115200
DEFAULT_TRANSPORT = "dual"
DEFAULT_BLE_NAME = "LVGL-C6-PERF"


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
        "transport": DEFAULT_TRANSPORT,
        "ble_enabled": True,
        "ble_name": DEFAULT_BLE_NAME,
        "ble_scan_timeout_s": 5.0,
        "ble_connect_timeout_s": 12.0,
        "serial_enabled": True,
        "serial_port": "",
        "link_wait_s": 0.5,
        "flash_baud": DEFAULT_FLASH_BAUD,
        "flash_timeout_s": 300,
        "flash_max_upload_bytes": 128 * 1024 * 1024,
        "flash_cache_dir": str(HOST_DIR / ".cache" / "flash"),
        "esptool": "",
    }


class HostState:
    def __init__(
        self,
        *,
        fake: bool = False,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.fake = fake
        self.config = default_config()
        if config:
            self.config.update(config)
        Path(self.config["log_dir"]).mkdir(parents=True, exist_ok=True)
        transport = str(self.config.get("transport") or DEFAULT_TRANSPORT)
        if fake:
            transport = "fake"
        if transport not in ("fake", "dual", "ble", "serial"):
            raise HostError(
                f"unknown transport: {transport}",
                code="transport_invalid",
            )
        if transport == "ble":
            self.config["serial_enabled"] = False
        self.transport = transport
        self.ble_name = str(self.config.get("ble_name") or DEFAULT_BLE_NAME)
        if fake:
            self.broker = SerialBroker(
                self.config, backend_factory=lambda: FakeSerialBackend()
            )
        elif transport == "serial":
            self.broker = SerialBroker(self.config)
        else:
            self.broker = DualBroker(self.config)
        self.session = CommandSession(self.broker, timeout_ms=4000)
        self.pages = PageController(self.session)
        self.device = DeviceController(self.session)
        self.jobs = JobManager(keep=20)
        self.flash = FlashController(
            HOST_DIR, self.config, self.broker, fake=fake
        )
        self.perf = PerfController(self.broker)

    def port_list(self) -> list[dict[str, Any]]:
        if self.fake:
            return [
                {
                    "port": "COM99",
                    "device": "COM99",
                    "description": "Fake ESP32-C6 (demo)",
                    "hwid": "FAKE",
                    "kind": "serial",
                }
            ]
        ports = [{**item, "kind": "serial"} for item in serial_ports()]
        if self.transport in ("dual", "ble"):
            ports.insert(
                0,
                {
                    "port": "ble",
                    "device": self.ble_name,
                    "description": f"BLE · {self.ble_name}",
                    "hwid": "BLE",
                    "kind": "ble",
                },
            )
        return ports

    def auto_connect(self) -> None:
        if self.fake:
            return
        thread = threading.Thread(
            target=self._auto_connect,
            name="host-auto-connect",
            daemon=True,
        )
        thread.start()

    def _auto_connect(self) -> None:
        try:
            self.broker.open()
        except BrokerError as exc:
            print(f"link open failed: {exc}")
            return
        if self.transport == "serial":
            return
        active = "none"
        for _ in range(20):
            status = self.broker.status()
            links = status.get("links") or {}
            active = str(links.get("active") or "none")
            if active != "none":
                break
            time.sleep(0.25)
        if active == "none":
            return
        try:
            self.session.exchange(
                "PERF HELLO",
                r"@PERF READY [^\r\n]*",
                timeout_ms=2000,
            )
        except (CommandError, BrokerError):
            pass


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
        return

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

    def _error(
        self,
        code: str,
        message: str,
        status: int = 400,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "ok": False,
            "error": code,
            "message": message,
        }
        if extra:
            payload.update(extra)
        self._json(payload, status)

    def _since(self) -> int:
        query = parse_qs(urlparse(self.path).query)
        try:
            return int(query.get("since", ["0"])[0])
        except ValueError:
            return 0

    def _index(self) -> None:
        data = (HOST_DIR / "web" / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _perf_page(self) -> None:
        data = (HOST_DIR / "web" / "perf.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _flash_page(self) -> None:
        target = flasher_web.asset_path("index.html")
        if target is None:
            self._error("not_found", "flasher page is missing", 404)
            return
        self._flash_file(target)

    def _flash_asset(self, path: str) -> None:
        relative = path[len("/flash/") :]
        target = flasher_web.asset_path(relative)
        if target is None:
            self._error("not_found", f"unknown flasher asset: {relative}", 404)
            return
        self._flash_file(target)

    def _flash_file(self, target: Path) -> None:
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", flasher_web.content_type(target))
        self.send_header("Cache-Control", "no-cache")
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

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.hostname in ("127.0.0.1", "localhost", "::1")

    def _upload_firmware(self) -> None:
        if not self._origin_allowed():
            raise HostError(
                "cross-origin upload rejected", code="forbidden", status=403
            )
        state = self.server.state
        query = parse_qs(urlparse(self.path).query)
        name = (query.get("name") or ["firmware.bin"])[0]
        length = int(self.headers.get("Content-Length") or 0)
        limit = int(state.config["flash_max_upload_bytes"])
        if length <= 0:
            raise HostError("uploaded file is empty", code="empty_upload")
        if length > limit:
            self.close_connection = True
            raise HostError(
                f"upload is larger than {limit} bytes",
                code="upload_too_large",
                status=413,
            )
        try:
            self.connection.settimeout(120)
            data = self.rfile.read(length)
        except TimeoutError as exc:
            raise HostError(
                "upload timed out",
                code="upload_timeout",
                status=400,
            ) from exc
        finally:
            try:
                self.connection.settimeout(None)
            except OSError:
                pass
        if len(data) != length:
            raise HostError(
                "upload was truncated",
                code="upload_truncated",
                status=400,
            )
        self._json({"ok": True, **state.flash.save_upload(name, data)})

    def _flash_source(self, body: dict[str, Any]) -> dict[str, Any]:
        source: dict[str, Any] = {}
        for key in ("token", "path", "build_dir"):
            if body.get(key):
                source[key] = body[key]
        if body.get("files"):
            source["files"] = body["files"]
        if body.get("address") is not None:
            source["address"] = body["address"]
        return source

    def _plan_firmware(self, body: dict[str, Any]) -> None:
        if not self._origin_allowed():
            raise HostError(
                "cross-origin plan rejected",
                code="forbidden",
                status=403,
            )
        state = self.server.state
        plan = state.flash.plan(self._flash_source(body))
        self._json({"ok": True, **plan})

    def _start_flash(self, body: dict[str, Any]) -> None:
        if not self._origin_allowed():
            raise HostError(
                "cross-origin flash rejected",
                code="forbidden",
                status=403,
            )
        state = self.server.state
        if body.get("plan_id"):
            plan = state.flash.get_plan(str(body["plan_id"]))
        else:
            preview = state.flash.plan(self._flash_source(body))
            plan = state.flash.get_plan(preview["plan_id"])
        options = {
            "port": str(body.get("port") or ""),
            "baud": int(body.get("baud") or 0) or None,
            "erase_all": bool(body.get("erase_all")),
            "verify": body.get("verify", True) is not False,
            "after": str(body.get("after") or "hard_reset"),
            "before": str(body.get("before") or "default_reset"),
            "reconnect": body.get("reconnect", True) is not False,
        }
        job = state.jobs.create("flash", "flash", actor="web")
        try:
            state.flash.start(job, plan, options)
        except FlashError as exc:
            job.finish(ok=False, error=str(exc))
            raise
        self._json({"ok": True, "job_id": job.id}, 202)

    def _get_jobs(self) -> None:
        jobs = self.server.state.jobs.list()
        self._json({"ok": True, "jobs": jobs})

    def _get_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        job_id = parts[2] if len(parts) >= 3 else ""
        job = self.server.state.jobs.get(job_id)
        if job is None:
            self._error("job_not_found", "job not found", 404)
            return
        if len(parts) >= 4 and parts[3] == "stream":
            self._serve_job_stream(job)
            return
        self._json({"ok": True, "job": job.snapshot(self._since())})

    def _serve_job_stream(self, job: Any) -> None:
        since = self._since()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                job.wait(since, 10.0)
                snapshot = job.snapshot(since)
                events = snapshot["events"]
                if events:
                    since = snapshot["next"]
                    payload = json.dumps(
                        {
                            "id": job.id,
                            "status": snapshot["status"],
                            "percent": snapshot["percent"],
                            "events": events,
                            "next": since,
                        },
                        ensure_ascii=False,
                    )
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                if snapshot["status"] in TERMINAL_STATUSES:
                    done = json.dumps(snapshot, ensure_ascii=False)
                    self.wfile.write(
                        f"event: done\ndata: {done}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                    return
                if not events:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _cancel_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 4 or parts[3] != "cancel":
            self._error("not_found", "unknown path", 404)
            return
        job = self.server.state.jobs.get(parts[2])
        if job is None:
            self._error("job_not_found", "job not found", 404)
            return
        job.cancel()
        self._json({"ok": True, "job_id": job.id})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._index()
                return
            if path in ("/perf", "/perf/", "/perf.html"):
                self._perf_page()
                return
            if path in ("/flash", "/flash/", "/flash.html"):
                self._flash_page()
                return
            if path.startswith("/flash/"):
                self._flash_asset(path)
                return
            if path == "/api/health":
                self._json({"ok": True})
                return
            if path == "/api/status":
                state = self.server.state
                status = state.broker.status()
                self._json(
                    {
                        "ok": True,
                        "fake": state.fake,
                        "transport": state.transport,
                        "serial": status,
                    }
                )
                return
            if path == "/api/perf/status":
                self._json({"ok": True, **self.server.state.perf.status()})
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
            if path == "/api/flash/env":
                self._json(
                    {
                        "ok": True,
                        "env": self.server.state.flash.environment(),
                    }
                )
                return
            if path == "/api/jobs":
                self._get_jobs()
                return
            if path.startswith("/api/jobs/"):
                self._get_job(path)
                return
            self._error("not_found", f"unknown path: {path}", 404)
        except FlashError as exc:
            self._error(exc.code, str(exc), exc.status, exc.extra)
        except BrokerError as exc:
            self._error(exc.code, str(exc), 409)
        except PageError as exc:
            status = 504 if exc.code == "page_timeout" else 400
            self._error(exc.code, str(exc), status)
        except DeviceError as exc:
            status = 504 if exc.code == "device_timeout" else 400
            self._error(exc.code, str(exc), status)
        except PerfError as exc:
            self._error(exc.code, str(exc), exc.status)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        try:
            if path == "/api/flash/upload":
                self._upload_firmware()
                return
            body = self._body()
            state = self.server.state
            if (
                state.flash.busy()
                and path
                not in ("/api/flash", "/api/flash/start", "/api/flash/plan")
                and not path.startswith("/api/jobs/")
            ):
                raise HostError(
                    "flash is running; the serial port is released",
                    code="flash_busy",
                    status=409,
                )
            if path == "/api/flash/plan":
                self._plan_firmware(body)
                return
            if path in ("/api/flash", "/api/flash/start"):
                self._start_flash(body)
                return
            if path.startswith("/api/jobs/"):
                self._cancel_job(path)
                return
            if path == "/api/open":
                port = str(body.get("port") or "")
                baud = int(body.get("baud") or DEFAULT_BAUD)
                if state.transport in ("dual", "ble"):
                    if port and port != "ble":
                        state.config["serial_port"] = port
                    status = state.broker.open(
                        None if port in ("", "ble") else port, baud
                    )
                    self._json({"ok": True, "status": status})
                    return
                if state.fake and not port:
                    port = "COM99"
                if not port:
                    raise HostError("port is required", code="port_required")
                status = state.broker.open(port, baud)
                self._json({"ok": True, "status": status})
                return
            if path == "/api/close":
                status = state.broker.close()
                self._json({"ok": True, "status": status})
                return
            if path == "/api/perf/start":
                result = state.perf.start(
                    str(body.get("mode") or "demo"),
                    body.get("interval", 0.3),
                    body.get("layout") or None,
                )
                self._json(result)
                return
            if path == "/api/perf/stop":
                self._json(state.perf.stop())
                return
            if path == "/api/perf/layout":
                self._json(
                    state.perf.set_layout(str(body.get("layout") or ""))
                )
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
                self._json({"ok": True, "networks": state.device.wifi_scan()})
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
                    {
                        "ok": True,
                        "disconnected": state.device.wifi_disconnect(),
                    }
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
        except FlashError as exc:
            self._error(exc.code, str(exc), exc.status, exc.extra)
        except BrokerError as exc:
            self._error(exc.code, str(exc), 409)
        except PageError as exc:
            status = 504 if exc.code == "page_timeout" else 400
            self._error(exc.code, str(exc), status)
        except DeviceError as exc:
            status = 504 if exc.code == "device_timeout" else 400
            self._error(exc.code, str(exc), status)
        except PerfError as exc:
            self._error(exc.code, str(exc), exc.status)


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


def wait_job(
    base_url: str,
    job_id: str,
    *,
    as_json: bool = False,
) -> dict[str, Any]:
    since = 0
    while True:
        payload = request_json(
            "GET", f"{base_url}/api/jobs/{job_id}?since={since}"
        )
        job = payload.get("job") or {}
        for event in job.get("events") or []:
            text = str(event.get("text") or "")
            if as_json or not text:
                continue
            stream = event.get("stream")
            print(
                text,
                file=sys.stderr if stream == "stderr" else sys.stdout,
            )
        since = int(job.get("next") or since)
        if job.get("status") in TERMINAL_STATUSES:
            return job
        time.sleep(0.2)


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


def cmd_flash(args: argparse.Namespace) -> int:
    base = args.url.rstrip("/")
    if args.file:
        entry: dict[str, Any] = {"path": str(Path(args.file).resolve())}
        if args.address:
            entry["address"] = args.address
        source: dict[str, Any] = {"files": [entry]}
    elif args.zip:
        source = {"path": str(Path(args.zip).resolve())}
        if args.address:
            source["address"] = args.address
    else:
        source = {"path": str(Path(args.build_dir).resolve())}
        if args.address:
            source["address"] = args.address
    plan = request_json("POST", f"{base}/api/flash/plan", source)
    if not plan.get("ok"):
        print_result(plan, as_json=args.json)
        return 1
    if args.plan_only:
        if args.json:
            print(json.dumps(plan, ensure_ascii=False))
        else:
            print(f"source: {plan.get('notes') or plan.get('source')}")
            for entry in plan.get("entries") or []:
                print(
                    f"  {entry.get('address')}  {entry.get('name')}"
                    f"  ({entry.get('size')} bytes)"
                )
        return 0
    status = request_json("GET", f"{base}/api/status")
    serial = status.get("serial") or {}
    transport = str(status.get("transport") or serial.get("transport") or "")
    candidate = args.port
    if not candidate:
        if transport in ("", "serial"):
            candidate = str(serial.get("port") or "")
        else:
            links = serial.get("links") or {}
            candidate = str((links.get("serial") or {}).get("port") or "")
    if candidate in ("dual", "ble"):
        candidate = ""
    port = candidate
    if not port:
        print(
            "choose a serial port with --port; BLE cannot be used for flashing"
        )
        return 1
    payload = request_json(
        "POST",
        f"{base}/api/flash",
        {
            "plan_id": plan["plan_id"],
            "port": port,
            "baud": args.baud,
            "erase_all": args.erase_all,
            "verify": not args.no_verify,
            "after": args.after,
            "before": args.before,
            "reconnect": not args.no_reconnect,
        },
    )
    if not payload.get("ok"):
        print_result(payload, as_json=args.json)
        return 1
    job = wait_job(base, payload["job_id"], as_json=args.json)
    if args.json:
        print(json.dumps(job, ensure_ascii=False))
    elif job.get("status") == "ok":
        print("flash ok")
    else:
        print(f"flash {job.get('status')}: {job.get('error') or ''}")
    return 0 if job.get("status") == "ok" else 1


def serve(args: argparse.Namespace) -> int:
    config: dict[str, Any] = {}
    if args.esptool:
        config["esptool"] = args.esptool
    if args.flash_baud:
        config["flash_baud"] = args.flash_baud
    transport = args.transport or (
        "serial" if args.port else DEFAULT_TRANSPORT
    )
    serial_port = args.serial_port or args.port
    config.update(
        {
            "transport": transport,
            "ble_name": args.ble_name,
            "serial_port": serial_port,
            "ble_enabled": not args.no_ble,
            "serial_enabled": not args.no_serial,
            "link_wait_s": args.link_wait,
        }
    )
    state = HostState(fake=args.fake, config=config)
    if args.fake:
        state.broker.open("COM99", args.baud)
    elif transport == "serial" and serial_port:
        try:
            state.broker.open(serial_port, args.baud)
        except BrokerError as exc:
            print(f"serial open failed: {exc}")
    else:
        state.auto_connect()
    server = HostServer((args.host, args.http_port), HostHandler, state)
    url = f"http://{args.host}:{args.http_port}/"
    print(f"ESP32-C6 host: {url}")
    print(f"flasher: {url}flash/")
    print(f"perf: {url}perf/")
    print(f"mode: {'fake (COM99)' if args.fake else state.transport}")
    if state.transport in ("dual", "ble"):
        print(f"ble: {state.ble_name}  serial: {serial_port or 'auto'}")
    environment = state.flash.environment()
    esptool = environment["esptool"]
    if args.fake:
        print("esptool: fake backend")
    elif esptool["found"]:
        print(f"esptool: {esptool['version']} ({esptool['label']})")
    else:
        print(f"esptool: not found ({environment.get('hint')})")
    print("press Ctrl+C to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.perf.stop()
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
    serve_parser.add_argument(
        "--transport",
        choices=("dual", "ble", "serial"),
        default="",
        help="runtime links (default: dual; --port implies serial)",
    )
    serve_parser.add_argument(
        "--serial-port",
        default="",
        help="UART port for dual/serial (empty = auto-detect)",
    )
    serve_parser.add_argument(
        "--port", default="", help="alias for --serial-port"
    )
    serve_parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    serve_parser.add_argument("--ble-name", default=DEFAULT_BLE_NAME)
    serve_parser.add_argument("--link-wait", type=float, default=0.5)
    serve_parser.add_argument(
        "--no-ble", action="store_true", help="disable the BLE link"
    )
    serve_parser.add_argument(
        "--no-serial", action="store_true", help="disable the UART link"
    )
    serve_parser.add_argument(
        "--fake", action="store_true", help="use the in-memory demo backend"
    )
    serve_parser.add_argument(
        "--open", action="store_true", help="open the browser"
    )
    serve_parser.add_argument(
        "--esptool", default="", help="path to esptool.exe or esptool.py"
    )
    serve_parser.add_argument(
        "--flash-baud", type=int, default=0, help="default flash baud rate"
    )

    flash_parser = sub.add_parser(
        "flash", help="flash firmware through the host (esptool)"
    )
    add_common(flash_parser)
    source_group = flash_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--file", help="a single .bin image")
    source_group.add_argument("--zip", help="ZIP with flash_args or one BIN")
    source_group.add_argument(
        "--build-dir", help="ESP-IDF build directory with flash_args"
    )
    flash_parser.add_argument(
        "--address", default="", help="address for --file (default 0x0)"
    )
    flash_parser.add_argument("--port", default="")
    flash_parser.add_argument("--baud", type=int, default=0)
    flash_parser.add_argument(
        "--erase-all", action="store_true", dest="erase_all"
    )
    flash_parser.add_argument("--no-verify", action="store_true")
    flash_parser.add_argument(
        "--after",
        choices=("hard_reset", "soft_reset", "no_reset"),
        default="hard_reset",
    )
    flash_parser.add_argument(
        "--before",
        choices=(
            "default_reset",
            "usb_reset",
            "no_reset",
            "no_reset_no_sync",
        ),
        default="default_reset",
    )
    flash_parser.add_argument("--no-reconnect", action="store_true")
    flash_parser.add_argument("--plan-only", action="store_true")

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
    if args.command == "flash":
        return cmd_flash(args)

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
