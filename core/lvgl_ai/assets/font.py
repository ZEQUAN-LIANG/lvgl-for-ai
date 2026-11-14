"""TTF/OTF -> LVGL ``lv_font_t`` C array conversion.

The bitmap/cmap layout follows ``lv_font_conv`` (MIT): glyphs are packed
independently, MSB-first, each glyph padded to a byte boundary; ``stride`` stays
0 (continuous packing).
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .emit import (
    codepoint_label,
    format_u16_array,
    format_u8_array,
    generator_label,
    header_guard,
    include_lvgl,
    merge_manifest_entry,
    relative_posix,
    require,
    sha256_file,
    write_if_changed,
)
from .errors import AssetError
from .version import major_minor, target_label
from .vendor import load_freetype

_MAX_BITMAP_INDEX = (1 << 20) - 1  # LV_FONT_FMT_TXT_LARGE == 0
_MAX_ADV_W = (1 << 12) - 1
_MAX_BOX = 255
_MIN_OFS = -128
_MAX_OFS = 127
_MAX_CMAPS = 511
_MAX_GLYPHS = 65535


@dataclass
class FontOptions:
    font_path: Path
    face_index: int = 0
    size: int = 16
    bpp: int = 4
    codepoints: tuple[int, ...] = ()
    metrics: str = "face"
    line_height: int | None = None
    base_line: int | None = None


@dataclass
class Glyph:
    code: int
    adv_w: int
    box_w: int
    box_h: int
    ofs_x: int
    ofs_y: int
    bitmap: bytes


@dataclass
class CmapSubtable:
    format: str
    codepoints: list[int]
    min_code: int
    max_code: int
    start_id: int
    unicode_list: list[int] | None = None
    glyph_ofs: list[int] | None = None
    list_length: int = 0

    @property
    def type_constant(self) -> str:
        return {
            "format0_tiny": "LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY",
            "format0": "LV_FONT_FMT_TXT_CMAP_FORMAT0_FULL",
            "sparse_tiny": "LV_FONT_FMT_TXT_CMAP_SPARSE_TINY",
        }[self.format]


@dataclass
class FontData:
    glyphs: list[Glyph]
    cmaps: list[CmapSubtable]
    bpp: int
    line_height: int
    base_line: int
    underline_position: int
    underline_thickness: int
    cap_height: int
    x_height: int
    family: str
    style: str
    missing: list[int] = field(default_factory=list)
    total_bitmap_bytes: int = 0

    @property
    def id_by_code(self) -> dict[int, int]:
        return {glyph.code: index + 1 for index, glyph in enumerate(self.glyphs)}


def _face_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _bitmap_rows(bitmap: object) -> tuple[list[bytes], int]:
    pitch = int(bitmap.pitch)
    rows = int(bitmap.rows)
    stride = abs(pitch)
    if stride == 0 or rows == 0:
        return [], 0
    buffer = getattr(bitmap, "_FT_Bitmap", None)
    if buffer is not None:
        raw = ctypes.string_at(buffer.buffer, stride * rows)
    else:
        raw = bytes(bitmap.buffer)
    result = [raw[index * stride : (index + 1) * stride] for index in range(rows)]
    if pitch < 0:
        result.reverse()
    return result, stride


def _quantize(value: int, bpp: int) -> int:
    if bpp >= 8:
        return value
    return value >> (8 - bpp)


def _pack_pixels(rows_values: Iterable[Iterable[int]], bpp: int) -> bytes:
    accumulator = 0
    bits = 0
    output = bytearray()
    for row in rows_values:
        for value in row:
            accumulator = (accumulator << bpp) | (value & ((1 << bpp) - 1))
            bits += bpp
            while bits >= 8:
                bits -= 8
                output.append((accumulator >> bits) & 0xFF)
    if bits:
        output.append((accumulator << (8 - bits)) & 0xFF)
    return bytes(output)


def _glyph_pixels(freetype: object, bitmap: object, bpp: int) -> Iterable[list[int]]:
    rows, _stride = _bitmap_rows(bitmap)
    width = int(bitmap.width)
    pixel_mode = int(bitmap.pixel_mode)
    if pixel_mode == freetype.FT_PIXEL_MODE_MONO:
        for row in rows:
            values = [
                _quantize(255, bpp)
                if (row[x // 8] >> (7 - (x % 8))) & 1
                else 0
                for x in range(width)
            ]
            yield values
        return
    if pixel_mode == freetype.FT_PIXEL_MODE_GRAY:
        for row in rows:
            yield [_quantize(row[x], bpp) for x in range(width)]
        return
    if pixel_mode == freetype.FT_PIXEL_MODE_BGRA:
        for row in rows:
            values: list[int] = []
            for x in range(width):
                base = x * 4
                blue, green, red, alpha = row[base : base + 4]
                gray = round(0.299 * red + 0.587 * green + 0.114 * blue)
                gray = min(255, max(0, gray))
                value = ((255 - gray) * alpha) // 255
                values.append(_quantize(value, bpp))
            yield values
        return
    raise AssetError(
        f"unsupported glyph pixel mode {pixel_mode}; only MONO, GRAY and BGRA are supported"
    )


def _glyph_top(freetype: object, face: object, char: str, flags: int) -> int:
    if face.get_char_index(ord(char)) == 0:
        return 0
    try:
        face.load_char(char, flags)
    except Exception:
        return 0
    return int(face.glyph.bitmap_top)


def _estimate_cmap_split(codepoints: list[int]) -> list[tuple[str, list[int]]]:
    """Port of lv_font_conv's breadth-first cmap optimiser."""
    count = len(codepoints)
    paths: list[tuple[float, int, int, str]] = []
    infinity = float("inf")
    for index in range(count):
        best = (infinity, 0, 0, "sparse_tiny")
        for start in range(index + 1):
            previous = paths[start - 1][0] if start > 0 else 0.0
            span = codepoints[index] - codepoints[start]
            if span < 256:
                size = 16 + (span + 1)
                if previous + size < best[0]:
                    best = (previous + size, start, index, "format0")
            if span < 256 and codepoints[index] - index == codepoints[start] - start:
                size = 16
                if previous + size < best[0]:
                    best = (previous + size, start, index, "format0_tiny")
            if span < 65536:
                size = 16 + (index - start + 1) * 2
                if previous + size < best[0]:
                    best = (previous + size, start, index, "sparse_tiny")
        paths.append(best)

    result: list[tuple[str, list[int]]] = []
    index = count - 1
    while index >= 0:
        _distance, start, end, fmt = paths[index]
        result.insert(0, (fmt, codepoints[start : end + 1]))
        index = start - 1
    return result


