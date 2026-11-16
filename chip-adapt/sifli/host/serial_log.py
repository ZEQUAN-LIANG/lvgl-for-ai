from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, TextIO

from timeutil import now_iso


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class SerialLog:
    def __init__(
        self,
        directory: Path,
        *,
        port: str,
        baud: int,
        opened_at: str | None,
        event_seq: int = 0,
    ) -> None:
        self.dir = directory
        self.port = port
        self.baud = int(baud)
        self.opened_at = opened_at
        self.log_path = directory / "serial.log"
        self.raw_path = directory / "serial.raw"
        self.events_path = directory / "events.ndjson"
        self.event_seq = int(event_seq)
        self._log_file: TextIO | None = None
        self._raw_file: BinaryIO | None = None
        self._events_file: TextIO | None = None

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        port: str,
        baud: int,
        opened_at: str | None,
        event_seq: int = 0,
    ) -> "SerialLog":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}-{port or 'serial'}"
        target = root / base
        suffix = 1
        while target.exists():
            suffix += 1
            target = root / f"{base}-{suffix}"
        target.mkdir(parents=True)

        log = cls(
            target,
            port=port,
            baud=baud,
            opened_at=opened_at,
            event_seq=event_seq,
        )
        log._open_files()
        log._write_meta()
        return log

    def _open_files(self) -> None:
        self._log_file = open(
            self.log_path,
            "a",
            encoding="utf-8",
            errors="replace",
            newline="",
        )
        self._raw_file = open(self.raw_path, "ab")
        self._events_file = open(
            self.events_path,
            "a",
            encoding="utf-8",
            newline="",
        )

    def _write_meta(self) -> None:
        meta = {
            "schema": "sifli-host-serial-v1",
            "port": self.port,
            "baud": self.baud,
            "started_at": self.opened_at,
            "log_path": str(self.log_path),
            "raw_path": str(self.raw_path),
            "events_path": str(self.events_path),
        }
        (self.dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        for handle in (self._log_file, self._raw_file, self._events_file):
            if handle is not None:
                try:
                    handle.flush()
                    handle.close()
                except OSError:
                    pass
        self._log_file = None
        self._raw_file = None
        self._events_file = None

    def write_rx(self, data: bytes) -> None:
        if self._log_file is not None:
            try:
                self._log_file.write(_text(data))
                self._log_file.flush()
            except OSError:
                pass
        if self._raw_file is not None:
            try:
                self._raw_file.write(data)
                self._raw_file.flush()
            except OSError:
                pass
        self.write_event("rx", data, source="device")

    def write_event(
        self,
        direction: str,
        data: bytes,
        *,
        source: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._events_file is None:
            return
        self.event_seq += 1
        event = {
            "seq": self.event_seq,
            "ts": now_iso(),
            "dir": direction,
            "source": source,
            "bytes": len(data),
            "data_b64": _b64(data),
        }
        if extra:
            event.update(extra)
        try:
            self._events_file.write(
                json.dumps(event, ensure_ascii=False) + "\n"
            )
            self._events_file.flush()
        except OSError:
            pass


def list_sessions(root: str | Path) -> list[dict[str, Any]]:
    root = Path(root)
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        meta_path = path / "meta.json"
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
        items.append(
            {
                "name": path.name,
                "meta": meta,
                "files": sorted(
                    item.name for item in path.iterdir() if item.is_file()
                ),
            }
        )
    return items
