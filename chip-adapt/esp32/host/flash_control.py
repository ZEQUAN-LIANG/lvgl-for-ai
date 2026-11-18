"""esptool-backed firmware flashing for the ESP32-C6 host.

The host owns the COM port through ``SerialBroker``; flashing releases it,
runs the official ``esptool`` CLI, and reattaches when asked.  Firmware can be
an explicit BIN list, an ESP-IDF build directory with ``flash_args``, or a ZIP
(Waveshare demo or an ESP-IDF build archive).  ZIPs are scanned first and only
the referenced BINs are extracted, because the demo archive expands to ~260 MB.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CHIP = "esp32c6"
DEFAULT_FLASH_BAUD = 460800
MAX_UPLOAD_BYTES = 128 * 1024 * 1024
MAX_EXTRACT_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
PLAN_TTL_S = 600
MAX_PLANS = 20
KEEP_UPLOADS = 10
KEEP_WORKDIRS = 10

AFTER_CHOICES = ("hard_reset", "soft_reset", "no_reset", "no_reset_stub")
BEFORE_CHOICES = (
    "default_reset",
    "usb_reset",
    "no_reset",
    "no_reset_no_sync",
)

_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
)
_PROGRESS_RE = re.compile(r"\((\d{1,3})\s*%\)")
_PROGRESS_RE_5 = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ADDRESS_RE = re.compile(r"^(0x[0-9a-fA-F]+|[0-9]+)$")
_TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")
_VERSION_CACHE: dict[tuple[str, ...], tuple[float, tuple[int, int, int] | None]] = {}
_VERSION_TTL_S = 60.0


class FlashError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "flash_error",
        status: int = 400,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.extra = extra or {}


@dataclass(frozen=True)
class Esptool:
    prefix: tuple[str, ...]
    label: str
    version: tuple[int, int, int]


# ------------------------------------------------------------------ esptool --


def _run_probe(command: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )


def _probe_version(
    prefix: tuple[str, ...],
    *,
    timeout: float = 20.0,
) -> tuple[int, int, int] | None:
    now = time.time()
    cached = _VERSION_CACHE.get(prefix)
    if cached and now - cached[0] < _VERSION_TTL_S:
        return cached[1]
    version: tuple[int, int, int] | None = None
    try:
        proc = _run_probe([*prefix, "version"], timeout=timeout)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", output)
            if match:
                version = tuple(int(item) for item in match.groups())
    except (OSError, subprocess.SubprocessError, ValueError):
        version = None
    _VERSION_CACHE[prefix] = (now, version)
    return version


def _esptool_candidates(config: dict[str, Any]) -> Iterable[tuple[tuple[str, ...], str]]:
    seen: set[tuple[str, ...]] = set()

    def add(prefix: tuple[str, ...], label: str) -> Iterable[tuple[tuple[str, ...], str]]:
        if prefix in seen:
            return ()
        seen.add(prefix)
        return ((prefix, label),)

    configured = str(config.get("esptool") or "").strip()
    env_value = str(os.environ.get("ESPTOOL_BIN") or "").strip()
    for value in (configured, env_value):
        if not value:
            continue
        path = Path(value).expanduser()
        if path.suffix.lower() == ".py":
            yield from add((sys.executable, str(path)), str(path))
        elif path.name.lower() in ("python.exe", "python", "python3"):
            yield from add((str(path), "-m", "esptool"), f"{path} -m esptool")
        else:
            yield from add((str(path),), str(path))

    vendor = Path(__file__).resolve().parent / "vendor" / "esptool"
    if os.name == "nt":
        vendor_python = vendor / "Scripts" / "python.exe"
        vendor_exes = (
            vendor / "Scripts" / "esptool.exe",
            vendor / "Scripts" / "esptool-script.py",
        )
    else:
        vendor_python = vendor / "bin" / "python"
        vendor_exes = (vendor / "bin" / "esptool",)
    # Prefer ``python -m esptool``: the pip console launcher spawns a child
    # Python process, so terminating the launcher can orphan the real flasher.
    if vendor_python.is_file():
        yield from add(
            (str(vendor_python), "-m", "esptool"),
            f"{vendor_python} -m esptool",
        )
    for exe in vendor_exes:
        if not exe.is_file():
            continue
        if exe.suffix == ".py":
            yield from add((sys.executable, str(exe)), str(exe))
        else:
            yield from add((str(exe),), str(exe))

    for name in ("esptool", "esptool.py"):
        found = shutil.which(name)
        if not found:
            continue
        if name.endswith(".py"):
            yield from add((sys.executable, found), found)
        else:
            yield from add((found,), found)

    python_env = str(os.environ.get("IDF_PYTHON_ENV_PATH") or "").strip()
    idf_pythons: list[Path] = []
    if python_env:
        candidate = Path(python_env) / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        if candidate.is_file():
            idf_pythons.append(candidate)
    espressif = Path.home() / ".espressif" / "python_env"
    if espressif.is_dir():
        for directory in sorted(espressif.iterdir(), reverse=True):
            candidate = directory / (
                "Scripts/python.exe" if os.name == "nt" else "bin/python"
            )
            if candidate.is_file():
                idf_pythons.append(candidate)
    for python in idf_pythons:
        yield from add(
            (str(python), "-m", "esptool"),
            f"{python} -m esptool",
        )

    yield from add(
        (sys.executable, "-m", "esptool"),
        f"{sys.executable} -m esptool",
    )


def find_esptool(config: dict[str, Any]) -> Esptool | None:
    for prefix, label in _esptool_candidates(config):
        version = _probe_version(prefix)
        if version is not None:
            return Esptool(prefix=prefix, label=label, version=version)
    return None


def version_text(version: tuple[int, int, int]) -> str:
    return ".".join(str(item) for item in version)


# ------------------------------------------------------------------ helpers --


def parse_address(value: Any) -> int:
    text = str(value).strip()
    if not _ADDRESS_RE.match(text):
        raise FlashError(
            f"invalid flash address: {value!r}",
            code="bad_address",
        )
    number = int(text, 16) if text.lower().startswith("0x") else int(text, 10)
    if number < 0 or number > 0xFFFFFFFF:
        raise FlashError(
            f"flash address out of range: {text}",
            code="bad_address",
        )
    return number


def format_address(value: Any) -> str:
    return f"0x{parse_address(value):x}"


def _safe_name(name: str) -> str:
    text = str(name).replace("\\", "/")
    base = Path(text).name.strip()
    base = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", base)
    if not base or base in (".", ".."):
        base = "firmware.bin"
    if base.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
        "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3",
    }:
        base = "_" + base
    return base[:120]


def _ensure_inside(root: Path, target: Path) -> Path:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise FlashError(
            f"path escapes the firmware directory: {target}",
            code="path_escape",
        ) from exc
    return resolved_target


def _zip_rel_name(info: zipfile.ZipInfo) -> str:
    name = info.filename.replace("\\", "/")
    if info.flag_bits & 0x1:
        raise FlashError(
            f"zip entry is encrypted: {info.filename}",
            code="bad_zip",
        )
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise FlashError(f"unsafe zip entry: {info.filename}", code="bad_zip")
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise FlashError(f"unsafe zip entry: {info.filename}", code="bad_zip")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise FlashError(f"zip entry is a symlink: {info.filename}", code="bad_zip")
    return "/".join(parts)


def _extract_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    target: Path,
    budget: list[int],
) -> Path:
    relative = _zip_rel_name(info)
    if not relative:
        raise FlashError(f"empty zip entry: {info.filename}", code="bad_zip")
    destination = _ensure_inside(target, target / relative)
    size = int(info.file_size or 0)
    if size <= 0:
        raise FlashError(f"empty firmware image: {info.filename}", code="bad_zip")
    if size > MAX_IMAGE_BYTES:
        raise FlashError(
            f"firmware image too large: {info.filename}",
            code="image_too_large",
        )
    budget[0] += size
    if budget[0] > MAX_EXTRACT_BYTES:
        raise FlashError(
            "extracted firmware exceeds the size limit",
            code="image_too_large",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as source, destination.open("wb") as sink:
        shutil.copyfileobj(source, sink, length=1024 * 1024)
    return destination


def parse_flash_args_text(text: str) -> dict[str, Any]:
    tokens = shlex.split(text)
    mode = freq = size = None
    pairs: list[tuple[str, str]] = []
    index = 0
    options = {
        "--flash_mode": "mode",
        "--flash_freq": "freq",
        "--flash_size": "size",
        "--flash-mode": "mode",
        "--flash-freq": "freq",
        "--flash-size": "size",
    }
    while index < len(tokens):
        token = tokens[index]
        key = token.lower()
        if "=" in token:
            option, value = token.split("=", 1)
            option_key = option.lower()
            if option_key in options:
                target = options[option_key]
                if target == "mode":
                    mode = value
                elif target == "freq":
                    freq = value
                else:
                    size = value
                index += 1
                continue
        if key in options and index + 1 < len(tokens):
            value = tokens[index + 1]
            target = options[key]
            if target == "mode":
                mode = value
            elif target == "freq":
                freq = value
            else:
                size = value
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        if index + 1 >= len(tokens):
            raise FlashError(
                "flash_args is missing a file after an address",
                code="bad_flash_args",
            )
        pairs.append((token, tokens[index + 1]))
        index += 2
    if not pairs:
        raise FlashError(
            "flash_args contains no image entries",
            code="bad_flash_args",
        )
    return {
        "flash_mode": mode,
        "flash_freq": freq,
        "flash_size": size,
        "pairs": pairs,
    }


def parse_flasher_args_json(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("flash_files")
    if not isinstance(files, dict) or not files:
        raise FlashError(
            "flasher_args.json has no flash_files",
            code="bad_flash_args",
        )
    settings = payload.get("flash_settings") or {}
    if not isinstance(settings, dict):
        settings = {}
    pairs = [(str(address), str(name)) for address, name in files.items()]
    return {
        "flash_mode": settings.get("flash_mode"),
        "flash_freq": settings.get("flash_freq"),
        "flash_size": settings.get("flash_size"),
        "pairs": pairs,
    }


def _entry(path: Path, address: Any, work_dir: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FlashError(
            f"firmware image not found: {path}",
            code="image_missing",
        )
    size = resolved.stat().st_size
    if size <= 0:
        raise FlashError(
            f"firmware image is empty: {path}",
            code="image_missing",
        )
    if size > MAX_IMAGE_BYTES:
        raise FlashError(
            f"firmware image too large: {path}",
            code="image_too_large",
        )
    try:
        relative = Path(os.path.relpath(resolved, work_dir)).as_posix()
    except ValueError:
        relative = resolved.as_posix()
    return {
        "path": relative,
        "name": resolved.name,
        "address": format_address(address),
        "size": size,
    }


def _single_bin_plan(
    path: Path,
    *,
    address: Any,
    source: str,
) -> dict[str, Any]:
    work_dir = path.resolve().parent
    entry = _entry(path, address, work_dir)
    return {
        "entries": [entry],
        "work_dir": str(work_dir),
        "source": source,
        "notes": "单 BIN",
    }


def _directory_plan(directory: Path, address: Any) -> dict[str, Any]:
    directory = directory.resolve()
    parsed: dict[str, Any] | None = None
    notes = ""
    args_path = directory / "flash_args"
    json_path = directory / "flasher_args.json"
    if args_path.is_file():
        parsed = parse_flash_args_text(
            args_path.read_text(encoding="utf-8", errors="replace")
        )
        notes = "ESP-IDF flash_args"
    elif json_path.is_file():
        try:
            payload = json.loads(
                json_path.read_text(encoding="utf-8", errors="replace")
            )
        except ValueError as exc:
            raise FlashError(
                f"cannot parse flasher_args.json: {exc}",
                code="bad_flash_args",
            ) from exc
        parsed = parse_flasher_args_json(payload)
        notes = "ESP-IDF flasher_args.json"
    if parsed is not None:
        entries = [
            _entry(_ensure_inside(directory, directory / name), addr, directory)
            for addr, name in parsed["pairs"]
        ]
        return {
            "entries": entries,
            "work_dir": str(directory),
            "flash_mode": parsed["flash_mode"],
            "flash_freq": parsed["flash_freq"],
            "flash_size": parsed["flash_size"],
            "source": "idf",
            "notes": notes,
        }
    images = sorted(
        path for path in directory.glob("*.bin") if path.is_file()
    )
    if not images:
        raise FlashError(
            f"no .bin or flash_args found in {directory}",
            code="no_images",
        )
    if len(images) > 1:
        raise FlashError(
            "multiple .bin files found; point at flash_args or pass --file",
            code="ambiguous_images",
            extra={"candidates": [path.name for path in images]},
        )
    return _single_bin_plan(
        images[0],
        address=0 if address is None else address,
        source="bin",
    )


def _zip_plan(
    archive_path: Path,
    *,
    address: Any,
    work_root: Path,
) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise FlashError(
            f"cannot read zip: {archive_path}",
            code="bad_zip",
        ) from exc
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        by_name = {_zip_rel_name(info): info for info in infos}
        names = sorted(by_name)

        json_names = [
            name
            for name in names
            if name.rsplit("/", 1)[-1] == "flasher_args.json"
        ]
        args_names = [
            name for name in names if name.rsplit("/", 1)[-1] == "flash_args"
        ]
        for candidates in (json_names, args_names):
            if len(candidates) > 1:
                raise FlashError(
                    "multiple IDF argument files found in the zip",
                    code="ambiguous_flash_args",
                    extra={"candidates": candidates},
                )
        parsed: dict[str, Any] | None = None
        prefix = ""
        notes = ""
        if json_names:
            name = json_names[0]
            try:
                payload = json.loads(
                    archive.read(by_name[name]).decode("utf-8", "replace")
                )
            except ValueError as exc:
                raise FlashError(
                    f"cannot parse flasher_args.json: {exc}",
                    code="bad_flash_args",
                ) from exc
            parsed = parse_flasher_args_json(payload)
            prefix = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
            notes = "ESP-IDF flasher_args.json（zip）"
        elif args_names:
            name = args_names[0]
            parsed = parse_flash_args_text(
                archive.read(by_name[name]).decode("utf-8", "replace")
            )
            prefix = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
            notes = "ESP-IDF flash_args（zip）"
        if parsed is not None:
            target = work_root / uuid.uuid4().hex[:8]
            target.mkdir(parents=True, exist_ok=True)
            budget = [0]
            entries: list[dict[str, Any]] = []
            for addr, name in parsed["pairs"]:
                relative = name.replace("\\", "/")
                zip_name = prefix + relative
                info = by_name.get(zip_name)
                if info is None:
                    raise FlashError(
                        f"IDF args reference a missing zip entry: {zip_name}",
                        code="bad_flash_args",
                    )
                saved = _extract_member(archive, info, target, budget)
                entries.append(
                    {
                        "path": Path(os.path.relpath(saved, target)).as_posix(),
                        "name": saved.name,
                        "address": format_address(addr),
                        "size": saved.stat().st_size,
                    }
                )
            return {
                "entries": entries,
                "work_dir": str(target),
                "flash_mode": parsed["flash_mode"],
                "flash_freq": parsed["flash_freq"],
                "flash_size": parsed["flash_size"],
                "source": "idf",
                "notes": notes,
            }

        firmware = [
            name
            for name in names
            if re.search(r"(^|/)Firmware/[^/]+\.bin$", name, re.IGNORECASE)
        ]
        candidates = firmware
        notes = "Waveshare 示例固件"
        if not candidates:
            candidates = [name for name in names if name.lower().endswith(".bin")]
            notes = "zip 内 BIN"
        if not candidates:
            raise FlashError(
                "no .bin or flash_args found in the zip",
                code="no_images",
            )
        if len(candidates) > 1:
            raise FlashError(
                "multiple .bin files found in the zip; flash one explicitly",
                code="ambiguous_images",
                extra={"candidates": candidates},
            )
        target = work_root / uuid.uuid4().hex[:8]
        target.mkdir(parents=True, exist_ok=True)
        budget = [0]
        info = by_name[candidates[0]]
        saved = _extract_member(archive, info, target, budget)
        return {
            "entries": [
                {
                    "path": Path(os.path.relpath(saved, target)).as_posix(),
                    "name": saved.name,
                    "address": format_address(
                        0 if address is None else address
                    ),
                    "size": saved.stat().st_size,
                }
            ],
            "work_dir": str(target),
            "source": "bin",
            "notes": notes,
        }


def _files_plan(files: list[Any], address: Any) -> dict[str, Any]:
    if not files:
        raise FlashError("no firmware files were given", code="no_images")
    normalized: list[tuple[Path, Any]] = []
    for item in files:
        if isinstance(item, dict):
            raw_path = item.get("path") or item.get("file") or ""
            item_address = item.get("address")
        else:
            raw_path = item
            item_address = None
        path = Path(str(raw_path)).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        normalized.append((path, item_address))
    if len(normalized) == 1 and normalized[0][1] is None:
        normalized[0] = (
            normalized[0][0],
            0 if address is None else address,
        )
    for path, item_address in normalized:
        if item_address is None:
            raise FlashError(
                f"address is required for {path.name}",
                code="address_required",
            )
    work_dir = Path.cwd()
    entries = [
        _entry(path, item_address, work_dir)
        for path, item_address in normalized
    ]
    return {
        "entries": entries,
        "work_dir": str(work_dir),
        "source": "files",
        "notes": "手动文件列表",
    }


def plan_from_path(
    path: Path,
    *,
    address: Any = None,
    work_root: Path | None = None,
) -> dict[str, Any]:
    path = path.expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if path.is_dir():
        return _directory_plan(path, address)
    if not path.is_file():
        raise FlashError(f"path not found: {path}", code="path_missing")
    suffix = path.suffix.lower()
    if suffix == ".zip":
        root = work_root or _default_work_root()
        root.mkdir(parents=True, exist_ok=True)
        return _zip_plan(path, address=address, work_root=root)
    if suffix == ".bin":
        return _single_bin_plan(
            path,
            address=0 if address is None else address,
            source="bin",
        )
    raise FlashError(
        f"unsupported firmware file: {path.name}",
        code="unsupported_source",
    )


def _default_work_root() -> Path:
    return Path(__file__).resolve().parent / ".cache" / "flash" / "work"


# ----------------------------------------------------------------- progress --


class _Progress:
    def __init__(self, total: int) -> None:
        self.total = max(1, int(total))
        self.done = 0
        self._lock = threading.Lock()

    def percent_for(self, line: str) -> int | None:
        with self._lock:
            percent: int | None = None
            match = None
            if "Writing at" in line:
                match = _PROGRESS_RE.search(line) or _PROGRESS_RE_5.search(line)
            if match:
                value = min(100.0, max(0.0, float(match.group(1))))
                percent = int(
                    (self.done + value / 100.0) / self.total * 100
                )
            if "Hash of data verified." in line:
                self.done = min(self.total, self.done + 1)
                percent = int(self.done / self.total * 100)
            return percent


def _run_streaming(
    job: Any,
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    progress: _Progress,
) -> tuple[int, list[str], list[str]]:
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise FlashError(
            f"command not found: {command[0]}",
            code="esptool_missing",
            status=409,
        ) from exc

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def pump(stream, name: str, sink: list[str]) -> None:
        try:
            for raw in iter(stream.readline, ""):
                for line in raw.replace("\r", "\n").split("\n"):
                    line = line.rstrip()
                    if not line:
                        continue
                    sink.append(line)
                    job.append(
                        name,
                        line,
                        percent=progress.percent_for(line),
                    )
        finally:
            try:
                stream.close()
            except OSError:
                pass

    threads = [
        threading.Thread(
            target=pump,
            args=(process.stdout, "stdout", stdout_lines),
            daemon=True,
        ),
        threading.Thread(
            target=pump,
            args=(process.stderr, "stderr", stderr_lines),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    started = time.monotonic()
    while process.poll() is None:
        if job.cancel_event.is_set():
            _stop_process(process)
            raise FlashError("cancelled", code="cancelled")
        if time.monotonic() - started > max(1.0, float(timeout_s)):
            _stop_process(process)
            raise FlashError(
                f"esptool timed out after {int(timeout_s)}s",
                code="timeout",
            )
        time.sleep(0.1)

    for thread in threads:
        thread.join(timeout=2)
    return int(process.returncode or 0), stdout_lines, stderr_lines


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def preferred_flash_port() -> str:
    """Pick a likely ESP32 USB-serial port; return ``""`` when unsure."""
    try:
        from broker import ports as serial_ports

        items = serial_ports()
    except Exception:  # noqa: BLE001 - listing ports is best effort
        return ""
    tokens = (
        "303a",
        "usb jtag",
        "usb serial",
        "usb-serial",
        "usb 串行",
        "usb串行",
        "ch340",
        "ch341",
        "cp210",
        "ftdi",
        "silicon labs",
    )
    for item in items:
        text = " ".join(
            str(item.get(key) or "")
            for key in ("port", "description", "hwid", "manufacturer")
        ).lower()
        if any(token in text for token in tokens):
            return str(item.get("port") or "")
    return ""


def _tail(lines: list[str], count: int = 15) -> str:
    return "\n".join(lines[-count:]) if lines else ""


# ------------------------------------------------------------------- command --


def build_flash_command(
    esptool: Esptool,
    port: str,
    baud: int,
    plan: dict[str, Any],
    options: dict[str, Any],
) -> list[str]:
    major = esptool.version[0] if esptool.version else 4
    before = str(options.get("before") or "default_reset")
    after = str(options.get("after") or "hard_reset")
    if before not in BEFORE_CHOICES:
        raise FlashError(f"unsupported reset mode: {before}", code="bad_option")
    if after not in AFTER_CHOICES:
        raise FlashError(f"unsupported after-reset mode: {after}", code="bad_option")
    if major >= 5:
        before = before.replace("_", "-")
        after = after.replace("_", "-")
    try:
        rate = int(baud)
    except (TypeError, ValueError) as exc:
        raise FlashError(f"invalid baud rate: {baud}", code="bad_option") from exc
    if rate <= 0:
        raise FlashError(f"invalid baud rate: {baud}", code="bad_option")
    command = [
        *esptool.prefix,
        "--chip",
        CHIP,
        "--port",
        str(port),
        "--baud",
        str(rate),
        "--before",
        before,
        "--after",
        after,
        "write-flash" if major >= 5 else "write_flash",
    ]
    if options.get("erase_all"):
        command.append("--erase-all")
    if major < 5 and options.get("verify", True):
        command.append("--verify")
    flash_options = {
        "flash_mode": "--flash-mode" if major >= 5 else "--flash_mode",
        "flash_freq": "--flash-freq" if major >= 5 else "--flash_freq",
        "flash_size": "--flash-size" if major >= 5 else "--flash_size",
    }
    for key, flag in flash_options.items():
        value = plan.get(key)
        if value and value != "keep":
            command.extend([flag, str(value)])
    for entry in plan["entries"]:
        command.extend([entry["address"], entry["path"]])
    return command


# ---------------------------------------------------------------- controller --


class FlashController:
    def __init__(
        self,
        host_dir: Path,
        config: dict[str, Any],
        broker: Any,
        *,
        fake: bool = False,
    ) -> None:
        self.host_dir = Path(host_dir)
        self.config = dict(config)
        self.broker = broker
        self.fake = bool(fake)
        cache = self.config.get("flash_cache_dir")
        self.cache_root = Path(cache) if cache else (
            self.host_dir / ".cache" / "flash"
        )
        self.uploads_root = self.cache_root / "uploads"
        self.work_root = self.cache_root / "work"
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._flash_lock = threading.Lock()
        self._plans: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------- environment

    def environment(self) -> dict[str, Any]:
        esptool = find_esptool(self.config)
        suggestions: list[dict[str, Any]] = []
        demo = (
            self.host_dir.parents[2]
            / "chip-adapt"
            / "vendor"
            / "esp32"
            / "demo"
            / "ESP32-C6-LCD-1.47-Demo.zip"
        )
        if demo.is_file():
            suggestions.append(
                {"label": "Waveshare 示例固件", "path": str(demo)}
            )
        default_baud = int(
            self.config.get("flash_baud") or DEFAULT_FLASH_BAUD
        )
        try:
            status = self.broker.status()
        except Exception:  # noqa: BLE001 - status is best effort
            status = {}
        transport = str(status.get("transport") or "")
        links = status.get("links") or {}
        if transport == "serial":
            current_port = str(status.get("port") or "")
        else:
            current_port = str(
                (links.get("serial") or {}).get("port") or ""
            )
        if (
            os.name == "nt"
            and current_port
            and not current_port.upper().startswith("COM")
        ):
            current_port = ""
        if not current_port:
            current_port = "COM99" if self.fake else preferred_flash_port()
        version = version_text(esptool.version) if esptool else ""
        found = esptool is not None
        backend = {
            "kind": "esptool",
            "name": "esptool",
            "found": found,
            "label": esptool.label if esptool else "",
            "version": version,
            "chip": "ESP32-C6",
            "board": CHIP,
            "detail": (
                "模拟后端（不调用 esptool）"
                if self.fake
                else (
                    f"esptool {version} · {esptool.label}"
                    if esptool
                    else "未找到 esptool"
                )
            ),
        }
        payload: dict[str, Any] = {
            "fake": self.fake,
            "default_baud": default_baud,
            "baud_rates": [115200, 230400, 460800, 921600],
            "max_upload_bytes": int(
                self.config.get("flash_max_upload_bytes")
                or MAX_UPLOAD_BYTES
            ),
            "sources": ["upload", "path", "build_dir"],
            "source_hint": (
                "上传 .bin/.zip，或填本机路径；"
                "ESP-IDF build 目录会读取 flash_args。"
            ),
            "defaults": {
                "port": current_port,
                "baud": default_baud,
            },
            "suggestions": suggestions,
            "backend": backend,
            "options": {
                "verify": True,
                "verify_supported": bool(
                    not esptool or esptool.version[0] < 5
                ),
                "erase_all": True,
                "after": ["hard_reset", "soft_reset", "no_reset"],
                "before": ["default_reset", "usb_reset"],
                "reconnect": True,
            },
            "esptool": {
                "found": found,
                "label": esptool.label if esptool else "",
                "version": version,
                "major": esptool.version[0] if esptool else 0,
                "verify_supported": bool(
                    not esptool or esptool.version[0] < 5
                ),
            },
        }
        if esptool is None and not self.fake:
            payload["hint"] = (
                "esptool not found; run "
                "chip-adapt/esp32/host/scripts/bootstrap.ps1"
            )
        return payload

    # ----------------------------------------------------------------- upload

    def save_upload(self, name: str, data: bytes) -> dict[str, Any]:
        limit = int(
            self.config.get("flash_max_upload_bytes") or MAX_UPLOAD_BYTES
        )
        if len(data) > limit:
            raise FlashError(
                f"upload is larger than {limit} bytes",
                code="upload_too_large",
                status=413,
            )
        if not data:
            raise FlashError("uploaded file is empty", code="empty_upload")
        token = uuid.uuid4().hex[:12]
        directory = self.uploads_root / token
        directory.mkdir(parents=True)
        safe = _safe_name(name)
        path = directory / safe
        path.write_bytes(data)
        meta = {
            "name": safe,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "created": time.time(),
        }
        (directory / "upload.json").write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )
        self._prune_uploads()
        return {"token": token, **meta}

    def _upload(self, token: str) -> Path:
        if not _TOKEN_RE.match(str(token)):
            raise FlashError("unknown upload token", code="upload_not_found", status=404)
        directory = self.uploads_root / token
        meta_path = directory / "upload.json"
        if not meta_path.is_file():
            raise FlashError(
                "upload token expired; upload the file again",
                code="upload_not_found",
                status=404,
            )
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FlashError("upload metadata is unreadable", code="upload_not_found", status=404) from exc
        path = directory / str(meta.get("name") or "")
        if not path.is_file():
            raise FlashError(
                "uploaded file is missing; upload it again",
                code="upload_not_found",
                status=404,
            )
        return path

    def _prune_uploads(self) -> None:
        directories = sorted(
            (path for path in self.uploads_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in directories[KEEP_UPLOADS:]:
            shutil.rmtree(old, ignore_errors=True)

    def _prune_workdirs(self) -> None:
        directories = sorted(
            (path for path in self.work_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in directories[KEEP_WORKDIRS:]:
            shutil.rmtree(old, ignore_errors=True)

    # ------------------------------------------------------------------- plan

    def plan(self, source: dict[str, Any]) -> dict[str, Any]:
        address = source.get("address")
        if source.get("token"):
            path = self._upload(str(source["token"]))
            resolved = self._plan_path(path, address)
        elif source.get("files"):
            resolved = _files_plan(list(source["files"]), address)
        elif source.get("path"):
            resolved = plan_from_path(
                Path(str(source["path"])),
                address=address,
                work_root=self.work_root,
            )
        elif source.get("build_dir"):
            resolved = _directory_plan(
                Path(str(source["build_dir"])),
                address,
            )
        else:
            raise FlashError(
                "token, path, build_dir or files is required",
                code="source_required",
            )
        self._prune_workdirs()
        plan_id = uuid.uuid4().hex[:12]
        resolved["plan_id"] = plan_id
        resolved["created"] = time.time()
        with self._lock:
            self._plans[plan_id] = resolved
            self._prune_plans()
        return {
            "plan_id": plan_id,
            "source": resolved.get("source", ""),
            "notes": resolved.get("notes", ""),
            "entries": [
                {
                    "name": entry["name"],
                    "address": entry["address"],
                    "size": entry["size"],
                }
                for entry in resolved["entries"]
            ],
        }

    def _plan_path(self, path: Path, address: Any) -> dict[str, Any]:
        if path.suffix.lower() == ".zip":
            return _zip_plan(
                path,
                address=address,
                work_root=self.work_root,
            )
        if path.suffix.lower() == ".bin":
            return _single_bin_plan(
                path,
                address=0 if address is None else address,
                source="bin",
            )
        raise FlashError(
            f"unsupported firmware file: {path.name}",
            code="unsupported_source",
        )

    def _prune_plans(self) -> None:
        now = time.time()
        expired = [
            plan_id
            for plan_id, plan in self._plans.items()
            if now - float(plan.get("created", 0)) > PLAN_TTL_S
        ]
        for plan_id in expired:
            self._plans.pop(plan_id, None)
        while len(self._plans) > MAX_PLANS:
            oldest = min(
                self._plans,
                key=lambda key: float(self._plans[key].get("created", 0)),
            )
            self._plans.pop(oldest, None)

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self._lock:
            plan = self._plans.get(str(plan_id))
        if plan is None:
            raise FlashError(
                "firmware plan expired; resolve the firmware again",
                code="plan_not_found",
                status=404,
            )
        if time.time() - float(plan.get("created", 0)) > PLAN_TTL_S:
            with self._lock:
                self._plans.pop(str(plan_id), None)
            raise FlashError(
                "firmware plan expired; resolve the firmware again",
                code="plan_not_found",
                status=404,
            )
        return plan

    # ------------------------------------------------------------------ start

    def busy(self) -> bool:
        return self._flash_lock.locked()

    def start(
        self,
        job: Any,
        plan: dict[str, Any],
        options: dict[str, Any],
    ) -> None:
        if not self._flash_lock.acquire(blocking=False):
            raise FlashError(
                "another flash job is already running",
                code="flash_busy",
                status=409,
            )
        try:
            job.start()
        except Exception:
            self._flash_lock.release()
            raise
        thread = threading.Thread(
            target=self._execute,
            args=(job, plan, dict(options)),
            name=f"flash-{job.id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            self._flash_lock.release()
            raise

    def _execute(
        self,
        job: Any,
        plan: dict[str, Any],
        options: dict[str, Any],
    ) -> None:
        try:
            if self.fake:
                result = self._fake_flash(job, plan, options)
            else:
                result = self._real_flash(job, plan, options)
            job.finish(ok=True, result=result)
        except FlashError as exc:
            if exc.code in ("cancelled", "timeout"):
                job.append(
                    "status",
                    "flash interrupted; the board may stay in the "
                    "bootloader until it is reset",
                )
            job.finish(
                ok=False,
                error=str(exc),
                cancelled=exc.code == "cancelled",
            )
        except Exception as exc:  # noqa: BLE001 - job boundary
            job.append("stderr", traceback.format_exc())
            job.finish(ok=False, error=str(exc))
        finally:
            self._flash_lock.release()

    def _fake_flash(
        self,
        job: Any,
        plan: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        job.append("status", "fake backend: no serial or esptool is used")
        started = time.monotonic()
        delay = float(self.config.get("flash_fake_delay", 0.12))
        for step in range(0, 101, 5):
            if job.cancel_event.is_set():
                raise FlashError("cancelled", code="cancelled")
            job.append(
                "stdout",
                f"Writing at 0x00000000... ({step} %)",
                percent=step,
            )
            time.sleep(delay)
        return {
            "ok": True,
            "fake": True,
            "port": options.get("port") or "",
            "baud": int(options.get("baud") or DEFAULT_FLASH_BAUD),
            "entries": [
                {
                    "name": entry["name"],
                    "address": entry["address"],
                    "size": entry["size"],
                }
                for entry in plan["entries"]
            ],
            "duration_s": round(time.monotonic() - started, 3),
        }

    def _real_flash(
        self,
        job: Any,
        plan: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        esptool = find_esptool(self.config)
        if esptool is None:
            raise FlashError(
                "esptool not found; run the host bootstrap",
                code="esptool_missing",
                status=409,
            )
        saved = self.broker.detach_for_flash()
        if saved.get("was_open"):
            job.append(
                "status",
                "serial released "
                f"({saved.get('serial_port') or saved.get('port')} "
                f"@ {saved.get('baud')})",
            )
            time.sleep(0.25)
        try:
            candidate = str(
                options.get("port")
                or saved.get("serial_port")
                or saved.get("port")
                or ""
            )
            if candidate in ("dual", "ble"):
                candidate = ""
            port = candidate or preferred_flash_port()
            if not port:
                raise FlashError(
                    "choose a serial port before flashing",
                    code="port_required",
                )
            baud = int(
                options.get("baud")
                or self.config.get("flash_baud")
                or DEFAULT_FLASH_BAUD
            )
            command = build_flash_command(esptool, port, baud, plan, options)
            job.append("status", "$ " + " ".join(command))
            progress = _Progress(len(plan["entries"]))
            started = time.monotonic()
            code, stdout, stderr = _run_streaming(
                job,
                command,
                cwd=Path(plan["work_dir"]),
                timeout_s=float(
                    self.config.get("flash_timeout_s") or 300
                ),
                progress=progress,
            )
            if code != 0:
                raise FlashError(
                    "flash failed: " + (_tail(stderr) or _tail(stdout)),
                    code="flash_failed",
                )
            return {
                "ok": True,
                "port": port,
                "baud": baud,
                "chip": CHIP,
                "entries": [
                    {
                        "name": entry["name"],
                        "address": entry["address"],
                        "size": entry["size"],
                    }
                    for entry in plan["entries"]
                ],
                "command": command,
                "esptool": {
                    "label": esptool.label,
                    "version": version_text(esptool.version),
                },
                "duration_s": round(time.monotonic() - started, 3),
            }
        finally:
            after = str(options.get("after") or "hard_reset")
            can_reconnect = after not in ("no_reset", "no_reset_stub")
            if (
                options.get("reconnect", True)
                and saved.get("was_open")
                and can_reconnect
            ):
                self._reconnect(job)

    def _reconnect(self, job: Any) -> None:
        for attempt in range(8):
            try:
                self.broker.reattach()
                job.append("status", "serial reconnected")
                return
            except Exception as exc:  # noqa: BLE001 - best effort
                if attempt == 7:
                    job.append(
                        "stderr",
                        f"serial reconnect failed: {exc}",
                    )
                else:
                    time.sleep(0.5)
