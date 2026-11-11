"""Run the lvgl_ai test suite under ``python -I``.

``-I`` removes the working directory from ``sys.path``, so add the tool root
and the tests directory explicitly (same pattern as the old workbench suite).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOL_ROOT = TESTS_DIR.parent

for path in (TOOL_ROOT, TESTS_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

# Importing support installs the retrying TemporaryDirectory used by the whole
# suite; Windows delete-pending handles otherwise make temp cleanup flaky.
import support  # noqa: E402,F401


def main() -> int:
    suite = unittest.defaultTestLoader.discover(
        str(TESTS_DIR), pattern="test_*.py", top_level_dir=str(TESTS_DIR)
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
