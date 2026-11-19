#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
SHARED_HOST_DIR = HOST_DIR.parents[1] / "host"
for path in (HOST_DIR, SHARED_HOST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parent),
        pattern="test_*.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
