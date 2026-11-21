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
