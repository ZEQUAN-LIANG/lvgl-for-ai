"""Small in-process event bus for the web activity feed.

Serial API calls and build/flash jobs publish here.  The browser subscribes
with SSE, so a flash started by an AI/CLI command is visible in the page even
when no human clicked anything.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from timeutil import now_iso


class EventHub:
    def __init__(self, *, maxlen: int = 800) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=max(50, int(maxlen)))
        self._seq = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)

    def current_seq(self) -> int:
        with self._lock:
            return self._seq

    def publish(
        self,
        actor: str,
        kind: str,
        message: str = "",
        data: dict[str, Any] | None = None,
        *,
        source: str = "api",
    ) -> dict[str, Any]:
        with self._cond:
            self._seq += 1
            event = {
                "seq": self._seq,
                "ts": now_iso(),
                "actor": actor or "system",
                "source": source,
                "kind": kind,
                "message": message,
                "data": data or {},
            }
            self._events.append(event)
            self._cond.notify_all()
            return event

    def snapshot(
        self,
        since: int = 0,
        *,
        limit: int = 300,
    ) -> dict[str, Any]:
        with self._lock:
            first = self._events[0]["seq"] if self._events else self._seq + 1
            events = [
                event
                for event in self._events
                if int(event["seq"]) > int(since)
            ]
            truncated = bool(events) and int(events[0]["seq"]) > int(since) + 1
            if len(events) > limit:
                events = events[-limit:]
            return {
                "events": events,
                "next": self._seq,
                "first": first,
                "truncated": truncated,
            }

    def wait(self, since: int, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_s)
        with self._cond:
            while self._seq <= int(since):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True
