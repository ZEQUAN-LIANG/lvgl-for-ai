"""Serialized request/reply exchange over the shared broker.

Both page switching and wireless configuration use the same serial line.  A
single ``CommandSession`` lock keeps a ``send``/``expect`` pair from being
interleaved with another controller's pair.
"""

from __future__ import annotations

import threading
from typing import Any


class CommandError(RuntimeError):
    def __init__(self, message: str, *, code: str = "command_timeout") -> None:
        super().__init__(message)
        self.code = code


class CommandSession:
    def __init__(self, broker: Any, *, timeout_ms: int = 4000) -> None:
        self._broker = broker
        self._timeout_ms = int(timeout_ms)
        self._lock = threading.Lock()

    def exchange(
        self,
        command: str,
        pattern: str,
        *,
        timeout_ms: int | None = None,
        private: bool = False,
    ) -> str:
        with self._lock:
            cursor = self._broker.current_seq()
            self._broker.send(
                (command + "\n").encode("ascii"), private=private
            )
            result = self._broker.expect(
                pattern,
                since=cursor,
                timeout_ms=self._timeout_ms if timeout_ms is None else timeout_ms,
                regex=True,
            )
        if not result.get("ok"):
            raise CommandError(
                f"timed out waiting for the firmware reply to {command!r}",
                code="command_timeout",
            )
        return str(result.get("matched") or "")
