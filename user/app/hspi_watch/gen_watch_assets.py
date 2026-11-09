#!/usr/bin/env python3
"""Generate Huangshan Pi watch PNG sources and the local C asset header."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

BG_W, BG_H = 390, 450
RING_SIZE = 280
HOUR_W, HOUR_H = 12, 96
MINUTE_W, MINUTE_H = 8, 136
SECOND_W, SECOND_H = 8, 160
CX, CY = BG_W // 2, BG_H // 2

GOLD = (200, 164, 100)
GOLD_BRIGHT = (230, 198, 140)
CREAM = (243, 235, 221)
RED = (224, 90, 79)


def put_rgb(buf, w, h, x, y, color):
    if 0 <= x < w and 0 <= y < h:
        i = (y * w + x) * 3
        buf[i:i + 3] = bytes(color)


def put_rgba(buf, w, h, x, y, color):
    if 0 <= x < w and 0 <= y < h:
        i = (y * w + x) * 4
        buf[i:i + 4] = bytes(color)


def fill_rect(buf, w, h, x0, y0, x1, y1, color, rgba):
    for y in range(max(0, y0), min(h, y1 + 1)):
        for x in range(max(0, x0), min(w, x1 + 1)):
            (put_rgba if rgba else put_rgb)(buf, w, h, x, y, color)


def draw_disc(buf, w, h, cx, cy, radius, color, rgba):
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                (put_rgba if rgba else put_rgb)(buf, w, h, x, y, color)


def draw_ring(buf, w, h, cx, cy, radius, width, color, rgba):
    inner = (radius - width) ** 2
    outer = (radius + width) ** 2
    for y in range(cy - radius - width, cy + radius + width + 1):
        for x in range(cx - radius - width, cx + radius + width + 1):
            dist = (x - cx) ** 2 + (y - cy) ** 2
            if inner <= dist <= outer:
                (put_rgba if rgba else put_rgb)(buf, w, h, x, y, color)


def draw_line(buf, w, h, x0, y0, x1, y1, color, thickness, rgba):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    radius = max(0, thickness // 2)
    while True:
        draw_disc(buf, w, h, x0, y0, radius, color, rgba)
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * err
        if twice >= dy:
            err += dy
            x0 += sx
        if twice <= dx:
            err += dx
            y0 += sy


def encode_png(width, height, pixels, channels):
    rows = []
    stride = width * channels
    for y in range(height):
        rows.append(b"\x00" + bytes(pixels[y * stride:(y + 1) * stride]))

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    color_type = 6 if channels == 4 else 2
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
    png += chunk(b"IEND", b"")
    return png


def build_background():
    buf = bytearray(BG_W * BG_H * 3)
    for y in range(BG_H):
        t = y / (BG_H - 1)
        color = (
            int(7 + 10 * t),
            int(10 + 15 * t),
            int(18 + 26 * t),
        )
        for x in range(BG_W):
            put_rgb(buf, BG_W, BG_H, x, y, color)

    draw_ring(buf, BG_W, BG_H, CX, CY, 168, 1, (86, 70, 44), False)
    draw_ring(buf, BG_W, BG_H, CX, CY, 164, 1, GOLD, False)
    for i in range(60):
        angle = math.radians(i * 6)
        inner = 138 if i % 5 == 0 else 146
        color = GOLD_BRIGHT if i % 5 == 0 else (120, 96, 58)
        x0 = CX + int(inner * math.sin(angle))
        y0 = CY - int(inner * math.cos(angle))
        x1 = CX + int(160 * math.sin(angle))
        y1 = CY - int(160 * math.cos(angle))
        draw_line(buf, BG_W, BG_H, x0, y0, x1, y1, color, 2 if i % 5 == 0 else 1, False)
    draw_disc(buf, BG_W, BG_H, CX, CY, 10, GOLD, False)
    draw_disc(buf, BG_W, BG_H, CX, CY, 4, (14, 11, 8), False)
    return buf


def build_ring():
    buf = bytearray(RING_SIZE * RING_SIZE * 4)
    center = RING_SIZE // 2
    draw_ring(buf, RING_SIZE, RING_SIZE, center, center, 128, 1, (200, 164, 100, 110), True)
    for i in range(24):
        angle = math.radians(i * 15)
        x = center + int(128 * math.sin(angle))
        y = center - int(128 * math.cos(angle))
        color = (*GOLD_BRIGHT, 255) if i % 6 == 0 else (140, 112, 68, 170)
        draw_disc(buf, RING_SIZE, RING_SIZE, x, y, 3, color, True)
    return buf


def build_pointer(width, height, body_width, color, tip_width):
    buf = bytearray(width * height * 4)
    cx = width // 2
    fill_rect(buf, width, height, cx - body_width // 2, tip_width, cx + body_width // 2, height - 3, color, True)
    for y in range(tip_width):
        half = max(1, int(body_width * (y + 1) / (2 * tip_width)))
        fill_rect(buf, width, height, cx - half, y, cx + half, y, color, True)
    draw_disc(buf, width, height, cx, height - 3, max(1, body_width // 2), color, True)
    return buf


def build_second_hand():
    buf = bytearray(SECOND_W * SECOND_H * 4)
    cx = SECOND_W // 2
    color = (*RED, 255)
    fill_rect(buf, SECOND_W, SECOND_H, cx - 1, 6, cx, SECOND_H - 3, color, True)
    draw_disc(buf, SECOND_W, SECOND_H, cx, SECOND_H - 3, 2, color, True)
    draw_disc(buf, SECOND_W, SECOND_H, cx, 6, 1, color, True)
    return buf


def rgb565_bytes(buf):
    values = []
    for i in range(0, len(buf), 3):
        r, g, b = buf[i], buf[i + 1], buf[i + 2]
        values.append(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    return values


def bgra_bytes(buf):
    out = bytearray(buf)
    for i in range(0, len(out), 4):
        out[i], out[i + 2] = out[i + 2], out[i]
    return out


def emit_array(lines, name, ctype, values, per_line):
    lines.append(f"static const {ctype} {name}[] = {{")
    for i in range(0, len(values), per_line):
        chunk = values[i:i + per_line]
        if ctype == "uint16_t":
            text = ", ".join(f"0x{value:04X}" for value in chunk)
        else:
            text = ", ".join(f"0x{value:02X}" for value in chunk)
        lines.append(f"    {text},")
    lines.append("};")
    lines.append("")


def emit_dsc(lines, name, cf, width, height, stride):
    lines.extend(
        [
            f"static const lv_image_dsc_t {name} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            f"        .cf = {cf},",
            "        .flags = 0,",
            f"        .w = {width},",
            f"        .h = {height},",
            f"        .stride = {stride},",
            "        .reserved_2 = 0,",
            "    },",
            f"    .data_size = sizeof({name}_pixels),",
            f"    .data = (const uint8_t *){name}_pixels,",
            "};",
            "",
        ]
    )


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)

    background = build_background()
    ring = build_ring()
    hour = build_pointer(HOUR_W, HOUR_H, 8, (*GOLD_BRIGHT, 255), 20)
    minute = build_pointer(MINUTE_W, MINUTE_H, 5, (*CREAM, 255), 18)
    second = build_second_hand()

    pngs = {
        "watch_bg": (BG_W, BG_H, background, 3),
        "watch_ring": (RING_SIZE, RING_SIZE, ring, 4),
        "watch_hour": (HOUR_W, HOUR_H, hour, 4),
        "watch_minute": (MINUTE_W, MINUTE_H, minute, 4),
        "watch_second": (SECOND_W, SECOND_H, second, 4),
    }
    for name, (width, height, pixels, channels) in pngs.items():
        (ASSETS / f"{name}.png").write_bytes(
            encode_png(width, height, pixels, channels)
        )

    lines = [
        "/* Generated by gen_watch_assets.py; do not edit by hand. */",
        "#ifndef HSPI_WATCH_ASSETS_H",
        "#define HSPI_WATCH_ASSETS_H",
        "",
        '#include "lvgl.h"',
        "",
        f"#define WATCH_BG_W {BG_W}",
        f"#define WATCH_BG_H {BG_H}",
        f"#define WATCH_RING_W {RING_SIZE}",
        f"#define WATCH_RING_H {RING_SIZE}",
        f"#define WATCH_HOUR_W {HOUR_W}",
        f"#define WATCH_HOUR_H {HOUR_H}",
        f"#define WATCH_MINUTE_W {MINUTE_W}",
        f"#define WATCH_MINUTE_H {MINUTE_H}",
        f"#define WATCH_SECOND_W {SECOND_W}",
        f"#define WATCH_SECOND_H {SECOND_H}",
        "",
    ]
    emit_array(lines, "watch_bg_pixels", "uint16_t", rgb565_bytes(background), 16)
    emit_dsc(lines, "watch_bg", "LV_COLOR_FORMAT_RGB565", BG_W, BG_H, BG_W * 2)
    for name, (width, height, pixels, _) in pngs.items():
        if name == "watch_bg":
            continue
        emit_array(lines, f"{name}_pixels", "uint8_t", bgra_bytes(pixels), 16)
        emit_dsc(lines, name, "LV_COLOR_FORMAT_ARGB8888", width, height, width * 4)
    lines.append("#endif")

    (HERE / "watch_assets.h").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"generated {len(pngs)} PNG files and watch_assets.h")


if __name__ == "__main__":
    main()
