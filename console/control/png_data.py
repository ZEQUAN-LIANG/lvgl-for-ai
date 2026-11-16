from __future__ import annotations

import base64
import binascii
from typing import Any

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA_URL_PREFIX = "data:image/png;base64,"
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096


class PngDataError(ValueError):
    pass


def decode_png_data_url(value: Any) -> bytes:
    if not isinstance(value, str) or not value.startswith(DATA_URL_PREFIX):
        raise PngDataError("image must be a data:image/png;base64 URL")
    encoded = value[len(DATA_URL_PREFIX) :]
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PngDataError("image is not valid base64") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise PngDataError(f"image must be at most {MAX_IMAGE_BYTES} bytes")
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24:
        raise PngDataError("image is not a PNG")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if (
        width < 1
        or height < 1
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
    ):
        raise PngDataError(
            f"image must be at most {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
        )
    return data
