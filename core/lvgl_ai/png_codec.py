"""Crop regions from session PNGs without Pillow or ffmpeg.

Frames and snapshots written by the engine are ordinary non-interlaced 8-bit
PNGs (RGB for the current XRGB8888 display). This module decodes the subset
needed by the evidence tools, crops an annotation box, and re-encodes a PNG.

Supported color types: grayscale (0), RGB (2), grayscale+alpha (4), RGBA (6);
bit depth 8, interlace 0. Anything else raises :class:`PngError` with the
actual header values so the caller knows which codec to extend.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Iterable

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


class PngError(ValueError):
    """A PNG is malformed or uses an unsupported subset."""


@dataclass(frozen=True)
class Region:
    """A display-pixel rectangle, the same coordinate space as annotations."""

    x: int
    y: int
    w: int
    h: int

    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.h

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    def clipped(self, width: int, height: int) -> "Region":
        x0 = max(0, self.x)
        y0 = max(0, self.y)
        x1 = min(width, self.x1)
        y1 = min(height, self.y1)
        if x1 <= x0 or y1 <= y0:
            raise PngError(
                f"region {self.as_dict()} does not intersect {width}x{height}"
            )
        return Region(x0, y0, x1 - x0, y1 - y0)


@dataclass(frozen=True)
class PngImage:
    width: int
    height: int
    color_type: int
    rows: tuple[bytes, ...]


def _read_chunks(data: bytes) -> Iterable[tuple[bytes, bytes]]:
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("not a PNG (bad signature)")
    pos = len(PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > len(data):
            raise PngError(f"truncated {chunk_type!r} chunk")
        payload = data[start:end]
        expected_crc = struct.unpack(">I", data[end:end + 4])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise PngError(f"bad CRC for {chunk_type!r} chunk")
        yield chunk_type, payload
        pos = end + 4


def decode_png(data: bytes) -> PngImage:
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()
    for chunk_type, payload in _read_chunks(data):
        if chunk_type == b"IHDR":
            if len(payload) != 13:
                raise PngError("malformed IHDR")
            (width, height, bit_depth, color_type,
             compression, filter_method, interlace) = struct.unpack(
                ">IIBBBBB", payload)
            if compression != 0 or filter_method != 0:
                raise PngError("unsupported PNG compression/filter method")
            if bit_depth != 8:
                raise PngError(f"unsupported PNG bit depth {bit_depth}")
            if interlace != 0:
                raise PngError("interlaced PNGs are not supported")
            if color_type not in CHANNELS:
                raise PngError(
                    f"unsupported PNG color type {color_type} "
                    "(supported: 0, 2, 4, 6)"
                )
        elif chunk_type == b"IDAT":
            idat += payload
        elif chunk_type == b"IEND":
            break
    if width is None or height is None:
        raise PngError("PNG has no IHDR")
    if width <= 0 or height <= 0:
        raise PngError(f"invalid PNG size {width}x{height}")
    if not idat:
        raise PngError("PNG has no IDAT data")

    channels = CHANNELS[color_type]
    stride = width * channels
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise PngError(f"cannot inflate PNG data: {exc}") from exc
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise PngError(
            f"unexpected PNG data size {len(raw)}; expected {expected}"
        )

    rows: list[bytes] = []
    previous = bytes(stride)
    pos = 0
    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        filtered = raw[pos:pos + stride]
        pos += stride
        if filter_type == 0:
            row = filtered
        elif filter_type == 1:
            row = _filter_sub(filtered, channels)
        elif filter_type == 2:
            row = _filter_up(filtered, previous)
        elif filter_type == 3:
            row = _filter_average(filtered, previous, channels)
        elif filter_type == 4:
            row = _filter_paeth(filtered, previous, channels)
        else:
            raise PngError(f"unsupported PNG filter type {filter_type}")
        rows.append(row)
        previous = row
    return PngImage(width, height, color_type, tuple(rows))


def _filter_sub(data: bytes, bpp: int) -> bytes:
    out = bytearray(len(data))
    for index, value in enumerate(data):
        left = out[index - bpp] if index >= bpp else 0
        out[index] = (value + left) & 0xFF
    return bytes(out)


def _filter_up(data: bytes, previous: bytes) -> bytes:
    return bytes((value + up) & 0xFF for value, up in zip(data, previous))


def _filter_average(data: bytes, previous: bytes, bpp: int) -> bytes:
    out = bytearray(len(data))
    for index, value in enumerate(data):
        left = out[index - bpp] if index >= bpp else 0
        out[index] = (value + ((left + previous[index]) >> 1)) & 0xFF
    return bytes(out)


def _filter_paeth(data: bytes, previous: bytes, bpp: int) -> bytes:
    out = bytearray(len(data))
    for index, value in enumerate(data):
        left = out[index - bpp] if index >= bpp else 0
        up = previous[index]
        upper_left = previous[index - bpp] if index >= bpp else 0
        predictor = _paeth(left, up, upper_left)
        out[index] = (value + predictor) & 0xFF
    return bytes(out)


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    dist_left = abs(estimate - left)
    dist_up = abs(estimate - up)
    dist_upper_left = abs(estimate - upper_left)
    if dist_left <= dist_up and dist_left <= dist_upper_left:
        return left
    if dist_up <= dist_upper_left:
        return up
    return upper_left


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def encode_png(image: PngImage) -> bytes:
    channels = CHANNELS[image.color_type]
    stride = image.width * channels
    if len(image.rows) != image.height:
        raise PngError("row count does not match image height")
    for row in image.rows:
        if len(row) != stride:
            raise PngError("row width does not match image width")
    raw = bytearray()
    for row in image.rows:
        raw.append(0)  # filter: None
        raw += row
    ihdr = struct.pack(
        ">IIBBBBB",
        image.width,
        image.height,
        8,
        image.color_type,
        0,
        0,
        0,
    )
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def crop_png(data: bytes, region: Region) -> tuple[bytes, Region, PngImage]:
    """Crop ``region`` out of ``data``; returns (PNG bytes, clipped box, image)."""
    image = decode_png(data)
    box = region.clipped(image.width, image.height)
    channels = CHANNELS[image.color_type]
    start = box.x * channels
    end = box.x1 * channels
    rows = tuple(row[start:end] for row in image.rows[box.y:box.y1])
    cropped = PngImage(box.w, box.h, image.color_type, rows)
    return encode_png(cropped), box, cropped
