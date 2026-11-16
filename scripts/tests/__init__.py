"""Test package bootstrap.

Put the repository root and the tool root on ``sys.path`` before any test
module imports ``control``, ``web`` or ``scripts.tests.support``. Importing ``apps``
here pins ``console/appmgr`` in ``sys.modules`` so the top-level ``user/app/`` source
directory cannot shadow it while the repository root is also importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSOLE_ROOT = REPO_ROOT / "console"
for _path in (REPO_ROOT, CONSOLE_ROOT):
    _text = str(_path)
    if _text not in sys.path:
        sys.path.insert(0, _text)

import appmgr  # noqa: F401,E402  (pin console/apps before user/app/)
