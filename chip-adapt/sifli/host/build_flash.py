"""Build and flash orchestration.

The flashing engine is the official ``sftool.exe``.  The host does not
reimplement the SiFli UART protocol, and it does not drive ``sftool-gui``:
that program is a Tauri app, not a CLI shell.  Human one-click flashing uses
the official Web Flasher page; CLI/AI flashing uses ``sftool`` directly.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

from jobs import Job
from serial_backend import SerialError, normalize_port, pick_port

_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
)


class BuildFlashError(RuntimeError):
    def __init__(self, message: str, *, code: str = "build_flash_error") -> None:
        super().__init__(message)
        self.code = code


class BuildCommand(NamedTuple):
    argv: list[str]
    uses_export_shell: bool


def _tail(lines: list[str], count: int = 20) -> str:
    return "\n".join(lines[-count:]) if lines else ""


# -- discovery ---------------------------------------------------------


def _versioned_tool_files(root: Path, name: str, filename: str) -> list[Path]:
    base = root / "tools" / name
    if not base.is_dir():
        return []
    return sorted(
        (path / filename for path in base.iterdir() if path.is_dir()),
        reverse=True,
    )


def find_sftool(config: dict[str, Any]) -> Path:
    toolchain_root = Path(config.get("toolchain_root", ""))
    candidates = [
        Path(os.environ.get("SFTOOL_BIN", "")),
        Path(config.get("sftool", "")),
        toolchain_root / "sftool" / "sftool.exe",
        *(_versioned_tool_files(toolchain_root, "sftool", "sftool.exe")),
        *(
            _versioned_tool_files(Path.home() / ".sifli", "sftool", "sftool.exe")
            if toolchain_root != Path.home() / ".sifli"
            else []
        ),
        Path(config.get("sdk_root", "")) / "tools" / "sftool" / "sftool.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    found = shutil.which("sftool")
    if found:
        return Path(found)
    raise BuildFlashError(
        "sftool.exe not found. Expected "
        f"{config.get('sftool')} or the official SDK tools under "
        f"{toolchain_root / 'tools' / 'sftool'}.",
        code="sftool_missing",
    )


def resolve_project_dir(
    project_dir: str | Path | None,
    config: dict[str, Any],
) -> Path | None:
    raw = project_dir or config.get("project_dir")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(config["repo_root"]) / path
    path = path.resolve()
    if (path / "SConstruct").is_file():
        return path
    if (path / "project" / "SConstruct").is_file():
        return path / "project"
    if (path / "sftool_param.json").is_file():
        return path.parent
    return path


def find_build_dir(project_dir: str | Path, board: str) -> Path:
    project = Path(project_dir)
    if (project / "sftool_param.json").is_file():
        return project

    candidates = [
        project / f"build_{board}_hcpu",
        project / f"build_{board}",
        project / f"build_{board}_lcpu",
    ]
    for candidate in candidates:
        if (candidate / "sftool_param.json").is_file():
            return candidate

    found = [path.parent for path in project.glob("build_*/sftool_param.json")]
    if not found:
        found = [
            path.parent
            for path in project.glob("**/sftool_param.json")
            if ".git" not in path.parts
        ]
    if not found:
        raise BuildFlashError(
            f"no sftool_param.json found under {project}; build first",
            code="build_dir_missing",
        )
    if len(found) > 1:
        preferred = [
            path for path in found if board in path.parent.name
        ]
        if len(preferred) == 1:
            return preferred[0]
        found.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return found[0]


def read_sftool_param(build_dir: str | Path) -> dict[str, Any]:
    build = Path(build_dir)
    path = build / "sftool_param.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise BuildFlashError(
            f"sftool_param.json not found in {build}",
            code="flash_config_missing",
        ) from exc
    except (OSError, ValueError) as exc:
        raise BuildFlashError(
            f"cannot read {path}: {exc}",
            code="flash_config_invalid",
        ) from exc

    if not isinstance(raw, dict):
        raise BuildFlashError(
            "sftool_param.json root must be an object",
            code="flash_config_invalid",
        )
    write = raw.get("write_flash")
    if not isinstance(write, dict):
        raise BuildFlashError(
            "sftool_param.json is missing write_flash",
            code="flash_config_invalid",
        )
    files = write.get("files")
    if not isinstance(files, list) or not files:
        raise BuildFlashError(
            "sftool_param.json is missing write_flash.files",
            code="flash_config_invalid",
        )

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise BuildFlashError(
                f"write_flash.files[{index}] must be an object",
                code="flash_config_invalid",
            )
        relative = item.get("path") or item.get("name")
        if not relative:
            raise BuildFlashError(
                f"write_flash.files[{index}] has no path",
                code="flash_config_invalid",
            )
        relative_text = str(relative).replace("\\", "/")
        file_path = Path(relative_text)
        if not file_path.is_absolute():
            file_path = build / file_path
        if not file_path.is_file():
            missing.append(str(file_path))
            continue
        entries.append(
            {
                "path": file_path.resolve(),
                "relative": relative_text,
                "address": item.get("address") or item.get("addr"),
            }
        )
    if missing:
        raise BuildFlashError(
            "flash image files are missing: " + ", ".join(missing),
            code="flash_image_missing",
        )

    chip = str(raw.get("chip") or "SF32LB52")
    memory = str(raw.get("memory") or "nor").lower()
    return {
        "path": path,
        "chip": chip,
        "memory": memory,
        "entries": entries,
        "verify": bool(write.get("verify", True)),
        "raw": raw,
    }


def build_sftool_command(
    sftool: Path,
    *,
    port: str,
    baud: int,
    chip: str,
    memory: str,
    entries: list[dict[str, Any]],
    verify: bool,
    erase_all: bool,
    after: str,
) -> list[str]:
    command = [
        str(sftool),
        "-p",
        normalize_port(port),
        "-b",
        str(int(baud)),
        "-c",
        chip,
        "-m",
        memory,
        "--after",
        after,
        "write_flash",
    ]
    if verify:
        command.append("--verify")
    if erase_all:
        command.append("-e")
    for entry in entries:
        target = str(entry["path"])
        address = entry.get("address")
        command.append(f"{target}@{address}" if address else target)
    return command


# -- build environment -------------------------------------------------


def _toolchain_bin_dirs(root: Path | None) -> list[Path]:
    if root is None:
        return []
    relatives = (
        Path("arm-none-eabi") / "bin",
        Path("cmake-3.30.2-windows-x86_64") / "bin",
        Path("ninja"),
        Path("sftool"),
        Path("sdk-py"),
    )
    dirs = [root / relative for relative in relatives if (root / relative).is_dir()]
    tools_root = root / "tools"
    for name, relative in (
        ("arm-none-eabi-gcc", "bin"),
        ("cmake", "bin"),
        ("ninja", ""),
        ("sftool", ""),
        ("sdk-py", ""),
    ):
        base = tools_root / name
        if not base.is_dir():
            continue
        for version_dir in sorted(base.iterdir()):
            candidate = version_dir / relative if relative else version_dir
            if candidate.is_dir():
                dirs.append(candidate)
    return dirs


def _apply_sdk_env(env: dict[str, str], sdk: Path | None) -> None:
    if sdk is None or not sdk.is_dir():
        return
    env["SIFLI_SDK"] = str(sdk)
    env["SIFLI_SDK_PATH"] = str(sdk)
    build_tools = sdk / "tools" / "build"
    if build_tools.is_dir():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(build_tools) + (
            os.pathsep + existing if existing else ""
        )


def _apply_host_caches(env: dict[str, str], host: Path | None) -> None:
    if host is None or not host.is_dir():
        return
    for key, name in (
        ("CONAN_HOME", "conan"),
        ("PKGS_ROOT", "pkgs"),
        ("PKGS_DIR", "pkgs"),
    ):
        target = host / ".cache" / name
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        env[key] = str(target)


def toolchain_env(config: dict[str, Any]) -> dict[str, str]:
    root_value = config.get("toolchain_root")
    sdk_value = config.get("sdk_root")
    host_value = config.get("host_dir")
    root = Path(root_value) if root_value else None
    sdk = Path(sdk_value) if sdk_value else None
    host = Path(host_value) if host_value else None
    lock_dir = sdk / "tools" / "locks" / "default" if sdk else None
    venv = lock_dir / ".venv" if lock_dir else None

    env = os.environ.copy()
    path_parts: list[str] = []
    if venv is not None:
        venv_scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        if venv_scripts.is_dir():
            path_parts.append(str(venv_scripts))
    path_parts.extend(str(path) for path in _toolchain_bin_dirs(root))
    if path_parts:
        env["PATH"] = os.pathsep.join(path_parts + [env.get("PATH", "")])

    _apply_sdk_env(env, sdk)
    for bin_dir in _toolchain_bin_dirs(root):
        text = str(bin_dir).replace("\\", "/").lower()
        if bin_dir.name == "bin" and "arm-none-eabi" in text:
            env["RTT_EXEC_PATH"] = str(bin_dir)
            break
    # GetLinkScript only searches for gcc/keil linker scripts when RTT_CC is
    # set; without it the SDK silently returns no linker script.
    env["RTT_CC"] = "gcc"
    if venv is not None and venv.is_dir():
        env["ENV_ROOT"] = str(venv)
        env["SIFLI_SDK_PYTHON_ENV_PATH"] = str(venv)
    _apply_host_caches(env, host)
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


# -- build command selection -------------------------------------------


def _configured_build_command(
    config: dict[str, Any],
    board: str,
) -> list[str] | None:
    configured = config.get("build_command") or []
    if not configured:
        return None
    if isinstance(configured, str):
        configured = shlex.split(configured)
    return [str(part).format(board=board) for part in configured]


def _path_scons_command(
    config: dict[str, Any],
    board: str,
) -> list[str] | None:
    scons = shutil.which("scons")
    if not scons:
        return None
    return [scons, f"--board={board}", "-j8"]


def _uv_lock_command(
    config: dict[str, Any],
    board: str,
) -> list[str] | None:
    # The SDK ships a uv lock with SCons and its build dependencies.  Using
    # `uv run --project` gives a self-contained build environment without
    # requiring the user to activate export.ps1 first.
    sdk = Path(config.get("sdk_root", ""))
    lock_dir = sdk / "tools" / "locks" / "default"
    uv = shutil.which("uv")
    if not uv or not (lock_dir / "uv.lock").is_file():
        return None
    return [
        uv,
        "run",
        "--project",
        str(lock_dir),
        "scons",
        f"--board={board}",
        "-j8",
    ]


def _export_shell_command(
    config: dict[str, Any],
    board: str,
) -> list[str] | None:
    if os.name != "nt":
        return None
    export_ps1 = Path(config.get("export_ps1", ""))
    if not export_ps1.is_file():
        return None
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None
    script = f". '{export_ps1}'; scons --board={board} -j8"
    return [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def resolve_build_command(
    config: dict[str, Any],
    board: str,
) -> BuildCommand:
    for factory in (
        _configured_build_command,
        _path_scons_command,
        _uv_lock_command,
    ):
        command = factory(config, board)
        if command is not None:
            return BuildCommand(command, False)
    command = _export_shell_command(config, board)
    if command is not None:
        return BuildCommand(command, True)
    raise BuildFlashError(
        "scons was not found. Run the SiFli-SDK export.ps1 in a shell first, "
        "or set build_command in host/config.json.",
        code="scons_missing",
    )


# -- process execution -------------------------------------------------


def _stop_process(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


def run_streaming(
    job: Job,
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    env: dict[str, str] | None = None,
) -> tuple[int, list[str], list[str]]:
    job.append("status", "$ " + " ".join(str(part) for part in command))
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
            env=env,
            creationflags=_CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise BuildFlashError(
            f"command not found: {command[0]}",
            code="command_not_found",
        ) from exc

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def pump(stream, name: str, sink: list[str]) -> None:
        try:
            for line in iter(stream.readline, ""):
                text = line.rstrip("\r\n")
                if text:
                    sink.append(text)
                    job.append(name, text)
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
            raise BuildFlashError("cancelled", code="cancelled")
        if time.monotonic() - started > max(1.0, float(timeout_s)):
            _stop_process(process)
            raise BuildFlashError(
                f"command timed out after {int(timeout_s)}s",
                code="timeout",
            )
        time.sleep(0.1)

    for thread in threads:
        thread.join(timeout=2)
    return int(process.returncode or 0), stdout_lines, stderr_lines


# -- export / build ----------------------------------------------------


def _find_json_payload(
    lines: list[str],
    key: str,
) -> dict[str, Any] | None:
    for line in reversed(lines):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get(key):
            return candidate
    return None


def run_export(
    config: dict[str, Any],
    job: Job,
    app: str,
) -> Path:
    export_script = Path(config.get("export_script", ""))
    if not export_script.is_file():
        raise BuildFlashError(
            f"export script not found: {export_script}",
            code="export_missing",
        )
    command = [
        sys.executable,
        "-I",
        str(export_script),
        app,
        "--force",
        "--json",
    ]
    code, stdout, stderr = run_streaming(
        job,
        command,
        cwd=Path(config["repo_root"]),
        timeout_s=float(config.get("build_timeout_sec", 1800)),
        env=toolchain_env(config),
    )
    if code != 0:
        raise BuildFlashError(
            "export failed: " + (_tail(stderr) or _tail(stdout)),
            code="export_failed",
        )
    payload = _find_json_payload(stdout, "output_dir")
    if payload is None:
        raise BuildFlashError(
            "export did not return an output_dir",
            code="export_invalid",
        )
    project_dir = Path(str(payload["output_dir"])) / "project"
    job.append("status", f"exported to {project_dir}")
    return project_dir


def _resolve_build_project(
    config: dict[str, Any],
    job: Job,
    *,
    app: str | None,
    project_dir: str | Path | None,
) -> Path:
    resolved = run_export(config, job, app) if app else resolve_project_dir(
        project_dir,
        config,
    )
    if resolved is None:
        raise BuildFlashError(
            "no app or project_dir was given",
            code="project_missing",
        )
    project = Path(resolved)
    if not (project / "SConstruct").is_file():
        raise BuildFlashError(
            f"{project} has no SConstruct; expected an exported project "
            "directory or an SDK example's project/ directory",
            code="project_invalid",
        )
    return project


def run_build(
    config: dict[str, Any],
    job: Job,
    *,
    app: str | None = None,
    project_dir: str | Path | None = None,
    board: str | None = None,
) -> dict[str, Any]:
    board = board or str(config.get("board") or "sf32lb52-lchspi-ulp")
    project = _resolve_build_project(
        config,
        job,
        app=app,
        project_dir=project_dir,
    )

    plan = resolve_build_command(config, board)
    env = None if plan.uses_export_shell else toolchain_env(config)
    started = time.monotonic()
    code, stdout, stderr = run_streaming(
        job,
        plan.argv,
        cwd=project,
        timeout_s=float(config.get("build_timeout_sec", 1800)),
        env=env,
    )
    if code != 0:
        raise BuildFlashError(
            "build failed: " + (_tail(stderr) or _tail(stdout)),
            code="build_failed",
        )
    build_dir = find_build_dir(project, board)
    return {
        "ok": True,
        "project_dir": str(project),
        "build_dir": str(build_dir),
        "command": plan.argv,
        "used_export_shell": plan.uses_export_shell,
        "duration_s": round(time.monotonic() - started, 3),
    }


# -- flash -------------------------------------------------------------


def _resolve_flash_build_dir(
    config: dict[str, Any],
    *,
    build_dir: str | Path | None,
    project_dir: str | Path | None,
    board: str,
) -> Path:
    if build_dir is None:
        project = resolve_project_dir(project_dir, config)
        if project is None:
            raise BuildFlashError(
                "no project_dir or build_dir was given",
                code="project_missing",
            )
        build_dir = find_build_dir(project, board)
    build = Path(build_dir)
    if not build.is_absolute():
        build = Path(config["repo_root"]) / build
    return build


def _flash_options(
    config: dict[str, Any],
    *,
    verify: bool | None,
    erase_all: bool | None,
    after: str | None,
) -> tuple[bool, bool, str]:
    return (
        bool(config.get("flash_verify", True)) if verify is None else bool(verify),
        (
            bool(config.get("flash_erase_all", False))
            if erase_all is None
            else bool(erase_all)
        ),
        after or str(config.get("flash_after", "soft_reset")),
    )


def run_flash(
    config: dict[str, Any],
    job: Job,
    *,
    port: str | None = None,
    baud: int | None = None,
    build_dir: str | Path | None = None,
    project_dir: str | Path | None = None,
    board: str | None = None,
    verify: bool | None = None,
    erase_all: bool | None = None,
    after: str | None = None,
) -> dict[str, Any]:
    board = board or str(config.get("board") or "sf32lb52-lchspi-ulp")
    build = _resolve_flash_build_dir(
        config,
        build_dir=build_dir,
        project_dir=project_dir,
        board=board,
    )
    parsed = read_sftool_param(build)
    sftool = find_sftool(config)
    try:
        selected_port = normalize_port(port) if port else pick_port()
    except SerialError as exc:
        raise BuildFlashError(str(exc), code=exc.code) from exc
    rate = int(baud or config.get("flash_baud", 1_000_000))
    verify_enabled, erase_enabled, after_action = _flash_options(
        config,
        verify=verify,
        erase_all=erase_all,
        after=after,
    )
    command = build_sftool_command(
        sftool,
        port=selected_port,
        baud=rate,
        chip=parsed["chip"],
        memory=parsed["memory"],
        entries=parsed["entries"],
        verify=verify_enabled,
        erase_all=erase_enabled,
        after=after_action,
    )
    started = time.monotonic()
    code, stdout, stderr = run_streaming(
        job,
        command,
        cwd=build,
        timeout_s=float(config.get("flash_timeout_sec", 300)),
        env=None,
    )
    if code != 0:
        raise BuildFlashError(
            "flash failed: " + (_tail(stderr) or _tail(stdout)),
            code="flash_failed",
        )
    return {
        "ok": True,
        "port": selected_port,
        "baud": rate,
        "chip": parsed["chip"],
        "memory": parsed["memory"],
        "build_dir": str(build),
        "files": [
            {
                "path": str(entry["path"]),
                "address": entry.get("address"),
            }
            for entry in parsed["entries"]
        ],
        "command": command,
        "duration_s": round(time.monotonic() - started, 3),
    }


# -- official Web Flasher package --------------------------------------


def _stage_images(
    entries: list[dict[str, Any]],
    staging: Path,
) -> list[dict[str, Any]]:
    new_files: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, entry in enumerate(entries):
        if not entry.get("address"):
            raise BuildFlashError(
                "the official Web Flasher requires an address for every "
                f"image; {entry['path']} has none. Use the sftool CLI "
                "path or add an address to sftool_param.json.",
                code="flash_address_missing",
            )
        name = Path(entry["path"]).name
        if name in used:
            name = f"{index}-{name}"
        used.add(name)
        shutil.copy2(entry["path"], staging / name)
        new_files.append({"path": name, "address": entry["address"]})
    return new_files


def _write_staged_param(
    parsed: dict[str, Any],
    files: list[dict[str, Any]],
    staging: Path,
) -> None:
    config = dict(parsed["raw"])
    write = dict(config.get("write_flash") or {})
    write["files"] = files
    write["verify"] = bool(write.get("verify", parsed["verify"]))
    config["write_flash"] = write
    (staging / "sftool_param.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _zip_staging(staging: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.iterdir()):
            archive.write(path, path.name)


def _prune_firmware_cache(cache: Path, keep: int = 20) -> None:
    # Old ZIPs are only used by an already-open flasher tab.
    stale = sorted(
        cache.glob("*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in stale[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def package_firmware(
    build_dir: str | Path,
    cache_dir: str | Path,
) -> dict[str, Any]:
    build = Path(build_dir)
    parsed = read_sftool_param(build)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    staging = cache / f".stage-{token}"
    staging.mkdir(parents=True)
    try:
        files = _stage_images(parsed["entries"], staging)
        _write_staged_param(parsed, files, staging)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_name = f"{build.name}-{stamp}-{token}.zip"
        zip_path = cache / zip_name
        _zip_staging(staging, zip_path)
        _prune_firmware_cache(cache)

        return {
            "ok": True,
            "zip_path": str(zip_path),
            "zip_name": zip_name,
            "size": zip_path.stat().st_size,
            "chip": parsed["chip"],
            "memory": parsed["memory"],
            "files": [item["path"] for item in files],
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def flasher_page_url(
    base_url: str,
    *,
    chip: str,
    memory: str,
    zip_name: str,
) -> str:
    base = base_url.rstrip("/")
    zip_url = f"{base}/firmware/{quote(zip_name)}"
    return (
        f"{base}/tools/sftool/?chip={quote(chip)}"
        f"&flash={quote(memory.lower())}"
        f"&zip={quote(zip_url, safe='')}"
    )


def environment(config: dict[str, Any]) -> dict[str, Any]:
    sftool_setting = config.get("sftool") or os.environ.get("SFTOOL_BIN", "")
    try:
        sftool_found = str(find_sftool(config))
    except BuildFlashError:
        sftool_found = ""
    lock_dir = Path(config.get("sdk_root", "")) / "tools" / "locks" / "default"
    return {
        "sftool": str(sftool_setting),
        "sftool_found": sftool_found,
        "sdk_root": str(config.get("sdk_root", "")),
        "toolchain_root": str(config.get("toolchain_root", "")),
        "scons": shutil.which("scons") or "",
        "uv": shutil.which("uv") or "",
        "uv_lock": str(lock_dir / "uv.lock"),
        "uv_lock_exists": (lock_dir / "uv.lock").is_file(),
        "uv_env": str(lock_dir / ".venv"),
        "export_ps1": str(config.get("export_ps1", "")),
        "export_ps1_exists": Path(config.get("export_ps1", "")).is_file(),
        "build_command": config.get("build_command") or [],
    }