def build_cmaps(glyphs: list[Glyph]) -> list[CmapSubtable]:
    codepoints = [glyph.code for glyph in glyphs]
    if not codepoints:
        raise AssetError("cannot build a cmap for an empty glyph set")
    ids = {glyph.code: index + 1 for index, glyph in enumerate(glyphs)}
    subtables: list[CmapSubtable] = []
    for fmt, codes in _estimate_cmap_split(codepoints):
        min_code = codes[0]
        max_code = codes[-1]
        start_id = ids[min_code]
        if fmt == "format0_tiny":
            subtables.append(
                CmapSubtable(fmt, codes, min_code, max_code, start_id, list_length=0)
            )
            continue
        if fmt == "format0":
            offsets: list[int] = []
            for code in range(min_code, max_code + 1):
                if code not in ids:
                    offsets.append(0)
                    continue
                delta = ids[code] - start_id
                require(
                    0 <= delta <= 255,
                    f"FORMAT0 cmap delta out of range at U+{code:04X}",
                )
                offsets.append(delta)
            subtables.append(
                CmapSubtable(
                    fmt,
                    codes,
                    min_code,
                    max_code,
                    start_id,
                    glyph_ofs=offsets,
                    list_length=len(offsets),
                )
            )
            continue
        unicode_list = [code - min_code for code in codes]
        require(
            all(0 <= delta <= 65535 for delta in unicode_list),
            "SPARSE cmap codepoint delta out of range",
        )
        subtables.append(
            CmapSubtable(
                fmt,
                codes,
                min_code,
                max_code,
                start_id,
                unicode_list=unicode_list,
                list_length=len(unicode_list),
            )
        )
    require(len(subtables) <= _MAX_CMAPS, "too many cmap subtables")
    return subtables


