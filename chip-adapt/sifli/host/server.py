"""HTTP broker and web UI for the SiFli Huangshan Pi host.

Run with ``python -I chip-adapt/sifli/host/server.py --open`` (or double-click
``chip-adapt/sifli/launcher/SiFli-Host.exe``).  The server owns the COM port; the browser, CLI and an AI
agent all use the same HTTP/JSON API and the same byte cursor.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from config import (
    ensure_runtime_dirs,
    load_config,
    public_base_url,
)
from broker import SerialBroker, ports
from build_flash import (
    environment,
    find_build_dir,
    flash_environment,
    flash_plan,
    flasher_page_url,
    package_firmware,
    resolve_project_dir,
)
import flasher_web
from events import EventHub
from http_layer import (
    SseWriter,
    actor_from,
    content_type_for,
    error_response,
    json_bytes,
    origin_allowed,
    query_int,
    read_json_body,
    safe_join,
)
from jobs import TERMINAL_STATUSES, Job, JobManager
from runner import BuildRequest, FlashRequest, JobRunner
from serial_log import list_sessions
from state import StateStore, suggest

VERSION = "0.1.0"


class HostServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, config: dict[str, Any]) -> None:
        super().__init__(address, handler)
        self.config = config
        self.events = EventHub()
        self.state_store = StateStore(HOST_DIR / ".cache" / "state.json")
        self.broker = SerialBroker(config)
        self.jobs = JobManager(publisher=self.events.publish)
        self.runner = JobRunner(config, self.broker, self.state_store)
        self.flash_plans = flasher_web.PlanStore()
        self.flash_gate = threading.Lock()
        self.started_at = time.time()
        self.base_url = public_base_url(config)
        self.web_dir = HOST_DIR / "web"
        self.flasher_dir = Path(config.get("web_flasher_dir", ""))
        self.firmware_dir = Path(config.get("firmware_cache_dir", ""))
        self.log_dir = Path(config.get("log_dir", ""))

    @property
    def uptime_s(self) -> float:
        return round(time.time() - self.started_at, 3)

    def run_flash_job(self, job: Job, request: FlashRequest) -> None:
        """Run a flash job and release the flash gate when it ends."""
        try:
            self.runner.flash(job, request)
        finally:
            self.flash_gate.release()


class HostHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"SiFliHost/{VERSION}"
    server: HostServer

    GET_ROUTES = {
        "/": "_get_index",
        "/index.html": "_get_index",
        "/api/health": "_get_health",
        "/api/ports": "_get_ports",
        "/api/status": "_get_status",
        "/api/suggest": "_get_suggest",
        "/api/events": "_get_events",
        "/api/events/stream": "_get_events_stream",
        "/api/read": "_get_read",
        "/api/stream": "_get_stream",
        "/api/jobs": "_get_jobs",
        "/api/logs": "_get_logs",
        "/api/flash/env": "_get_flash_env",
        "/flash": "_get_flash_index",
        "/flash/": "_get_flash_index",
        "/flash.html": "_get_flash_index",
        "/firmware": "_get_firmware",
        "/tools/sftool": "_get_flasher_redirect",
        "/tools/sftool/": "_get_flasher_index",
        "/app.js": "_get_static",
        "/style.css": "_get_static",
    }
    GET_PREFIX_ROUTES = (
        ("/api/jobs/", "_get_job"),
        ("/api/logs/", "_get_log"),
        ("/firmware/", "_get_firmware"),
        ("/flash/", "_get_flash_asset"),
        ("/tools/sftool/", "_get_flasher_asset"),
        ("/vendor/", "_get_vendor_asset"),
    )
    POST_ROUTES = {
        "/api/open": "_post_open",
        "/api/close": "_post_close",
        "/api/serial/auto_reconnect": "_post_auto_reconnect",
        "/api/serial/handoff": "_post_handoff",
        "/api/send": "_post_send",
        "/api/expect": "_post_expect",
        "/api/reset": "_post_reset",
        "/api/build": "_post_build",
        "/api/flash": "_post_flash",
        "/api/flash/plan": "_post_flash_plan",
        "/api/flash/start": "_post_flash_start",
        "/api/shutdown": "_post_shutdown",
        "/api/flasher/prepare": "_post_flasher_prepare",
    }
    POST_PREFIX_ROUTES = (("/api/jobs/", "_post_job_action"),)

    @classmethod
    def route_for_get(cls, path: str) -> str | None:
        if path.endswith("/favicon.ico"):
            return "_get_favicon"
        handler = cls.GET_ROUTES.get(path)
        if handler is not None:
            return handler
        for prefix, name in cls.GET_PREFIX_ROUTES:
            if path.startswith(prefix):
                return name
        return None

    @classmethod
    def route_for_post(cls, path: str) -> str | None:
        handler = cls.POST_ROUTES.get(path)
        if handler is not None:
            return handler
        for prefix, name in cls.POST_PREFIX_ROUTES:
            if path.startswith(prefix):
                return name
        return None

    def log_message(self, fmt: str, *args: Any) -> None:
        print(
            f"[host] {self.address_string()} {fmt % args}",
            file=sys.stderr,
            flush=True,
        )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if not origin_allowed(
                self.headers.get("Origin"),
                int(self.server.server_address[1]),
            ):
                self._send_json(
                    403,
                    {"ok": False, "error": "cross-origin request rejected"},
                )
                return
            if method == "GET":
                self._route_get(path, query)
            else:
                self._route_post(path, query)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # noqa: BLE001 - HTTP boundary
            status, payload = error_response(exc)
            if status == 500:
                traceback.print_exc()
            self._send_json(status, payload)

    def _route_get(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        handler = self.route_for_get(path)
        if handler is None:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        getattr(self, handler)(path, query)

    def _route_post(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        # Consume the body for every POST so keep-alive framing stays valid.
        body = read_json_body(
            self.rfile,
            self.headers.get("Content-Length"),
        )
        handler = self.route_for_post(path)
        if handler is None:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        getattr(self, handler)(body, path, query)

    def _send_json(self, status: int, payload: Any) -> None:
        self._send_bytes(
            status,
            json_bytes(payload),
            "application/json; charset=utf-8",
        )

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        cache: str = "no-store",
        download_name: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{download_name}"',
            )
        self.end_headers()
        self.wfile.write(body)

    def _send_file(
        self,
        path: Path,
        *,
        cache: str = "no-cache",
        download_name: str | None = None,
    ) -> None:
        if not path.is_file():
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        self._send_bytes(
            200,
            path.read_bytes(),
            content_type_for(path),
            cache=cache,
            download_name=download_name,
        )

    def _begin_sse(self) -> SseWriter | None:
        writer = SseWriter(self.wfile)
        try:
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/event-stream; charset=utf-8"
            )
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            writer.start()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return None
        return writer

    def _request_base_url(self) -> str:
        """Use the host the browser actually used (127.0.0.1 vs localhost).

        The official Web Flasher fetches the firmware ZIP from the page's
        origin.  If the page was opened on ``localhost`` but the ZIP URL said
        ``127.0.0.1``, the fetch would be cross-origin and CORS would block it.
        """

        host = (self.headers.get("Host") or "").strip()
        port = int(self.server.server_address[1])
        allowed = {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
        }
        if host.lower() in allowed:
            return f"http://{host}"
        return self.server.base_url

    def _actor(self) -> str:
        return actor_from(self.headers.get("X-Sifli-Actor"))

    def _event(
        self,
        kind: str,
        message: str,
        data: dict[str, Any] | None = None,
        *,
        actor: str | None = None,
    ) -> None:
        self.server.events.publish(
            actor or self._actor(),
            kind,
            message,
            data=data or {},
        )

    def _get_index(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_file(self.server.web_dir / "index.html")

    def _get_flash_index(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        self._send_file(flasher_web.WEB_DIR / "index.html")

    def _get_flash_asset(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        relative = path[len("/flash/") :]
        target = flasher_web.asset_path(relative)
        if target is None:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        self._send_file(target)

    def _get_flash_env(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        payload = flash_environment(self.server.config)
        advice = suggest(self.server.config, self.server.state_store)
        suggestions = [
            {
                "label": (
                    f"{item.get('app') or 'build'} · "
                    f"{Path(item['build_dir']).name}"
                ),
                "build_dir": item["build_dir"],
            }
            for item in advice.get("builds", [])
        ]
        if advice.get("app") and advice.get("project_dir"):
            suggestions.append(
                {
                    "label": f"{advice['app']} · 工程",
                    "app": advice["app"],
                    "project_dir": advice["project_dir"],
                }
            )
        payload["defaults"] = {
            "app": advice.get("app", ""),
            "project_dir": advice.get("project_dir", ""),
            "build_dir": advice.get("build_dir", ""),
            "port": advice.get("port", ""),
            "baud": advice.get("baud") or payload["default_baud"],
        }
        payload["suggestions"] = suggestions
        self._send_json(200, {"ok": True, "env": payload})

    def _get_favicon(self, path: str, query: dict[str, list[str]]) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _get_health(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_json(
            200,
            {
                "ok": True,
                "name": "sifli-host",
                "version": VERSION,
                "pid": os.getpid(),
                "started_at": self.server.started_at,
                "uptime_s": self.server.uptime_s,
                "base_url": self.server.base_url,
            },
        )

    def _get_ports(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_json(200, {"ok": True, "ports": ports()})

    def _get_status(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_json(
            200,
            {
                "ok": True,
                "broker": self.server.broker.status(),
                "environment": environment(self.server.config),
                "server": {
                    "version": VERSION,
                    "uptime_s": self.server.uptime_s,
                    "base_url": self.server.base_url,
                    "flasher_page": "/flash/",
                    "official_flasher_page": "/tools/sftool/",
                },
            },
        )

    def _get_suggest(self, path: str, query: dict[str, list[str]]) -> None:
        payload = suggest(self.server.config, self.server.state_store)
        self._send_json(200, {"ok": True, **payload})

    def _get_events(self, path: str, query: dict[str, list[str]]) -> None:
        since = query_int(query, "since", 0)
        limit = query_int(query, "limit", 300)
        self._send_json(
            200,
            {
                "ok": True,
                **self.server.events.snapshot(since, limit=limit),
            },
        )

    def _get_events_stream(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        since = query_int(
            query,
            "since",
            self.server.events.current_seq(),
        )
        writer = self._begin_sse()
        if writer is None:
            return
        cursor = max(0, int(since))
        try:
            while True:
                if not self.server.events.wait(cursor, 15.0):
                    writer.ping()
                    continue
                snapshot = self.server.events.snapshot(cursor)
                cursor = int(snapshot["next"])
                if snapshot["events"]:
                    writer.send(snapshot)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _get_read(self, path: str, query: dict[str, list[str]]) -> None:
        since = query_int(query, "since", 0)
        max_bytes = query_int(query, "max", 0) or None
        timeout_ms = query_int(query, "timeout_ms", 0)
        self._send_json(
            200,
            {
                "ok": True,
                **self.server.broker.read_since(
                    since,
                    max_bytes=max_bytes,
                    timeout_ms=timeout_ms,
                ),
            },
        )

    def _get_stream(self, path: str, query: dict[str, list[str]]) -> None:
        since = query_int(query, "since", self.server.broker.current_seq())
        writer = self._begin_sse()
        if writer is None:
            return
        cursor = max(0, int(since))
        try:
            while True:
                if not self.server.broker.wait_for_data(cursor, 15.0):
                    writer.ping()
                    continue
                chunk = self.server.broker.read_since(cursor)
                if chunk["bytes"]:
                    cursor = chunk["next"]
                    writer.send(
                        {
                            "since": chunk["since"],
                            "next": chunk["next"],
                            "first_seq": chunk["first_seq"],
                            "next_seq": chunk["next_seq"],
                            "truncated": chunk["truncated"],
                            "data_b64": chunk["data_b64"],
                        }
                    )
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _get_jobs(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_json(200, {"ok": True, "jobs": self.server.jobs.list()})

    def _get_job(self, path: str, query: dict[str, list[str]]) -> None:
        parts = path.split("/")
        if len(parts) < 4:
            self._send_json(404, {"ok": False, "error": "job not found"})
            return
        job_id = parts[3]
        if len(parts) >= 5 and parts[4] == "stream":
            self._serve_job_stream(job_id, query)
            return
        job = self.server.jobs.get(job_id)
        if job is None:
            self._send_json(404, {"ok": False, "error": "job not found"})
            return
        since = query_int(query, "since", 0)
        self._send_json(200, {"ok": True, "job": job.snapshot(since)})

    def _serve_job_stream(
        self,
        job_id: str,
        query: dict[str, list[str]],
    ) -> None:
        job = self.server.jobs.get(job_id)
        if job is None:
            self._send_json(404, {"ok": False, "error": "job not found"})
            return
        since = query_int(query, "since", 0)
        writer = self._begin_sse()
        if writer is None:
            return
        try:
            while True:
                job.wait(since, 10.0)
                snapshot = job.snapshot(since)
                events = snapshot["events"]
                if events:
                    since = snapshot["next"]
                    writer.send(
                        {
                            "id": job.id,
                            "status": snapshot["status"],
                            "percent": snapshot["percent"],
                            "events": events,
                            "next": since,
                        }
                    )
                if snapshot["status"] in TERMINAL_STATUSES:
                    writer.send(snapshot, event="done")
                    return
                if not events:
                    writer.ping()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _get_logs(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_json(
            200,
            {"ok": True, "logs": list_sessions(self.server.log_dir)},
        )

    def _get_log(self, path: str, query: dict[str, list[str]]) -> None:
        parts = path.split("/")
        if len(parts) < 5:
            self._send_json(404, {"ok": False, "error": "log not found"})
            return
        name, filename = parts[3], "/".join(parts[4:])
        target = safe_join(self.server.log_dir, f"{name}/{filename}")
        if target is None:
            self._send_json(403, {"ok": False, "error": "invalid path"})
            return
        self._send_file(target, cache="no-store", download_name=target.name)

    def _get_firmware(self, path: str, query: dict[str, list[str]]) -> None:
        name = (
            path[len("/firmware/") :] if path.startswith("/firmware/") else ""
        )
        target = safe_join(self.server.firmware_dir, name)
        if target is None:
            self._send_json(403, {"ok": False, "error": "invalid path"})
            return
        self._send_file(target, cache="no-store", download_name=target.name)

    def _get_flasher_redirect(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        self.send_response(301)
        self.send_header("Location", "/tools/sftool/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _get_flasher_index(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        self._send_file(self.server.flasher_dir / "index.html")

    def _get_flasher_asset(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        relative = path[len("/tools/sftool/") :]
        target = safe_join(self.server.flasher_dir, relative)
        if target is None:
            self._send_json(403, {"ok": False, "error": "invalid path"})
            return
        self._send_file(target, cache="no-cache")

    def _get_vendor_asset(
        self,
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        target = safe_join(self.server.web_dir, path.lstrip("/"))
        if target is None:
            self._send_json(403, {"ok": False, "error": "invalid path"})
            return
        self._send_file(
            target,
            cache="public, max-age=31536000, immutable",
        )

    def _get_static(self, path: str, query: dict[str, list[str]]) -> None:
        self._send_file(self.server.web_dir / path.lstrip("/"))

    def _post_open(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        port = body.get("port") or None
        baud = body.get("baud")
        status = self.server.broker.open(
            port,
            int(baud) if baud else None,
        )
        self.server.state_store.record_open(
            port=status["port"],
            baud=status["baud"],
        )
        self._event(
            "serial.open",
            f"opened {status['port']} @ {status['baud']}",
            {"port": status["port"], "baud": status["baud"]},
        )
        self._send_json(200, {"ok": True, "status": status})

    def _post_close(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        status = self.server.broker.close()
        self._event(
            "serial.close",
            "closed",
            {"port": status.get("port", "")},
        )
        self._send_json(200, {"ok": True, "status": status})

    def _post_auto_reconnect(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        enabled = bool(body.get("enabled"))
        status = self.server.broker.set_auto_reconnect(enabled)
        self._event(
            "serial.auto_reconnect",
            f"auto reconnect {'on' if enabled else 'off'}",
            {"enabled": enabled},
        )
        self._send_json(200, {"ok": True, "status": status})

    def _post_handoff(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        result = self.server.broker.handoff_to_flasher()
        self._event(
            "serial.handoff",
            "serial released for Web Flasher; auto-reconnect armed",
            result,
        )
        self._send_json(200, {"ok": True, **result})

    def _post_send(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        data = body.get("data", "")
        encoding = str(body.get("encoding") or "utf-8").lower()
        if encoding == "hex":
            payload = bytes.fromhex(str(data))
        else:
            payload = str(data).encode("utf-8")
        line_ending = str(body.get("line_ending") or "none").lower()
        payload += {
            "none": b"",
            "cr": b"\r",
            "lf": b"\n",
            "crlf": b"\r\n",
        }.get(line_ending, b"")
        result = self.server.broker.send(payload)
        actor = self._actor()
        if actor != "web":
            preview = payload.decode("utf-8", "replace")
            if len(preview) > 200:
                preview = preview[:200] + "…"
            self._event(
                "serial.send",
                preview or f"{len(payload)} bytes",
                {
                    "bytes": len(payload),
                    "encoding": encoding,
                    "line_ending": line_ending,
                    "text": preview,
                },
                actor=actor,
            )
        self._send_json(200, {"ok": True, **result})

    def _post_expect(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        pattern = str(body.get("pattern") or "")
        result = self.server.broker.expect(
            pattern,
            since=int(body.get("since") or 0),
            timeout_ms=int(body.get("timeout_ms") or 5000),
            regex=bool(body.get("regex")),
            ignore_case=bool(body.get("ignore_case")),
        )
        self._event(
            "serial.expect",
            f"expect {pattern!r} -> {'ok' if result.get('ok') else 'timeout'}",
            {
                "pattern": pattern,
                "ok": bool(result.get("ok")),
                "matched": result.get("matched", ""),
            },
        )
        self._send_json(200, result)

    def _post_reset(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        result = self.server.broker.reset(int(body.get("pulse_ms") or 100))
        self._event("serial.reset", "RTS reset pulse", result)
        self._send_json(200, {"ok": True, **result})

    def _post_build(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        request = BuildRequest.from_body(body)
        job = self.server.jobs.create(
            "build",
            "build",
            actor=self._actor(),
        )
        self._event(
            "job.request",
            "build requested",
            {
                "job_id": job.id,
                "kind": "build",
                "app": request.app,
                "project_dir": request.project_dir or "",
            },
        )
        self._start_job_thread(self.server.runner.build, job, request)
        self._send_json(202, {"ok": True, "job_id": job.id})

    def _post_flash(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        if not self.server.flash_gate.acquire(blocking=False):
            self._send_json(
                409,
                {
                    "ok": False,
                    "code": "flash_busy",
                    "error": "another flash job is already running",
                },
            )
            return
        started = False
        try:
            request = FlashRequest.from_body(body)
            job = self.server.jobs.create(
                "flash",
                "flash",
                actor=self._actor(),
            )
            self._event(
                "job.request",
                "flash requested",
                {
                    "job_id": job.id,
                    "kind": "flash",
                    "app": request.app,
                    "project_dir": request.project_dir or "",
                    "build_dir": request.build_dir or "",
                },
            )
            self._start_job_thread(
                self.server.run_flash_job,
                job,
                request,
            )
            started = True
            self._send_json(202, {"ok": True, "job_id": job.id})
        finally:
            if not started:
                self.server.flash_gate.release()

    def _post_flash_plan(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        source = {
            key: body[key]
            for key in ("app", "project_dir", "build_dir", "board")
            if body.get(key)
        }
        plan = flash_plan(self.server.config, **source)
        plan_id = self.server.flash_plans.put(plan)
        payload = flasher_web.public_plan({**plan, "plan_id": plan_id})
        self._event(
            "flasher.plan",
            "resolved sftool_param.json",
            {
                "plan_id": plan_id,
                "build_dir": plan["build_dir"],
                "entries": len(plan["entries"]),
            },
        )
        self._send_json(200, {"ok": True, **payload})

    def _post_flash_start(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        plan_id = str(body.get("plan_id") or "")
        plan = self.server.flash_plans.get(plan_id)
        if plan is None:
            self._send_json(
                404,
                {
                    "ok": False,
                    "code": "plan_not_found",
                    "error": "firmware plan expired; resolve it again",
                },
            )
            return
        if not self.server.flash_gate.acquire(blocking=False):
            self._send_json(
                409,
                {
                    "ok": False,
                    "code": "flash_busy",
                    "error": "another flash job is already running",
                },
            )
            return
        started = False
        try:
            request = FlashRequest(
                app=str(plan.get("app") or ""),
                project_dir=plan.get("project_dir") or None,
                build_dir=plan.get("build_dir") or None,
                board=plan.get("board") or None,
                build=False,
                port=str(body["port"]) if body.get("port") else None,
                baud=int(body["baud"]) if body.get("baud") else None,
                verify=body.get("verify"),
                erase_all=body.get("erase_all"),
                after=body.get("after") or None,
                reconnect=body.get("reconnect", True) is not False,
            )
            job = self.server.jobs.create(
                "flash",
                "flash",
                actor=self._actor(),
            )
            self._event(
                "job.request",
                "flash requested",
                {
                    "job_id": job.id,
                    "kind": "flash",
                    "app": request.app,
                    "project_dir": request.project_dir or "",
                    "build_dir": request.build_dir or "",
                    "plan_id": plan_id,
                },
            )
            self._start_job_thread(
                self.server.run_flash_job,
                job,
                request,
            )
            started = True
            self._send_json(202, {"ok": True, "job_id": job.id})
        finally:
            if not started:
                self.server.flash_gate.release()

    def _post_job_action(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        if not path.endswith("/cancel"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        job_id = path.split("/")[3]
        job = self.server.jobs.get(job_id)
        if job is None:
            self._send_json(404, {"ok": False, "error": "job not found"})
            return
        job.cancel()
        self._send_json(200, {"ok": True, "job_id": job.id})

    def _post_shutdown(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        self._send_json(200, {"ok": True})
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _post_flasher_prepare(
        self,
        body: dict[str, Any],
        path: str,
        query: dict[str, list[str]],
    ) -> None:
        build_dir = body.get("build_dir") or None
        if not build_dir:
            board = str(
                body.get("board") or self.server.config.get("board") or ""
            )
            project = resolve_project_dir(
                body.get("project_dir") or None,
                self.server.config,
            )
            if project is not None:
                build_dir = find_build_dir(project, board)
        if not build_dir:
            self._send_json(
                409,
                {
                    "ok": False,
                    "code": "build_required",
                    "error": "build the project first, then prepare the flasher",
                },
            )
            return
        build_path = Path(str(build_dir))
        if not build_path.is_absolute():
            build_path = Path(self.server.config["repo_root"]) / build_path
        packed = package_firmware(
            build_path,
            self.server.config["firmware_cache_dir"],
        )
        base_url = self._request_base_url()
        page = flasher_page_url(
            base_url,
            chip=packed["chip"],
            memory=packed["memory"],
            zip_name=packed["zip_name"],
        )
        self._event(
            "flasher.prepare",
            f"prepared {len(packed['files'])} BIN for Web Flasher",
            {
                "chip": packed["chip"],
                "memory": packed["memory"],
                "files": packed["files"],
                "build_dir": str(build_path),
            },
        )
        self._send_json(
            200,
            {
                **packed,
                "zip_url": f"{base_url}/firmware/{packed['zip_name']}",
                "page_url": page,
                "build_dir": str(build_path),
            },
        )

    def _start_job_thread(
        self,
        target,
        job: Job,
        request: BuildRequest | FlashRequest,
    ) -> None:
        job.start()
        thread = threading.Thread(
            target=target,
            args=(job, request),
            name=f"job-{job.kind}-{job.id}",
            daemon=True,
        )
        thread.start()


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _serving_host(url: str) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"{url}/api/health",
            timeout=0.6,
        ) as response:
            health = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return health.get("name") == "sifli-host"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sifli-host",
        description="HTTP serial broker for the SiFli Huangshan Pi.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--open", action="store_true", help="open the browser")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0

    config = load_config(args.config)
    if args.host:
        config["host"] = args.host
    if args.port is not None:
        config["port"] = args.port
    ensure_runtime_dirs(config)

    host = str(config["host"])
    port = int(config["port"])
    if port and _port_in_use(host, port):
        url = public_base_url(config)
        if _serving_host(url):
            print(f"[sifli-host] already serving at {url}", file=sys.stderr)
            if args.open and not args.no_open:
                webbrowser.open(url)
            return 0
        print(
            f"[sifli-host] {host}:{port} is used by another process",
            file=sys.stderr,
        )
        return 1

    try:
        server = HostServer((host, port), HostHandler, config)
    except OSError as exc:
        print(
            f"[sifli-host] cannot bind {host}:{port}: {exc}", file=sys.stderr
        )
        return 1

    actual_host, actual_port = server.server_address[:2]
    if actual_host in ("0.0.0.0", "::"):
        actual_host = "127.0.0.1"
    server.base_url = f"http://{actual_host}:{actual_port}"
    config["port"] = int(actual_port)
    url = server.base_url
    print(f"[sifli-host] serving {url}", file=sys.stderr)
    print(f"[sifli-host] flasher {url}/flash/", file=sys.stderr)
    print(
        f"[sifli-host] config {config.get('config_path')} "
        f"(exists={config.get('config_exists')})",
        file=sys.stderr,
    )
    if args.open and not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\n[sifli-host] stopping", file=sys.stderr)
    finally:
        try:
            server.broker.close()
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
