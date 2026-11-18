#!/usr/bin/env python3
"""Run the ESP32-C6 host tests without needing a board."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for path in (HOST_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from paths import ensure_import_paths

ensure_import_paths()


def main() -> int:
    suite = unittest.defaultTestLoader.discover(
        str(TESTS_DIR), pattern="test_*.py"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
