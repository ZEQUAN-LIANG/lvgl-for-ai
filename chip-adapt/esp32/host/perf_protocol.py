"""Encoder for the PERF TAPE serial protocol.

The device-side parser lives in ``user/app/perf_monitor/perf_protocol.c``.
Keep the field names, units, and limits in sync with that file and
``user/app/perf_monitor/README.md``.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

PERF_VERSION = 1
PERF_BARS = 16
PERF_MAX_LINE = 320
PERF_HOST_MAX = 12

_HOST_RE = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class PerfSample:
    seq: int
    cpu: int
    mem_mb: int = 0
    mem_total_mb: int = 0
    gpu: Optional[int] = None
    freq_mhz: Optional[int] = None
    temp_c: Optional[int] = None
    gpu_temp_c: Optional[int] = None
    down_kib_s: int = 0
    up_kib_s: int = 0
    ping_ms: Optional[int] = None
    hhmm: Optional[int] = None
    host: str = ""
    bars: List[int] = field(default_factory=lambda: [0] * PERF_BARS)
    thread_count: int = PERF_BARS


def sanitize_host(host: str) -> str:
    return _HOST_RE.sub("", host or "")[:PERF_HOST_MAX]


def _check(value: int, low: int, high: int, name: str) -> int:
    if not isinstance(value, int) or value < low or value > high:
        raise ValueError(f"{name} must be {low}..{high}, got {value!r}")
    return value


def _check_optional(
    value: Optional[int], low: int, high: int, name: str
) -> Optional[int]:
    if value is None:
        return None
    return _check(value, low, high, name)


def encode(sample: PerfSample) -> str:
    """Return one LF-less protocol line.

    Unknown optional fields are omitted.  The result is always <= 320 bytes.
    """

    seq = _check(sample.seq % 65536, 0, 65535, "seq")
    cpu = _check(sample.cpu, 0, 100, "cpu")
    gpu = _check_optional(sample.gpu, 0, 100, "gpu")
    mem_mb = _check(sample.mem_mb, 0, 4194304, "mem")
    mem_total_mb = _check(sample.mem_total_mb, 0, 4194304, "memt")
    freq_mhz = _check_optional(sample.freq_mhz, 0, 100000, "freq")
    temp_c = _check_optional(sample.temp_c, -1, 150, "temp")
    gpu_temp_c = _check_optional(sample.gpu_temp_c, -1, 150, "gtemp")
    down = _check(sample.down_kib_s, 0, 4194304, "down")
    up = _check(sample.up_kib_s, 0, 4194304, "up")
    ping = _check_optional(sample.ping_ms, 0, 60000, "ping")
    hhmm = _check_optional(sample.hhmm, 0, 2359, "time")
    if hhmm is not None and hhmm % 100 > 59:
        raise ValueError(f"time must be HHMM, got {hhmm}")

    thread_count = _check(sample.thread_count, 1, PERF_BARS, "thn")
    bars = [int(value) for value in sample.bars[:PERF_BARS]]
    bars.extend([0] * (PERF_BARS - len(bars)))
    for value in bars:
        _check(value, 0, 100, "th")

    parts = [
        "PERF",
        f"v={PERF_VERSION}",
        f"seq={seq}",
        f"cpu={cpu}",
    ]
    if gpu is not None:
        parts.append(f"gpu={gpu}")
    if mem_total_mb > 0:
        parts.extend((f"mem={mem_mb}", f"memt={mem_total_mb}"))
    if freq_mhz:
        parts.append(f"freq={freq_mhz}")
    if temp_c is not None:
        parts.append(f"temp={temp_c}")
    if gpu_temp_c is not None:
        parts.append(f"gtemp={gpu_temp_c}")
    parts.extend((f"down={down}", f"up={up}"))
    if ping is not None:
        parts.append(f"ping={ping}")
    if hhmm is not None:
        parts.append(f"time={hhmm:04d}")
    host = sanitize_host(sample.host)
    if host:
        parts.append(f"host={host}")
    if thread_count != PERF_BARS:
        parts.append(f"thn={thread_count}")
    parts.append("th=" + ",".join(str(value) for value in bars))

    line = " ".join(parts)
    if len(line) > PERF_MAX_LINE:
        raise ValueError(
            f"encoded line is {len(line)} bytes; limit is {PERF_MAX_LINE}"
        )
    return line


def current_hhmm() -> int:
    now = time.localtime()
    return now.tm_hour * 100 + now.tm_min


def demo_sample(seq: int, tick: int) -> PerfSample:
    """Deterministic, plausible data for --demo and tests."""

    cpu = 45 + 16 * math.sin(tick / 7.0) + 6 * math.sin(tick / 2.1)
    cpu = max(2, min(99, int(cpu)))
    gpu = 28 + 12 * math.sin(tick / 6.0 + 1.0) + 4 * math.sin(tick / 2.7)
    gpu = max(1, min(99, int(gpu)))
    mem_mb = 11300 + int(180 * math.sin(tick / 13.0))
    down = (
        12000
        + int(5200 * math.sin(tick / 5.0))
        + int(1200 * math.sin(tick / 1.7))
    )
    up = 900 + int(420 * math.sin(tick / 4.0 + 1.3))
    bars = []
    for index in range(PERF_BARS):
        value = cpu + 26 * math.sin(tick / 3.0 + index * 0.9)
        bars.append(max(1, min(100, int(value))))

    return PerfSample(
        seq=seq % 65536,
        cpu=cpu,
        gpu=gpu,
        mem_mb=mem_mb,
        mem_total_mb=32768,
        freq_mhz=2000 + cpu * 30,
        temp_c=38 + cpu // 2,
        gpu_temp_c=41 + gpu // 2,
        down_kib_s=max(0, down),
        up_kib_s=max(0, up),
        ping_ms=12 + (tick * 7) % 17,
        hhmm=current_hhmm(),
        host="DESKTOP-01",
        bars=bars,
        thread_count=PERF_BARS,
    )
