#!/usr/bin/env python3
"""Record and compare the external behavior contract of the LVGL AI tools.

The refactor work in ``.scratch/ai-tools/issues/14-architecture-deepening.md``
must not change any user-visible behavior.  This tool captures the six
contracts that refactors may not drift:

- ``http``: routes, methods, status codes and JSON key shapes
- ``cli``: ``cli.py`` / ``web.py`` / ``tools/new_app.py`` parsers, help text,
  exit codes and ``--json`` keys
- ``protocol``: engine command grammar, reply shapes, required ready/reply
  fields and engine launch flags
- ``session``: session file set, manifest fields/artifacts, ndjson row shapes
  and ``Recording`` read requirements
- ``page``: server-rendered element ids/classes, visible copy and endpoint
  references
- ``python``: top-level ``lvgl_ai`` exports and the ``apps`` lifecycle API

Record once before a refactor and compare after it::

    python -I core/tools/contract_snapshot.py record
    python -I core/tools/contract_snapshot.py compare

``compare`` re-records in a temporary directory and exits 0 when the snapshot
matches, 1 when it differs, and 2 on a harness error.  All probes run against
temporary sessions/repos and an ephemeral HTTP port; the snapshot never
contains absolute paths, timestamps, runtime-generated session ids or bound
ports.  Fixed fixture values (for example the page fixture session id) are
part of the recorded contract.

The protocol and session probes drive the Python control layer with a scripted
fake engine.  Real C-engine semantics stay covered by the full test suite; the
snapshot freezes the Python-visible command/reply and evidence contract.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import warnings
import zlib
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable

# ``python -I`` does not add the script directory to sys.path.
TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import Recording, Runtime, play_scenario  # noqa: E402
from lvgl_ai import paths  # noqa: E402

SNAPSHOT_SCHEMA = "lvgl-ai-contract-snapshot-v1"
DEFAULT_SNAPSHOT_PATH = Path(__file__).resolve().with_name(
    "contract_snapshot.json"
)
FIXTURE_SESSION_ID = "20260102-030405-abcd"
FIXTURE_APP = "alpha"
REQUEST_HEADER = "X-LVGL-AI-Request"

# Environment variables read by the embedded fake engine.  They only carry
# probe configuration; the engine itself never appears in the snapshot.
ENGINE_ARGV_LOG = "CONTRACT_SNAPSHOT_ARGV_LOG"
ENGINE_COMMAND_LOG = "CONTRACT_SNAPSHOT_COMMAND_LOG"
ENGINE_REPLY_LOG = "CONTRACT_SNAPSHOT_REPLY_LOG"
ENGINE_READY_OMIT = "CONTRACT_SNAPSHOT_READY_OMIT"
ENGINE_REPLY_OMIT = "CONTRACT_SNAPSHOT_REPLY_OMIT"
ENGINE_REPLY_ERROR = "CONTRACT_SNAPSHOT_REPLY_ERROR"
ENGINE_PROTOCOL = "CONTRACT_SNAPSHOT_PROTOCOL"
ENGINE_EXIT_AFTER_READY = "CONTRACT_SNAPSHOT_EXIT_AFTER_READY"

_FAKE_ENGINE_SOURCE = r'''
"""Scripted lvgl-ai-engine-v1 double used by the contract snapshot tool."""

import json
import os
import sys
import zlib
from pathlib import Path

PROTOCOL = os.environ.get("CONTRACT_SNAPSHOT_PROTOCOL", "lvgl-ai-engine-v1")
READY_OMIT = {
    item
    for item in os.environ.get("CONTRACT_SNAPSHOT_READY_OMIT", "").split(",")
    if item
}
REPLY_OMIT = os.environ.get("CONTRACT_SNAPSHOT_REPLY_OMIT", "")
REPLY_ERROR = os.environ.get("CONTRACT_SNAPSHOT_REPLY_ERROR", "")


def log(name, text):
    path = os.environ.get(name)
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip("\n") + "\n")


def emit(payload):
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    log("CONTRACT_SNAPSHOT_REPLY_LOG", line)
    print(line, flush=True)


def png(width, height, rgb):
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        for _ in range(width):
            raw.extend(rgb)
    def chunk(kind, payload):
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big")
        )
    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes(
        (8, 2, 0, 0, 0)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def write_evidence(root, reference_path):
    frames = root / "frames"
    frames.mkdir(exist_ok=True)
    (frames / "000001.png").write_bytes(png(2, 2, (255, 0, 0)))
    (frames / "000002.png").write_bytes(png(2, 2, (0, 255, 0)))
    timeline = [
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 1,
            "t_ms": 0,
            "file": "frames/000001.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 2,
            "t_ms": 16,
            "file": "frames/000002.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "input",
            "seq": 1,
            "frame_no": 2,
            "t_ms": 16,
            "device": "pointer",
            "action": "down",
            "x": 10,
            "y": 20,
            "hit": "snap_button",
            "hit_class": "lv_button",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "wait",
            "frame_start": 1,
            "frame_end": 2,
            "t_ms_start": 0,
            "t_ms_end": 16,
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "mark",
            "frame_no": 2,
            "t_ms": 16,
            "id": "static_mark",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "end",
            "frame_count": 2,
            "t_ms": 16,
            "truncated": False,
        },
    ]
    (root / "timeline.ndjson").write_text(
        "".join(json.dumps(row) + "\n" for row in timeline),
        encoding="utf-8",
    )
    diff = {
        "schema": "lvgl-ai-frame-diffs-v1",
        "frame_no": 2,
        "prev_frame_no": 1,
        "t_ms": 16,
        "width": 2,
        "height": 2,
        "threshold": 10,
        "bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
        "changed_px": 1,
        "changed_ratio": 0.25,
        "max_delta": 0.2,
    }
    (root / "frame_diffs.ndjson").write_text(
        json.dumps(diff) + "\n", encoding="utf-8"
    )
    if reference_path:
        reference = dict(diff)
        reference["prev_frame_no"] = None
        reference["bbox"] = {"x": 1, "y": 1, "w": 1, "h": 1}
        (root / "reference_diffs.ndjson").write_text(
            json.dumps(reference) + "\n", encoding="utf-8"
        )


def reply(seq, frames, t_ms, extra=None):
    payload = {
        "protocol": PROTOCOL,
        "seq": seq,
        "ok": True,
        "frames": frames,
        "t_ms": t_ms,
    }
    if extra:
        payload.update(extra)
    return payload


def main():
    args = sys.argv[1:]
    log("CONTRACT_SNAPSHOT_ARGV_LOG", json.dumps(args, ensure_ascii=False))
    session = None
    reference_path = None
    record = False
    live_frame = False
    index = 0
    while index < len(args):
        if args[index] == "--session" and index + 1 < len(args):
            session = args[index + 1]
            index += 2
        elif args[index] == "--record":
            record = True
            index += 1
        elif args[index] == "--no-record":
            record = False
            index += 1
        elif args[index] == "--live-frame":
            live_frame = True
            index += 1
        elif args[index] == "--reference" and index + 1 < len(args):
            reference_path = args[index + 1]
            index += 2
        elif args[index] in ("--max-frames", "--diff-threshold") and index + 1 < len(args):
            index += 2
        else:
            index += 1

    root = Path(session) if session else None
    if root is not None and record:
        write_evidence(root, reference_path)
    if root is not None and live_frame:
        (root / "live.rgba").write_bytes(b"\x00" * 16)

    ready = {
        "protocol": PROTOCOL,
        "ready": True,
        "seq": 0,
        "lvgl": "9.6.0",
        "lvgl_src": "/fake/lvgl-src/9.6",
        "display": {"width": 800, "height": 600, "format": "XRGB8888"},
        "mode": "headless",
        "inputs": ["real", "virtual"],
        "capabilities": [
            "pointer",
            "key",
            "encoder",
            "tick",
            "wait",
            "snapshot",
            "mark",
            "record",
        ],
        "adapter": "9x",
        "frames": 2,
        "max_frames": 600,
        "truncated": False,
    }
    for key in READY_OMIT:
        ready.pop(key, None)
    emit(ready)
    if os.environ.get("CONTRACT_SNAPSHOT_EXIT_AFTER_READY") == "1":
        return 0

    frames = 2
    t_ms = 16
    snapshots = 0
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        log("CONTRACT_SNAPSHOT_COMMAND_LOG", line)
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            seq = int(parts[0])
        except ValueError:
            continue
        verb = parts[1]
        if verb == "quit":
            emit(reply(seq, frames, t_ms))
            return 0
        if REPLY_ERROR == verb:
            emit(
                {
                    "protocol": PROTOCOL,
                    "seq": seq,
                    "ok": False,
                    "error": "bad_args",
                    "message": "contract probe",
                }
            )
            continue
        extra = None
        if verb == "pointer" and len(parts) >= 5:
            extra = {"hit": "snap_button", "hit_class": "lv_button"}
        elif verb == "key" and len(parts) >= 5:
            extra = {"delivered": True, "key": parts[4]}
        elif verb == "encoder" and len(parts) >= 4:
            extra = {"delivered": True, "diff": int(parts[3])}
        elif verb == "snapshot" and len(parts) >= 3:
            snapshots += 1
            relative = "snapshots/%03d_%s.png" % (snapshots, parts[2])
            extra = {"file": relative}
            if root is not None and record:
                (root / "snapshots").mkdir(exist_ok=True)
                (root / relative).write_bytes(png(2, 2, (9, 9, 9)))
                with open(
                    root / "timeline.ndjson", "a", encoding="utf-8",
                    newline="\n",
                ) as handle:
                    handle.write(
                        json.dumps(
                            {
                                "schema": "lvgl-ai-timeline-v1",
                                "type": "snapshot",
                                "frame_no": frames,
                                "t_ms": t_ms,
                                "label": parts[2],
                                "file": relative,
                            }
                        )
                        + "\n"
                    )
        elif verb == "tick" and len(parts) >= 3:
            t_ms += int(parts[2])
            frames += 1
        elif verb == "wait" and len(parts) >= 4 and parts[2] == "frames":
            frames += int(parts[3])
            t_ms += 16 * int(parts[3])
        elif verb == "wait" and len(parts) >= 3:
            t_ms += int(parts[2])
        payload = reply(seq, frames, t_ms, extra)
        if REPLY_OMIT:
            omit_verb, _, omit_field = REPLY_OMIT.partition(":")
            if omit_verb == verb:
                payload.pop(omit_field, None)
        emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


# ---------------------------------------------------------------------------
# canonical JSON / shapes


def _canonical_json(value: Any, *, indent: int | None = 2) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=indent
    )


def _shape(value: Any) -> Any:
    """Return a deterministic type/key shape without any values."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return {"object": {str(key): _shape(item) for key, item in value.items()}}
    if isinstance(value, (list, tuple)):
        unique: dict[str, Any] = {}
        for item in value:
            item_shape = _shape(item)
            unique[_canonical_json(item_shape, indent=None)] = item_shape
        return {"array": [unique[key] for key in sorted(unique)]}
    return {"unknown": type(value).__name__}


