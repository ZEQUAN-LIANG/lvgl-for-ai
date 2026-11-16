from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
CONSOLE_ROOT = REPO_ROOT / "console"

for path in (REPO_ROOT, CONSOLE_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

# Importing support installs the retrying TemporaryDirectory used by the whole
# suite; Windows delete-pending handles otherwise make temp cleanup flaky.
from scripts.tests import support  # noqa: E402,F401


def main(argv: list[str] | None = None) -> int:
    names = list(sys.argv[1:] if argv is None else argv)
    loader = unittest.defaultTestLoader
    if names:
        suite = loader.loadTestsFromNames(names)
    else:
        suite = loader.discover(
            str(TESTS_DIR),
            pattern="test_*.py",
            top_level_dir=str(REPO_ROOT),
        )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
