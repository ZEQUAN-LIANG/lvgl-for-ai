#!/usr/bin/env python3
"""Generate Spectrum (ORBITAL) assets: covers, icons, glow and fonts.

Run from the repository root:

    python -I user/app/spectrum/gen_spectrum_assets.py

The generated C headers are committed; the build never runs Node. Pass
``--preview <empty-dir>`` to also write PNG previews.

Fonts need Node.js (``npx lv_font_conv``) and Windows fonts:
Segoe UI Bold for headings and Consolas Bold for readouts. Every user-visible
string is ASCII, so the subset is 0x20-0x7E only.
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANS = Path("C:/Windows/Fonts/segoeuib.ttf")
MONO = Path("C:/Windows/Fonts/consola.ttf")
MONO_BOLD = Path("C:/Windows/Fonts/consolab.ttf")

FONTS = [
    ("spectrum_sans_14", SANS, 14),
    ("spectrum_mono_7", MONO, 7),
    ("spectrum_mono_8", MONO, 8),
    ("spectrum_mono_9", MONO, 9),
    ("spectrum_mono_9b", MONO_BOLD, 9),
    ("spectrum_mono_32", MONO_BOLD, 32),
]

ICON_SIZE = 28
ICON_SCALE = 4
COVER_SIZE = 160
COVER_SCALE = 2
GLOW_SIZE = 160


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if value < lo else hi if value > hi else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.px = [(0.0, 0.0, 0.0, 0.0)] * (width * height)

    def _idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def blend(self, x: int, y: int, color: tuple[int, int, int], alpha: float) -> None:
        if x < 0 or y < 0 or x >= self.w or y >= self.h or alpha <= 0:
            return
        alpha = clamp(alpha)
        r, g, b = color
        dr, dg, db, da = self.px[self._idx(x, y)]
        out_a = alpha + da * (1 - alpha)
        if out_a <= 0.0001:
            self.px[self._idx(x, y)] = (0.0, 0.0, 0.0, 0.0)
            return
        self.px[self._idx(x, y)] = (
            (r * alpha + dr * da * (1 - alpha)) / out_a,
            (g * alpha + dg * da * (1 - alpha)) / out_a,
            (b * alpha + db * da * (1 - alpha)) / out_a,
            out_a,
        )

    def erase(self, x: int, y: int, alpha: float) -> None:
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        r, g, b, a = self.px[self._idx(x, y)]
        self.px[self._idx(x, y)] = (r, g, b, a * (1 - clamp(alpha)))

    def erase_disc(self, cx: float, cy: float, radius: float, soft: float = 1.0) -> None:
        for y in range(int(cy - radius - soft), int(cy + radius + soft) + 1):
            for x in range(int(cx - radius - soft), int(cx + radius + soft) + 1):
                dist = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                cov = clamp((radius + soft * 0.5 - dist) / soft)
                if cov > 0:
                    self.erase(x, y, cov)

    def disc(self, cx: float, cy: float, radius: float,
             color: tuple[int, int, int], alpha: float = 1.0,
             soft: float = 1.0) -> None:
        for y in range(int(cy - radius - soft), int(cy + radius + soft) + 1):
            for x in range(int(cx - radius - soft), int(cx + radius + soft) + 1):
                dist = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                cov = clamp((radius + soft * 0.5 - dist) / soft)
                if cov > 0:
                    self.blend(x, y, color, alpha * cov)

    def ring(self, cx: float, cy: float, radius: float, width: float,
             color: tuple[int, int, int], alpha: float = 1.0) -> None:
        outer = radius + width / 2
        inner = radius - width / 2
        for y in range(int(cy - outer - 1), int(cy + outer + 1) + 1):
            for x in range(int(cx - outer - 1), int(cx + outer + 1) + 1):
                dist = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if inner - 0.5 <= dist <= outer + 0.5:
                    cov = min(clamp((dist - inner + 0.5)), clamp((outer - dist + 0.5)))
                    self.blend(x, y, color, alpha * cov)

    def arc(self, cx: float, cy: float, radius: float, width: float,
            start: float, end: float, color: tuple[int, int, int],
            alpha: float = 1.0) -> None:
        outer = radius + width / 2
        inner = radius - width / 2
        for y in range(int(cy - outer - 1), int(cy + outer + 1) + 1):
            for x in range(int(cx - outer - 1), int(cx + outer + 1) + 1):
                dx = x + 0.5 - cx
                dy = y + 0.5 - cy
                dist = math.hypot(dx, dy)
                if not (inner - 0.5 <= dist <= outer + 0.5):
                    continue
                angle = math.degrees(math.atan2(dy, dx))
                if start <= end:
                    inside = start <= angle <= end
                else:
                    inside = angle >= start or angle <= end
                if not inside:
                    continue
                cov = min(clamp(dist - inner + 0.5), clamp(outer - dist + 0.5))
                self.blend(x, y, color, alpha * cov)

    def line(self, x0: float, y0: float, x1: float, y1: float,
             width: float, color: tuple[int, int, int], alpha: float = 1.0) -> None:
        half = width / 2
        minx = int(min(x0, x1) - half - 1)
        maxx = int(max(x0, x1) + half + 1)
        miny = int(min(y0, y1) - half - 1)
        maxy = int(max(y0, y1) + half + 1)
        dx = x1 - x0
        dy = y1 - y0
        length2 = dx * dx + dy * dy
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                px = x + 0.5
                py = y + 0.5
                if length2 <= 0:
                    t = 0.0
                else:
                    t = clamp(((px - x0) * dx + (py - y0) * dy) / length2)
                nx = x0 + dx * t
                ny = y0 + dy * t
                dist = math.hypot(px - nx, py - ny)
                cov = clamp(half + 0.5 - dist)
                if cov > 0:
                    self.blend(x, y, color, alpha * cov)

    def polyline(self, points: list[tuple[float, float]], width: float,
                 color: tuple[int, int, int], alpha: float = 1.0) -> None:
        for i in range(len(points) - 1):
            self.line(points[i][0], points[i][1],
                      points[i + 1][0], points[i + 1][1], width, color, alpha)

    def polygon(self, points: list[tuple[float, float]],
                color: tuple[int, int, int], alpha: float = 1.0) -> None:
        minx = int(min(p[0] for p in points))
        maxx = int(max(p[0] for p in points)) + 1
        miny = int(min(p[1] for p in points))
        maxy = int(max(p[1] for p in points)) + 1
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                if point_in_poly(x + 0.5, y + 0.5, points):
                    self.blend(x, y, color, alpha)

    def downsample(self, factor: int) -> "Canvas":
        out = Canvas(self.w // factor, self.h // factor)
        area = factor * factor
        for oy in range(out.h):
            for ox in range(out.w):
                r = g = b = a = 0.0
                for sy in range(factor):
                    for sx in range(factor):
                        pr, pg, pb, pa = self.px[(oy * factor + sy) * self.w + ox * factor + sx]
                        r += pr * pa
                        g += pg * pa
                        b += pb * pa
                        a += pa
                a /= area
                if a > 0.0001:
                    out.px[oy * out.w + ox] = (r / area / a, g / area / a, b / area / a, a)
                else:
                    out.px[oy * out.w + ox] = (0.0, 0.0, 0.0, 0.0)
        return out

    def mask_circle(self, radius: float, soft: float = 1.5) -> None:
        cx = self.w / 2
        cy = self.h / 2
        for y in range(self.h):
            for x in range(self.w):
                dist = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                cov = clamp((radius + soft * 0.5 - dist) / soft)
                r, g, b, a = self.px[y * self.w + x]
                self.px[y * self.w + x] = (r, g, b, a * cov)


def point_in_poly(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


# The implicit heart curve spans x -1.13..1.13 and y -0.98..1.23; map that box
# onto the requested square so both top lobes are drawn instead of flattened.
HEART_X = 1.13
HEART_Y_CENTER = (1.23 - 0.98) / 2
HEART_Y_HALF = (1.23 + 0.98) / 2


def heart_hit(cx: float, cy: float, size: float, x: int, y: int) -> bool:
    nx = (x + 0.5 - cx) / size * HEART_X
    ny = -(y + 0.5 - cy) / size * HEART_Y_HALF + HEART_Y_CENTER
    base = nx * nx + ny * ny - 1
    return base * base * base - nx * nx * ny * ny * ny <= 0


def heart(canvas: Canvas, cx: float, cy: float, size: float,
          color: tuple[int, int, int], alpha: float) -> None:
    left = int(cx - size) - 1
    right = int(cx + size) + 1
    top = int(cy - size) - 1
    bottom = int(cy + size) + 1
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if heart_hit(cx, cy, size, x, y):
                canvas.blend(x, y, color, alpha)


def emit_u16(values: list[int], name: str) -> list[str]:
    lines = [f"static const uint16_t {name}[] = {{"]
    for start in range(0, len(values), 12):
        chunk = ", ".join(f"0x{value:04X}" for value in values[start:start + 12])
        lines.append(f"    {chunk},")
    lines.append("};")
    return lines


def emit_u32(values: list[int], name: str) -> list[str]:
    lines = [f"static const uint32_t {name}[] = {{"]
    for start in range(0, len(values), 8):
        chunk = ", ".join(f"0x{value:08X}" for value in values[start:start + 8])
        lines.append(f"    {chunk},")
    lines.append("};")
    return lines


def read_png_rgba(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Minimal 8-bit RGB/RGBA PNG reader for the committed covers_src files."""
    data = path.read_bytes()
    if data[:8] != bytes((137, 80, 78, 71, 13, 10, 26, 10)):
        raise SystemExit(f"not a PNG: {path}")
    pos = 8
    width = height = color_type = 0
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, depth, color_type = struct.unpack(">IIBB", chunk[:10])
            if depth != 8 or color_type not in (2, 6):
                raise SystemExit(f"unsupported PNG: {path}")
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    rows = []
    prev = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                pred = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
                row[i] = (row[i] + pred) & 0xFF
        rows.append(row)
        prev = row
    pixels = []
    for row in rows:
        for x in range(width):
            base = x * channels
            if channels == 4:
                pixels.append((row[base], row[base + 1], row[base + 2], row[base + 3]))
            else:
                pixels.append((row[base], row[base + 1], row[base + 2], 255))
    return width, height, pixels


