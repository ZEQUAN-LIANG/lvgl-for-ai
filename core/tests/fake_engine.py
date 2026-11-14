"""Minimal engine protocol double for unit tests.

Not imported by production code. It speaks ``lvgl-ai-engine-v1`` so Runtime's
process boundary can be tested without compiling LVGL: ready, pointer,
tick, wait, mark, snapshot, key, encoder and quit.

Set FAKE_READY=malformed or FAKE_READY=crash to exercise error paths.
Set FAKE_WAIT_CHANGED=never|always|flaky to include the wait ``changed`` flag
(never = no painted refresh, always = every wait paints, flaky = alternating);
unset omits the field like an older engine. Set FAKE_WAIT_FRAMES=hold to keep
the reported retained ``frames`` constant across waits, modelling changed-only
recording that retained no new frame.
Set FAKE_UNKNOWN_ARG=1 to mimic an old engine artifact that rejects a newer
command-line flag, prints the reason to stderr and exits 2 before ready.
Set FAKE_DECOY=1 to print JSON-looking user log lines that must not be
mistaken for protocol replies. Set FAKE_LOG_LINES=<n> to print that many
log lines before ready (log-truncation tests). Set FAKE_REPLY_SEQ_OFFSET
to answer every command with a shifted seq (protocol-error tests). Set
FAKE_MISSING_FIELDS=1 to omit pointer hit fields.
"""

from __future__ import annotations

import json
import math
import os
import sys

PROTOCOL = "lvgl-ai-engine-v1"


def emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def main() -> int:
    session_dir = None
    record = False
    max_frames = 600
    display_width = 800
    display_height = 600
    args = sys.argv[1:]
    index = 0
    while index < len(args):
        if args[index] == "--session" and index + 1 < len(args):
            session_dir = args[index + 1]
            index += 2
        elif args[index] == "--record":
            record = True
            index += 1
        elif args[index] == "--no-record":
            record = False
            index += 1
        elif args[index] == "--max-frames" and index + 1 < len(args):
            max_frames = int(args[index + 1])
            index += 2
        elif args[index] == "--width" and index + 1 < len(args):
            display_width = int(args[index + 1])
            index += 2
        elif args[index] == "--height" and index + 1 < len(args):
            display_height = int(args[index + 1])
            index += 2
        else:
            index += 1

    mode = os.environ.get("FAKE_READY", "ok")
    print(f"[fake_engine] started session={session_dir} record={record}", flush=True)
    for line_index in range(int(os.environ.get("FAKE_LOG_LINES", "0") or 0)):
        print(f"[fake_engine] log line {line_index:05d}", flush=True)
    if os.environ.get("FAKE_UNKNOWN_ARG") == "1":
        print(
            "[engine] unknown argument: --record-changed-only",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if mode == "crash":
        print("[fake_engine] crashing before ready", flush=True)
        return 3
    if os.environ.get("FAKE_DECOY") == "1":
        # User printf that happens to look like the old loose protocol shape.
        emit({"seq": 99, "ok": True})
        emit({"ready": True, "seq": 0})

    if mode == "malformed":
        # Missing lvgl_src/display/mode/inputs/capabilities, but a valid seq.
        emit({"protocol": PROTOCOL, "ready": True, "seq": 0, "lvgl": "9.6.0"})
    else:
        emit(
            {
                "protocol": PROTOCOL,
                "ready": True,
                "seq": 0,
                "lvgl": "9.6.0",
                "lvgl_src": "/fake/lvgl-src/9.6",
                "display": {
                    "width": display_width,
                    "height": display_height,
                    "format": "XRGB8888",
                },
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
                "frames": 1,
                "max_frames": max_frames,
                "truncated": False,
            }
        )

    if os.environ.get("FAKE_DECOY") == "1":
        # Same seq as the first real reply: only the protocol marker saves us.
        emit({"seq": 1, "ok": True})

    frames = 1
    t_ms = 0
    snapshots = 0
    wait_count = 0
    hold_frames = os.environ.get("FAKE_WAIT_FRAMES") == "hold"

    def retain_frames(count: int) -> None:
        nonlocal frames
        if not hold_frames:
            frames += count

    def next_wait_changed() -> bool | None:
        nonlocal wait_count
        wait_count += 1
        mode = os.environ.get("FAKE_WAIT_CHANGED", "")
        if mode == "never":
            return False
        if mode == "always":
            return True
        if mode == "flaky":
            return wait_count % 2 == 1
        return None

    def emit_wait(seq: int) -> None:
        payload = {
            "protocol": PROTOCOL,
            "seq": seq,
            "ok": True,
            "frames": frames,
            "t_ms": t_ms,
        }
        changed = next_wait_changed()
        if changed is not None:
            payload["changed"] = changed
        emit(payload)

    seq_offset = int(os.environ.get("FAKE_REPLY_SEQ_OFFSET", "0") or 0)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            seq = int(parts[0]) + seq_offset
        except ValueError:
            continue
        verb = parts[1]
        if verb == "quit":
            emit({"protocol": PROTOCOL, "seq": seq, "ok": True, "frames": frames, "t_ms": t_ms})
            return 0
        if verb == "pointer" and len(parts) >= 5:
            payload = {
                "protocol": PROTOCOL,
                "seq": seq,
                "ok": True,
                "frames": frames,
                "t_ms": t_ms,
            }
            if os.environ.get("FAKE_MISSING_FIELDS") != "1":
                payload["hit"] = "fake_button"
                payload["hit_class"] = "lv_button"
            emit(payload)
        elif verb == "tick" and len(parts) >= 3:
            t_ms += int(parts[2])
            frames += 1
            emit({"protocol": PROTOCOL, "seq": seq, "ok": True, "frames": frames, "t_ms": t_ms})
        elif verb == "wait" and len(parts) >= 4 and parts[2] == "frames":
            retain_frames(int(parts[3]))
            t_ms += 16 * int(parts[3])
            emit_wait(seq)
        elif verb == "wait" and len(parts) >= 3:
            ms = int(parts[2])
            retain_frames(math.ceil(ms / 16))
            t_ms += ms
            emit_wait(seq)
        elif verb == "snapshot":
            snapshots += 1
            emit(
                {
                    "protocol": PROTOCOL,
                    "seq": seq,
                    "ok": True,
                    "frames": frames,
                    "t_ms": t_ms,
                    "file": f"snapshots/{snapshots:03d}_{parts[2]}.png",
                }
            )
        elif verb == "key" and len(parts) >= 5:
            # <seq> key <action> <code> <name>
            emit(
                {
                    "protocol": PROTOCOL,
                    "seq": seq,
                    "ok": True,
                    "frames": frames,
                    "t_ms": t_ms,
                    "delivered": True,
                    "key": parts[4],
                }
            )
        elif verb == "encoder" and len(parts) >= 4:
            emit(
                {
                    "protocol": PROTOCOL,
                    "seq": seq,
                    "ok": True,
                    "frames": frames,
                    "t_ms": t_ms,
                    "delivered": True,
                    "diff": int(parts[3]),
                }
            )
        elif verb == "mark":
            emit(
                {
                    "protocol": PROTOCOL,
                    "seq": seq,
                    "ok": True,
                    "frames": frames,
                    "t_ms": t_ms,
                }
            )
        else:
            emit(
                {
                    "protocol": PROTOCOL,
                    "seq": seq,
                    "ok": False,
                    "error": "unknown_command",
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
