from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from .errors import AssetError

_PRINTABLE_ASCII = range(0x20, 0x7F)
_SCAN_SUFFIXES = {".c", ".h"}
_SCAN_SKIP_DIRS = {".git", ".trash", "__pycache__", ".cache"}

_SIMPLE_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}


def _parse_int(text: str) -> int:
    text = text.strip()
    if not text:
        raise ValueError("empty number")
    if text.lower().startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def parse_ranges(values: Sequence[str]) -> set[int]:
    result: set[int] = set()
    for raw in values:
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            if "-" in item:
                start_text, end_text = item.split("-", 1)
                try:
                    start = _parse_int(start_text)
                    end = _parse_int(end_text)
                except ValueError as exc:
                    raise AssetError(
                        f"invalid --range item: {item!r}"
                    ) from exc
                if start > end:
                    raise AssetError(
                        f"invalid --range item (start > end): {item!r}"
                    )
                result.update(range(start, end + 1))
            else:
                try:
                    result.add(_parse_int(item))
                except ValueError as exc:
                    raise AssetError(
                        f"invalid --range item: {item!r}"
                    ) from exc
    return result


def _decode_c_literal(raw: str) -> str:
    parts: list[bytes] = []
    index = 0
    length = len(raw)
    while index < length:
        char = raw[index]
        if char != "\\":
            parts.append(char.encode("utf-8"))
            index += 1
            continue

        index += 1
        if index >= length:
            parts.append(b"\\")
            break
        escaped = raw[index]
        index += 1

        if escaped == "\n":
            continue
        if escaped in _SIMPLE_ESCAPES:
            parts.append(_SIMPLE_ESCAPES[escaped].encode("utf-8"))
            continue
        if escaped == "x":
            digits = raw[index : index + 2]
            if len(digits) != 2 or not re.fullmatch(r"[0-9A-Fa-f]{2}", digits):
                raise AssetError(
                    f"invalid \\x escape in C string: \\x{digits}"
                )
            parts.append(bytes([int(digits, 16)]))
            index += 2
            continue
        if escaped == "u":
            digits = raw[index : index + 4]
            if len(digits) != 4 or not re.fullmatch(r"[0-9A-Fa-f]{4}", digits):
                raise AssetError(
                    f"invalid \\u escape in C string: \\u{digits}"
                )
            parts.append(chr(int(digits, 16)).encode("utf-8"))
            index += 4
            continue
        if escaped == "U":
            digits = raw[index : index + 8]
            if len(digits) != 8 or not re.fullmatch(r"[0-9A-Fa-f]{8}", digits):
                raise AssetError(
                    f"invalid \\U escape in C string: \\U{digits}"
                )
            parts.append(chr(int(digits, 16)).encode("utf-8"))
            index += 8
            continue
        if escaped in "01234567":
            digits = escaped
            while (
                index < length and len(digits) < 3 and raw[index] in "01234567"
            ):
                digits += raw[index]
                index += 1
            parts.append(bytes([int(digits, 8) & 0xFF]))
            continue

        parts.append(escaped.encode("utf-8"))

    return b"".join(parts).decode("utf-8", errors="replace")


def scan_c_strings(text: str) -> list[str]:
    strings: list[str] = []
    state = "code"
    buffer: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if state == "code":
            if char == '"':
                state = "string"
                buffer = []
            elif char == "'":
                state = "char"
            elif char == "/" and index + 1 < length and text[index + 1] == "/":
                state = "line"
                index += 1
            elif char == "/" and index + 1 < length and text[index + 1] == "*":
                state = "block"
                index += 1
        elif state == "line":
            if char == "\n":
                state = "code"
        elif state == "block":
            if char == "*" and index + 1 < length and text[index + 1] == "/":
                state = "code"
                index += 1
        elif state == "char":
            if char == "\\":
                index += 1
            elif char == "'":
                state = "code"
        else:
            if char == "\\":
                buffer.append(char)
                index += 1
                if index < length:
                    buffer.append(text[index])
            elif char == '"':
                strings.append(_decode_c_literal("".join(buffer)))
                state = "code"
            else:
                buffer.append(char)
        index += 1
    return strings


def _iter_source_files(app_dir: Path) -> Iterable[Path]:
    for path in sorted(app_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        if any(part in _SCAN_SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan_app_sources(app_dir: Path) -> tuple[set[int], dict[str, object]]:
    if not app_dir.is_dir():
        raise AssetError(f"app directory not found: {app_dir}")
    codepoints: set[int] = set()
    files: list[str] = []
    literals = 0
    for path in _iter_source_files(app_dir):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise AssetError(f"cannot read C source {path}: {exc}") from exc
        found = scan_c_strings(text)
        if not found:
            continue
        files.append(path.name)
        literals += len(found)
        for literal in found:
            for char in literal:
                codepoints.add(ord(char))
    return codepoints, {
        "scanned_files": files,
        "scanned_literals": literals,
    }


def _valid_codepoint(value: int) -> bool:
    if value < 0x20 or value == 0x7F:
        return False
    if value > 0x10FFFF:
        return False
    if 0xD800 <= value <= 0xDFFF:
        return False
    return True


def build_charset(
    *,
    texts: Sequence[str] = (),
    text_files: Sequence[Path] = (),
    ranges: Sequence[str] = (),
    scan_app_dir: Path | None = None,
    include_ascii: bool = True,
) -> tuple[list[int], dict[str, object]]:
    codepoints: set[int] = set()
    metadata: dict[str, object] = {}
    explicit = bool(texts or text_files or ranges)

    if include_ascii:
        codepoints.update(_PRINTABLE_ASCII)

    for text in texts:
        codepoints.update(ord(char) for char in text)

    for path in text_files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise AssetError(f"cannot read --text-file {path}: {exc}") from exc
        codepoints.update(ord(char) for char in text)

    if ranges:
        try:
            codepoints.update(parse_ranges(ranges))
        except AssetError:
            raise

    if scan_app_dir is not None:
        scanned, scan_meta = scan_app_sources(scan_app_dir)
        codepoints.update(scanned)
        metadata.update(scan_meta)
        metadata["scanned_codepoints"] = len(scanned)

    filtered = sorted(cp for cp in codepoints if _valid_codepoint(cp))
    if not filtered:
        raise AssetError(
            "empty character set; pass --text/--text-file/--range or --scan-app"
        )
    metadata["codepoint_count"] = len(filtered)
    metadata["explicit_charset"] = explicit
    return filtered, metadata
