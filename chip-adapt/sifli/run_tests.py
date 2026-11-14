#!/usr/bin/env python3
"""Run the SiFli adapter tests (layout, asset plan, export)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE / "tests"
for path in (HERE, TESTS):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def main() -> int:
    suite = unittest.defaultTestLoader.discover(
        str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS)
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
