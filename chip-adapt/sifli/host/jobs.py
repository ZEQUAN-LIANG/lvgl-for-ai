"""In-memory job records for build and flash operations."""

from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any, Callable

from timeutil import now_iso

_PROGRESS_RE = re.compile(r"^\s*(\d{1,3})\s*%\s*$")

TERMINAL_STATUSES = ("ok", "failed", "cancelled")

Publisher = Callable[[str, str, str, dict[str, Any]], None]


class Job:
    def __init__(
        self,
        kind: str,
        title: str,
        *,
        actor: str = "system",
        publisher: Publisher | None = None,
    ) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.actor = actor
        self.status = "queued"  # queued / running / ok / failed / cancelled
        self.created_at = now_iso()
        self.started_at: str | None = None
        self.ended_at: str | None = None
        self.percent: int | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.cancel_event = threading.Event()
        self._publisher = publisher
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)

    def _publish(self, kind: str, message: str, data: dict[str, Any]) -> None:
        if self._publisher is None:
            return
        try:
            self._publisher(self.actor, kind, message, data)
        except Exception:
            pass

    def start(self) -> None:
        with self._cond:
            if self.status == "queued":
                self.status = "running"
                self.started_at = now_iso()
                self._cond.notify_all()
        self._publish(
            "job.start",
            f"{self.kind} started",
            {
                "job_id": self.id,
                "kind": self.kind,
                "title": self.title,
                "status": self.status,
            },
        )

    def append(self, stream: str, text: str) -> dict[str, Any]:
        previous = self.percent
        with self._cond:
            self._seq += 1
            event = {
                "seq": self._seq,
                "ts": now_iso(),
                "stream": stream,
                "text": text,
            }
            self._events.append(event)
            match = _PROGRESS_RE.match(text)
            if match:
                value = min(100, max(0, int(match.group(1))))
                self.percent = value
            self._cond.notify_all()
        if stream == "status" or self.percent != previous:
            self._publish(
                "job.progress",
                text if stream == "status" else f"{self.kind} {self.percent}%",
                {
                    "job_id": self.id,
                    "kind": self.kind,
                    "title": self.title,
                    "status": self.status,
                    "percent": self.percent,
                    "stream": stream,
                    "text": text,
                },
            )
        return event

    def finish(
        self,
        *,
        ok: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        cancelled: bool = False,
    ) -> None:
        with self._cond:
            self.status = "cancelled" if cancelled else ("ok" if ok else "failed")
            self.result = result
            self.error = error
            self.ended_at = now_iso()
            self._cond.notify_all()
        self._publish(
            "job.done",
            self.error or f"{self.kind} {self.status}",
            {
                "job_id": self.id,
                "kind": self.kind,
                "title": self.title,
                "status": self.status,
                "percent": self.percent,
                "error": self.error,
                "result": self.result,
            },
        )

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._cond:
            if self.status in ("queued", "running"):
                self.append("status", "cancel requested")
            self._cond.notify_all()
        self._publish(
            "job.cancel",
            "cancel requested",
            {"job_id": self.id, "kind": self.kind, "status": self.status},
        )

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "title": self.title,
                "actor": self.actor,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "percent": self.percent,
                "result": self.result,
                "error": self.error,
                "events": [
                    event
                    for event in self._events
                    if int(event["seq"]) > int(since)
                ],
                "next": self._seq,
            }

    def wait(self, since: int, timeout_s: float) -> None:
        deadline = time.monotonic() + max(0.0, timeout_s)
        with self._cond:
            while self._seq <= since and self.status not in TERMINAL_STATUSES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._cond.wait(remaining)


class JobManager:
    def __init__(
        self,
        *,
        keep: int = 50,
        publisher: Publisher | None = None,
    ) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._keep = max(1, int(keep))
        self._publisher = publisher
        self._lock = threading.RLock()

    def create(
        self,
        kind: str,
        title: str,
        *,
        actor: str = "system",
    ) -> Job:
        job = Job(
            kind,
            title,
            actor=actor,
            publisher=self._publisher,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self._keep:
                old = self._order.pop(0)
                self._jobs.pop(old, None)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [self._jobs[job_id] for job_id in self._order]
        return [job.snapshot(0) for job in reversed(jobs)]
