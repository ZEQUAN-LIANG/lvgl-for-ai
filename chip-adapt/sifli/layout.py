"""Canonical layout for the SiFli adapter, downloaded tools and exports.

Only this module knows where the three zones live.  Scripts that need a path
import these constants instead of hardcoding ``chip-adapt/sifli/<app>`` or the
downloaded SDK location.
"""

from __future__ import annotations

from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parent
CHIP_ADAPT_DIR = ADAPTER_DIR.parent
REPO_ROOT = CHIP_ADAPT_DIR.parent
VENDOR_DIR = CHIP_ADAPT_DIR / "vendor"
SDK_DIR = VENDOR_DIR / "sifli-sdk"
EXPORTS_DIR = CHIP_ADAPT_DIR / "exports"
# Per-app export declarations: they describe the device target, so they live
# here instead of inside ``user/app/<name>/``.
APPS_DIR = ADAPTER_DIR / "apps"
HOST_DIR = ADAPTER_DIR / "host"
