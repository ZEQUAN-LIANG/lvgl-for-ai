from __future__ import annotations

import sys
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOST_DIR.parents[2]
CHIP_ADAPT_DIR = REPO_ROOT / "chip-adapt"
SIFLI_HOST_DIR = CHIP_ADAPT_DIR / "sifli" / "host"
SHARED_HOST_DIR = CHIP_ADAPT_DIR / "host"
TRANSPORT_DIR = HOST_DIR / "transport"
DEVICE_DIR = HOST_DIR / "device"
PERF_DIR = HOST_DIR / "perf"
FLASH_DIR = HOST_DIR / "flash"


def ensure_import_paths() -> None:
    for path in (
        HOST_DIR,
        TRANSPORT_DIR,
        DEVICE_DIR,
        PERF_DIR,
        FLASH_DIR,
        SIFLI_HOST_DIR,
        SHARED_HOST_DIR,
    ):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
