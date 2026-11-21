from __future__ import annotations

import mimetypes
import threading
import time
import uuid
from pathlib import Path
from typing import Any

WEB_DIR = Path(__file__).resolve().parent / "flash_web"

PLAN_TTL_S = 600
MAX_PLANS = 20

_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def asset_path(relative: str) -> Path | None:
    value = (relative or "index.html").strip().replace("\\", "/")
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if not parts:
        parts = ["index.html"]
    if ".." in parts:
        return None
    target = WEB_DIR.joinpath(*parts).resolve()
    try:
        target.relative_to(WEB_DIR.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _CONTENT_TYPES:
        return _CONTENT_TYPES[suffix]
    guessed = mimetypes.guess_type(str(path))[0]
    return guessed or "application/octet-stream"


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "plan_id": plan["plan_id"],
        "source": plan.get("source", ""),
        "notes": plan.get("notes", ""),
        "entries": [
            {
                "name": entry.get("name", ""),
                "address": entry.get("address", ""),
                "size": entry.get("size", 0),
            }
            for entry in plan.get("entries", [])
        ],
    }
    for key in ("chip", "memory", "board", "backend"):
        if plan.get(key):
            payload[key] = plan[key]
    return payload


class PlanStore:
    def __init__(
        self,
        *,
        ttl_s: float = PLAN_TTL_S,
        limit: int = MAX_PLANS,
    ) -> None:
        self._plans: dict[str, dict[str, Any]] = {}
        self._ttl_s = float(ttl_s)
        self._limit = max(1, int(limit))
        self._lock = threading.RLock()

    def put(self, plan: dict[str, Any]) -> str:
        plan_id = uuid.uuid4().hex[:12]
        record = dict(plan)
        record["plan_id"] = plan_id
        record["created"] = time.time()
        with self._lock:
            self._plans[plan_id] = record
            self._prune_locked()
        return plan_id

    def get(self, plan_id: str) -> dict[str, Any] | None:
        key = str(plan_id or "")
        with self._lock:
            record = self._plans.get(key)
            if record is None:
                return None
            if time.time() - float(record.get("created", 0)) > self._ttl_s:
                self._plans.pop(key, None)
                return None
            return dict(record)

    def clear(self) -> None:
        with self._lock:
            self._plans.clear()

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            key
            for key, plan in self._plans.items()
            if now - float(plan.get("created", 0)) > self._ttl_s
        ]
        for key in expired:
            self._plans.pop(key, None)
        while len(self._plans) > self._limit:
            oldest = min(
                self._plans,
                key=lambda key: float(self._plans[key].get("created", 0)),
            )
            self._plans.pop(oldest, None)
