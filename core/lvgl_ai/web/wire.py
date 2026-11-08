"""Single source for the live preview wire format and the page heartbeat.

The C engine writes raw ``live.rgba``; Python packs each hub frame with the
header layout below and the browser parses the same layout from the config that
``page_render.py`` injects into the rendered page. Keeping the magic, header fields,
pixel stride, frame limit and heartbeat interval here means the JS parser
cannot silently drift from the Python encoder while every Python test stays
green.
"""

from __future__ import annotations

import struct
from typing import Any

STREAM_MAGIC = b"LVFR"
PIXEL_STRIDE = 4
# Field name (as the browser sees it) and struct format, in wire order.
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
# The page refreshes its id every 10 s; the server treats a page unseen for
# two minutes as gone (PAGE_HEARTBEAT_TTL_S).
PAGE_HEARTBEAT_INTERVAL_MS = 10000


def header_fields() -> dict[str, int]:
    """Byte offsets derived from the one header layout, for the JS parser."""
    offsets: dict[str, int] = {}
    offset = 0
    for name, fmt in HEADER_FIELDS:
        offsets[name] = offset
        offset += struct.calcsize(fmt)
    return offsets


def page_config() -> dict[str, Any]:
    """Values the browser needs to parse frames and refresh its page id."""
    return {
        "magic": STREAM_MAGIC.decode("ascii"),
        "headerSize": HEADER_SIZE,
        "headerFields": header_fields(),
        "pixelStride": PIXEL_STRIDE,
        "maxFrameBytes": MAX_FRAME_BYTES,
        "heartbeatMs": PAGE_HEARTBEAT_INTERVAL_MS,
    }
