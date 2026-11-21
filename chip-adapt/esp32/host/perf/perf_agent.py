#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from perf_protocol import (  # noqa: E402
    PERF_BARS,
    PerfSample,
    current_hhmm,
    demo_sample,
    encode,
    sanitize_host,
)

_PS_COLLECT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem
$total = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
$cores = @(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor |
  Where-Object { $_.Name -match '^\d+$' } |
  Sort-Object { [int]$_.Name } |
  ForEach-Object { [int]$_.PercentProcessorTime })
$clock = (Get-CimInstance Win32_Processor |
  Measure-Object -Property CurrentClockSpeed -Maximum).Maximum

$cpuValue = 0
if ($null -ne $total) { $cpuValue = [int]$total.PercentProcessorTime }
$memTotal = 0
$memFree = 0
if ($null -ne $os) {
  $memTotal = [int64]$os.TotalVisibleMemorySize
  $memFree = [int64]$os.FreePhysicalMemory
}
$freq = 0
if ($null -ne $clock) { $freq = [int]$clock }

$rx = [int64]0
$tx = [int64]0
$stats = Get-NetAdapterStatistics
if ($null -ne $stats) {
  $rx = [int64](($stats | Measure-Object -Property ReceivedBytes -Sum).Sum)
  $tx = [int64](($stats | Measure-Object -Property SentBytes -Sum).Sum)
}

$gpu = $null
$engines = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine
if ($null -ne $engines) {
  $sum = ($engines | Where-Object { $_.Name -like '*3D*' } |
    Measure-Object -Property UtilizationPercentage -Sum).Sum
  if ($null -ne $sum) { $gpu = [math]::Min(100, [int]$sum) }
}