def image_header(name: str, width: int, height: int, fmt: str, stride: int) -> list[str]:
    return [
        f"static const lv_image_dsc_t {name} = {{",
        "    .header = {",
        "        .magic = LV_IMAGE_HEADER_MAGIC,",
        f"        .cf = {fmt},",
        "        .flags = 0,",
        f"        .w = {width},",
        f"        .h = {height},",
        f"        .stride = {stride},",
        "        .reserved_2 = 0,",
        "    },",
        f"    .data_size = sizeof({name}_data),",
        f"    .data = (const uint8_t *){name}_data,",
        "};",
        "",
    ]


# ---------------------------------------------------------------- covers

COVER_PALETTES = [
    ("#0a1430", "#03060f", "#25e7ff", "#7c5cff", "#ff4fd8", 11),
    ("#2a0a1c", "#100308", "#ff4f8b", "#ff8a3d", "#ffd166", 29),
    ("#07261f", "#020d0a", "#5dffb0", "#29d7ff", "#d4ff4d", 47),
]


def make_cover(index: int) -> Canvas:
    bg1, bg0, accent_a, accent_b, accent_c, seed = COVER_PALETTES[index]
    size = COVER_SIZE * COVER_SCALE
    canvas = Canvas(size, size)
    c1 = hex_rgb(bg1)
    c0 = hex_rgb(bg0)
    ca = hex_rgb(accent_a)
    cb = hex_rgb(accent_b)
    cc = hex_rgb(accent_c)

    for y in range(size):
        for x in range(size):
            t = clamp((x + y) / (size * 2.0))
            color = (round(lerp(c1[0], c0[0], t)),
                     round(lerp(c1[1], c0[1], t)),
                     round(lerp(c1[2], c0[2], t)))
            canvas.px[y * size + x] = (color[0], color[1], color[2], 1.0)

    cx = size / 2
    cy = size / 2
    # soft center glow
    for radius in range(int(size * 0.60), 0, -5):
        alpha = 0.010 + (1 - radius / (size * 0.60)) * 0.045
        canvas.ring(cx, cy, radius, 10, ca, alpha)

    # concentric arcs
    for i in range(11):
        radius = size * (0.22 + i * 0.038)
        start = seed * 11 + i * 47
        span = 80 + (i * 29 + seed) % 160
        width = 2.0 + (i % 3) * 1.6
        color = ca if i % 3 == 0 else cb if i % 3 == 1 else cc
        canvas.arc(cx, cy, radius, width, start % 360, (start + span) % 360,
                   color, 0.42 + (i % 4) * 0.10)

    # bright orbit rings
    canvas.ring(cx, cy, size * 0.61, 3.0, ca, 0.55)
    canvas.ring(cx, cy, size * 0.655, 1.2, cc, 0.35)

    # waveform bands above and below the vinyl
    for band, band_color in ((-0.27, ca), (0.27, cc)):
        points = []
        for i in range(61):
            f = i / 60
            y = cy + band * size + math.sin(f * math.pi * 4 + seed) * size * 0.055 \
                + math.sin(f * math.pi * 9 - seed * 0.7) * size * 0.022
            points.append((size * (0.09 + f * 0.82), y))
        canvas.polyline(points, 5, band_color, 0.18)
        canvas.polyline(points, 2, band_color, 0.85)
        canvas.polyline(points, 0.9, (255, 255, 255), 0.45)

    # stars / dust
    rnd = seed * 7919 + 17
    for _ in range(58):
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        x = (rnd >> 8) % size
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        y = (rnd >> 8) % size
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        radius = 0.7 + ((rnd >> 8) % 22) / 10
        color = ca if _ % 4 == 0 else (255, 255, 255)
        canvas.disc(x, y, radius, color, 0.35 + (_ % 5) * 0.10)

    # center vinyl (small enough to keep the art visible)
    vinyl = (6, 8, 16)
    canvas.disc(cx, cy, size * 0.19, vinyl, 0.90)
    for i in range(1, 6):
        canvas.ring(cx, cy, size * 0.19 * (i / 6), 0.8, (255, 255, 255), 0.10)
    canvas.disc(cx, cy, size * 0.032, ca, 0.98)
    canvas.disc(cx, cy, size * 0.012, (4, 6, 12), 1.0)

    # vignette
    for y in range(size):
        for x in range(size):
            dist = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / (size * 0.72)
            dark = clamp((dist - 0.55) / 0.55) * 0.55
            if dark > 0:
                r, g, b, a = canvas.px[y * size + x]
                canvas.px[y * size + x] = (r * (1 - dark), g * (1 - dark), b * (1 - dark), a)

    canvas.mask_circle(size / 2 - 1.5)
    return canvas.downsample(COVER_SCALE)


