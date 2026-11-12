"""Configuration for the SiFli Huangshan Pi serial host.

The host is deliberately chip-specific: paths point at the downloaded SDK,
toolchain and official Web Flasher assets under ``chip-adapt/sifli/vendor``.
Nothing here imports ``core``; the LVGL harness and this host are separate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

HOST_DIR = Path(__file__).resolve().parent
SIFLI_DIR = HOST_DIR.parent
CHIP_ADAPT_DIR = SIFLI_DIR.parent
REPO_ROOT = CHIP_ADAPT_DIR.parent
VENDOR_DIR = SIFLI_DIR / "vendor"

CONFIG_PATH = HOST_DIR / "config.json"

PATH_KEYS = (
    "sdk_root",
    "toolchain_root",
    "sftool",
    "export_script",
    "export_ps1",
    "web_flasher_dir",
    "project_dir",
    "log_dir",
    "firmware_cache_dir",
)

DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8766,
    "default_baud": 1_000_000,
    "baud_rates": [
        1_000_000,
        921_600,
        460_800,
        230_400,
        115_200,
        57_600,
        38_400,
        19_200,
        9_600,
    ],
    "board": "sf32lb52-lchspi-ulp",
    "sdk_root": str(VENDOR_DIR / "sifli-sdk"),
    "toolchain_root": str(VENDOR_DIR / "toolchain"),
    "sftool": str(VENDOR_DIR / "toolchain" / "sftool" / "sftool.exe"),
    "export_script": str(SIFLI_DIR / "export.py"),
    "export_ps1": str(VENDOR_DIR / "sifli-sdk" / "export.ps1"),
    "web_flasher_dir": str(
        VENDOR_DIR / "SiFli-Wiki" / "source" / "_static" / "sftool"
    ),
    "project_dir": "",
    "app": "",
    "build_command": [],
    "build_timeout_sec": 1_800,
    "flash_timeout_sec": 300,
    "flash_baud": 1_000_000,
    "flash_verify": True,
    "flash_erase_all": False,
    "flash_after": "soft_reset",
    "ring_buffer_bytes": 2 * 1024 * 1024,
    "max_read_bytes": 256 * 1024,
    "auto_reconnect": True,
    "reconnect_interval_s": 0.8,
    "reconnect_max_delay_s": 5.0,
    "log_dir": str(HOST_DIR / "logs"),
    "firmware_cache_dir": str(HOST_DIR / ".cache" / "firmware"),
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_path(value: Any) -> str:
    if value in (None, ""):
        return ""
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path.resolve())


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load ``host/config.json`` and merge it over the defaults.

    Relative paths in the JSON file are resolved against the repository root,
    so a config can say ``"project_dir": "chip-adapt/sifli/hspi_watch/project"``.
    """

    config_path = Path(path) if path else CONFIG_PATH
    loaded: dict[str, Any] = {}
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"cannot read {config_path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise SystemExit(f"{config_path} must contain a JSON object")

    config = _deep_merge(DEFAULT_CONFIG, loaded)

    # Environment overrides are useful for tests and for launching more than
    # one broker without editing config.json.
    env_map = {
        "host": "SIFLI_HOST_BIND",
        "port": "SIFLI_HOST_PORT",
        "default_baud": "SIFLI_HOST_BAUD",
        "sftool": "SIFLI_HOST_SFTOOL",
        "sdk_root": "SIFLI_HOST_SDK",
        "project_dir": "SIFLI_HOST_PROJECT_DIR",
    }
    for key, env_name in env_map.items():
        if os.environ.get(env_name):
            config[key] = os.environ[env_name]

    config["port"] = int(config["port"])
    config["default_baud"] = int(config["default_baud"])
    config["flash_baud"] = int(config["flash_baud"])
    config["ring_buffer_bytes"] = int(config["ring_buffer_bytes"])
    config["max_read_bytes"] = int(config["max_read_bytes"])

    for key in PATH_KEYS:
        config[key] = _resolve_path(config.get(key))
    config["repo_root"] = str(REPO_ROOT)
    config["host_dir"] = str(HOST_DIR)
    config["config_path"] = str(config_path)
    config["config_exists"] = config_path.is_file()
    return config


def ensure_runtime_dirs(config: dict[str, Any]) -> None:
    Path(config["log_dir"]).mkdir(parents=True, exist_ok=True)
    Path(config["firmware_cache_dir"]).mkdir(parents=True, exist_ok=True)


def public_base_url(config: dict[str, Any]) -> str:
    host = str(config.get("host") or "127.0.0.1")
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{int(config['port'])}"
