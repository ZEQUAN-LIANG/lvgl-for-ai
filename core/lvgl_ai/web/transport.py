"""Raw framebuffer frames for the web live preview.

The C engine writes the transient ``live.rgba`` file; the live ticker reads
it and publishes immutable frames here. HTTP stream handlers only touch this
hub, never the engine process or the line protocol.

Wire frame: ``<4sIIII>`` = magic ``LVFR``, width, height, frame number and
virtual time in milliseconds (little-endian), followed by width * height * 4
RGBA bytes. ``frame number`` is the hub publish sequence so it keeps growing
even after recording reaches ``max_frames``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .wire import (
    HEADER_SIZE,
    HEADER_STRUCT as _HEADER,
    MAX_FRAME_BYTES,
    STREAM_MAGIC,
)

__all__ = [
    "HEADER_SIZE",
    "MAX_FRAME_BYTES",
    "STREAM_MAGIC",
    "LiveFrame",
    "LiveFrameHub",
    "encode_frame",
]


def encode_frame(
    width: int, height: int, frame_no: int, t_ms: int, pixels: bytes
) -> bytes:
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    if len(pixels) != width * height * 4:
        raise ValueError("raw frame size does not match its dimensions")
    return _HEADER.pack(STREAM_MAGIC, width, height, frame_no, t_ms) + pixels


@dataclass(frozen=True)
class LiveFrame:

    seq: int
    t_ms: int
    width: int
    height: int
    pixels: bytes

    def to_bytes(self) -> bytes:
        return encode_frame(
            self.width, self.height, self.seq, self.t_ms, self.pixels
        )


class LiveFrameHub:

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._seq = 0
        self._frame: LiveFrame | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._cond:
            return self._closed

    def publish(
        self, width: int, height: int, t_ms: int, pixels: bytes
    ) -> LiveFrame | None:
        if width <= 0 or height <= 0:
            raise ValueError("frame dimensions must be positive")
        expected = width * height * 4
        if expected > MAX_FRAME_BYTES:
            raise ValueError("frame is larger than the stream limit")
        if len(pixels) != expected:
            raise ValueError("raw frame size does not match its dimensions")
        with self._cond:
            if self._closed:
                return None
            self._seq += 1
            frame = LiveFrame(
                seq=self._seq,
                t_ms=max(0, int(t_ms)),
                width=width,
                height=height,
                pixels=bytes(pixels),
            )
            self._frame = frame
            self._cond.notify_all()
            return frame

    def wait_next(
        self, last_seq: int, timeout: float | None = None
    ) -> LiveFrame | None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while True:
                frame = self._frame
                if frame is not None and frame.seq > last_seq:
                    return frame
                if self._closed:
                    return None
                if deadline is None:
                    self._cond.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
