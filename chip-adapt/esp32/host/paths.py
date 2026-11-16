"""Paths shared by the ESP32-C6 host prototype.

The host reuses the SiFli host's serial broker so there is exactly one
``pyserial`` code path (and one vendored pyserial).  Only the board-specific
build/flash pieces are new.
"""

from __future__ import annotations

import sys
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOST_DIR.parents[2]
SIFLI_HOST_DIR = REPO_ROOT / "chip-adapt" / "sifli" / "host"


def ensure_import_paths() -> None:
    for path in (HOST_DIR, SIFLI_HOST_DIR):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