def _json_lines(path: Path) -> list[Any]:
    rows: list[Any] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def snapshot_bytes(snapshot: dict[str, Any]) -> bytes:
    return (_canonical_json(snapshot) + "\n").encode("utf-8")


def load_snapshot(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError(
            f"{path}: schema must be {SNAPSHOT_SCHEMA!r}"
        )
    return data


def write_snapshot(path: str | Path, snapshot: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(snapshot_bytes(snapshot))


# ---------------------------------------------------------------------------
# comparison


def _same_json(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_json(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_json(a, b) for a, b in zip(left, right)
        )
    return left == right


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 160 else text[:157] + "..."


def compare_snapshots(
    expected: Any, actual: Any, path: str = ""
) -> list[dict[str, Any]]:
    """Return ordered structural differences between two JSON values."""
    if _same_json(expected, actual):
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences: list[dict[str, Any]] = []
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}" if path else str(key)
            if key not in actual:
                differences.append(
                    {"path": child, "kind": "missing", "expected": expected[key]}
                )
            elif key not in expected:
                differences.append(
                    {"path": child, "kind": "unexpected", "actual": actual[key]}
                )
            else:
                differences.extend(
                    compare_snapshots(expected[key], actual[key], child)
                )
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        for index in range(min(len(expected), len(actual))):
            differences.extend(
                compare_snapshots(
                    expected[index], actual[index], f"{path}[{index}]"
                )
            )
        if len(expected) != len(actual):
            differences.append(
                {
                    "path": f"{path}.length",
                    "kind": "length",
                    "expected": len(expected),
                    "actual": len(actual),
                }
            )
        return differences
    return [
        {
            "path": path or "<root>",
            "kind": "changed",
            "expected": expected,
            "actual": actual,
        }
    ]


def render_diff_report(
    differences: Iterable[dict[str, Any]], *, reference: str | None = None
) -> str:
    items = list(differences)
    lines = []
    if reference is not None:
        lines.append(f"[contract] snapshot: {reference}")
    lines.append(f"[contract] differences: {len(items)}")
    for item in items:
        kind = item["kind"]
        if kind == "missing":
            lines.append(
                f"- {item['path']}: missing from current snapshot "
                f"(was {_short(item['expected'])})"
            )
        elif kind == "unexpected":
            lines.append(
                f"+ {item['path']}: new in current snapshot "
                f"({_short(item['actual'])})"
            )
        elif kind == "length":
            lines.append(
                f"~ {item['path']}: length {item['expected']} -> "
                f"{item['actual']}"
            )
        else:
            lines.append(
                f"- {item['path']}: {_short(item['expected'])} -> "
                f"{_short(item['actual'])}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# temporary workspace helpers


@contextlib.contextmanager
def _workspace() -> Iterable[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory(prefix="lvgl-ai-contract-") as raw:
        root = Path(raw)
        engine = root / "fake_engine.py"
        engine.write_text(_FAKE_ENGINE_SOURCE, encoding="utf-8")
        yield root, engine


@contextlib.contextmanager
def _environment(**values: str | None) -> Iterable[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _new_runtime(
    engine: Path,
    sessions_root: Path,
    *,
    record: bool = False,
    live_frame: bool = False,
    record_changed_only: bool = False,
    diff_threshold: int = 10,
    max_frames: int = 600,
    reference: Path | None = None,
    timeout: float = 5.0,
) -> Runtime:
    return Runtime(
        lvgl="9.6",
        build=False,
        record=record,
        live_frame=live_frame,
        record_changed_only=record_changed_only,
        diff_threshold=diff_threshold,
        max_frames=max_frames,
        reference=reference,
        headless=True,
        sessions_root=sessions_root,
        session_retention=None,
        timeout=timeout,
        _engine_command=[sys.executable, "-I", str(engine)],
    )


class _RunResult:
    def __init__(
        self,
        root: Path,
        runtime: Runtime,
        error: Exception | None,
    ) -> None:
        self.root = root
        self.runtime = runtime
        self.error = error

    def outcome(self) -> str:
        if self.error is None:
            return "ok"
        return type(self.error).__name__


def _capture_run(
    workspace: Path,
    engine: Path,
    sessions_root: Path,
    name: str,
    *,
    actions: Iterable[Callable[[Runtime], Any]] = (),
    prepare: Callable[[Runtime], None] | None = None,
    env: dict[str, str] | None = None,
    **runtime_kwargs: Any,
) -> _RunResult:
    root = workspace / name
    root.mkdir()
    log_env = {
        ENGINE_ARGV_LOG: str(root / "argv.json"),
        ENGINE_COMMAND_LOG: str(root / "commands.ndjson"),
        ENGINE_REPLY_LOG: str(root / "replies.ndjson"),
    }
    if env:
        log_env.update(env)
    runtime = _new_runtime(engine, sessions_root, **runtime_kwargs)
    error: Exception | None = None
    with _environment(**log_env):
        try:
            runtime.start()
            if prepare is not None:
                prepare(runtime)
            for action in actions:
                action(runtime)
        except Exception as exc:  # noqa: BLE001 - snapshot every outcome
            error = exc
        finally:
            try:
                runtime.stop()
            except Exception as exc:  # noqa: BLE001
                if error is None:
                    error = exc
    return _RunResult(root, runtime, error)


def _commands(result: _RunResult) -> list[str]:
    path = result.root / "commands.ndjson"
    if not path.is_file():
        return []
    return [line.split(" ", 1)[1] for line in path.read_text(
        encoding="utf-8"
    ).splitlines() if " " in line]


def _replies(result: _RunResult) -> list[dict[str, Any]]:
    path = result.root / "replies.ndjson"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(
        encoding="utf-8"
    ).splitlines() if line.strip()]


def _argv(result: _RunResult) -> list[str]:
    path = result.root / "argv.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# protocol


def _protocol_section(workspace: Path, engine: Path) -> dict[str, Any]:
    sessions = workspace / "protocol-sessions"
    actions = [
        lambda rt: rt.pointer("down", 10, 20),
        lambda rt: rt.wait(ms=64),
        lambda rt: rt.pointer("move", 12, 24),
        lambda rt: rt.pointer("up", 12, 24),
        lambda rt: rt.key("press", "enter"),
        lambda rt: rt.key("release", "LV_KEY_ENTER"),
        lambda rt: rt.encoder("turn", -2),
        lambda rt: rt.tick(16),
        lambda rt: rt.wait(ms=32),
        lambda rt: rt.wait(frames=2),
        lambda rt: rt.mark("mark_one"),
        lambda rt: rt.snapshot("direct_shot"),
        lambda rt: play_scenario(
            rt,
            [
                {"type": "click_at", "x": 100, "y": 200, "hold_ms": 48},
                {"type": "drag", "from": [10, 20], "to": [30, 40], "steps": 2},
                {"type": "key", "action": "press", "key": "down"},
                {"type": "encoder", "action": "turn", "diff": 3},
                {"type": "wait", "frames": 1},
                {"type": "mark", "id": "scenario_mark"},
                {"type": "snapshot", "label": "scenario_shot"},
            ],
        ),
        lambda rt: rt.input(
            [
                {
                    "at_ms": 0,
                    "device": "pointer",
                    "action": "down",
                    "x": 5,
                    "y": 6,
                },
                {
                    "at_ms": 16,
                    "device": "key",
                    "action": "press",
                    "key": "esc",
                },
                {
                    "at_ms": 32,
                    "device": "encoder",
                    "action": "turn",
                    "diff": 1,
                },
            ]
        ),
    ]
    reference_run = _capture_run(
        workspace,
        engine,
        sessions,
        "protocol-reference",
        actions=actions,
    )
    commands = _commands(reference_run)
    replies = _replies(reference_run)
    ready = next(
        (reply for reply in replies if reply.get("ready") is True), {}
    )
    seq_values = [
        int(line.split(" ", 1)[0])
        for line in (reference_run.root / "commands.ndjson").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    reply_by_verb: dict[str, dict[str, Any]] = {}
    for reply in replies:
        seq = reply.get("seq")
        if not isinstance(seq, int) or seq <= 0:
            continue
        index = seq - 1
        if 0 <= index < len(commands):
            verb = commands[index].split(" ", 1)[0]
            reply_by_verb.setdefault(verb, reply)

    reference = workspace / "protocol-reference.png"
    reference.write_bytes(_png_bytes(2, 2, (1, 2, 3)))
    options = _capture_run(
        workspace,
        engine,
        sessions,
        "protocol-options",
        record=True,
        live_frame=True,
        record_changed_only=True,
        diff_threshold=12,
        max_frames=42,
        reference=reference,
    )
    engine_args = _normalize_engine_args(_argv(options))

    ready_keys = sorted(ready)
    required_ready: list[str] = []
    optional_ready: list[str] = []
    ready_timeout = 2.0
    for key in ready_keys:
        probe = _capture_run(
            workspace,
            engine,
            sessions,
            f"ready-omit-{key}",
            env={
                ENGINE_READY_OMIT: key,
                ENGINE_EXIT_AFTER_READY: "1",
            },
            timeout=ready_timeout,
        )
        if probe.outcome() == "ok":
            optional_ready.append(key)
        else:
            required_ready.append(key)

    version_probe = _capture_run(
        workspace,
        engine,
        sessions,
        "protocol-version",
        env={
            ENGINE_PROTOCOL: "lvgl-ai-engine-v0",
            ENGINE_EXIT_AFTER_READY: "1",
        },
        timeout=ready_timeout,
    )

    reply_candidates = {
        "pointer": ("hit", "hit_class"),
        "key": ("delivered",),
        "encoder": ("delivered",),
        "snapshot": ("file",),
    }
    reply_actions: dict[str, Callable[[Runtime], Any]] = {
        "pointer": lambda rt: rt.pointer("down", 1, 1),
        "key": lambda rt: rt.key("press", "enter"),
        "encoder": lambda rt: rt.encoder("turn", 1),
        "snapshot": lambda rt: rt.snapshot("probe"),
    }
    required_reply_fields: dict[str, list[str]] = {}
    for verb, fields in reply_candidates.items():
        missing = []
        for field in fields:
            probe = _capture_run(
                workspace,
                engine,
                sessions,
                f"reply-omit-{verb}-{field}",
                actions=[reply_actions[verb]],
                env={ENGINE_REPLY_OMIT: f"{verb}:{field}"},
            )
            if probe.outcome() != "ok":
                missing.append(field)
        required_reply_fields[verb] = missing

    error_probe = _capture_run(
        workspace,
        engine,
        sessions,
        "reply-error",
        actions=[reply_actions["pointer"]],
        env={ENGINE_REPLY_ERROR: "pointer"},
    )
    error_replies = [
        reply for reply in _replies(error_probe) if reply.get("ok") is False
    ]

    return {
        "engine_args": engine_args,
        "commands": commands,
        "seq_starts_at": min(seq_values) if seq_values else None,
        "seq_contiguous": seq_values == list(range(1, len(seq_values) + 1)),
        "ready_seq": ready.get("seq"),
        "ready_protocol": ready.get("protocol"),
        "ready_shape": _shape(ready),
        "reply_shapes": {
            verb: _shape(reply) for verb, reply in sorted(reply_by_verb.items())
        },
        "required_ready_keys": sorted(required_ready),
        "optional_ready_keys": sorted(optional_ready),
        "protocol_versions": {
            "lvgl-ai-engine-v1": True,
            "lvgl-ai-engine-v0": version_probe.outcome() == "ok",
        },
        "required_reply_fields": required_reply_fields,
        "error_reply_shape": _shape(error_replies[0]) if error_replies else None,
        "error_reply_outcome": error_probe.outcome(),
    }


def _normalize_engine_args(args: list[str]) -> list[str]:
    normalized: list[str] = []
    replacements = {"--session": "<session>", "--reference": "<reference>"}
    index = 0
    while index < len(args):
        value = args[index]
        normalized.append(value)
        if value in replacements and index + 1 < len(args):
            normalized.append(replacements[value])
            index += 2
            continue
        index += 1
    return normalized


# ---------------------------------------------------------------------------
# session


def _write_annotations(session_dir: Path) -> None:
    document = {
        "schema": "lvgl-ai-annotations-v1",
        "notes": [
            {
                "id": "static-note",
                "frame_no": 2,
                "t_ms": 16,
                "regions": [],
                "tags": ["layout"],
                "text": "static annotation",
            }
        ],
    }
    (session_dir / "annotations.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )


def _session_section(
    workspace: Path, engine: Path
) -> tuple[dict[str, Any], Path | None]:
    sessions = workspace / "session-sessions"

    # A plain recording: only the files the engine and Runtime normally write.
    plain = _capture_run(
        workspace,
        engine,
        sessions,
        "session-plain",
        record=True,
        live_frame=True,
    )
    plain_dir = plain.runtime.session_dir
    if plain_dir is None:
        raise RuntimeError("the scripted engine did not create a session")

    # A complete session: reference diffs, an annotation document and a
    # snapshot exercise every optional artifact the manifest can list.
    reference = workspace / "session-reference.png"
    reference.write_bytes(_png_bytes(2, 2, (1, 2, 3)))
    live_state: dict[str, bool] = {}

    def prepare_complete(rt: Runtime) -> None:
        _write_annotations(rt.session_dir)
        live_state["live_present"] = (rt.session_dir / "live.rgba").is_file()

    recorded = _capture_run(
        workspace,
        engine,
        sessions,
        "session-complete",
        actions=[lambda rt: rt.snapshot("static")],
        prepare=prepare_complete,
        record=True,
        live_frame=True,
        reference=reference,
    )
    session_dir = recorded.runtime.session_dir
    if session_dir is None:
        raise RuntimeError("the scripted engine did not create a session")
    live_present = live_state.get("live_present", False)
    live_removed = not (session_dir / "live.rgba").exists()

    record_false_state: dict[str, bool] = {}
    record_false = _capture_run(
        workspace,
        engine,
        sessions,
        "session-record-false",
        prepare=lambda rt: record_false_state.update(
            live_present=(rt.session_dir / "live.rgba").is_file()
        ),
        record=False,
        live_frame=True,
    )
    record_false_dir = record_false.runtime.session_dir
    if record_false_dir is None:
        raise RuntimeError("the scripted engine did not create a session")
    record_false_live_present = record_false_state.get("live_present", False)
    record_false_live_removed = not (
        record_false_dir / "live.rgba"
    ).exists()

    file_set = _relative_files(session_dir)
    manifest = json.loads(
        (session_dir / "manifest.json").read_text(encoding="utf-8")
    )
    recording = Recording.open(session_dir)
    timeline = recording.timeline()
    timeline_shapes: dict[str, Any] = {}
    for row in timeline:
        timeline_shapes.setdefault(str(row.get("type")), _shape(row))
    frame_diffs = recording.frame_diffs()
    reference_diffs = recording.reference_diffs() or []
    annotations = recording.annotations

    required_files: list[str] = []
    optional_files: list[str] = []
    for relative in file_set:
        probe = workspace / "file-probe"
        if probe.exists():
            shutil.rmtree(probe)
        shutil.copytree(session_dir, probe)
        (probe / relative).unlink()
        try:
            Recording.open(probe)
        except Exception:  # noqa: BLE001 - any failure means required
            required_files.append(relative)
        else:
            optional_files.append(relative)

    required_fields: list[str] = []
    optional_fields: list[str] = []
    manifest_probe = workspace / "manifest-probe"
    for field in sorted(manifest):
        if manifest_probe.exists():
            shutil.rmtree(manifest_probe)
        shutil.copytree(session_dir, manifest_probe)
        path = manifest_probe / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop(field, None)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        try:
            Recording.open(manifest_probe)
        except Exception:  # noqa: BLE001
            required_fields.append(field)
        else:
            optional_fields.append(field)

    status_probe = workspace / "status-probe"
    accepted_statuses: list[str] = []
    rejected_statuses: list[str] = []
    for status in (
        "ok",
        "build_error",
        "link_error",
        "crash",
        "harness_error",
        "pass",
        "fail",
        "unverified",
    ):
        if status_probe.exists():
            shutil.rmtree(status_probe)
        shutil.copytree(session_dir, status_probe)
        path = status_probe / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = status
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        try:
            Recording.open(status_probe)
        except Exception:  # noqa: BLE001
            rejected_statuses.append(status)
        else:
            accepted_statuses.append(status)

    type_probe = workspace / "type-probe"
    timeline_types: dict[str, bool] = {}
    for row_type in ("frame", "input", "wait", "mark", "snapshot", "end", "other"):
        if type_probe.exists():
            shutil.rmtree(type_probe)
        shutil.copytree(session_dir, type_probe)
        (type_probe / "timeline.ndjson").write_text(
            json.dumps(
                {"schema": "lvgl-ai-timeline-v1", "type": row_type}
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            recording_probe = Recording.open(type_probe)
            recording_probe.timeline()
        except Exception:  # noqa: BLE001
            timeline_types[row_type] = False
        else:
            timeline_types[row_type] = True

    return {
        "plain_files": _relative_files(plain_dir),
        "complete_files": file_set,
        "record_false_files": _relative_files(record_false_dir),
        "manifest_shape": _shape(manifest),
        "manifest_values": {
            "schema": manifest["schema"],
            "status": manifest["status"],
            "app": manifest["app"],
            "display": manifest["display"],
            "record_changed_only": manifest["record_changed_only"],
            "mode": manifest["mode"],
            "input": manifest["input"],
            "build": manifest["build"],
            "adapter": manifest["adapter"],
            "frame_count": manifest["frame_count"],
            "truncated": manifest["truncated"],
            "log_truncated": manifest["log_truncated"],
            "error": manifest["error"],
        },
        "plain_artifacts": json.loads(
            (plain_dir / "manifest.json").read_text(encoding="utf-8")
        )["artifacts"],
        "complete_artifacts": manifest["artifacts"],
        "record_false_artifacts": json.loads(
            (record_false_dir / "manifest.json").read_text(encoding="utf-8")
        )["artifacts"],
        "required_files": sorted(required_files),
        "optional_files": sorted(optional_files),
        "required_manifest_fields": sorted(required_fields),
        "optional_manifest_fields": sorted(optional_fields),
        "accepted_statuses": accepted_statuses,
        "rejected_statuses": rejected_statuses,
        "timeline_types": timeline_types,
        "timeline_row_shapes": timeline_shapes,
        "frame_diffs_shape": _shape(frame_diffs[0]) if frame_diffs else None,
        "reference_diffs_shape": (
            _shape(reference_diffs[0]) if reference_diffs else None
        ),
        "annotations_shape": _shape(annotations),
        "note_shape": _shape(annotations["notes"][0])
        if annotations.get("notes")
        else None,
        "live_rgba": {
            "present_while_recording": live_present,
            "removed_after_stop": live_removed,
            "present_while_record_false": record_false_live_present,
            "removed_after_stop_record_false": record_false_live_removed,
        },
    }, session_dir


def _relative_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def _png_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        for _ in range(width):
            raw.extend(rgb)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes((8, 2, 0, 0, 0))
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# HTTP fixture


def _write_repo(root: Path) -> None:
    (root / "user" / "app" / "coffee").mkdir(parents=True)
    (root / "user" / "app" / "alpha").mkdir()
    (root / "user" / "scenarios").mkdir()
    (root / "user" / "app" / "coffee" / "coffee.c").write_text(
        "/* coffee */\n", encoding="utf-8"
    )
    (root / "user" / "app" / "alpha" / "alpha.c").write_text(
        "/* alpha */\n", encoding="utf-8"
    )
    (root / "user" / "app" / "app.c").write_text(
        """#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
#include "coffee/coffee.h"
#include "alpha/alpha.h"
#endif

typedef void (* app_create_fn)(lv_obj_t * screen);
typedef struct {
    const char * name;
    app_create_fn create;
} app_entry_t;

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
static const app_entry_t apps[] = {
    {"coffee", coffee_create},
    {"alpha", alpha_create},
};
#endif

void app_create(void) {}
""",
        encoding="utf-8",
    )
    for name in ("coffee", "alpha"):
        (root / "user" / "scenarios" / f"{name}.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-scenario-v1",
                    "name": name,
                    "app": name,
                    "steps": [{"type": "wait", "ms": 16}],
                }
            ),
            encoding="utf-8",
        )


def _write_http_session(root: Path) -> Path:
    session = root / FIXTURE_SESSION_ID
    frames = session / "frames"
    frames.mkdir(parents=True)
    _png_rgb(frames / "000001.png", (255, 0, 0))
    _png_rgb(frames / "000002.png", (0, 255, 0))
    snapshots = session / "snapshots"
    snapshots.mkdir()
    _png_rgb(snapshots / "001_after.png", (9, 9, 9))
    regions = session / "regions"
    regions.mkdir()
    _png_rgb(regions / "001_region.png", (7, 7, 7))
    timeline = [
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 1,
            "t_ms": 0,
            "file": "frames/000001.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 2,
            "t_ms": 16,
            "file": "frames/000002.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "input",
            "seq": 1,
            "frame_no": 2,
            "t_ms": 16,
            "device": "pointer",
            "action": "down",
            "x": 10,
            "y": 20,
            "hit": "snap_button",
            "hit_class": "lv_button",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "wait",
            "frame_start": 1,
            "frame_end": 2,
            "t_ms_start": 0,
            "t_ms_end": 16,
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "mark",
            "frame_no": 2,
            "t_ms": 16,
            "id": "static_mark",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "snapshot",
            "frame_no": 2,
            "t_ms": 16,
            "label": "after",
            "file": "snapshots/001_after.png",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "end",
            "frame_count": 2,
            "t_ms": 16,
            "truncated": False,
        },
    ]
    (session / "timeline.ndjson").write_text(
        "".join(json.dumps(row) + "\n" for row in timeline),
        encoding="utf-8",
    )
    (session / "frame_diffs.ndjson").write_text(
        json.dumps(
            {
                "schema": "lvgl-ai-frame-diffs-v1",
                "frame_no": 2,
                "prev_frame_no": 1,
                "t_ms": 16,
                "width": 2,
                "height": 2,
                "threshold": 10,
                "bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
                "changed_px": 1,
                "changed_ratio": 0.25,
                "max_delta": 0.2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (session / "reference_diffs.ndjson").write_text(
        json.dumps(
            {
                "schema": "lvgl-ai-frame-diffs-v1",
                "frame_no": 1,
                "prev_frame_no": None,
                "t_ms": 0,
                "width": 2,
                "height": 2,
                "threshold": 10,
                "bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
                "changed_px": 1,
                "changed_ratio": 0.25,
                "max_delta": 0.1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (session / "annotations.json").write_text(
        json.dumps(
            {
                "schema": "lvgl-ai-annotations-v1",
                "notes": [
                    {
                        "id": "seed-note",
                        "frame_no": 1,
                        "t_ms": 0,
                        "regions": [
                            {
                                "x": 0,
                                "y": 0,
                                "w": 1,
                                "h": 1,
                                "image": "regions/001_region.png",
                            }
                        ],
                        "tags": ["seed"],
                        "text": "existing note",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (session / "engine.log").write_text(
        "[app] app_create\n", encoding="utf-8"
    )
    (session / "build.log").write_text("# phase: build\n", encoding="utf-8")
    manifest = {
        "schema": "lvgl-ai-session-v1",
        "id": FIXTURE_SESSION_ID,
        "status": "ok",
        "app": FIXTURE_APP,
        "record_changed_only": False,
        "mode": "headless",
        "input": ["real", "virtual"],
        "build": {"status": "ok", "log": "build.log"},
        "lvgl": "9.6.0",
        "lvgl_src": "lvgl-src/9.6",
        "adapter": "9x",
        "tool_version": "0.1.0",
        "frame_count": 2,
        "truncated": False,
        "log_truncated": False,
        "checks": [],
        "error": None,
        "artifacts": {
            "manifest": "manifest.json",
            "build_log": "build.log",
            "engine_log": "engine.log",
            "timeline": "timeline.ndjson",
            "frame_diffs": "frame_diffs.ndjson",
            "reference_diffs": "reference_diffs.ndjson",
            "annotations": "annotations.json",
            "frames": ["frames/000001.png", "frames/000002.png"],
            "snapshots": ["snapshots/001_after.png"],
        },
    }
    (session / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return session


def _png_rgb(path: Path, rgb: tuple[int, int, int]) -> None:
    path.write_bytes(_png_bytes(2, 2, rgb))


class _LiveStub:
    """Minimal Runtime surface for the live HTTP endpoints."""

    def __init__(self, session_dir: Path) -> None:
        self.is_running = False
        self.pid: int | None = None
        self.mode = "headless"
        self.app: str | None = None
        self.session_id = "stub-session"
        self.session_dir = session_dir
        self.manifest_path = None
        self.engine_log_path = None
        self.ready = {
            "display": {"width": 2, "height": 2, "format": "XRGB8888"},
            "mode": "headless",
            "inputs": ["real", "virtual"],
            "capabilities": ["pointer", "key", "encoder", "tick", "wait",
                             "snapshot", "mark"],
            "frames": 1,
        }
        self.frame_count = 1
        self.t_ms = 16
        self.exit_code: int | None = None

    def start(self) -> _LiveStub:
        self.is_running = True
        self.pid = 4242
        return self

    def stop(self) -> None:
        self.is_running = False
        self.pid = None

    def tick(self, ms: int, *, track_check: bool = True) -> dict[str, Any]:
        self.t_ms += int(ms)
        return {"protocol": "lvgl-ai-engine-v1", "seq": 1, "ok": True}

    def pointer(self, action: str, x: int, y: int) -> dict[str, Any]:
        return {
            "protocol": "lvgl-ai-engine-v1",
            "seq": 1,
            "ok": True,
            "hit": "stub_button",
            "hit_class": "lv_button",
        }

    def key(self, action: str, key: str) -> dict[str, Any]:
        return {
            "protocol": "lvgl-ai-engine-v1",
            "seq": 1,
            "ok": True,
            "delivered": True,
            "key": key,
        }

    def wait(self, ms: int | None = None, *, frames: int | None = None):
        return {"protocol": "lvgl-ai-engine-v1", "seq": 1, "ok": True}

    def record_error(self, error: BaseException) -> None:
        pass

    def log_tail(self, n: int = 40) -> list[str]:
        return []


def _http_request(
    base: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    raw: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, str], bytes]:
    data = raw
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, dict(exc.headers), exc.read()
        finally:
            exc.close()


def _template_path(path: str) -> str:
    return path.replace(FIXTURE_SESSION_ID, "<session>")


def _error_code(payload: Any) -> str | None:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"]
    return None


def _http_section(workspace: Path) -> dict[str, Any]:
    from lvgl_ai.web import create_server

    root = workspace / "http-repo"
    _write_repo(root)
    sessions = workspace / "http-sessions"
    _write_http_session(sessions)
    stub_session = workspace / "http-live"
    stub_session.mkdir()
    (stub_session / "live.rgba").write_bytes(b"\x00" * 16)

    server = create_server(
        sessions_root=sessions,
        scenarios_dir=root / "user" / "scenarios",
        repo_root=root,
        runtime_factory=lambda: _LiveStub(stub_session),
        lvgl="9.6",
        build=False,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(
        target=server.serve_forever, name="contract-snapshot-web", daemon=True
    )
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    probes: list[dict[str, Any]] = []

    def probe(
        name: str,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        status, response_headers, body = _http_request(
            base, method, path, payload=payload, raw=raw, headers=headers
        )
        content_type = response_headers.get("Content-Type")
        entry: dict[str, Any] = {
            "name": name,
            "method": method,
            "path": _template_path(path),
            "status": status,
            "content_type": content_type,
        }
        media_type = (content_type or "").split(";", 1)[0].strip().lower()
        if media_type == "application/json" and body:
            parsed = json.loads(body.decode("utf-8"))
            entry["json_shape"] = _shape(parsed)
            code = _error_code(parsed)
            if code is not None:
                entry["error_code"] = code
        probes.append(entry)
        return json.loads(body.decode("utf-8")) if media_type == "application/json" else {}

    mutation_headers = {
        "Content-Type": "application/json",
        REQUEST_HEADER: "1",
    }
    session_path = f"/api/sessions/{FIXTURE_SESSION_ID}"

    try:
        probe("live_idle", "GET", "/api/live")
        probe("live_stream_idle", "GET", "/api/live/stream")
        probe("live_stop_idle", "POST", "/api/live/stop")
        probe(
            "live_start_invalid_mode",
            "POST",
            "/api/live/start?mode=bogus",
        )
        probe("sessions", "GET", "/api/sessions")
        probe("page_root", "GET", "/")
        probe("page_session", "GET", f"/?session={FIXTURE_SESSION_ID}")
        probe("page_missing_session", "GET", "/?session=missing-session")
        probe("page_invalid_app", "GET", "/?app=bad%20app")
        probe("session", "GET", session_path)
        probe("session_timeline", "GET", f"{session_path}/timeline")
        probe("session_diffs", "GET", f"{session_path}/diffs")
        probe("session_log", "GET", f"{session_path}/log")
        probe("session_annotations", "GET", f"{session_path}/annotations")
        probe("session_missing", "GET", "/api/sessions/missing-session")
        probe("session_unknown_sub", "GET", f"{session_path}/bogus")
        probe("frame", "GET", f"/frames/{FIXTURE_SESSION_ID}/000001.png")
        probe(
            "frame_missing",
            "GET",
            f"/frames/{FIXTURE_SESSION_ID}/missing.png",
        )
        probe(
            "snapshot",
            "GET",
            f"/snapshots/{FIXTURE_SESSION_ID}/001_after.png",
        )
        probe(
            "region",
            "GET",
            f"/regions/{FIXTURE_SESSION_ID}/001_region.png",
        )
        note = {
            "id": "note-1",
            "frame_no": 1,
            "t_ms": 0,
            "regions": [{"x": 0, "y": 0, "w": 1, "h": 1}],
            "tags": ["layout"],
            "text": "snapshot note",
        }
        probe(
            "annotation_create",
            "POST",
            f"{session_path}/annotations",
            payload=note,
        )
        probe(
            "annotation_duplicate",
            "POST",
            f"{session_path}/annotations",
            payload=note,
        )
        probe(
            "annotation_invalid",
            "POST",
            f"{session_path}/annotations",
            payload={"id": "broken"},
        )
        probe(
            "annotation_invalid_json",
            "POST",
            f"{session_path}/annotations",
            raw=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        probe("annotations_after", "GET", f"{session_path}/annotations")
        # Wrong-method probes: every route's allowed method is recorded by a
        # successful call above; these freeze the 405/501 response instead.
        probe("method_post_live", "POST", "/api/live")
        probe("method_get_start", "GET", "/api/live/start")
        probe("method_post_stream", "POST", "/api/live/stream")
        probe("method_post_sessions", "POST", "/api/sessions")
        probe("method_get_page_close", "GET", "/api/page/close")
        probe("method_get_apps_create", "GET", "/api/apps/create")
        probe("method_post_apps_tree", "POST", "/api/apps/tree")
        probe("method_get_apps_delete", "GET", "/api/apps/delete")
        probe("method_get_restore", "GET", "/api/apps/trash/restore")
        probe("method_get_purge", "GET", "/api/apps/trash/delete")
        probe("method_post_timeline", "POST", f"{session_path}/timeline")
        probe("method_post_diffs", "POST", f"{session_path}/diffs")
        probe("method_post_log", "POST", f"{session_path}/log")
        probe(
            "method_post_frame",
            "POST",
            f"/frames/{FIXTURE_SESSION_ID}/000001.png",
        )
        probe(
            "method_post_snapshot",
            "POST",
            f"/snapshots/{FIXTURE_SESSION_ID}/001_after.png",
        )
        probe(
            "method_post_region",
            "POST",
            f"/regions/{FIXTURE_SESSION_ID}/001_region.png",
        )
        probe("method_post_root", "POST", "/")
        probe("method_put", "PUT", "/api/apps")
        probe("method_delete", "DELETE", "/api/apps")
        probe("apps_list", "GET", "/api/apps")
        probe("apps_tree", "GET", "/api/apps/tree?name=alpha")
        probe(
            "app_create",
            "POST",
            "/api/apps/create",
            payload={"name": "gamma"},
            headers=mutation_headers,
        )
        probe(
            "app_create_exists",
            "POST",
            "/api/apps/create",
            payload={"name": "gamma"},
            headers=mutation_headers,
        )
        probe(
            "app_create_no_header",
            "POST",
            "/api/apps/create",
            payload={"name": "delta"},
        )
        probe(
            "app_create_wrong_media",
            "POST",
            "/api/apps/create",
            raw=b'{"name":"delta"}',
            headers={"Content-Type": "text/plain", REQUEST_HEADER: "1"},
        )
        probe(
            "app_create_reserved",
            "POST",
            "/api/apps/create",
            payload={"name": "coffee"},
            headers=mutation_headers,
        )
        probe(
            "app_delete_protected",
            "POST",
            "/api/apps/delete",
            payload={"name": "coffee"},
            headers=mutation_headers,
        )
        deleted = probe(
            "app_delete",
            "POST",
            "/api/apps/delete",
            payload={"name": "alpha"},
            headers=mutation_headers,
        )
        trash_id = deleted.get("trash_id")
        trash_root = root / "user" / ".trash" / "apps"
        trash_dirs = sorted(
            (path for path in trash_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
        trash_meta = None
        trash_layout: list[str] = []
        if trash_dirs:
            trash_dir = trash_dirs[-1]
            trash_layout = sorted(
                path.relative_to(trash_dir).as_posix()
                for path in trash_dir.rglob("*")
            )
            meta_path = trash_dir / "meta.json"
            if meta_path.is_file():
                trash_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(trash_id, str):
            raise RuntimeError("app delete did not return a trash id")
        probe(
            "app_restore",
            "POST",
            "/api/apps/trash/restore",
            payload={"trash_id": trash_id},
            headers=mutation_headers,
        )
        deleted_again = probe(
            "app_delete_again",
            "POST",
            "/api/apps/delete",
            payload={"name": "alpha"},
            headers=mutation_headers,
        )
        second_trash_id = deleted_again.get("trash_id")
        if not isinstance(second_trash_id, str):
            raise RuntimeError("app delete did not return a trash id")
        probe(
            "app_purge",
            "POST",
            "/api/apps/trash/delete",
            payload={"trash_id": second_trash_id, "confirm": True},
            headers=mutation_headers,
        )
        probe(
            "app_purge_unconfirmed",
            "POST",
            "/api/apps/trash/delete",
            payload={"trash_id": second_trash_id},
            headers=mutation_headers,
        )
        probe("apps_list_after", "GET", "/api/apps")

        probe("live_start", "POST", "/api/live/start?mode=test")
        probe("live_running", "GET", "/api/live")
        probe("live_start_conflict", "POST", "/api/live/start")
        probe(
            "live_pointer",
            "POST",
            "/api/live/pointer",
            payload={"action": "down", "x": 1, "y": 2},
        )
        probe(
            "live_pointer_invalid",
            "POST",
            "/api/live/pointer",
            payload={"action": "tap", "x": 1, "y": 2},
        )
        probe(
            "live_key",
            "POST",
            "/api/live/key",
            payload={"action": "press", "key": "ENTER"},
        )
        probe(
            "live_key_invalid",
            "POST",
            "/api/live/key",
            payload={"action": "press", "key": ""},
        )
        stream = _stream_probe(host, port)
        probes.append(stream)
        probe("live_stop", "POST", "/api/live/stop")
        probe("live_stop_again", "POST", "/api/live/stop")
        probe(
            "page_open",
            "POST",
            "/api/page/open",
            payload={"id": "page-1"},
        )
        probe(
            "page_close",
            "POST",
            "/api/page/close",
            payload={"id": "page-1"},
        )
        probe(
            "page_open_invalid",
            "POST",
            "/api/page/open",
            payload={"id": "bad id"},
        )
        probe("unknown_path", "GET", "/api/nope")
    finally:
        server.shutdown()
        server.app.shutdown()
        server.server_close()
        thread.join(timeout=10)

    return {
        "probes": probes,
        "trash_meta_shape": _shape(trash_meta) if trash_meta else None,
        "trash_meta_schema": (
            trash_meta.get("schema") if isinstance(trash_meta, dict) else None
        ),
        "trash_layout": trash_layout,
    }


def _stream_probe(host: str, port: int) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": "live_stream",
        "method": "GET",
        "path": "/api/live/stream",
        "status": None,
        "content_type": None,
    }
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        connection.request("GET", "/api/live/stream")
        response = connection.getresponse()
        headers = dict(response.getheaders())
        entry["status"] = response.status
        entry["content_type"] = headers.get("Content-Type")
        entry["cache_control"] = headers.get("Cache-Control")
        data = response.read(20)
    finally:
        connection.close()
    if len(data) >= 20:
        magic, width, height, frame_no, t_ms = struct.unpack(
            "<4sIIII", data[:20]
        )
        entry["magic"] = magic.decode("ascii", "replace")
        entry["header_size"] = 20
        entry["header_fields"] = [
            "magic",
            "width",
            "height",
            "frame_no",
            "t_ms",
        ]
        entry["width"] = width
        entry["height"] = height
        entry["frame_no"] = frame_no
        entry["t_ms"] = t_ms
        entry["pixel_bytes"] = width * height * 4
    else:
        entry["magic"] = data[:4].decode("ascii", "replace")
        entry["header_size"] = len(data)
    return entry


# ---------------------------------------------------------------------------
# CLI


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _default_repr(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return "Path"
    if callable(value):
        return getattr(value, "__name__", repr(value))
    return re.sub(r"0x[0-9a-fA-F]+", "0x...", repr(value))


def _parser_contract(parser: argparse.ArgumentParser) -> dict[str, Any]:
    actions = []
    for action in parser._actions:
        actions.append(
            {
                "option_strings": list(action.option_strings),
                "dest": action.dest,
                "required": bool(action.required),
                "nargs": action.nargs,
                "default": _default_repr(action.default),
                "type": (
                    getattr(action.type, "__name__", repr(action.type))
                    if action.type is not None
                    else None
                ),
                "choices": (
                    list(action.choices) if action.choices is not None else None
                ),
                "action": type(action).__name__,
                "help": action.help,
            }
        )
    groups = []
    for group in parser._mutually_exclusive_groups:
        groups.append(
            {
                "required": bool(group.required),
                "options": [
                    option
                    for action in group._group_actions
                    for option in action.option_strings
                ],
            }
        )
    return {
        "prog": parser.prog,
        "description": parser.description,
        "actions": actions,
        "mutually_exclusive": groups,
    }


def _run_python(
    script: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    # ``-I`` ignores PYTHONIOENCODING; ``-X utf8`` keeps piped help/JSON output
    # decodable on non-UTF-8 Windows consoles.  COLUMNS fixes argparse wrapping.
    environment["COLUMNS"] = "80"
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-I", str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        cwd=str(paths.REPO_ROOT),
        timeout=timeout,
    )


def _help_contract(script: Path) -> dict[str, Any]:
    result = _run_python(script, ["--help"])
    text = re.sub(r"\s+", " ", result.stdout).strip()
    # Python 3.9 prints "optional arguments:"; 3.10+ prints "options:".
    text = re.sub(r"\b(?:optional arguments|options):", "arguments:", text)
    return {"exit": result.returncode, "text": text}


def _json_contract(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    payload = json.loads(lines[0]) if len(lines) == 1 else None
    return {
        "exit": result.returncode,
        "stdout_lines": len(lines),
        "json_shape": _shape(payload) if payload is not None else None,
        "keys": sorted(payload) if isinstance(payload, dict) else None,
        "error_code": _error_code(payload),
    }


def _cli_section(workspace: Path) -> dict[str, Any]:
    cli_module = _load_module("contract_snapshot_cli", TOOL_ROOT / "cli.py")
    web_module = _load_module("contract_snapshot_web", TOOL_ROOT / "web.py")
    new_app_module = _load_module(
        "contract_snapshot_new_app", TOOL_ROOT / "tools" / "new_app.py"
    )

    class _FakeRuntime:
        def __init__(self, **kwargs: Any) -> None:
            self.session_id = "stub-session"
            self.session_dir = None
            self.manifest_path = None
            self.app = kwargs.get("app")

        def start(self) -> _FakeRuntime:
            return self

        def stop(self) -> None:
            pass

    output = io.StringIO()
    original_runtime = cli_module.Runtime
    try:
        cli_module.Runtime = _FakeRuntime
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(
            io.StringIO()
        ):
            exit_code = cli_module.main(["--json"])
    finally:
        cli_module.Runtime = original_runtime
    lines = output.getvalue().splitlines()
    payload = json.loads(lines[0]) if len(lines) == 1 else None

    sessions_root = workspace / "cli-sessions"
    missing_lvgl = workspace / "missing-lvgl-src"
    build_error = _run_python(
        TOOL_ROOT / "cli.py",
        ["--json", "--lvgl", "9.6"],
        env={
            "LVGL_AI_SESSIONS_ROOT": str(sessions_root),
            "LVGL_AI_LVGL_SRC": str(missing_lvgl),
        },
    )
    build_payload = (
        json.loads(build_error.stdout.splitlines()[0])
        if len(build_error.stdout.splitlines()) == 1
        else None
    )

    repo = workspace / "cli-repo"
    _write_repo(repo)
    new_app = _run_python(
        TOOL_ROOT / "tools" / "new_app.py",
        [
            "hello",
            "--dry-run",
            "--json",
            "--repo-root",
            str(repo),
        ],
    )
    new_app_error = _run_python(
        TOOL_ROOT / "tools" / "new_app.py",
        ["Bad-Name", "--repo-root", str(repo)],
    )

    return {
        "cli": {
            "parser": _parser_contract(cli_module.build_parser()),
            "help": _help_contract(TOOL_ROOT / "cli.py"),
            "invalid_exit": _run_python(
                TOOL_ROOT / "cli.py", ["--definitely-not-an-option"]
            ).returncode,
            "json_success": {
                "exit": exit_code,
                "stdout_lines": len(lines),
                "keys": sorted(payload) if isinstance(payload, dict) else None,
                "json_shape": _shape(payload) if payload is not None else None,
                "error": payload.get("error") if isinstance(payload, dict) else None,
            },
            "json_build_error": {
                "exit": build_error.returncode,
                "stdout_lines": len(build_error.stdout.splitlines()),
                "keys": (
                    sorted(build_payload)
                    if isinstance(build_payload, dict)
                    else None
                ),
                "error_code": _error_code(build_payload),
                "session_id_present": bool(
                    build_payload.get("session_id")
                    if isinstance(build_payload, dict)
                    else None
                ),
                "manifest_path_present": bool(
                    build_payload.get("manifest_path")
                    if isinstance(build_payload, dict)
                    else None
                ),
            },
        },
        "web": {
            "parser": _parser_contract(web_module.build_parser()),
            "help": _help_contract(TOOL_ROOT / "web.py"),
            "invalid_exit": _run_python(
                TOOL_ROOT / "web.py", ["--definitely-not-an-option"]
            ).returncode,
        },
        "new_app": {
            "parser": _parser_contract(new_app_module.build_parser()),
            "help": _help_contract(TOOL_ROOT / "tools" / "new_app.py"),
            "invalid_exit": _run_python(
                TOOL_ROOT / "tools" / "new_app.py", ["--definitely-not-an-option"]
            ).returncode,
            "json_success": _json_contract(new_app),
            "error_exit": new_app_error.returncode,
            "error_stdout_empty": new_app_error.stdout == "",
        },
    }


# ---------------------------------------------------------------------------
# page


class _DomParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.tags: Counter[str] = Counter()
        self.ids: list[str] = []
        self.classes: set[str] = set()
        self.attributes: set[str] = set()
        self.labels: set[str] = set()
        self.texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] += 1
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        for class_name in (values.get("class") or "").split():
            self.classes.add(f"{tag}.{class_name}")
        for key, value in attrs:
            self.attributes.add(f"{tag}@{key}")
            if key in ("aria-label", "title", "placeholder", "alt") and value:
                self.labels.add(f"{key}={value}")
        if tag in ("script", "style"):
            self.skip += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.texts.append(text)


def _dom_contract(
    markup: str, *, redactions: Iterable[str] = ()
) -> dict[str, Any]:
    for value in redactions:
        markup = markup.replace(value, "<workspace>")
    parser = _DomParser()
    parser.feed(markup)
    parser.close()
    endpoints = sorted(
        set(
            re.findall(
                r"/(?:api|frames|snapshots|regions)/[A-Za-z0-9_./$%{}:+~-]*",
                markup,
            )
        )
    )
    return {
        "ids": sorted(parser.ids),
        "classes": sorted(parser.classes),
        "tag_counts": {tag: parser.tags[tag] for tag in sorted(parser.tags)},
        "attributes": sorted(parser.attributes),
        "labels": sorted(parser.labels),
        "texts": parser.texts,
        "endpoints": endpoints,
    }


@contextlib.contextmanager
def _page_server(
    sessions_root: Path, repo_root: Path
) -> Iterable[str]:
    from lvgl_ai.web import create_server

    server = create_server(
        sessions_root=sessions_root,
        scenarios_dir=repo_root / "user" / "scenarios",
        repo_root=repo_root,
        lvgl="9.6",
        build=False,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(
        target=server.serve_forever, name="contract-snapshot-page", daemon=True
    )
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.app.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _page_section(workspace: Path) -> dict[str, Any]:
    """Render the page through the real HTTP route, not internal modules.

    The three variants are produced from real fixture sessions, so the page
    contract survives template/module refactors as long as the rendered DOM
    stays the same.
    """
    repo = workspace / "page-repo"
    _write_repo(repo)
    sessions = workspace / "page-sessions"
    _write_http_session(sessions)
    broken = sessions / "broken-session"
    broken.mkdir()
    (broken / "manifest.json").write_text(
        '{"schema": "not-a-session"}\n', encoding="utf-8"
    )
    (broken / "engine.log").write_text("", encoding="utf-8")
    empty_sessions = workspace / "page-sessions-empty"
    empty_sessions.mkdir()

    def fetch(base: str, path: str) -> tuple[int, str]:
        status, _headers, body = _http_request(base, "GET", path)
        return status, body.decode("utf-8")

    with _page_server(sessions, repo) as base:
        replay_status, replay_html = fetch(
            base, f"/?session={FIXTURE_SESSION_ID}"
        )
        error_status, error_html = fetch(base, "/?session=broken-session")
    with _page_server(empty_sessions, repo) as base:
        empty_status, empty_html = fetch(base, "/")

    redactions = [str(workspace)]
    return {
        "replay": _dom_contract(replay_html, redactions=redactions),
        "error": _dom_contract(error_html, redactions=redactions),
        "empty": _dom_contract(empty_html, redactions=redactions),
        "statuses": {
            "replay": replay_status,
            "error": error_status,
            "empty": empty_status,
        },
    }


# ---------------------------------------------------------------------------
# Python interface


def _signature(fn: Any) -> list[dict[str, Any]] | None:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    parameters = []
    for parameter in signature.parameters.values():
        if parameter.name in ("self", "cls"):
            continue
        item: dict[str, Any] = {
            "name": parameter.name,
            "kind": parameter.kind.name,
        }
        if parameter.default is not inspect.Parameter.empty:
            item["default"] = _default_repr(parameter.default)
        parameters.append(item)
    return parameters


def _project_member_names(cls: type) -> list[str]:
    """Public members declared by the class or its project base classes.

    Inherited ``Exception``/``object`` helpers differ between Python versions
    (for example ``add_note``), so they are deliberately excluded.
    """
    names: set[str] = set()
    for base in cls.__mro__:
        module = getattr(base, "__module__", "") or ""
        if not module.startswith("lvgl_ai"):
            continue
        for name in base.__dict__:
            if name == "__init__":
                continue
            if name.startswith("_") and name not in ("__enter__", "__exit__"):
                continue
            names.add(name)
    return sorted(names)


def _member_contract(obj: Any) -> dict[str, Any]:
    if inspect.isclass(obj):
        members: dict[str, Any] = {}
        for name in _project_member_names(obj):
            static_member = inspect.getattr_static(obj, name)
            if isinstance(static_member, property):
                members[name] = "property"
            elif callable(static_member) or isinstance(
                static_member, (classmethod, staticmethod)
            ):
                members[name] = {"signature": _signature(getattr(obj, name))}
        return {
            "kind": "class",
            "signature": _signature(obj),
            "members": members,
        }
    if inspect.isfunction(obj) or inspect.ismethod(obj):
        return {"kind": "function", "signature": _signature(obj)}
    return {"kind": type(obj).__name__}


def _python_section() -> dict[str, Any]:
    import lvgl_ai
    import lvgl_ai.apps as apps_module

    exports = sorted(getattr(lvgl_ai, "__all__", []))
    members = {
        name: _member_contract(getattr(lvgl_ai, name)) for name in exports
    }
    error_classes = {
        name: getattr(lvgl_ai, name)
        for name in exports
        if inspect.isclass(getattr(lvgl_ai, name, None))
        and issubclass(getattr(lvgl_ai, name), BaseException)
    }
    error_hierarchy = {
        name: sorted(
            base_name
            for base_name, base in error_classes.items()
            if base_name != name and issubclass(cls, base)
        )
        for name, cls in error_classes.items()
    }
    apps_members: dict[str, Any] = {}
    for name in sorted(dir(apps_module)):
        if name.startswith("_"):
            continue
        obj = getattr(apps_module, name)
        module = getattr(obj, "__module__", "") or ""
        if module != "lvgl_ai.apps" and not module.startswith("lvgl_ai.apps."):
            continue
        if inspect.isfunction(obj) or inspect.isclass(obj):
            apps_members[name] = _member_contract(obj)
    return {
        "lvgl_ai": {
            "exports": exports,
            "members": members,
            "error_hierarchy": error_hierarchy,
        },
        "apps": apps_members,
    }


# ---------------------------------------------------------------------------
# entry points


def record_snapshot() -> dict[str, Any]:
    """Record the six contract sections into a fresh temporary workspace.

    Ready/reply omission probes intentionally make ``Runtime.start()`` fail on
    validated fields.  Those paths leave the pre-existing engine pipes to the
    garbage collector, so ResourceWarning is silenced while recording; it is
    noise from the probe design, not part of the contract.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        with _workspace() as (workspace, engine):
            session, _session_dir = _session_section(workspace, engine)
            return {
                "schema": SNAPSHOT_SCHEMA,
                "sections": {
                    "cli": _cli_section(workspace),
                    "http": _http_section(workspace),
                    "page": _page_section(workspace),
                    "protocol": _protocol_section(workspace, engine),
                    "python": _python_section(),
                    "session": session,
                },
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="contract_snapshot.py",
        description=(
            "Record or compare the external behavior contract of the tool."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="record a new snapshot")
    record.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help=f"snapshot path (default: {DEFAULT_SNAPSHOT_PATH.name})",
    )
    compare = commands.add_parser("compare", help="compare against a snapshot")
    compare.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help=f"snapshot path (default: {DEFAULT_SNAPSHOT_PATH.name})",
    )
    compare.add_argument(
        "--report",
        type=Path,
        default=None,
        help="also write the difference report to this path",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "record":
            snapshot = record_snapshot()
            write_snapshot(args.out, snapshot)
            print(f"[contract] recorded: {args.out}")
            print(
                "[contract] sections: "
                + ", ".join(sorted(snapshot["sections"]))
            )
            return 0
        reference = load_snapshot(args.snapshot)
        current = record_snapshot()
        differences = compare_snapshots(reference, current)
        report = render_diff_report(differences, reference=str(args.snapshot))
        print(report)
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report + "\n", encoding="utf-8")
        return 0 if not differences else 1
    except Exception as exc:  # noqa: BLE001 - report every harness failure
        print(f"[contract] error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
