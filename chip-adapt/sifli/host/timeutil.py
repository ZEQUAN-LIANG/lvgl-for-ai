"""Timestamp helper shared by the host modules.

Every timestamp the broker, jobs and logs expose uses the same local-time
ISO-8601 form with milliseconds, so event and job streams can be compared
across modules.
"""

from __future__ import annotations

from datetime import datetime


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
