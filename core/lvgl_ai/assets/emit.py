from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from lvgl_ai.paths import TOOL_VERSION

from .errors import AssetError

MANIFEST_SCHEMA = "lvgl-ai-assets-v1"

_C_KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "inline",
    "int",
    "long",
    "register",
    "restrict",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
}


def generator_label() -> str:
    return f"lvgl-verify-loop {TOOL_VERSION}"


def sanitize_identifier(text: str, fallback: str = "asset") -> str:
    value = re.sub(r"[^0-9A-Za-z_]", "_", text.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = fallback
    if value[0].isdigit():
        value = f"{fallback}_{value}"
    if value in _C_KEYWORDS:
        value = f"{fallback}_{value}"
    return value


def header_guard(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "_", name).upper() + "_H"


def include_lvgl() -> str:
    return (
        "#ifdef LV_LVGL_H_INCLUDE_SIMPLE\n"
        '#include "lvgl.h"\n'
        "#else\n"
        '#include "lvgl/lvgl.h"\n'
        "#endif"
    )


def format_c_comment(text: str) -> str:
    return text.replace("*/", "* /").replace("\r", " ").replace("\n", " ")


def codepoint_label(codepoint: int) -> str:
    label = f"U+{codepoint:04X}"
    if 0x20 <= codepoint <= 0x10FFFF and not 0xD800 <= codepoint <= 0xDFFF:
        char = chr(codepoint)
        if char.isprintable() and char not in "\r\n\t":
            label += f" {char}"
    return format_c_comment(label)


def _format_values(
    values: Iterable[int], template: str, per_line: int, indent: str
) -> list[str]:
    rendered = [template.format(value) for value in values]
    lines: list[str] = []
    for start in range(0, len(rendered), per_line):
        chunk = rendered[start : start + per_line]
        lines.append(indent + " ".join(part + "," for part in chunk))
    if not lines:
        lines.append(indent + "0x00,")
    return lines


def format_u8_array(values: Iterable[int], per_line: int = 16) -> list[str]:
    return _format_values(values, "0x{:02X}", per_line, "    ")


def format_u16_array(values: Iterable[int], per_line: int = 12) -> list[str]:
    return _format_values(values, "0x{:04X}", per_line, "    ")


def format_u32_array(values: Iterable[int], per_line: int = 8) -> list[str]:
    return _format_values(values, "0x{:08X}", per_line, "    ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def write_if_changed(path: Path, text: str, force: bool = False) -> str:
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            current = None
        if current == text:
            return "unchanged"
        if not force:
            raise AssetError(
                f"output exists and differs: {path}; pass --force to overwrite"
            )
        atomic_write_text(path, text)
        return "updated"
    atomic_write_text(path, text)
    return "created"


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": MANIFEST_SCHEMA, "assets": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AssetError(f"cannot read asset manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssetError(f"asset manifest {path} is not a JSON object")
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise AssetError(
            f"asset manifest {path} has schema {payload.get('schema')!r}; "
            f"expected {MANIFEST_SCHEMA!r}"
        )
    assets = payload.setdefault("assets", {})
    if not isinstance(assets, dict):
        raise AssetError(f"asset manifest {path}: 'assets' must be an object")
    return payload


def merge_manifest_entry(
    path: Path,
    entry: dict[str, Any],
    target_lvgl: str,
) -> None:
    payload = load_manifest(path)
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise AssetError("asset manifest entry has no name")
    existing = payload["assets"].get(name)
    if isinstance(existing, dict) and existing.get("kind") != entry.get(
        "kind"
    ):
        raise AssetError(
            f"asset name {name!r} is already used by a {existing.get('kind')!r} asset"
        )
    entry = dict(entry)
    entry.setdefault("generator", generator_label())
    entry.setdefault("target_lvgl", target_lvgl)
    payload["schema"] = MANIFEST_SCHEMA
    payload["generator"] = generator_label()
    payload["target_lvgl"] = target_lvgl
    payload["assets"][name] = entry
    text = (
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
    )
    atomic_write_text(path, text)


def relative_posix(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetError(message)
