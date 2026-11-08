#!/usr/bin/env python3
"""Check the per-version LVGL API navigation documents.

For each ``api-nav/<version>.md``:

* every backticked ``lv_*`` identifier must exist in a header of the matching
  ``lvgl-src/<version>`` tree, unless the line explicitly marks it as a
  version difference (e.g. "9.6 才有", "9.4 没有") or as one of the 8.x shims
  provided by ``user/app/lvgl_compat.h``;
* every backticked ``lvgl-src/...`` or ``user/...`` path must exist;
* the twelve fixed sections, at least eight task-index rows, at least eight
  C snippets, and the ~400 line budget are present.

Run from anywhere with::

    python -I core/tools/check_api_nav.py

Exit code 0 means all documents pass. Exceptions are printed with their line
numbers so they can be recorded in the ticket Progress log.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from lvgl_ai import paths  # noqa: E402

VERSIONS = ("9.6", "9.5", "9.4", "9.1", "8.4", "8.3")

SECTIONS = (
    "版本与源码路径",
    "初始化 / display / indev",
    "对象与控件",
    "样式",
    "布局",
    "事件",
    "定时器与动画",
    "字体与图片",
    "keypad / encoder / group",
    "日志与断言",
    "与相邻版本差异",
    "常见任务索引",
)

SHIMS = {"lv_screen_active", "lv_image_create", "lv_image_set_src"}
SHIM_HEADER = "user/app/lvgl_compat.h"

# A missing symbol is accepted only when the line says it is absent, old, or
# belongs to another version. The exception is printed for the ticket log.
DIFF_MARKER = re.compile(
    r"(无|没有|不可用|不存在|未提供|仅有|只有|仅在|新增|才|不同|差异|改名|"
    r"旧|legacy|shim|9\.x|8\.x|9\.[0-9]|8\.[0-9])"
)

CODE_SPAN = re.compile(r"`([^`\n]+)`")
LV_SYMBOL = re.compile(r"\blv_[a-z0-9_]*[a-z0-9]\b")
PATH_SPAN = re.compile(r"^(lvgl-src|user)/[^\s`]+$")
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def repo_root() -> Path:
    return paths.REPO_ROOT


def header_identifiers(version_root: Path) -> set[str]:
    found: set[str] = set()
    for path in version_root.rglob("*.h"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        found.update(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
    return found


def shim_identifiers(root: Path) -> set[str]:
    path = root / SHIM_HEADER
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))


def section_lines(text: str, name: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"## {name}":
            start = index + 1
            break
    if start is None:
        return []
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return lines[start:end]


def check_document(root: Path, version: str, shims: set[str]) -> list[str]:
    errors: list[str] = []
    doc_path = paths.TOOL_ROOT / "api-nav" / f"{version}.md"
    if not doc_path.is_file():
        return [f"{doc_path}: missing"]

    text = doc_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header_ids = header_identifiers(root / "lvgl-src" / version)

    if len(lines) > 400:
        errors.append(f"{doc_path.name}: {len(lines)} lines exceeds ~400")

    headings = set(HEADING.findall(text))
    for name in SECTIONS:
        if name not in headings:
            errors.append(f"{doc_path.name}: missing section '## {name}'")

    snippet_count = sum(1 for line in lines if line.strip() == "```c")
    if snippet_count < 8:
        errors.append(f"{doc_path.name}: {snippet_count} C snippets (<8)")

    index_rows = [
        line
        for line in section_lines(text, "常见任务索引")
        if "→" in line and "`lvgl-src/" in line
    ]
    if len(index_rows) < 8:
        errors.append(f"{doc_path.name}: {len(index_rows)} task-index rows (<8)")

    symbols: list[tuple[int, str, str]] = []
    path_spans: list[tuple[int, str]] = []
    exceptions: list[tuple[int, str, str]] = []
    missing: list[tuple[int, str]] = []

    for lineno, line in enumerate(lines, 1):
        for span in CODE_SPAN.findall(line):
            if "/" in span or span.endswith(".h"):
                if PATH_SPAN.match(span) and not any(ch in span for ch in "*<>"):
                    path_spans.append((lineno, span))
                continue
            for symbol in LV_SYMBOL.findall(span):
                symbols.append((lineno, symbol, line))
                if symbol in header_ids:
                    continue
                if version in ("8.4", "8.3") and symbol in SHIMS and symbol in shims:
                    exceptions.append((lineno, symbol, "8.x shim"))
                    continue
                if DIFF_MARKER.search(line):
                    exceptions.append((lineno, symbol, "version difference"))
                    continue
                missing.append((lineno, symbol))

    seen_paths: set[str] = set()
    for lineno, path_text in path_spans:
        if path_text in seen_paths:
            continue
        seen_paths.add(path_text)
        target = root / path_text
        if not target.exists():
            errors.append(f"{doc_path.name}:{lineno}: path does not exist: {path_text}")

    for lineno, symbol in missing:
        errors.append(f"{doc_path.name}:{lineno}: symbol not in {version} headers: {symbol}")

    unique_symbols = {symbol for _, symbol, _ in symbols}
    print(
        f"{doc_path.name}: lines={len(lines)} snippets={snippet_count} "
        f"index={len(index_rows)} symbols={len(symbols)} "
        f"unique={len(unique_symbols)} paths={len(seen_paths)} "
        f"exceptions={len(exceptions)} missing={len(missing)}"
    )
    for lineno, symbol, reason in exceptions:
        print(f"  exception line {lineno}: {symbol} ({reason})")
    for error in errors:
        print(f"  ERROR: {error}")

    return errors


def check_readme(root: Path) -> list[str]:
    errors: list[str] = []
    readme = paths.TOOL_ROOT / "api-nav" / "README.md"
    if not readme.is_file():
        return [f"{readme}: missing"]
    text = readme.read_text(encoding="utf-8")
    if "LVGL_AI_LVGL_VERSION" not in text:
        errors.append("README.md: does not mention LVGL_AI_LVGL_VERSION")
    for version in VERSIONS:
        target = f"{version}.md"
        if f"]({target})" not in text:
            errors.append(f"README.md: no link to {target}")
        if not (readme.parent / target).is_file():
            errors.append(f"README.md: linked file missing: {target}")
    print(
        f"README.md: lines={len(text.splitlines())} "
        f"links={sum(text.count(f']({v}.md)') for v in VERSIONS)}"
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="repository root containing lvgl-src/ and user/",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve() if args.repo_root else repo_root()

    shims = shim_identifiers(root)
    errors: list[str] = []
    for version in VERSIONS:
        errors.extend(check_document(root, version, shims))
    errors.extend(check_readme(root))

    if errors:
        print(f"\nFAIL: {len(errors)} problem(s)")
        return 1
    print("\nOK: api-nav documents match lvgl-src headers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
