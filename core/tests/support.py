
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import unittest
import tempfile
import time
import zlib
from pathlib import Path
from unittest import mock

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class RetryingTemporaryDirectory(tempfile.TemporaryDirectory):
    """TemporaryDirectory that waits out Windows delete-pending handles.

    Windows can keep a just-deleted file in the delete-pending state while a
    scanner or another process still holds a handle. ``rmtree`` then sees the
    file during its scan, unlinks it, and the final ``rmdir`` fails with
    ``ERROR_DIR_NOT_EMPTY`` even though the directory is already empty. A few
    bounded retries let the pending delete finish; the last failure is raised,
    so a real cleanup problem still fails the test.
    """

    def cleanup(self) -> None:
        delay = 0.02
        for attempt in range(6):
            try:
                super().cleanup()
                return
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(delay)
                delay *= 2


def install_retrying_tempdir() -> None:
    tempfile.TemporaryDirectory = RetryingTemporaryDirectory


install_retrying_tempdir()


def ensure_host_sdk(version: str = "9.6") -> Path:
    from lvgl_ai import paths

    manifest = paths.sdk_dir_for(version) / "manifest.json"
    if manifest.is_file():
        return manifest
    script = paths.TOOL_ROOT / "tools" / "export_sdk.py"
    result = subprocess.run(
        [
            sys.executable, "-I", "-B", str(script),
            "--version", version, "--force", "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    if result.returncode != 0 or not manifest.is_file():
        raise RuntimeError(
            f"cannot export host SDK {version}: "
            f"{result.stderr.strip()[-1500:]}"
        )
    return manifest


def read_ndjson(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_png_rgb(path: str | Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path} is not a PNG")

    pos = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        pos += 4
        chunk_type = data[pos : pos + 4]
        pos += 4
        chunk = data[pos : pos + length]
        pos += length + 4
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise ValueError(f"{path}: missing IHDR")
    if bit_depth != 8:
        raise ValueError(f"{path}: only 8-bit PNGs are supported, got {bit_depth}")
    channels = _CHANNELS[color_type]
    if color_type == 3:
        raise ValueError(f"{path}: indexed PNGs are not supported")

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    pixels: list[tuple[int, int, int]] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset : offset + stride])
        offset += stride
        _unfilter(row, previous, channels, filter_type)
        for x in range(0, stride, channels):
            pixels.append((row[x], row[x + 1], row[x + 2]))
        previous = row
    return width, height, pixels


def _unfilter(row: bytearray, previous: bytearray, channels: int, filter_type: int) -> None:
    stride = len(row)
    if filter_type == 0:
        return
    if filter_type == 1:
        for i in range(channels, stride):
            row[i] = (row[i] + row[i - channels]) & 0xFF
        return
    if filter_type == 2:
        for i in range(stride):
            row[i] = (row[i] + previous[i]) & 0xFF
        return
    if filter_type == 3:
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            row[i] = (row[i] + ((left + previous[i]) >> 1)) & 0xFF
        return
    if filter_type == 4:
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = previous[i]
            up_left = previous[i - channels] if i >= channels else 0
            estimate = left + up - up_left
            pa = abs(estimate - left)
            pb = abs(estimate - up)
            pc = abs(estimate - up_left)
            if pa <= pb and pa <= pc:
                predictor = left
            elif pb <= pc:
                predictor = up
            else:
                predictor = up_left
            row[i] = (row[i] + predictor) & 0xFF
        return
    raise ValueError(f"unsupported PNG filter {filter_type}")


def distinct_rgb(path: str | Path) -> set[tuple[int, int, int]]:
    _, _, pixels = read_png_rgb(path)
    return set(pixels)


def write_png_rgb(
    path: str | Path,
    width: int,
    height: int,
    pixels: list[tuple[int, int, int]],
) -> None:
    if len(pixels) != width * height:
        raise ValueError("pixel count does not match width * height")
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    data = bytearray(PNG_SIGNATURE)
    _write_chunk(data, b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    _write_chunk(data, b"IDAT", zlib.compress(bytes(raw), 9))
    _write_chunk(data, b"IEND", b"")
    Path(path).write_bytes(bytes(data))


def symlinked_file(
    testcase: unittest.TestCase, link: str | Path, target: str | Path
) -> Path:
    """Make ``link`` behave as a symlink to ``target`` for one test.

    Creating a real symlink needs extra privilege on Windows. When it is
    unavailable the helper writes the target bytes to ``link`` and patches
    ``Path.is_symlink`` for that path, so callers still exercise the symlink
    branch instead of skipping the test or changing its expectations.
    """
    link_path = Path(link)
    target_path = Path(target)
    try:
        os.symlink(target_path, link_path)
    except (OSError, NotImplementedError):
        link_path.write_bytes(target_path.read_bytes())
        original = Path.is_symlink

        def is_symlink(self: Path) -> bool:
            return self == link_path or original(self)

        patcher = mock.patch.object(Path, "is_symlink", is_symlink)
        patcher.start()
        testcase.addCleanup(patcher.stop)
    return link_path


def _write_chunk(out: bytearray, chunk_type: bytes, payload: bytes) -> None:
    out.extend(struct.pack(">I", len(payload)))
    out.extend(chunk_type)
    out.extend(payload)
    out.extend(struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF))
