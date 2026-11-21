from __future__ import annotations

import struct
from typing import Any

STREAM_MAGIC = b"LVFR"
PIXEL_STRIDE = 4
HEADER_FIELDS = (
    ("magic", "4s"),
    ("width", "I"),
    ("height", "I"),
    ("frameNo", "I"),
    ("tMs", "I"),
)
HEADER_FORMAT = "<" + "".join(fmt for _, fmt in HEADER_FIELDS)
HEADER_STRUCT = struct.Struct(HEADER_FORMAT)
HEADER_SIZE = HEADER_STRUCT.size
MAX_FRAME_BYTES = 64 * 1024 * 1024
PAGE_HEARTBEAT_INTERVAL_MS = 10000


def header_fields() -> dict[str, int]:
    offsets: dict[str, int] = {}
    offset = 0
    for name, fmt in HEADER_FIELDS:
        offsets[name] = offset
        offset += struct.calcsize(fmt)
    return offsets


def page_config() -> dict[str, Any]:
    return {
        "magic": STREAM_MAGIC.decode("ascii"),
        "headerSize": HEADER_SIZE,
        "headerFields": header_fields(),
        "pixelStride": PIXEL_STRIDE,
        "maxFrameBytes": MAX_FRAME_BYTES,
        "heartbeatMs": PAGE_HEARTBEAT_INTERVAL_MS,
    }