def rasterize_font(options: FontOptions) -> FontData:
    freetype = load_freetype()
    if options.bpp not in (1, 2, 4, 8):
        raise AssetError("--bpp must be one of 1, 2, 4, 8")
    if options.size <= 0:
        raise AssetError("--size must be a positive integer")
    if options.metrics not in ("face", "glyphs"):
        raise AssetError("--metrics must be 'face' or 'glyphs'")
    path = options.font_path
    if not path.is_file():
        raise AssetError(f"font not found: {path}")

    try:
        face = freetype.Face(str(path), index=options.face_index)
    except Exception as exc:
        raise AssetError(f"cannot open font {path.name}: {exc}") from exc
    try:
        face.set_pixel_sizes(0, options.size)
    except Exception as exc:
        raise AssetError(f"cannot set font size {options.size}: {exc}") from exc
    try:
        face.select_charmap(freetype.FT_ENCODING_UNICODE)
    except Exception:
        pass

    flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_FORCE_AUTOHINT
    if options.bpp == 1:
        flags |= freetype.FT_LOAD_TARGET_MONO
    else:
        flags |= freetype.FT_LOAD_TARGET_LIGHT

    glyphs: list[Glyph] = []
    missing: list[int] = []
    for codepoint in sorted(set(options.codepoints)):
        if codepoint < 0 or codepoint > 0x10FFFF:
            missing.append(codepoint)
            continue
        if face.get_char_index(codepoint) == 0:
            missing.append(codepoint)
            continue
        try:
            face.load_char(chr(codepoint), flags)
        except Exception as exc:
            raise AssetError(
                f"cannot render U+{codepoint:04X} with {path.name}: {exc}"
            ) from exc
        bitmap = face.glyph.bitmap
        box_w = int(bitmap.width)
        box_h = int(bitmap.rows)
        bitmap_bytes = _pack_pixels(_glyph_pixels(freetype, bitmap, options.bpp), options.bpp)
        advance = float(face.glyph.linearHoriAdvance) / 65536.0
        if advance <= 0:
            advance = float(face.glyph.advance.x) / 64.0
        glyphs.append(
            Glyph(
                code=codepoint,
                adv_w=round(advance * 16.0),
                box_w=box_w,
                box_h=box_h,
                ofs_x=int(face.glyph.bitmap_left),
                ofs_y=int(face.glyph.bitmap_top) - box_h,
                bitmap=bitmap_bytes,
            )
        )

    if not glyphs:
        raise AssetError(
            f"font {path.name} has none of the requested codepoints; "
            "check the font and the selected character set"
        )

    units_per_em = int(face.units_per_EM) or options.size
    scale = options.size / units_per_em
    face_top = round(int(face.ascender) * scale)
    face_bottom = round(int(face.descender) * scale)
    face_height = round(int(face.height) * scale)
    glyph_top = max(glyph.ofs_y + glyph.box_h for glyph in glyphs)
    glyph_bottom = min(glyph.ofs_y for glyph in glyphs)
    top = max(face_top, glyph_top)
    bottom = min(face_bottom, glyph_bottom)

    if options.metrics == "glyphs":
        line_height = glyph_top - glyph_bottom
        base_line = -glyph_bottom
    else:
        line_height = max(face_height, top - bottom)
        base_line = -bottom
    if line_height <= 0:
        line_height = max(1, options.size)
        base_line = 0
    if options.line_height is not None:
        line_height = options.line_height
    if options.base_line is not None:
        base_line = options.base_line
    require(
        0 <= base_line <= line_height,
        f"invalid font metrics: line_height={line_height}, base_line={base_line}",
    )

    underline_position = round(int(face.underline_position) * scale)
    underline_thickness = round(int(face.underline_thickness) * scale)
    underline_position = max(-128, min(127, underline_position))
    underline_thickness = max(0, min(127, underline_thickness))

    cap_height = _glyph_top(freetype, face, "H", flags)
    x_height = _glyph_top(freetype, face, "x", flags)

    total_bitmap_bytes = sum(len(glyph.bitmap) for glyph in glyphs)
    require(
        total_bitmap_bytes <= _MAX_BITMAP_INDEX + 1,
        f"glyph bitmap is {total_bitmap_bytes} bytes; LV_FONT_FMT_TXT_LARGE=0 "
        "allows at most 1 MiB. Reduce --size/--bpp or the character set, or "
        "rebuild LVGL with LV_FONT_FMT_TXT_LARGE=1.",
    )
    require(
        len(glyphs) <= _MAX_GLYPHS,
        f"{len(glyphs)} glyphs exceed the uint16 glyph id range",
    )
    for glyph in glyphs:
        require(
            0 <= glyph.adv_w <= _MAX_ADV_W,
            f"U+{glyph.code:04X} advance width {glyph.adv_w}/16 px does not fit "
            "the 12-bit adv_w field; reduce --size",
        )
        require(
            0 <= glyph.box_w <= _MAX_BOX and 0 <= glyph.box_h <= _MAX_BOX,
            f"U+{glyph.code:04X} bitmap {glyph.box_w}x{glyph.box_h} does not fit "
            "the uint8 box fields; reduce --size",
        )
        require(
            _MIN_OFS <= glyph.ofs_x <= _MAX_OFS
            and _MIN_OFS <= glyph.ofs_y <= _MAX_OFS,
            f"U+{glyph.code:04X} offsets ({glyph.ofs_x},{glyph.ofs_y}) do not fit "
            "int8; reduce --size",
        )

    cmaps = build_cmaps(glyphs)
    family = _face_text(getattr(face, "family_name", ""))
    style = _face_text(getattr(face, "style_name", ""))

    return FontData(
        glyphs=glyphs,
        cmaps=cmaps,
        bpp=options.bpp,
        line_height=line_height,
        base_line=base_line,
        underline_position=underline_position,
        underline_thickness=underline_thickness,
        cap_height=cap_height,
        x_height=x_height,
        family=family,
        style=style,
        missing=missing,
        total_bitmap_bytes=total_bitmap_bytes,
    )


