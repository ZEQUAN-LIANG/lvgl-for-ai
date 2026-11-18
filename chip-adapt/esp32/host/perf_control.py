"""In-process control of the PERF TAPE monitor.

The browser page talks to this controller through ``host.py``.  The controller
still writes through the host's ``SerialBroker``: it never opens a second COM
port and the host remains the only serial owner.
"""

from __future__ import annotations

import platform
import threading
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, Optional

from perf_agent import live_sample
from perf_protocol import PerfSample, demo_sample, encode

MODE_COMMANDS: Dict[str, str] = {
    "demo": "PERF DEMO",
    "live": "PERF LIVE",
}
LAYOUT_COMMANDS: Dict[str, str] = {
    "portrait": "PERF PORTRAIT",
    "landscape": "PERF LANDSCAPE",
}
MIN_INTERVAL_S = 0.2
MAX_INTERVAL_S = 60.0

SampleProvider = Callable[[str, int, int, Dict[str, Any]], PerfSample]


class PerfError(RuntimeError):
    def __init__(
        self, message: str, *, code: str = "perf_error", status: int = 400
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class PerfController:
    """Run the demo/live frame loop in one background thread."""

    def __init__(
        self,
        broker: Any,
        *,
        provider: Optional[SampleProvider] = None,
    ) -> None:
        self._broker = broker
        self._provider = provider or self._default_provider
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._generation = 0
        self._runner: Optional[threading.Thread] = None
        self._state = "idle"
        self._mode = "demo"
        self._interval = 0.3
        self._layout = "portrait"
        self._seq = 0
        self._sent = 0
        self._period_ms = 0
        self._started_at: Optional[str] = None
        self._last_sent_at: Optional[str] = None
        self._last_error: Optional[str] = None
        self._sample: Optional[PerfSample] = None

    @staticmethod
    def _default_provider(
        mode: str, seq: int, tick: int, live_state: Dict[str, Any]
    ) -> PerfSample:
        if mode == "demo":
            return demo_sample(seq, tick)
        return live_sample(seq, live_state, time.monotonic())

    @staticmethod
    def _clock() -> str:
        return time.strftime("%H:%M:%S")

    def _send(self, line: str) -> Dict[str, Any]:
        if not self._broker.is_open:
            raise PerfError(
                "no active UART or BLE link; connect a device first",
                code="serial_not_open",
                status=409,
            )
        with self._send_lock:
            return self._broker.send(
                (line + "\n").encode("utf-8"), source="perf_web"
            )

    def status(self) -> Dict[str, Any]:
        with self._lock:
            sample = asdict(self._sample) if self._sample is not None else None
            return {
                "running": self._state == "running",
                "state": self._state,
                "mode": self._mode,
                "interval_s": self._interval,
                "layout": self._layout,
                "seq": self._seq,
                "sent": self._sent,
                "period_ms": self._period_ms,
                "started_at": self._started_at,
                "last_sent_at": self._last_sent_at,
                "last_error": self._last_error,
                "sample": sample,
            }

    def set_layout(self, layout: str) -> Dict[str, Any]:
        layout = str(layout or "").lower()
        if layout not in LAYOUT_COMMANDS:
            raise PerfError(
                f"layout must be portrait or landscape, got {layout!r}",
                code="bad_layout",
            )
        self._send(LAYOUT_COMMANDS[layout])
        with self._lock:
            self._layout = layout
        return {"ok": True, "layout": layout}

    def start(
        self,
        mode: str = "demo",
        interval: float = 0.3,
        layout: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode = str(mode or "").lower()
        if mode not in MODE_COMMANDS:
            raise PerfError(
                f"mode must be demo or live, got {mode!r}", code="bad_mode"
            )
        try:
            interval = float(interval)
        except (TypeError, ValueError) as exc:
            raise PerfError("interval must be a number", code="bad_interval") from exc
        if not (MIN_INTERVAL_S <= interval <= MAX_INTERVAL_S):
            raise PerfError(
                f"interval must be {MIN_INTERVAL_S:g}..{MAX_INTERVAL_S:g} s",
                code="bad_interval",
            )
        if mode == "live" and platform.system() != "Windows":
            raise PerfError(
                "live collection requires Windows", code="unsupported", status=400
            )
        if not self._broker.is_open:
            raise PerfError(
                "no active UART or BLE link; connect a device first",
                code="serial_not_open",
                status=409,
            )
        if layout is not None:
            layout = str(layout).lower()
            if layout not in LAYOUT_COMMANDS:
                raise PerfError(
                    f"layout must be portrait or landscape, got {layout!r}",
                    code="bad_layout",
                )

        self.stop()
        if layout is not None:
            self.set_layout(layout)
        self._send(MODE_COMMANDS[mode])

        stop_event = threading.Event()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._stop = stop_event
            self._mode = mode
            self._interval = interval
            self._state = "starting"
            self._last_error = None
            self._seq = 0
            self._sent = 0
            self._period_ms = 0
            self._started_at = self._clock()
            self._runner = threading.Thread(
                target=self._run,
                args=(generation, mode, interval, stop_event),
                name="perf-monitor",
                daemon=True,
            )
            self._state = "running"
            runner = self._runner
        runner.start()
        return {"ok": True, **self.status()}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._generation += 1
            runner = self._runner
            self._stop.set()
            if self._state != "idle":
                self._state = "stopping"
        if runner is not None and runner is not threading.current_thread():
            runner.join(timeout=0.6)
        with self._lock:
            if runner is None or not runner.is_alive():
                self._runner = None
            if self._state == "stopping":
                self._state = "idle"
        return {"ok": True, **self.status()}

    def _run(
        self,
        generation: int,
        mode: str,
        interval: float,
        stop_event: threading.Event,
    ) -> None:
        seq = 0
        tick = 0
        live_state: Dict[str, Any] = {}
        last_frame_at: Optional[float] = None

        while not stop_event.is_set() and generation == self._generation:
            started = time.monotonic()
            try:
                sample = self._provider(mode, seq, tick, live_state)
                line = encode(sample)
                if stop_event.is_set() or generation != self._generation:
                    break
                self._send(line)
                now = time.monotonic()
                period_ms = (
                    int((now - last_frame_at) * 1000)
                    if last_frame_at is not None
                    else 0
                )
                last_frame_at = now
                with self._lock:
                    if generation == self._generation:
                        self._seq = sample.seq
                        self._sent += 1
                        self._sample = sample
                        self._last_sent_at = self._clock()
                        self._period_ms = period_ms
                        self._state = "running"
            except Exception as exc:  # keep the page alive and show the reason
                with self._lock:
                    if generation == self._generation:
                        self._state = "error"
                        self._last_error = str(exc)
                        self._runner = None
                return

            seq = (seq + 1) % 65536
            tick += 1
            delay = max(0.05, interval - (time.monotonic() - started))
            if stop_event.wait(delay):
                break

        with self._lock:
            if generation == self._generation:
                self._state = "idle"
                self._runner = None
