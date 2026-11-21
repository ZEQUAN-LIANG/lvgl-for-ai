from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from config import ensure_runtime_dirs, load_config, public_base_url
from jobs import TERMINAL_STATUSES

_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
)


class CliError(RuntimeError):
    def __init__(self, message: str, *, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


class Client:
    def __init__(self, base_url: str, *, actor: str = "cli") -> None:
        self.base_url = base_url.rstrip("/")
        self.actor = actor

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        data = None
        headers = {
            "Accept": "application/json",
            "X-Sifli-Actor": self.actor,
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw.decode("utf-8"))
                message = payload.get("error") or raw.decode(
                    "utf-8", "replace"
                )
                code = payload.get("code") or f"http_{exc.code}"
            except (UnicodeDecodeError, ValueError):
                message = raw.decode("utf-8", "replace") or str(exc)
                code = f"http_{exc.code}"
            raise CliError(f"{code}: {message}", code=2) from exc
        except urllib.error.URLError as exc:
            raise CliError(
                f"cannot reach broker at {self.base_url}: {exc.reason}",
                code=2,
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CliError(
                f"broker returned invalid JSON: {exc}",
                code=2,
            ) from exc
        if not isinstance(payload, dict):
            raise CliError("broker returned a non-object JSON payload", code=2)
        return payload

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.request("POST", path, payload or {}, **kwargs)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _server_url(args: argparse.Namespace, config: dict[str, Any]) -> str:
    return (
        getattr(args, "server", None)
        or os.environ.get("SIFLI_HOST_URL")
        or public_base_url(config)
    )


def _health(url: str) -> dict[str, Any] | None:
    try:
        payload = Client(url).get("/api/health", timeout=0.6)
    except CliError:
        return None
    return payload if payload.get("name") == "sifli-host" else None


def _server_log_tail(config: dict[str, Any]) -> str:
    try:
        data = (Path(config["log_dir"]) / "server.log").read_bytes()[-2000:]
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def _spawn_server(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> None:
    ensure_runtime_dirs(config)
    log_path = Path(config["log_dir"]) / "server.log"
    log = open(log_path, "ab")
    command = [
        sys.executable,
        "-I",
        str(HOST_DIR / "server.py"),
        "--host",
        str(config["host"]),
        "--port",
        str(config["port"]),
    ]
    if getattr(args, "config", None):
        command.extend(["--config", args.config])
    try:
        subprocess.Popen(
            command,
            cwd=config["repo_root"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
            close_fds=True,
        )
    finally:
        log.close()


def ensure_server(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> Client:
    actor = getattr(args, "actor", "cli")
    url = _server_url(args, config)
    if _health(url):
        return Client(url, actor=actor)
    custom_target = getattr(args, "server", None) or os.environ.get(
        "SIFLI_HOST_URL"
    )
    if custom_target:
        raise CliError(
            f"broker is not running at {url}; start it manually or omit "
            "--server / SIFLI_HOST_URL",
            code=2,
        )
    if getattr(args, "no_autostart", False):
        raise CliError(
            f"broker is not running at {url} (--no-autostart)",
            code=2,
        )
    _spawn_server(args, config)
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        if _health(url):
            return Client(url, actor=actor)
        time.sleep(0.2)
    log_path = Path(config["log_dir"]) / "server.log"
    tail = _server_log_tail(config)
    raise CliError(
        "broker failed to start"
        + (f"; log tail:\n{tail}" if tail else f"; see {log_path}"),
        code=2,
    )


def _human_status(payload: dict[str, Any]) -> str:
    broker = payload.get("broker", {})
    env = payload.get("environment", {})
    lines = [
        f"state:   {broker.get('state')}",
        f"port:    {broker.get('port') or '-'}",
        f"baud:    {broker.get('baud') or '-'}",
        f"rx/tx:   {broker.get('total_rx', 0)} / {broker.get('total_tx', 0)} bytes",
        f"cursor:  {broker.get('next_seq', 0)} (first {broker.get('first_seq', 0)})",
        f"sftool:  {env.get('sftool_found') or env.get('sftool') or '-'}",
        f"scons:   {env.get('scons') or '-'}",
    ]
    if broker.get("log_path"):
        lines.append(f"log:     {broker['log_path']}")
    if broker.get("last_error"):
        lines.append(f"error:   {broker['last_error']}")
    return "\n".join(lines)


def _job_wait(
    client: Client,
    job_id: str,
    *,
    as_json: bool,
    poll_s: float = 0.2,
) -> dict[str, Any]:
    since = 0
    while True:
        payload = client.get(f"/api/jobs/{job_id}?since={since}")
        job = payload["job"]
        if not as_json:
            for event in job.get("events", []):
                text = event.get("text", "")
                stream = event.get("stream", "stdout")
                if stream == "stderr":
                    print(text, file=sys.stderr, flush=True)
                else:
                    print(text, flush=True)
        since = job.get("next", since)
        if job["status"] in TERMINAL_STATUSES:
            if as_json:
                _print_json(job)
            return job
        time.sleep(poll_s)


def _job_exit(
    client: Client,
    job_id: str,
    *,
    as_json: bool,
) -> int:
    job = _job_wait(client, job_id, as_json=as_json)
    return 0 if job["status"] == "ok" else 1


def cmd_serve(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from server import main as server_main

    argv: list[str] = [
        "--host",
        args.host or str(config["host"]),
        "--port",
        str(args.port if args.port is not None else config["port"]),
    ]
    if args.config:
        argv.extend(["--config", args.config])
    if args.open:
        argv.append("--open")
    return int(server_main(argv))


def cmd_ports(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.get("/api/ports")
    if args.json:
        _print_json(payload)
        return 0
    ports = payload.get("ports", [])
    if not ports:
        print("no serial ports found")
        return 0
    for item in ports:
        description = item.get("description") or item.get("device") or ""
        print(f"{item['port']:<8} {description}")
    return 0


def cmd_status(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.get("/api/status")
    _print_json(payload) if args.json else print(_human_status(payload))
    return 0


def cmd_open(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.post(
        "/api/open",
        {
            "port": args.port,
            "baud": args.baud or config["default_baud"],
        },
    )
    _print_json(payload) if args.json else print(
        _human_status({"broker": payload["status"]})
    )
    return 0


def cmd_close(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.post("/api/close")
    _print_json(payload) if args.json else print("closed")
    return 0


def cmd_send(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.post(
        "/api/send",
        {
            "data": args.data,
            "encoding": "hex" if args.hex else "utf-8",
            "line_ending": args.line_ending,
        },
    )
    _print_json(payload) if args.json else print(
        f"sent {payload.get('bytes', 0)} bytes"
    )
    return 0


def cmd_read(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    since = args.since
    if since == "now":
        status = client.get("/api/status")
        since = str(status["broker"]["next_seq"])
    path = (
        f"/api/read?since={int(since)}"
        f"&max={int(args.max)}&timeout_ms={int(args.timeout_ms)}"
    )
    payload = client.get(path, timeout=args.timeout_ms / 1000.0 + 10)
    if args.json:
        _print_json(payload)
    else:
        sys.stdout.write(payload.get("text", ""))
        sys.stdout.flush()
    return 0


def cmd_tail(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    if args.since == "now":
        status = client.get("/api/status")
        cursor = int(status["broker"]["next_seq"])
    else:
        cursor = int(args.since)
    try:
        while True:
            payload = client.get(
                f"/api/read?since={cursor}&timeout_ms=1000",
                timeout=15,
            )
            cursor = int(payload.get("next", cursor))
            if args.json:
                if payload.get("bytes"):
                    _print_json(payload)
            else:
                sys.stdout.write(payload.get("text", ""))
                sys.stdout.flush()
            time.sleep(0.05)
    except KeyboardInterrupt:
        return 0


def cmd_expect(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    since = args.since
    if since == "now":
        status = client.get("/api/status")
        since = str(status["broker"]["next_seq"])
    payload = client.post(
        "/api/expect",
        {
            "pattern": args.pattern,
            "since": int(since),
            "timeout_ms": args.timeout_ms,
            "regex": args.regex,
            "ignore_case": args.ignore_case,
        },
        timeout=args.timeout_ms / 1000.0 + 10,
    )
    if args.json:
        _print_json(payload)
    elif payload.get("ok"):
        print(payload.get("matched", ""))
    else:
        print(payload.get("text", ""), file=sys.stderr)
        print("expect timed out", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def cmd_reset(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.post("/api/reset", {"pulse_ms": args.pulse_ms})
    _print_json(payload) if args.json else print("reset pulse sent")
    return 0


def cmd_build(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.post(
        "/api/build",
        {
            "app": args.app,
            "project_dir": args.project_dir,
            "board": args.board,
        },
    )
    return _job_exit(client, payload["job_id"], as_json=args.json)


def cmd_flash(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    build = bool(args.build or (args.app and not args.build_dir))
    payload = client.post(
        "/api/flash",
        {
            "app": args.app,
            "project_dir": args.project_dir,
            "build_dir": args.build_dir,
            "build": build,
            "port": args.port,
            "baud": args.baud,
            "verify": args.verify,
            "erase_all": args.erase_all,
            "after": args.after,
            "reconnect": not args.no_reconnect,
        },
    )
    return _job_exit(client, payload["job_id"], as_json=args.json)


def cmd_flasher(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    build_dir = args.build_dir
    if args.build:
        job_payload = client.post(
            "/api/build",
            {
                "app": args.app,
                "project_dir": args.project_dir,
                "board": args.board,
            },
        )
        job = _job_wait(client, job_payload["job_id"], as_json=args.json)
        if job["status"] != "ok":
            return 1
        build_dir = (job.get("result") or {}).get("build_dir")
    payload = client.post(
        "/api/flasher/prepare",
        {
            "build_dir": build_dir,
            "project_dir": args.project_dir,
            "board": args.board,
        },
    )
    status = client.get("/api/status")
    if status.get("broker", {}).get("open"):
        client.post("/api/serial/handoff")
        print(
            "serial released for the official Web Flasher; "
            "reconnect with `open --port ...` when it is done",
            file=sys.stderr,
        )
    if args.json:
        _print_json(payload)
    else:
        print(payload["page_url"])
    if args.open:
        webbrowser.open(payload["page_url"])
    return 0


def cmd_logs(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.get("/api/logs")
    if args.json:
        _print_json(payload)
        return 0
    logs = payload.get("logs", [])
    if not logs:
        print("no logs")
        return 0
    for item in logs[:20]:
        meta = item.get("meta") or {}
        print(
            f"{item['name']:<28} {meta.get('port', '-'):<8} "
            f"{len(item.get('files', []))} files"
        )
    return 0


def cmd_shutdown(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.post("/api/shutdown")
    _print_json(payload) if args.json else print("broker stopping")
    return 0


def cmd_suggest(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    payload = client.get("/api/suggest")
    if args.json:
        _print_json(payload)
    else:
        print(f"app:     {payload.get('app') or '-'}")
        print(f"project: {payload.get('project_dir') or '-'}")
        print(f"build:   {payload.get('build_dir') or '-'}")
        print(f"port:    {payload.get('port') or '-'}")
        print(f"baud:    {payload.get('baud') or '-'}")
    return 0


def cmd_auto_reconnect(
    args: argparse.Namespace, config: dict[str, Any]
) -> int:
    client = ensure_server(args, config)
    enabled = args.state == "on"
    payload = client.post(
        "/api/serial/auto_reconnect",
        {"enabled": enabled},
    )
    _print_json(payload) if args.json else print(
        f"auto-reconnect {'on' if enabled else 'off'}"
    )
    return 0


def cmd_events(args: argparse.Namespace, config: dict[str, Any]) -> int:
    client = ensure_server(args, config)
    since = int(args.since)
    try:
        while True:
            payload = client.get(f"/api/events?since={since}")
            for event in payload.get("events", []):
                if args.json:
                    _print_json(event)
                else:
                    print(
                        f"[{event.get('ts', '')}] "
                        f"{event.get('actor', '?'):<4} "
                        f"{event.get('kind', ''):<20} "
                        f"{event.get('message', '')}"
                    )
            since = int(payload.get("next", since))
            if not args.follow:
                return 0
            time.sleep(0.35)
    except KeyboardInterrupt:
        return 0


@dataclass(frozen=True)
class Argument:
    flags: tuple[str, ...]
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Command:
    name: str
    help: str
    handler: Callable[[argparse.Namespace, dict[str, Any]], int]
    arguments: tuple[Argument, ...] = ()


def _arg(flags: str, **options: Any) -> Argument:
    return Argument((flags,), options)


COMMANDS: tuple[Command, ...] = (
    Command(
        "serve",
        "run the broker/web UI",
        cmd_serve,
        (
            _arg("--host", default=None),
            _arg("--port", type=int, default=None),
            _arg("--open", action="store_true"),
        ),
    ),
    Command("ports", "list serial ports", cmd_ports),
    Command("status", "broker status", cmd_status),
    Command(
        "open",
        "open a serial port",
        cmd_open,
        (
            _arg("--port", default=None),
            _arg("--baud", type=int, default=None),
        ),
    ),
    Command("close", "close the serial port", cmd_close),
    Command(
        "send",
        "write serial data",
        cmd_send,
        (
            _arg("data"),
            _arg("--hex", action="store_true", help="data is hex bytes"),
            _arg(
                "--line-ending",
                choices=["none", "cr", "lf", "crlf"],
                default="none",
            ),
        ),
    ),
    Command(
        "read",
        "read buffered data",
        cmd_read,
        (
            _arg("--since", default="0", help="cursor or 'now'"),
            _arg("--max", type=int, default=262144),
            _arg("--timeout-ms", type=int, default=0),
        ),
    ),
    Command(
        "tail",
        "follow serial output",
        cmd_tail,
        (_arg("--since", default="now", help="cursor or 'now'"),),
    ),
    Command(
        "expect",
        "wait for a pattern",
        cmd_expect,
        (
            _arg("pattern"),
            _arg("--since", default="now", help="cursor or 'now'"),
            _arg("--timeout-ms", type=int, default=5000),
            _arg("--regex", action="store_true"),
            _arg("--ignore-case", action="store_true"),
        ),
    ),
    Command(
        "reset",
        "pulse RTS reset",
        cmd_reset,
        (_arg("--pulse-ms", type=int, default=100),),
    ),
    Command(
        "build",
        "build a project",
        cmd_build,
        (
            _arg("--app", default=None, help="export this user/app first"),
            _arg("--project-dir", default=None),
            _arg("--board", default=None),
        ),
    ),
    Command(
        "flash",
        "flash via sftool",
        cmd_flash,
        (
            _arg("--app", default=None),
            _arg("--project-dir", default=None),
            _arg("--build-dir", default=None),
            _arg("--board", default=None),
            _arg("--port", default=None),
            _arg("--baud", type=int, default=None),
            _arg("--build", action="store_true", help="build before flashing"),
            _arg("--verify", dest="verify", action="store_true", default=None),
            _arg("--no-verify", dest="verify", action="store_false"),
            _arg("--erase-all", action="store_true", default=None),
            _arg(
                "--after",
                choices=["soft_reset", "no_reset"],
                default=None,
            ),
            _arg("--no-reconnect", action="store_true"),
        ),
    ),
    Command(
        "flasher",
        "prepare the official Web Flasher page",
        cmd_flasher,
        (
            _arg("--app", default=None),
            _arg("--project-dir", default=None),
            _arg("--build-dir", default=None),
            _arg("--board", default=None),
            _arg("--build", action="store_true"),
            _arg("--open", action="store_true"),
        ),
    ),
    Command("logs", "list serial logs", cmd_logs),
    Command("suggest", "suggest the last app/build/port", cmd_suggest),
    Command(
        "auto-reconnect",
        "toggle serial auto-reconnect",
        cmd_auto_reconnect,
        (_arg("state", choices=["on", "off"]),),
    ),
    Command(
        "events",
        "show activity events",
        cmd_events,
        (
            _arg("--since", default="0"),
            _arg("--follow", action="store_true"),
        ),
    ),
    Command("shutdown", "stop the broker", cmd_shutdown),
)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--server", default=None, help="broker base URL")
    common.add_argument("--config", default=None, help="host config JSON")
    common.add_argument(
        "--no-autostart",
        action="store_true",
        help="do not start the broker automatically",
    )
    common.add_argument(
        "--actor",
        choices=["cli", "ai", "web", "system"],
        default="cli",
        help="activity label shown in the web UI",
    )
    common.add_argument("--json", action="store_true", help="JSON output")

    parser = argparse.ArgumentParser(
        prog="sifli-host",
        description="Serial and flash CLI for the SiFli Huangshan Pi.",
    )
    parser.add_argument("--version", action="version", version="0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    for command in COMMANDS:
        sub_parser = sub.add_parser(
            command.name,
            parents=[common],
            help=command.help,
        )
        for argument in command.arguments:
            sub_parser.add_argument(*argument.flags, **argument.options)
        sub_parser.set_defaults(func=command.handler)
    return parser


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    try:
        return int(args.func(args, config))
    except CliError as exc:
        print(f"[sifli-host] {exc}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
