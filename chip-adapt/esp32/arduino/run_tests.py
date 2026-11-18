#!/usr/bin/env python3
"""Run the ESP32 Arduino adapter tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parent
TESTS_DIR = ADAPTER_DIR / "tests"
for path in (ADAPTER_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(TESTS_DIR), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