def emit_covers(preview_dir: Path | None) -> None:
    lines = [
        "/* Generated by gen_spectrum_assets.py from covers_src PNG files. */",
        "#ifndef SPECTRUM_COVERS_H",
        "#define SPECTRUM_COVERS_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    for track in range(3):
        for palette in range(3):
            for layer in ("base", "spin", "spin96", "spin88", "spin78", "base88", "base78"):
                suffix = "" if layer == "base" else "_" + layer
                name = f"spectrum_cover{suffix}_t{track}_p{palette}"
                path = HERE / "covers_src" / f"cover_t{track}_p{palette}_{layer}.png"
                if not path.is_file():
                    raise SystemExit(f"missing cover source: {path}")
                width, height, pixels = read_png_rgba(path)
                expected = {"spin96": 96, "spin88": 88, "spin78": 78, "base88": 88, "base78": 78}.get(layer, COVER_SIZE)
                if width != expected or height != expected:
                    raise SystemExit(f"cover must be {expected}x{expected}: {path}")
                radius = expected / 2 - 0.5
                values = []
                for y in range(height):
                    for x in range(width):
                        r, g, b, a = pixels[y * width + x]
                        dx = x + 0.5 - width / 2
                        dy = y + 0.5 - height / 2
                        if dx * dx + dy * dy > radius * radius:
                            a = 0
                        values.append((a << 24) | (r << 16) | (g << 8) | b)
                if preview_dir:
                    shutil.copyfile(path, preview_dir / f"{name}.png")
                lines += [f"#define {name.upper()}_W {width}",
                          f"#define {name.upper()}_H {height}", ""]
                lines += emit_u32(values, f"{name}_data")
                lines += image_header(name, width, height, "LV_COLOR_FORMAT_ARGB8888",
                                      width * 4)
    lines += ["#endif /* SPECTRUM_COVERS_H */", ""]
    (HERE / "spectrum_covers.h").write_text(chr(10).join(lines), encoding="utf-8")


# ----------------------------------------------------------------- icons

WHITE = (255, 255, 255)


def icon_canvas() -> Canvas:
    return Canvas(ICON_SIZE * ICON_SCALE, ICON_SIZE * ICON_SCALE)


def s(value: float) -> float:
    return value * ICON_SCALE


def finish_icon(canvas: Canvas, preview_dir: Path | None, name: str) -> Canvas:
    icon = canvas.downsample(ICON_SCALE)
    if preview_dir:
        write_png(preview_dir / f"icon_{name}.png", icon.w, icon.h,
                  [(255, 255, 255, round(a * 255)) for _, _, _, a in icon.px])
    return icon


def make_icons(preview_dir: Path | None) -> dict[str, Canvas]:
    out: dict[str, Canvas] = {}

    c = icon_canvas()
    c.polygon([(s(14), s(1.5)), (s(18), s(10)), (s(26.5), s(14)),
               (s(18), s(18)), (s(14), s(26.5)), (s(10), s(18)),
               (s(1.5), s(14)), (s(10), s(10))], WHITE, 1.0)
    out["logo"] = finish_icon(c, preview_dir, "logo")

    c = icon_canvas()
    c.polygon([(s(8), s(5)), (s(23), s(14)), (s(8), s(23))], WHITE, 1.0)
    out["play"] = finish_icon(c, preview_dir, "play")

    c = icon_canvas()
    c.polygon([(s(6.5), s(4.5)), (s(11.5), s(4.5)), (s(11.5), s(23.5)), (s(6.5), s(23.5))], WHITE)
    c.polygon([(s(16.5), s(4.5)), (s(21.5), s(4.5)), (s(21.5), s(23.5)), (s(16.5), s(23.5))], WHITE)
    out["pause"] = finish_icon(c, preview_dir, "pause")

    c = icon_canvas()
    c.polygon([(s(6), s(5)), (s(9), s(5)), (s(9), s(23)), (s(6), s(23))], WHITE)
    c.polygon([(s(23), s(5)), (s(10), s(14)), (s(23), s(23))], WHITE)
    out["prev"] = finish_icon(c, preview_dir, "prev")

    c = icon_canvas()
    c.polygon([(s(22), s(5)), (s(19), s(5)), (s(19), s(23)), (s(22), s(23))], WHITE)
    c.polygon([(s(5), s(5)), (s(18), s(14)), (s(5), s(23))], WHITE)
    out["next"] = finish_icon(c, preview_dir, "next")

    c = icon_canvas()
    heart(c, s(14), s(14), s(11), WHITE, 1.0)
    for y in range(c.h):
        for x in range(c.w):
            if heart_hit(s(14), s(14), s(8.6), x, y):
                c.erase(x, y, 1.0)
    out["heart"] = finish_icon(c, preview_dir, "heart")

    c = icon_canvas()
    heart(c, s(14), s(14), s(11), WHITE, 1.0)
    out["heart_filled"] = finish_icon(c, preview_dir, "heart_filled")

    c = icon_canvas()
    c.disc(s(14), s(14), s(11.5), WHITE, 1.0)
    for angle in (-60, -10, 45, 120):
        cx = s(14) + math.cos(math.radians(angle)) * s(7.2)
        cy = s(14) + math.sin(math.radians(angle)) * s(7.2)
        c.erase_disc(cx, cy, s(1.8), s(0.5))
    c.erase_disc(s(14), s(19.5), s(2.6), s(0.5))
    out["palette"] = finish_icon(c, preview_dir, "palette")

    c = icon_canvas()
    c.arc(s(14), s(14), s(9), s(1.8), 20, 160, WHITE, 1.0)
    c.arc(s(14), s(14), s(9), s(1.8), 200, 340, WHITE, 1.0)
    c.polygon([(s(4.4), s(10.5)), (s(9.6), s(8.2)), (s(7.8), s(13.4))], WHITE)
    c.polygon([(s(23.6), s(17.5)), (s(18.4), s(19.8)), (s(20.2), s(14.6))], WHITE)
    out["auto"] = finish_icon(c, preview_dir, "auto")

    c = icon_canvas()
    c.polygon([(s(4), s(10)), (s(11), s(10)), (s(18), s(4)), (s(18), s(24)),
               (s(11), s(18)), (s(4), s(18))], WHITE)
    c.arc(s(19), s(14), s(6), s(1.6), -55, 55, WHITE, 1.0)
    c.arc(s(19), s(14), s(10), s(1.4), -50, 50, WHITE, 0.75)
    out["volume"] = finish_icon(c, preview_dir, "volume")

    c = icon_canvas()
    c.ring(s(14), s(14), s(9.5), s(2), WHITE, 1.0)
    c.disc(s(14), s(14), s(2.6), WHITE)
    c.disc(s(21.5), s(6.5), s(1.8), WHITE)
    out["orbit"] = finish_icon(c, preview_dir, "orbit")

    c = icon_canvas()
    c.ring(s(14), s(14), s(10), s(1.6), WHITE, 1.0)
    c.ring(s(14), s(14), s(5.5), s(1.6), WHITE, 1.0)
    for angle in (0, 90, 180, 270):
        cx = s(14) + math.cos(math.radians(angle)) * s(10)
        cy = s(14) + math.sin(math.radians(angle)) * s(10)
        c.disc(cx, cy, s(1.5), WHITE)
    out["dual"] = finish_icon(c, preview_dir, "dual")

    c = icon_canvas()
    for angle in range(0, 360, 45):
        x0 = s(14) + math.cos(math.radians(angle)) * s(4)
        y0 = s(14) + math.sin(math.radians(angle)) * s(4)
        x1 = s(14) + math.cos(math.radians(angle)) * s(11)
        y1 = s(14) + math.sin(math.radians(angle)) * s(11)
        c.line(x0, y0, x1, y1, s(1.8), WHITE, 1.0)
    c.disc(s(14), s(14), s(2.2), WHITE)
    out["radial"] = finish_icon(c, preview_dir, "radial")

    c = icon_canvas()
    points = []
    for i in range(80):
        ang = i * 0.40
        radius = s(1.1) + i * s(0.135)
        points.append((s(14) + math.cos(ang) * radius, s(14) + math.sin(ang) * radius))
    c.polyline(points, s(1.6), WHITE, 1.0)
    out["spiral"] = finish_icon(c, preview_dir, "spiral")

    c = icon_canvas()
    for radius in (s(4), s(7.5), s(11)):
        c.ring(s(14), s(14), radius, s(1.3), WHITE, 0.9)
    c.line(s(14), s(14), s(23), s(6), s(1.8), WHITE, 1.0)
    c.disc(s(20), s(8.5), s(1.8), WHITE)
    out["sonar"] = finish_icon(c, preview_dir, "sonar")

    c = icon_canvas()
    c.polygon([(s(14), s(2.5)), (s(16.2), s(11.8)), (s(25.5), s(14)),
               (s(16.2), s(16.2)), (s(14), s(25.5)), (s(11.8), s(16.2)),
               (s(2.5), s(14)), (s(11.8), s(11.8))], WHITE)
    c.disc(s(21), s(21), s(1.5), WHITE)
    c.disc(s(5), s(20), s(1.1), WHITE)
    out["stars"] = finish_icon(c, preview_dir, "stars")

    return out


def emit_icons(preview_dir: Path | None) -> None:
    icons = make_icons(preview_dir)
    lines = [
        "/* Generated by gen_spectrum_assets.py; do not edit by hand. */",
        "#ifndef SPECTRUM_ICONS_H",
        "#define SPECTRUM_ICONS_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    for name, icon in icons.items():
        values = [(round(a * 255) << 24) | 0x00FFFFFF for _, _, _, a in icon.px]
        symbol = f"spectrum_icon_{name}"
        lines += [f"#define {symbol.upper()}_W {icon.w}",
                  f"#define {symbol.upper()}_H {icon.h}", ""]
        lines += emit_u32(values, f"{symbol}_data")
        lines += image_header(symbol, icon.w, icon.h, "LV_COLOR_FORMAT_ARGB8888",
                              icon.w * 4)
    lines += ["#endif /* SPECTRUM_ICONS_H */", ""]
    (HERE / "spectrum_icons.h").write_text("\n".join(lines), encoding="utf-8")


def emit_glow() -> None:
    size = 256
    values = []
    for y in range(size):
        for x in range(size):
            dist = math.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2) / (size / 2)
            if dist >= 1.0:
                alpha = 0.0
            elif dist < 0.45:
                alpha = 1.0 - 0.66 * (dist / 0.45)
            else:
                alpha = 0.34 * (1.0 - (dist - 0.45) / 0.55)
            values.append((round(alpha * 255) << 24) | 0x00FFFFFF)
    lines = [
        "/* Generated by gen_spectrum_assets.py; do not edit by hand. */",
        "#ifndef SPECTRUM_GLOW_H",
        "#define SPECTRUM_GLOW_H",
        "",
        '#include "lvgl.h"',
        "",
        f"#define SPECTRUM_GLOW_W {size}",
        f"#define SPECTRUM_GLOW_SIZE {size}",
        "",
    ]
    lines += emit_u32(values, "spectrum_glow_data")
    lines += image_header("spectrum_glow", size, size, "LV_COLOR_FORMAT_ARGB8888",
                          size * 4)
    lines += ["#endif /* SPECTRUM_GLOW_H */", ""]
    (HERE / "spectrum_glow.h").write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------- fonts

def generate_fonts(force: bool) -> None:
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx not found; install Node.js to regenerate fonts")
    for name, source, size in FONTS:
        output = HERE / f"{name}.c"
        print(f"font: {name} ({size}px, {source.name})")
        subprocess.run([
            npx, "--yes", "lv_font_conv",
            "--font", str(source),
            "--size", str(size),
            "--bpp", "4",
            "--no-compress",
            "--no-kerning",
            "--format", "lvgl",
            "--lv-font-name", name,
            "-o", str(output),
            "-r", "0x20-0x7E",
        ], check=True, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        text = output.read_text(encoding="utf-8")
        # Keep the generated banner free of build-machine absolute paths.
        text = text.replace(str(HERE), ".")
        text = text.replace(str(source), source.name)
        text = text.replace(f"const lv_font_t {name} =",
                            f"static const lv_font_t {name} =")
        text = text.replace("uint8_t glyph_bitmap[]",
                            f"uint8_t {name}_glyph_bitmap[]")
        text = text.replace(".glyph_bitmap = glyph_bitmap,",
                            f".glyph_bitmap = {name}_glyph_bitmap,")
        text = text.replace("lv_font_fmt_txt_glyph_dsc_t glyph_dsc[]",
                            f"lv_font_fmt_txt_glyph_dsc_t {name}_glyph_dsc[]")
        text = text.replace(".glyph_dsc = glyph_dsc,",
                            f".glyph_dsc = {name}_glyph_dsc,")
        text = re.sub(r"static const uint16_t (unicode_list_\d+)\[\]",
                      rf"static const uint16_t {name}_\1[]", text)
        text = re.sub(r"\.unicode_list = (unicode_list_\d+),",
                      rf".unicode_list = {name}_\1,", text)
        text = text.replace("lv_font_fmt_txt_cmap_t cmaps[]",
                            f"lv_font_fmt_txt_cmap_t {name}_cmaps[]")
        text = text.replace(".cmaps = cmaps,",
                            f".cmaps = {name}_cmaps,")
        text = text.replace("lv_font_fmt_txt_dsc_t font_dsc =",
                            f"lv_font_fmt_txt_dsc_t {name}_font_dsc =")
        text = text.replace(".dsc = &font_dsc,",
                            f".dsc = &{name}_font_dsc,")
        text = text.replace("lv_font_fmt_txt_glyph_cache_t cache;",
                            f"lv_font_fmt_txt_glyph_cache_t {name}_cache;")
        text = text.replace(".cache = &cache", f".cache = &{name}_cache")
        header = f"/* Generated by gen_spectrum_assets.py from {source.name}; do not edit. */\n" + text
        (HERE / f"{name}.h").write_text(header, encoding="utf-8")
        output.unlink()


def emit_assets_header() -> None:
    lines = [
        "/* Generated by gen_spectrum_assets.py; do not edit by hand. */",
        "#ifndef SPECTRUM_ASSETS_H",
        "#define SPECTRUM_ASSETS_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    for name, _, _ in FONTS:
        lines.append(f'#include "{name}.h"')
    lines += ['#include "spectrum_covers.h"',
              '#include "spectrum_icons.h"',
              '#include "spectrum_glow.h"',
              "",
              "#endif /* SPECTRUM_ASSETS_H */",
              ""]
    (HERE / "spectrum_assets.h").write_text("\n".join(lines), encoding="utf-8")


def write_png(path: Path, width: int, height: int,
              pixels: list[tuple[int, int, int, int] | tuple[int, int, int]]) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            pixel = pixels[y * width + x]
            if len(pixel) == 4:
                red, green, blue, alpha = pixel
                raw += bytes((red, green, blue, alpha))
            else:
                red, green, blue = pixel
                raw += bytes((red, green, blue))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    color_type = 6 if len(pixels[0]) == 4 else 2
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path, default=None)
    parser.add_argument("--skip-fonts", action="store_true")
    args = parser.parse_args()
    if args.preview:
        args.preview.mkdir(parents=True, exist_ok=True)
    emit_covers(args.preview)
    emit_icons(args.preview)
    emit_glow()
    emit_assets_header()
    if not args.skip_fonts:
        generate_fonts(force=True)
    print("spectrum assets written")


if __name__ == "__main__":
    main()