def _bitmap_lines(glyph: Glyph) -> list[str]:
    label = codepoint_label(glyph.code)
    if not glyph.bitmap:
        return [f"    /* {label} (empty) */"]
    lines = [f"    /* {label} */"]
    values = list(glyph.bitmap)
    for start in range(0, len(values), 16):
        chunk = values[start : start + 16]
        lines.append("    " + " ".join(f"0x{value:02X}," for value in chunk))
    return lines


def render_font_header(
    *,
    name: str,
    data: FontData,
    target_version: str,
    source_path: Path,
    source_sha256: str,
    face_index: int,
    size: int,
) -> str:
    guard = header_guard(name)
    bpp_note = []
    if data.bpp == 8:
        bpp_note = [
            " * 8 bpp requires LVGL 8.x or 9.3+; 9.1/9.2 have no plain 8 bpp renderer."
        ]
    lines: list[str] = [
        "/*",
        f" * Generated by lvgl assets font ({generator_label()}).",
        f" * Source: {source_path.name} (face {face_index}, sha256: {source_sha256[:16]}...)",
        f" * {size} px, {data.bpp} bpp, {len(data.glyphs)} glyphs, "
        f"{data.total_bitmap_bytes} bitmap bytes.",
        f" * Target: {target_label(target_version)}.",
        *bpp_note,
        " * Font data is shared; struct fields are gated for LVGL 8.3-9.6.",
        " * Do not edit by hand.",
        " */",
        "",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        include_lvgl(),
        "",
    ]
    if data.bpp == 8:
        lines.extend(
            [
                "#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR < 3",
                '#error "8 bpp plain fonts are not supported before LVGL 9.3; '
                'use --bpp 4 or regenerate for 8.x/9.4+."',
                "#endif",
                "",
            ]
        )
    lines.extend(
        [
            "#ifndef LV_ATTRIBUTE_LARGE_CONST",
            "#define LV_ATTRIBUTE_LARGE_CONST",
            "#endif",
            "",
            f"static LV_ATTRIBUTE_LARGE_CONST const uint8_t {name}_glyph_bitmap[] = {{",
        ]
    )
    emitted_bitmap = False
    for glyph in data.glyphs:
        lines.extend(_bitmap_lines(glyph))
        emitted_bitmap = emitted_bitmap or bool(glyph.bitmap)
    if not emitted_bitmap:
        lines.append("    0x00, /* empty bitmap placeholder */")
    lines.extend(
        [
            "};",
            "",
            f"static const lv_font_fmt_txt_glyph_dsc_t {name}_glyph_dsc[] = {{",
            "    {.bitmap_index = 0, .adv_w = 0, .box_w = 0, .box_h = 0, "
            ".ofs_x = 0, .ofs_y = 0},",
        ]
    )
    offset = 0
    for glyph in data.glyphs:
        lines.append(
            f"    {{.bitmap_index = {offset}, .adv_w = {glyph.adv_w}, "
            f".box_w = {glyph.box_w}, .box_h = {glyph.box_h}, "
            f".ofs_x = {glyph.ofs_x}, .ofs_y = {glyph.ofs_y}}},"
        )
        offset += len(glyph.bitmap)
    lines.extend(["};", ""])

    for index, subtable in enumerate(data.cmaps):
        if subtable.unicode_list is not None:
            lines.extend(
                [
                    f"static const uint16_t {name}_unicode_list_{index}[] = {{",
                    *format_u16_array(subtable.unicode_list),
                    "};",
                    "",
                ]
            )
        if subtable.glyph_ofs is not None:
            lines.extend(
                [
                    f"static const uint8_t {name}_glyph_id_ofs_list_{index}[] = {{",
                    *format_u8_array(subtable.glyph_ofs),
                    "};",
                    "",
                ]
            )

    lines.extend(
        [
            f"static const lv_font_fmt_txt_cmap_t {name}_cmaps[] = {{",
        ]
    )
    for index, subtable in enumerate(data.cmaps):
        unicode_ref = (
            f"{name}_unicode_list_{index}"
            if subtable.unicode_list is not None
            else "NULL"
        )
        glyph_ref = (
            f"{name}_glyph_id_ofs_list_{index}"
            if subtable.glyph_ofs is not None
            else "NULL"
        )
        lines.extend(
            [
                "    {",
                f"        .range_start = {subtable.min_code}, "
                f".range_length = {subtable.max_code - subtable.min_code + 1}, "
                f".glyph_id_start = {subtable.start_id},",
                f"        .unicode_list = {unicode_ref}, "
                f".glyph_id_ofs_list = {glyph_ref}, "
                f".list_length = {subtable.list_length}, "
                f".type = {subtable.type_constant},",
                "    },",
            ]
        )
    lines.extend(["};", ""])

    lines.extend(
        [
            "#if LVGL_VERSION_MAJOR == 8",
            f"static lv_font_fmt_txt_glyph_cache_t {name}_cache;",
            "#endif",
            "",
            f"static const lv_font_fmt_txt_dsc_t {name}_font_dsc = {{",
            f"    .glyph_bitmap = {name}_glyph_bitmap,",
            f"    .glyph_dsc = {name}_glyph_dsc,",
            f"    .cmaps = {name}_cmaps,",
            "    .kern_dsc = NULL,",
            "    .kern_scale = 0,",
            f"    .cmap_num = {len(data.cmaps)},",
            f"    .bpp = {data.bpp},",
            "    .kern_classes = 0,",
            "    .bitmap_format = LV_FONT_FMT_TXT_PLAIN,",
            "#if LVGL_VERSION_MAJOR == 8",
            f"    .cache = &{name}_cache,",
            "#elif LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4",
            "    .stride = 0,",
            "#endif",
            "#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6",
            "    .are_glyphs_dynamic_loaded = false,",
            "#endif",
            "};",
            "",
            f"static const lv_font_t {name} = {{",
            "#if LVGL_VERSION_MAJOR >= 9",
            f"    .dsc = &{name}_font_dsc,",
            "    .fallback = NULL,",
            "    .user_data = NULL,",
            "    .get_glyph_dsc = lv_font_get_glyph_dsc_fmt_txt,",
            "    .get_glyph_bitmap = lv_font_get_bitmap_fmt_txt,",
            "    .release_glyph = NULL,",
            "#else",
            "    .get_glyph_dsc = lv_font_get_glyph_dsc_fmt_txt,",
            "    .get_glyph_bitmap = lv_font_get_bitmap_fmt_txt,",
            f"    .dsc = &{name}_font_dsc,",
            "    .fallback = NULL,",
            "#if LV_USE_USER_DATA",
            "    .user_data = NULL,",
            "#endif",
            "#endif",
            f"    .line_height = {data.line_height},",
            f"    .base_line = {data.base_line},",
            "#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6",
            f"    .cap_height = {data.cap_height},",
            f"    .x_height = {data.x_height},",
            "#endif",
            "    .subpx = LV_FONT_SUBPX_NONE,",
            "#if LVGL_VERSION_MAJOR >= 9",
            "    .kerning = LV_FONT_KERNING_NONE,",
            "#endif",
            "#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4",
            "    .static_bitmap = 0,",
            "#endif",
            f"    .underline_position = {data.underline_position},",
            f"    .underline_thickness = {data.underline_thickness},",
            "};",
            "",
            f"#endif /* {guard} */",
            "",
        ]
    )
    return "\n".join(lines)


