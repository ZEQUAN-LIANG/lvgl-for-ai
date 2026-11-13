#!/usr/bin/env python3
"""Run the SiFli adapter tests (export, assets, layout)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in ("test_layout", "test_asset_plan", "test_export"):
        suite.addTests(loader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