[pscustomobject]@{
  cpu = $cpuValue
  cores = @($cores)
  mem_total_kb = $memTotal
  mem_free_kb = $memFree
  freq_mhz = $freq
  rx_bytes = $rx
  tx_bytes = $tx
  gpu = $gpu
} | ConvertTo-Json -Compress
"""


def _no_window() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _last_json_object(text: str) -> Dict[str, Any]:
    for line in reversed(text.splitlines()):
        candidate = line.strip().lstrip("﻿")
        if candidate.startswith("{") and candidate.endswith("}"):
            return json.loads(candidate)
    raise RuntimeError("PowerShell returned no JSON object")


def _nvidia_gpu() -> Optional[Tuple[int, int]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=_no_window(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [
        line.strip() for line in completed.stdout.splitlines() if line.strip()
    ]
    if completed.returncode != 0 or not lines:
        return None
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) < 2:
        return None
    try:
        return int(fields[0]), int(fields[1])
    except ValueError:
        return None


def _map_cores(cores: List[int]) -> List[int]:
    if not cores:
        return [0] * PERF_BARS
    if len(cores) < PERF_BARS:
        return cores + [0] * (PERF_BARS - len(cores))
    mapped: List[int] = []
    for index in range(PERF_BARS):
        start = index * len(cores) // PERF_BARS
        end = max(start + 1, (index + 1) * len(cores) // PERF_BARS)
        mapped.append(max(cores[start:end]))
    return mapped


def collect_windows() -> Dict[str, Any]:
    if platform.system() != "Windows":
        raise RuntimeError("--live collection is only implemented on Windows")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _PS_COLLECT,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
        creationflags=_no_window(),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"PowerShell collection failed: {detail[:300]}")
    payload = _last_json_object(completed.stdout)

    def number(name: str, default: int = 0) -> int:
        try:
            return int(payload.get(name, default) or default)
        except (TypeError, ValueError):
            return default

    raw_cores = payload.get("cores") or []
    if isinstance(raw_cores, (int, float)):
        raw_cores = [raw_cores]
    cores = []
    for item in raw_cores:
        try:
            cores.append(max(0, min(100, int(item))))
        except (TypeError, ValueError):
            cores.append(0)

    gpu_value = payload.get("gpu")
    gpu: Optional[int] = None
    if gpu_value is not None:
        try:
            gpu = max(0, min(100, int(gpu_value)))
        except (TypeError, ValueError):
            gpu = None

    return {
        "cpu": max(0, min(100, number("cpu"))),
        "cores": cores,
        "mem_total_kb": max(0, number("mem_total_kb")),
        "mem_free_kb": max(0, number("mem_free_kb")),
        "freq_mhz": max(0, number("freq_mhz")),
        "rx_bytes": max(0, number("rx_bytes")),
        "tx_bytes": max(0, number("tx_bytes")),
        "gpu": gpu,
    }


def live_sample(seq: int, state: Dict[str, Any], now: float) -> PerfSample:
    data = collect_windows()
    previous = state.get("previous")
    down_kib_s = 0
    up_kib_s = 0
    if previous is not None:
        elapsed = max(0.2, now - previous["at"])
        down_kib_s = max(
            0, int((data["rx_bytes"] - previous["rx"]) / 1024.0 / elapsed)
        )
        up_kib_s = max(
            0, int((data["tx_bytes"] - previous["tx"]) / 1024.0 / elapsed)
        )
    state["previous"] = {
        "at": now,
        "rx": data["rx_bytes"],
        "tx": data["tx_bytes"],
    }

    nvidia = _nvidia_gpu()
    gpu = data["gpu"]
    gpu_temp = None
    if nvidia is not None:
        gpu, gpu_temp = nvidia

    mem_total_mb = data["mem_total_kb"] // 1024
    mem_free_mb = data["mem_free_kb"] // 1024
    mem_mb = max(0, mem_total_mb - mem_free_mb)
    host = sanitize_host(platform.node()) or "DESKTOP"

    return PerfSample(
        seq=seq % 65536,
        cpu=data["cpu"],
        gpu=gpu,
        mem_mb=mem_mb,
        mem_total_mb=mem_total_mb,
        freq_mhz=data["freq_mhz"] or None,
        gpu_temp_c=gpu_temp,
        down_kib_s=down_kib_s,
        up_kib_s=up_kib_s,
        hhmm=current_hhmm(),
        host=host,
        bars=_map_cores(data["cores"]),
        thread_count=max(1, min(PERF_BARS, len(data["cores"]))),
    )


def send_line(host: str, line: str) -> Dict[str, Any]:
    payload = json.dumps({"data": line, "line_ending": "lf"}).encode("utf-8")
    http_request = request.Request(
        host.rstrip("/") + "/api/send",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo",
        action="store_true",
        help="send generated samples instead of Windows metrics",
    )
    source.add_argument(
        "--live",
        action="store_true",
        help="collect Windows metrics (default)",
    )
    parser.add_argument(
        "--host",
        default="http://127.0.0.1:8767",
        help="ESP32-C6 host base URL (default: %(default)s)",
    )
    parser.add_argument("--interval", type=float, default=0.3)
    parser.add_argument(
        "--once", action="store_true", help="send one frame and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print frames instead of sending",
    )
    parser.add_argument(
        "--layout",
        choices=("portrait", "landscape"),
        help="send PERF PORTRAIT/LANDSCAPE before the first frame",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.interval < 0.2:
        parser.error("--interval must be >= 0.2")

    use_demo = bool(args.demo)
    if platform.system() != "Windows" and not use_demo and not args.dry_run:
        print(
            "perf_agent: --live requires Windows; use --demo", file=sys.stderr
        )
        return 2

    if not args.quiet:
        mode = "demo" if use_demo else "windows"
        target = "stdout" if args.dry_run else args.host
        print(
            f"perf_agent: source={mode} target={target} interval={args.interval:.1f}s",
            file=sys.stderr,
        )

    if args.layout:
        command = f"PERF {args.layout.upper()}"
        if args.dry_run:
            print(command, flush=True)
        else:
            try:
                response = send_line(args.host, command)
            except (error.URLError, TimeoutError, OSError, ValueError) as exc:
                print(
                    f"perf_agent: layout command failed: {exc}",
                    file=sys.stderr,
                )
                return 1
            if not response.get("ok"):
                print(
                    f"perf_agent: host rejected layout command: {response}",
                    file=sys.stderr,
                )
                return 1

    seq = 0
    tick = 0
    state: Dict[str, Any] = {}
    while True:
        started = time.monotonic()
        try:
            if use_demo:
                sample = demo_sample(seq, tick)
            else:
                sample = live_sample(seq, state, started)
            line = encode(sample)
        except (
            RuntimeError,
            ValueError,
            OSError,
            subprocess.SubprocessError,
        ) as exc:
            print(f"perf_agent: {exc}", file=sys.stderr)
            return 1

        if args.dry_run:
            print(line, flush=True)
        else:
            try:
                response = send_line(args.host, line)
            except (error.URLError, TimeoutError, OSError, ValueError) as exc:
                print(f"perf_agent: send failed: {exc}", file=sys.stderr)
                return 1
            if not response.get("ok"):
                print(
                    f"perf_agent: host rejected frame: {response}",
                    file=sys.stderr,
                )
                return 1
            elif not args.quiet:
                print(line, file=sys.stderr, flush=True)

        if args.once:
            return 0
        seq = (seq + 1) % 65536
        tick += 1
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, args.interval - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