def generate_font(
    *,
    options: FontOptions,
    name: str,
    output_path: Path,
    repo_root: Path,
    target_version: str,
    force: bool,
    dry_run: bool,
    manifest_path: Path | None,
) -> dict[str, object]:
    major, minor = major_minor(target_version)
    if options.bpp == 8 and major == 9 and minor < 3:
        raise AssetError(
            "LVGL 9.1/9.2 cannot render plain 8 bpp fonts "
            "(lv_font_fmt_txt has no 8 bpp path); use --bpp 4 or target 9.4+"
        )
    data = rasterize_font(options)
    source_hash = sha256_file(options.font_path)
    text = render_font_header(
        name=name,
        data=data,
        target_version=target_version,
        source_path=options.font_path,
        source_sha256=source_hash,
        face_index=options.face_index,
        size=options.size,
    )
    warnings: list[str] = []
    if data.missing:
        shown = ", ".join(f"U+{code:04X}" for code in data.missing[:20])
        suffix = "" if len(data.missing) <= 20 else f" (+{len(data.missing) - 20} more)"
        warnings.append(f"font is missing {len(data.missing)} codepoints: {shown}{suffix}")
    status = "dry-run"
    if not dry_run:
        status = write_if_changed(output_path, text, force=force)
        if manifest_path is not None:
            merge_manifest_entry(
                manifest_path,
                {
                    "kind": "font",
                    "name": name,
                    "output": output_path.name,
                    "source": options.font_path.name,
                    "source_sha256": source_hash,
                    "options": {
                        "face_index": options.face_index,
                        "size": options.size,
                        "bpp": options.bpp,
                        "metrics": options.metrics,
                        "codepoints": len(options.codepoints),
                    },
                    "glyph_count": len(data.glyphs),
                    "bitmap_bytes": data.total_bitmap_bytes,
                    "status": "generated",
                },
                target_lvgl=target_version,
            )
    return {
        "ok": True,
        "kind": "font",
        "name": name,
        "status": status,
        "wrote": relative_posix(output_path, repo_root),
        "bytes": len(text.encode("utf-8")),
        "glyphs": len(data.glyphs),
        "bitmap_bytes": data.total_bitmap_bytes,
        "line_height": data.line_height,
        "base_line": data.base_line,
        "target_lvgl": target_version,
        "warnings": warnings,
    }
