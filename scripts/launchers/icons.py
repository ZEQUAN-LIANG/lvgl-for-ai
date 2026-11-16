"""Draw the launcher icons and write multi-size .ico files.

Pure standard library. Shapes are laid out in a 1024-unit design space, rendered
4x larger with premultiplied-alpha scanline fills, then box-filtered down to
each icon size and stored as BMP-in-ICO entries.
"""

from __future__ import annotations

import argparse
import math
import struct
from array import array
from pathlib import Path
from typing import Tuple

ICON_DIR = Path(__file__).resolve().parent / "icons"
ICON_NAMES = ("lvgl-verify-loop-viewer", "sifli-host")
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
DESIGN = 1024.0
SUPERSAMPLE = 4

Color = Tuple[float, float, float, float]

NAVY = (0.118, 0.165, 0.267, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
BORDER = (0.788, 0.847, 0.941, 1.0)
BG_TOP = (1.0, 1.0, 1.0, 1.0)
BG_BOTTOM = (0.914, 0.945, 1.0, 1.0)
CYAN = (0.133, 0.827, 0.933, 1.0)
VIOLET = (0.545, 0.361, 0.965, 1.0)
AMBER = (0.961, 0.620, 0.043, 1.0)
ORANGE = (0.984, 0.573, 0.235, 1.0)


class Canvas:
    def __init__(self, size: int) -> None:
        self.size = size
        self.buf = array("f", [0.0]) * (size * size * 4)

    def blend(
        self, pixel: int, red: float, green: float, blue: float, alpha: float
    ) -> None:
        if alpha <= 0.0:
            return
        if alpha > 1.0:
            alpha = 1.0
        buf = self.buf
        index = pixel * 4
        inv = 1.0 - alpha
        buf[index] = red * alpha + buf[index] * inv
        buf[index + 1] = green * alpha + buf[index + 1] * inv
        buf[index + 2] = blue * alpha + buf[index + 2] * inv
        buf[index + 3] = alpha + buf[index + 3] * inv


def fill_rounded_rect(
    canvas: Canvas,
    left: float,
    top: float,
    right: float,
    bottom: float,
    radius: float,
    color: Color,
    color_bottom: Color | None = None,
) -> None:
    scale = canvas.size / DESIGN
    left *= scale
    top *= scale
    right *= scale
    bottom *= scale
    radius = max(0.0, radius * scale)
    color_bottom = color if color_bottom is None else color_bottom
    start = max(0, int(math.floor(top)))
    end = min(canvas.size, int(math.ceil(bottom)))
    for py in range(start, end):
        cy = py + 0.5
        if cy < top or cy > bottom:
            continue
        row_cover = min(py + 1.0, bottom) - max(float(py), top)
        if row_cover <= 0.0:
            continue
        inset = 0.0
        if radius > 0.0:
            if cy < top + radius:
                dy = top + radius - cy
                inset = radius - math.sqrt(max(0.0, radius * radius - dy * dy))
            elif cy > bottom - radius:
                dy = cy - (bottom - radius)
                inset = radius - math.sqrt(max(0.0, radius * radius - dy * dy))
        xa = left + inset
        xb = right - inset
        if xb <= xa:
            continue
        t = (cy - top) / (bottom - top) if bottom > top else 0.0
        red = color[0] + (color_bottom[0] - color[0]) * t
        green = color[1] + (color_bottom[1] - color[1]) * t
        blue = color[2] + (color_bottom[2] - color[2]) * t
        alpha = color[3] + (color_bottom[3] - color[3]) * t
        row = py * canvas.size
        first = max(0, int(math.floor(xa)))
        last = min(canvas.size - 1, int(math.ceil(xb)) - 1)
        for px in range(first, last + 1):
            cover = min(px + 1.0, xb) - max(float(px), xa)
            if cover > 0.0:
                canvas.blend(
                    row + px, red, green, blue, alpha * cover * row_cover
                )


def fill_circle(
    canvas: Canvas, cx: float, cy: float, radius: float, color: Color
) -> None:
    scale = canvas.size / DESIGN
    cx *= scale
    cy *= scale
    radius *= scale
    start = max(0, int(math.floor(cy - radius)))
    end = min(canvas.size, int(math.ceil(cy + radius)))
    for py in range(start, end):
        dy = py + 0.5 - cy
        if abs(dy) > radius:
            continue
        half = math.sqrt(max(0.0, radius * radius - dy * dy))
        xa = cx - half
        xb = cx + half
        row = py * canvas.size
        first = max(0, int(math.floor(xa)))
        last = min(canvas.size - 1, int(math.ceil(xb)) - 1)
        for px in range(first, last + 1):
            cover = min(px + 1.0, xb) - max(float(px), xa)
            if cover > 0.0:
                canvas.blend(
                    row + px, color[0], color[1], color[2], color[3] * cover
                )


def _draw_background(canvas: Canvas) -> None:
    fill_rounded_rect(canvas, 16, 16, 1008, 1008, 232, BORDER)
    fill_rounded_rect(canvas, 30, 30, 994, 994, 218, BG_TOP, BG_BOTTOM)


def _draw_viewer(canvas: Canvas, size: int) -> None:
    _draw_background(canvas)
    fill_rounded_rect(canvas, 170, 210, 854, 700, 64, NAVY)
    fill_rounded_rect(canvas, 214, 254, 810, 656, 36, CYAN, VIOLET)
    bars = ((300, 470), (424, 390), (548, 300))
    for left, top in bars:
        fill_rounded_rect(canvas, left, top, left + 76, 590, 26, WHITE)
    fill_rounded_rect(canvas, 462, 700, 562, 784, 8, NAVY)
    fill_rounded_rect(canvas, 322, 784, 702, 860, 38, NAVY)


def _draw_host(canvas: Canvas, size: int) -> None:
    _draw_background(canvas)
    centers = (400, 512, 624) if size > 32 else (426, 598)
    thickness = 54.0 if size > 32 else 72.0
    half = thickness / 2.0
    for center in centers:
        fill_rounded_rect(
            canvas, 146, center - half, 306, center + half, 24, AMBER
        )
        fill_rounded_rect(
            canvas, 718, center - half, 878, center + half, 24, AMBER
        )
        fill_rounded_rect(
            canvas, center - half, 146, center + half, 306, 24, AMBER
        )
        fill_rounded_rect(
            canvas, center - half, 718, center + half, 878, 24, AMBER
        )
    fill_rounded_rect(canvas, 296, 296, 728, 728, 96, NAVY)
    fill_rounded_rect(canvas, 372, 372, 652, 652, 44, AMBER, ORANGE)
    fill_circle(canvas, 512, 512, 58, WHITE)
    fill_circle(canvas, 512, 512, 30, NAVY)


def render_icon(name: str, size: int) -> bytes:
    canvas = Canvas(size * SUPERSAMPLE)
    if name == "lvgl-verify-loop-viewer":
        _draw_viewer(canvas, size)
    elif name == "sifli-host":
        _draw_host(canvas, size)
    else:
        raise ValueError(f"unknown icon: {name}")
    return _downsample(canvas, size)


def _downsample(canvas: Canvas, size: int) -> bytes:
    buf = canvas.buf
    samples = canvas.size // size
    inv_area = 1.0 / (samples * samples)
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            sr = sg = sb = sa = 0.0
            for sy in range(samples):
                row = (y * samples + sy) * canvas.size + x * samples
                for sx in range(samples):
                    index = (row + sx) * 4
                    sa += buf[index + 3]
                    sr += buf[index]
                    sg += buf[index + 1]
                    sb += buf[index + 2]
            if sa <= 0.0:
                continue
            target = (y * size + x) * 4
            out[target] = max(0, min(255, int(round(sr / sa * 255.0))))
            out[target + 1] = max(0, min(255, int(round(sg / sa * 255.0))))
            out[target + 2] = max(0, min(255, int(round(sb / sa * 255.0))))
            out[target + 3] = max(
                0, min(255, int(round(sa * inv_area * 255.0)))
            )
    return bytes(out)


def _bmp_entry(size: int, rgba: bytes) -> bytes:
    mask_stride = ((size + 31) // 32) * 4
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        size * size * 4 + mask_stride * size,
        0,
        0,
        0,
        0,
    )
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        base = y * size * 4
        for x in range(size):
            index = base + x * 4
            pixels += bytes(
                (
                    rgba[index + 2],
                    rgba[index + 1],
                    rgba[index],
                    rgba[index + 3],
                )
            )
    mask = bytearray(mask_stride * size)
    for y in range(size):
        base = y * size * 4
        row = (size - 1 - y) * mask_stride
        for x in range(size):
            if rgba[base + x * 4 + 3] == 0:
                mask[row + x // 8] |= 0x80 >> (x % 8)
    return header + bytes(pixels) + bytes(mask)


def write_ico(path: Path, name: str) -> None:
    entries = bytearray()
    images = bytearray()
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        blob = _bmp_entry(size, render_icon(name, size))
        dimension = 0 if size == 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(blob), offset
        )
        images += blob
        offset += len(blob)
    path.write_bytes(
        struct.pack("<HHH", 0, 1, len(SIZES)) + bytes(entries) + bytes(images)
    )


def write_all(output_dir: Path = ICON_DIR) -> list:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in ICON_NAMES:
        path = output_dir / f"{name}.ico"
        write_ico(path, name)
        paths.append(path)
    return paths


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate launcher .ico files."
    )
    parser.add_argument("--output-dir", type=Path, default=ICON_DIR)
    args = parser.parse_args(argv)
    for path in write_all(args.output_dir):
        print(f"[icons] wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
