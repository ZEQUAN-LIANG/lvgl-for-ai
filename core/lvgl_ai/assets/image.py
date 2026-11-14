"""PNG -> LVGL image C array conversion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from .emit import (
    format_u32_array,
    format_u8_array,
    generator_label,
    include_lvgl,
    merge_manifest_entry,
    relative_posix,
    require,
    sha256_file,
    write_if_changed,
)
from .errors import AssetError
from .version import major_minor, target_label
from .vendor import load_png

_CFS = ("auto", "RGB565", "ARGB8888", "RGB888", "A8")

_BYTES_PER_PIXEL = {
    "RGB565": 2,
    "ARGB8888": 4,
    "RGB888": 3,
    "A8": 1,
}


def _v8_cf(image: ImageData) -> str:
    if image.cf == "A8":
        return "LV_IMG_CF_ALPHA_8BIT"
    if image.cf == "ARGB8888" and image.had_alpha:
        return "LV_IMG_CF_TRUE_COLOR_ALPHA"
    return "LV_IMG_CF_TRUE_COLOR"


@dataclass(frozen=True)
class ImageOptions:
    input_path: Path
    requested_cf: str = "auto"
    background: tuple[int, int, int] = (0, 0, 0)
    dither: bool = False


@dataclass(frozen=True)
class ImageData:
    width: int
    height: int
    cf: str
    data: bytes
    stride: int
    had_alpha: bool
    warnings: tuple[str, ...] = ()


def _parse_background(value: str | int | tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, tuple):
        require(len(value) == 3, "background must have three channels")
        return tuple(int(channel) & 0xFF for channel in value)  # type: ignore[return-value]
    if isinstance(value, int):
        color = value
    else:
        text = value.strip()
        if text.startswith("#"):
            text = "0x" + text[1:]
        try:
            color = int(text, 0)
        except ValueError as exc:
            raise AssetError(f"invalid background colour: {value!r}") from exc
    if not 0 <= color <= 0xFFFFFF:
        raise AssetError(f"background colour out of range: {value!r}")
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


def _read_rows(path: Path) -> tuple[int, int, list[bytes], bool]:
    png = load_png()
    try:
        reader = png.Reader(filename=str(path))
        width, height, rows, info = reader.asRGBA8()
    except Exception as exc:  # pypng raises several exception types
        raise AssetError(f"cannot decode PNG {path.name}: {exc}") from exc
    row_bytes = [bytes(row) for row in rows]
    require(
        len(row_bytes) == height,
        f"PNG {path.name} returned {len(row_bytes)} rows; expected {height}",
    )
    # asRGBA8() always reports ``alpha: True`` because it requests RGBA output,
    # even for an opaque RGB source.  Inspect the actual alpha bytes instead.
    seen_alpha = False
    for row in row_bytes:
        if any(value != 0xFF for value in row[3::4]):
            seen_alpha = True
            break
    return width, height, row_bytes, seen_alpha


def _composite(
    red: int, green: int, blue: int, alpha: int, background: tuple[int, int, int]
) -> tuple[int, int, int]:
    if alpha == 0xFF:
        return red, green, blue
    if alpha == 0:
        return background
    inverse = 255 - alpha
    return (
        (red * alpha + background[0] * inverse + 127) // 255,
        (green * alpha + background[1] * inverse + 127) // 255,
        (blue * alpha + background[2] * inverse + 127) // 255,
    )


def _rgb565(red: int, green: int, blue: int) -> int:
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)


def _convert_rgb565(
    width: int,
    height: int,
    rows: Sequence[bytes],
    background: tuple[int, int, int],
    dither: bool,
) -> bytes:
    if not dither:
        output = bytearray()
        for row in rows:
            for index in range(0, len(row), 4):
                red, green, blue, alpha = row[index : index + 4]
                red, green, blue = _composite(red, green, blue, alpha, background)
                value = _rgb565(red, green, blue)
                output += bytes((value & 0xFF, value >> 8))
        return bytes(output)

    errors = [[0.0, 0.0, 0.0] for _ in range(width + 2)]
    output = bytearray()
    for y in range(height):
        current = errors
        following = [[0.0, 0.0, 0.0] for _ in range(width + 2)]
        row = rows[y]
        for x in range(width):
            index = x * 4
            red, green, blue, alpha = row[index : index + 4]
            red, green, blue = _composite(red, green, blue, alpha, background)
            values = [
                max(0.0, min(255.0, red + current[x + 1][0])),
                max(0.0, min(255.0, green + current[x + 1][1])),
                max(0.0, min(255.0, blue + current[x + 1][2])),
            ]
            quantized = [
                (int(values[0]) >> 3) << 3,
                (int(values[1]) >> 2) << 2,
                (int(values[2]) >> 3) << 3,
            ]
            value = _rgb565(quantized[0], quantized[1], quantized[2])
            output += bytes((value & 0xFF, value >> 8))
            diff = [values[i] - quantized[i] for i in range(3)]
            for channel in range(3):
                current[x + 2][channel] += diff[channel] * 7 / 16
                following[x][channel] += diff[channel] * 3 / 16
                following[x + 1][channel] += diff[channel] * 5 / 16
                following[x + 2][channel] += diff[channel] * 1 / 16
        errors = following
    return bytes(output)


def _convert_argb8888(rows: Sequence[bytes]) -> bytes:
    output = bytearray()
    for row in rows:
        for index in range(0, len(row), 4):
            red, green, blue, alpha = row[index : index + 4]
            output += bytes((blue, green, red, alpha))
    return bytes(output)


def _convert_rgb888(
    rows: Sequence[bytes], background: tuple[int, int, int]
) -> bytes:
    output = bytearray()
    for row in rows:
        for index in range(0, len(row), 4):
            red, green, blue, alpha = row[index : index + 4]
            red, green, blue = _composite(red, green, blue, alpha, background)
            output += bytes((blue, green, red))
    return bytes(output)


def _convert_a8(rows: Sequence[bytes], width: int, height: int) -> bytes:
    output = bytearray()
    for row in rows:
        output += row[3::4]
    require(len(output) == width * height, "A8 conversion produced an unexpected size")
    return bytes(output)


def build_image_data(options: ImageOptions) -> ImageData:
    requested = options.requested_cf
    if requested not in _CFS:
        choices = ", ".join(_CFS)
        raise AssetError(f"unsupported --cf {requested!r}; choose one of {choices}")
    path = options.input_path
    if not path.is_file():
        raise AssetError(f"input image not found: {path}")
    if path.suffix.lower() != ".png":
        raise AssetError(
            f"unsupported image format {path.suffix!r}; only .png is supported"
        )

    width, height, rows, had_alpha = _read_rows(path)
    require(width > 0 and height > 0, f"PNG {path.name} has zero width or height")

    warnings: list[str] = []
    cf = requested
    if cf == "auto":
        cf = "ARGB8888" if had_alpha else "RGB565"
    elif cf in ("RGB565", "RGB888") and had_alpha:
        warnings.append(
            f"{path.name} has alpha; pixels are composited onto the background"
        )
    if cf == "A8" and not had_alpha:
        raise AssetError("--cf A8 requires a PNG with an alpha channel")

    if cf == "RGB565":
        data = _convert_rgb565(width, height, rows, options.background, options.dither)
    elif cf == "ARGB8888":
        data = _convert_argb8888(rows)
    elif cf == "RGB888":
        data = _convert_rgb888(rows, options.background)
    else:
        data = _convert_a8(rows, width, height)

    stride = width * _BYTES_PER_PIXEL[cf]
    require(
        len(data) >= stride * height,
        "converted image data is shorter than the declared stride",
    )
    return ImageData(
        width=width,
        height=height,
        cf=cf,
        data=data,
        stride=stride,
        had_alpha=had_alpha,
        warnings=tuple(warnings),
    )


def _v8_values(data: bytes) -> list[int]:
    values: list[int] = []
    for index in range(0, len(data), 4):
        blue, green, red, alpha = data[index : index + 4]
        values.append((alpha << 24) | (red << 16) | (green << 8) | blue)
    return values


def render_image_header(
    *,
    name: str,
    image: ImageData,
    target_version: str,
    source_path: Path,
    source_sha256: str,
) -> str:
    major, _minor = major_minor(target_version)
    # <NAME>_H is the image height macro, so the include guard needs a
    # different suffix.
    guard = f"{name.upper()}_H_INCLUDED"
    lines: list[str] = [
        "/*",
        f" * Generated by lvgl assets image ({generator_label()}).",
        f" * Source: {source_path.name} (sha256: {source_sha256[:16]}...)",
        f" * {image.width}x{image.height}, {image.cf}, {target_label(target_version)}.",
        " * Do not edit by hand.",
        " */",
        "",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        include_lvgl(),
        "",
        f"#define {name.upper()}_W {image.width}",
        f"#define {name.upper()}_H {image.height}",
        "",
    ]

    if major >= 9:
        require(
            image.width <= 0xFFFF and image.height <= 0xFFFF,
            "LVGL 9 image dimensions must be <= 65535",
        )
        require(
            image.stride <= 0xFFFF,
            f"LVGL 9 stride {image.stride} exceeds the 16-bit header field",
        )
        lines.extend(
            [
                "#if LVGL_VERSION_MAJOR >= 9",
                "",
                f"static const uint8_t {name}_map[] = {{",
                *format_u8_array(image.data),
                "};",
                "",
                f"static const lv_image_dsc_t {name} = {{",
                "    .header = {",
                "        .magic = LV_IMAGE_HEADER_MAGIC,",
                f"        .cf = LV_COLOR_FORMAT_{image.cf},",
                "        .flags = 0,",
                f"        .w = {image.width},",
                f"        .h = {image.height},",
                f"        .stride = {image.stride},",
                "        .reserved_2 = 0,",
                "    },",
                f"    .data_size = sizeof({name}_map),",
                f"    .data = {name}_map,",
                "};",
                "",
                "#else",
                f'#error "This image header targets LVGL 9.x; regenerate it with '
                f'--lvgl 9.6 (or 9.4) for this build."',
                "#endif",
            ]
        )
    else:
        require(
            image.width <= 2047 and image.height <= 2047,
            "LVGL 8 image dimensions must be <= 2047 (11-bit header fields)",
        )
        v8_cf = _v8_cf(image)
        if image.cf == "A8":
            lines.extend(
                [
                    "#if LVGL_VERSION_MAJOR == 8",
                    "",
                    f"static const uint8_t {name}_map[] = {{",
                    *format_u8_array(image.data),
                    "};",
                    "",
                    f"static const lv_img_dsc_t {name} = {{",
                    "    .header = {",
                    f"        .cf = {v8_cf},",
                    "        .always_zero = 0,",
                    "        .reserved = 0,",
                    f"        .w = {image.width},",
                    f"        .h = {image.height},",
                    "    },",
                    f"    .data_size = sizeof({name}_map),",
                    f"    .data = (const uint8_t *){name}_map,",
                    "};",
                ]
            )
        else:
            lines.extend(
                [
                    "#if LVGL_VERSION_MAJOR == 8",
                    "",
                    f"static const uint32_t {name}_map[] = {{",
                    *format_u32_array(_v8_values(image.data)),
                    "};",
                    "",
                    f"static const lv_img_dsc_t {name} = {{",
                    "    .header = {",
                    f"        .cf = {v8_cf},",
                    "        .always_zero = 0,",
                    "        .reserved = 0,",
                    f"        .w = {image.width},",
                    f"        .h = {image.height},",
                    "    },",
                    f"    .data_size = sizeof({name}_map),",
                    f"    .data = (const uint8_t *){name}_map,",
                    "};",
                ]
            )
        lines.extend(
            [
                "",
                "#else",
                f'#error "This image header targets LVGL 8.x; regenerate it with '
                f'--lvgl 8.4 for this build."',
                "#endif",
            ]
        )

    lines.extend(["", f"#endif /* {guard} */", ""])
    return "\n".join(lines)


def generate_image(
    *,
    options: ImageOptions,
    name: str,
    output_path: Path,
    repo_root: Path,
    target_version: str,
    force: bool,
    dry_run: bool,
    manifest_path: Path | None,
) -> dict[str, object]:
    major, _minor = major_minor(target_version)
    conversion_options = options
    version_warnings: list[str] = []
    if major < 9 and options.requested_cf != "A8":
        if options.requested_cf in ("RGB565", "RGB888"):
            version_warnings.append(
                "LVGL 8 stores colour images as 32-bit TRUE_COLOR; "
                f"{options.requested_cf} was widened to BGRA"
            )
        conversion_options = replace(options, requested_cf="ARGB8888")

    image = build_image_data(conversion_options)
    source_hash = sha256_file(options.input_path)
    text = render_image_header(
        name=name,
        image=image,
        target_version=target_version,
        source_path=options.input_path,
        source_sha256=source_hash,
    )
    status = "dry-run"
    if not dry_run:
        status = write_if_changed(output_path, text, force=force)
        if manifest_path is not None:
            merge_manifest_entry(
                manifest_path,
                {
                    "kind": "image",
                    "name": name,
                    "output": output_path.name,
                    "source": options.input_path.name,
                    "source_sha256": source_hash,
                    "options": {
                        "requested_cf": options.requested_cf,
                        "effective_cf": _v8_cf(image) if major < 9 else image.cf,
                        "storage_cf": image.cf,
                        "background": "0x%06X"
                        % (
                            (options.background[0] << 16)
                            | (options.background[1] << 8)
                            | options.background[2]
                        ),
                        "dither": options.dither,
                    },
                    "width": image.width,
                    "height": image.height,
                    "status": "generated",
                },
                target_lvgl=target_version,
            )
    warnings = list(image.warnings) + version_warnings
    payload: dict[str, object] = {
        "ok": True,
        "kind": "image",
        "name": name,
        "status": status,
        "wrote": relative_posix(output_path, repo_root),
        "bytes": len(text.encode("utf-8")),
        "width": image.width,
        "height": image.height,
        "cf": _v8_cf(image) if major < 9 else image.cf,
        "storage_cf": image.cf,
        "target_lvgl": target_version,
        "warnings": warnings,
    }
    return payload
