"""Read and crop session PNGs without Pillow or ffmpeg.

Frames and snapshots written by the engine are ordinary non-interlaced 8-bit
PNGs (RGB for the current XRGB8888 display). This module decodes the subset
needed by the evidence tools, reads pixels, crops boxes, arranges labeled
contact sheets, compares image pairs with an optional heatmap, and re-encodes
PNGs.

Supported color types: grayscale (0), RGB (2), grayscale+alpha (4), RGBA (6);
bit depth 8, interlace 0. Anything else raises :class:`PngError` with the
actual header values so the caller knows which codec to extend.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Iterable, Sequence

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}

DEFAULT_CONTACT_COLUMNS = 4
DEFAULT_CONTACT_TILE_WIDTH = 240
DEFAULT_CONTACT_TILE_HEIGHT = 180
MIN_CONTACT_TILE_SIDE = 32
MAX_CONTACT_COLUMNS = 8
MAX_CONTACT_TILES = 32
MAX_CONTACT_TILE_SIDE = 480
MAX_CONTACT_SHEET_SIDE = 4096
MAX_CONTACT_SHEET_PIXELS = 4_000_000
MAX_SOURCE_SIDE = 8192
MAX_SOURCE_PIXELS = 16_000_000
MAX_COMPARE_SIDE = 4096
MAX_COMPARE_PIXELS = 4_000_000

_CONTACT_GAP = 8
_TILE_PADDING = 4
_LABEL_SCALE = 2
_LABEL_BAND = _LABEL_SCALE * 7 + _TILE_PADDING
_BACKGROUND = (24, 24, 24)
_HEATMAP_BACKGROUND_BYTES = bytes(_BACKGROUND)
_TILE_BACKGROUND = (48, 48, 48)
_TILE_BORDER = (96, 96, 96)
_LABEL_COLOR = (255, 255, 255)


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


@dataclass(frozen=True)
class PngHeader:
    width: int
    height: int
    color_type: int


@dataclass(frozen=True)
class ImageComparison:

    width: int
    height: int
    bbox: Region | None
    changed_px: int
    changed_ratio: float
    max_delta: float
    heatmap: PngImage | None

    def to_png(self) -> bytes:
        if self.heatmap is None:
            raise PngError("comparison was built without a heatmap")
        return encode_png(self.heatmap)


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


def _parse_ihdr(payload: bytes) -> PngHeader:
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
    if width <= 0 or height <= 0:
        raise PngError(f"invalid PNG size {width}x{height}")
    return PngHeader(width, height, color_type)


def read_png_header(data: bytes) -> PngHeader:
    for chunk_type, payload in _read_chunks(data):
        if chunk_type == b"IHDR":
            return _parse_ihdr(payload)
    raise PngError("PNG has no IHDR")


def decode_png(data: bytes) -> PngImage:
    header: PngHeader | None = None
    idat = bytearray()
    for chunk_type, payload in _read_chunks(data):
        if chunk_type == b"IHDR":
            header = _parse_ihdr(payload)
        elif chunk_type == b"IDAT":
            idat += payload
        elif chunk_type == b"IEND":
            break
    if header is None:
        raise PngError("PNG has no IHDR")
    if not idat:
        raise PngError("PNG has no IDAT data")

    width, height, color_type = header.width, header.height, header.color_type
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
        raw.append(0)
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
    image = decode_png(data)
    box = region.clipped(image.width, image.height)
    channels = CHANNELS[image.color_type]
    start = box.x * channels
    end = box.x1 * channels
    rows = tuple(row[start:end] for row in image.rows[box.y:box.y1])
    cropped = PngImage(box.w, box.h, image.color_type, rows)
    return encode_png(cropped), box, cropped


def read_pixel(data: bytes, x: int, y: int) -> tuple[int, int, int]:
    return pixel_at(decode_png(data), x, y)


def compare_png(
    left: bytes, right: bytes, *, heatmap: bool = False
) -> ImageComparison:
    """Compare two same-size PNGs and report changed-pixel statistics.

    A pixel changes when any RGB channel differs; alpha is ignored.
    ``max_delta`` is the largest channel difference divided by 255, matching
    the frame-diff evidence. With ``heatmap=True`` the result carries an RGB
    image where changed pixels are yellow-to-red by delta and unchanged pixels
    stay dark.
    """
    left_header = read_png_header(left)
    right_header = read_png_header(right)
    for header, side in ((left_header, "left"), (right_header, "right")):
        _check_source(
            header,
            side=side,
            max_side=MAX_COMPARE_SIDE,
            max_pixels=MAX_COMPARE_PIXELS,
            limit_name="compare",
        )
    if (left_header.width, left_header.height) != (
        right_header.width,
        right_header.height,
    ):
        raise PngError(
            f"image sizes differ: left is "
            f"{left_header.width}x{left_header.height}, right is "
            f"{right_header.width}x{right_header.height}; compare needs "
            "identical dimensions"
        )
    left_image = decode_png(left)
    right_image = decode_png(right)
    width, height = left_image.width, left_image.height
    left_channels = CHANNELS[left_image.color_type]
    right_channels = CHANNELS[right_image.color_type]
    left_gray = left_image.color_type in (0, 4)
    right_gray = right_image.color_type in (0, 4)

    changed_px = 0
    max_delta = 0
    min_x = min_y = None
    max_x = max_y = 0
    heatmap_rows: list[bytes] = []
    for y in range(height):
        left_row = left_image.rows[y]
        right_row = right_image.rows[y]
        target = bytearray(width * 3) if heatmap else None
        for x in range(width):
            left_offset = x * left_channels
            right_offset = x * right_channels
            if left_gray:
                left_pixel = (left_row[left_offset],) * 3
            else:
                left_pixel = left_row[left_offset:left_offset + 3]
            if right_gray:
                right_pixel = (right_row[right_offset],) * 3
            else:
                right_pixel = right_row[right_offset:right_offset + 3]
            delta = max(
                abs(left_pixel[0] - right_pixel[0]),
                abs(left_pixel[1] - right_pixel[1]),
                abs(left_pixel[2] - right_pixel[2]),
            )
            if delta == 0:
                if target is not None:
                    target[x * 3:x * 3 + 3] = _HEATMAP_BACKGROUND_BYTES
                continue
            changed_px += 1
            max_delta = max(max_delta, delta)
            min_x = x if min_x is None else min(min_x, x)
            min_y = y if min_y is None else min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            if target is not None:
                target[x * 3:x * 3 + 3] = bytes(
                    (255, 255 - delta, 0)
                )
        if target is not None:
            heatmap_rows.append(bytes(target))

    bbox = None
    if changed_px:
        bbox = Region(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    heatmap_image = None
    if heatmap:
        heatmap_image = PngImage(
            width, height, 2, tuple(heatmap_rows)
        )
    return ImageComparison(
        width=width,
        height=height,
        bbox=bbox,
        changed_px=changed_px,
        changed_ratio=changed_px / (width * height),
        max_delta=max_delta / 255.0,
        heatmap=heatmap_image,
    )


def pixel_at(image: PngImage, x: int, y: int) -> tuple[int, int, int]:
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise PngError(
            f"pixel {x},{y} outside image {image.width}x{image.height}"
        )
    channels = CHANNELS[image.color_type]
    offset = x * channels
    row = image.rows[y]
    if image.color_type in (0, 4):
        gray = row[offset]
        return (gray, gray, gray)
    return (row[offset], row[offset + 1], row[offset + 2])


@dataclass(frozen=True)
class ContactTile:

    label: str
    x: int
    y: int
    width: int
    height: int
    image_x: int
    image_y: int
    image_width: int
    image_height: int


@dataclass(frozen=True)
class ContactSheet:

    image: PngImage
    tiles: tuple[ContactTile, ...]
    columns: int
    rows: int

    def to_png(self) -> bytes:
        return encode_png(self.image)


def build_contact_sheet(
    items: Sequence[tuple[str, bytes]],
    *,
    columns: int = DEFAULT_CONTACT_COLUMNS,
    tile_width: int = DEFAULT_CONTACT_TILE_WIDTH,
    tile_height: int = DEFAULT_CONTACT_TILE_HEIGHT,
) -> ContactSheet:
    entries = list(items)
    _validate_contact_layout(entries, columns, tile_width, tile_height)
    gap = _CONTACT_GAP
    rows = (len(entries) + columns - 1) // columns
    width = columns * tile_width + (columns + 1) * gap
    height = rows * tile_height + (rows + 1) * gap
    if (
        width > MAX_CONTACT_SHEET_SIDE
        or height > MAX_CONTACT_SHEET_SIDE
        or width * height > MAX_CONTACT_SHEET_PIXELS
    ):
        raise PngError(
            f"contact sheet would be {width}x{height} "
            f"({width * height} px), above the limit of "
            f"{MAX_CONTACT_SHEET_PIXELS} px or {MAX_CONTACT_SHEET_SIDE} per "
            "side; reduce --columns or --tile"
        )

    background = bytes(_BACKGROUND)
    sheet_rows = [
        bytearray(background * width) for _ in range(height)
    ]
    tiles: list[ContactTile] = []
    for index, (label, data) in enumerate(entries):
        header = read_png_header(data)
        _check_source(
            header,
            side="source",
            max_side=MAX_SOURCE_SIDE,
            max_pixels=MAX_SOURCE_PIXELS,
            limit_name="contact-sheet",
        )
        image = decode_png(data)
        column = index % columns
        row = index // columns
        tile_x = gap + column * (tile_width + gap)
        tile_y = gap + row * (tile_height + gap)
        _fill_rect(
            sheet_rows, width, height, tile_x, tile_y, tile_width,
            tile_height, _TILE_BACKGROUND,
        )
        _stroke_rect(
            sheet_rows, width, height, tile_x, tile_y, tile_width,
            tile_height, _TILE_BORDER,
        )
        _draw_label(
            sheet_rows,
            width,
            height,
            tile_x + _TILE_PADDING,
            tile_y + _TILE_PADDING,
            tile_width - 2 * _TILE_PADDING,
            label,
        )
        area_x = tile_x + _TILE_PADDING
        area_y = tile_y + _LABEL_BAND
        area_width = tile_width - 2 * _TILE_PADDING
        area_height = tile_height - _LABEL_BAND - _TILE_PADDING
        scale = min(
            area_width / image.width, area_height / image.height, 1.0
        )
        image_width = max(1, int(image.width * scale))
        image_height = max(1, int(image.height * scale))
        image_x = area_x + (area_width - image_width) // 2
        image_y = area_y + (area_height - image_height) // 2
        _blit_rgb(
            sheet_rows,
            width,
            image,
            image_x,
            image_y,
            image_width,
            image_height,
        )
        tiles.append(
            ContactTile(
                label=label,
                x=tile_x,
                y=tile_y,
                width=tile_width,
                height=tile_height,
                image_x=image_x,
                image_y=image_y,
                image_width=image_width,
                image_height=image_height,
            )
        )
    return ContactSheet(
        image=PngImage(width, height, 2, tuple(bytes(row) for row in sheet_rows)),
        tiles=tuple(tiles),
        columns=columns,
        rows=rows,
    )


def _validate_contact_layout(
    entries: list[tuple[str, bytes]],
    columns: int,
    tile_width: int,
    tile_height: int,
) -> None:
    if not entries:
        raise PngError("contact sheet needs at least one image")
    if len(entries) > MAX_CONTACT_TILES:
        raise PngError(
            f"contact sheet accepts at most {MAX_CONTACT_TILES} tiles, "
            f"got {len(entries)}"
        )
    if not 1 <= columns <= MAX_CONTACT_COLUMNS:
        raise PngError(
            f"contact sheet columns must be 1..{MAX_CONTACT_COLUMNS}, "
            f"got {columns}"
        )
    for side in (tile_width, tile_height):
        if not MIN_CONTACT_TILE_SIDE <= side <= MAX_CONTACT_TILE_SIDE:
            raise PngError(
                f"contact sheet tile side must be "
                f"{MIN_CONTACT_TILE_SIDE}..{MAX_CONTACT_TILE_SIDE}, got {side}"
            )
    for label, _data in entries:
        if not isinstance(label, str):
            raise PngError("contact sheet labels must be strings")


def _check_source(
    header: PngHeader,
    *,
    side: str,
    max_side: int,
    max_pixels: int,
    limit_name: str,
) -> None:
    pixels = header.width * header.height
    if (
        header.width > max_side
        or header.height > max_side
        or pixels > max_pixels
    ):
        raise PngError(
            f"{side} image is {header.width}x{header.height} ({pixels} px), "
            f"above the {limit_name} limit of {max_pixels} px or "
            f"{max_side} per side; crop it first"
        )


def _fill_rect(
    rows: list[bytearray],
    sheet_width: int,
    sheet_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(sheet_width, x + width)
    y1 = min(sheet_height, y + height)
    if x1 <= x0 or y1 <= y0:
        return
    pixel = bytes(color) * (x1 - x0)
    for row in range(y0, y1):
        rows[row][x0 * 3:x1 * 3] = pixel


def _stroke_rect(
    rows: list[bytearray],
    sheet_width: int,
    sheet_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    _fill_rect(rows, sheet_width, sheet_height, x, y, width, 1, color)
    _fill_rect(rows, sheet_width, sheet_height, x, y + height - 1, width, 1, color)
    _fill_rect(rows, sheet_width, sheet_height, x, y, 1, height, color)
    _fill_rect(rows, sheet_width, sheet_height, x + width - 1, y, 1, height, color)


def _draw_label(
    rows: list[bytearray],
    sheet_width: int,
    sheet_height: int,
    x: int,
    y: int,
    max_width: int,
    label: str,
) -> None:
    advance = (_LABEL_SCALE * 6) or 1
    max_chars = max(1, max_width // advance)
    text = label.upper()[:max_chars]
    for index, character in enumerate(text):
        glyph = _FONT_5X7.get(character, _FONT_5X7["?"])
        char_x = x + index * advance
        for row_index, bits in enumerate(glyph):
            for column in range(5):
                if bits & (1 << (4 - column)):
                    _fill_rect(
                        rows,
                        sheet_width,
                        sheet_height,
                        char_x + column * _LABEL_SCALE,
                        y + row_index * _LABEL_SCALE,
                        _LABEL_SCALE,
                        _LABEL_SCALE,
                        _LABEL_COLOR,
                    )


def _blit_rgb(
    rows: list[bytearray],
    sheet_width: int,
    source: PngImage,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    source_rows = _scale_rgb_rows(source, width, height)
    for offset, source_row in enumerate(source_rows):
        target_y = y + offset
        if 0 <= target_y < len(rows):
            start = x * 3
            rows[target_y][start:start + width * 3] = source_row


def _scale_rgb_rows(
    image: PngImage, width: int, height: int
) -> tuple[bytes, ...]:
    channels = CHANNELS[image.color_type]
    grayscale = image.color_type in (0, 4)
    scaled: list[bytes] = []
    for y in range(height):
        source_y = min(image.height - 1, y * image.height // height)
        source_row = image.rows[source_y]
        output = bytearray(width * 3)
        for x in range(width):
            source_x = min(image.width - 1, x * image.width // width)
            offset = source_x * channels
            if grayscale:
                gray = source_row[offset]
                output[x * 3:x * 3 + 3] = bytes((gray, gray, gray))
            else:
                output[x * 3:x * 3 + 3] = source_row[offset:offset + 3]
        scaled.append(bytes(output))
    return tuple(scaled)


_FONT_5X7: dict[str, tuple[int, ...]] = {
    " ": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
    "0": (0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110),
    "1": (0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "2": (0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b11111),
    "3": (0b11110, 0b00001, 0b00001, 0b01110, 0b00001, 0b00001, 0b11110),
    "4": (0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010),
    "5": (0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110),
    "6": (0b00110, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110),
    "7": (0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000),
    "8": (0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110),
    "9": (0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b00010, 0b01100),
    "A": (0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "B": (0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110),
    "C": (0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110),
    "D": (0b11110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b11110),
    "E": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111),
    "F": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000),
    "G": (0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01110),
    "H": (0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "I": (0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "J": (0b00111, 0b00010, 0b00010, 0b00010, 0b00010, 0b10010, 0b01100),
    "K": (0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001),
    "L": (0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111),
    "M": (0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001),
    "N": (0b10001, 0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001),
    "O": (0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "P": (0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000),
    "Q": (0b01110, 0b10001, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101),
    "R": (0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001),
    "S": (0b01110, 0b10001, 0b10000, 0b01110, 0b00001, 0b10001, 0b01110),
    "T": (0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100),
    "U": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "V": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100),
    "W": (0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b10101, 0b01010),
    "X": (0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001),
    "Y": (0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100),
    "Z": (0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111),
    "-": (0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000),
    "_": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b11111),
    ".": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00110, 0b00110),
    ",": (0b00000, 0b00000, 0b00000, 0b00000, 0b00110, 0b00110, 0b00100),
    ":": (0b00000, 0b00110, 0b00110, 0b00000, 0b00110, 0b00110, 0b00000),
    ";": (0b00000, 0b00110, 0b00110, 0b00000, 0b00110, 0b00110, 0b00100),
    "/": (0b00001, 0b00010, 0b00010, 0b00100, 0b01000, 0b01000, 0b10000),
    "\\": (0b10000, 0b01000, 0b01000, 0b00100, 0b00010, 0b00010, 0b00001),
    "?": (0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b00000, 0b00100),
    "#": (0b01010, 0b11111, 0b01010, 0b01010, 0b11111, 0b01010, 0b00000),
    "+": (0b00000, 0b00100, 0b00100, 0b11111, 0b00100, 0b00100, 0b00000),
    "=": (0b00000, 0b00000, 0b11111, 0b00000, 0b11111, 0b00000, 0b00000),
    "(": (0b00010, 0b00100, 0b01000, 0b01000, 0b01000, 0b00100, 0b00010),
    ")": (0b01000, 0b00100, 0b00010, 0b00010, 0b00010, 0b00100, 0b01000),
    "[": (0b01110, 0b01000, 0b01000, 0b01000, 0b01000, 0b01000, 0b01110),
    "]": (0b01110, 0b00010, 0b00010, 0b00010, 0b00010, 0b00010, 0b01110),
    "%": (0b11001, 0b11010, 0b00010, 0b00100, 0b01000, 0b01011, 0b10011),
    "*": (0b00000, 0b10101, 0b01110, 0b11111, 0b01110, 0b10101, 0b00000),
}
