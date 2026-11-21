from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from .errors import AssetError

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"


def ensure_vendor_path() -> Path:
    path = str(VENDOR_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return VENDOR_DIR


def _load(name: str) -> ModuleType:
    ensure_vendor_path()
    try:
        module = __import__(name)
    except ImportError as exc:
        raise AssetError(
            f"bundled {name} dependency is unavailable: {exc}. "
            f"Expected it under {VENDOR_DIR}."
        ) from exc
    filename = getattr(module, "__file__", None)
    if not filename:
        raise AssetError(f"bundled {name} module has no __file__: {module!r}")
    resolved = Path(filename).resolve()
    try:
        resolved.relative_to(VENDOR_DIR)
    except ValueError as exc:
        raise AssetError(
            f"{name} resolved to {resolved}, outside the bundled vendor directory "
            f"{VENDOR_DIR}; remove the system package or run the skill's converter."
        ) from exc
    return module


def load_freetype() -> ModuleType:
    return _load("freetype")


def load_png() -> ModuleType:
    return _load("png")


def versions() -> dict[str, str]:
    freetype = load_freetype()
    png = load_png()
    ft_version = ".".join(str(part) for part in freetype.version())
    return {
        "freetype": ft_version,
        "pypng": getattr(png, "__version__", "unknown"),
        "vendor_dir": str(VENDOR_DIR),
    }
