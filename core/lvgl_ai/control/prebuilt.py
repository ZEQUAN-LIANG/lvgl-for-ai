"""Host SDK loading and the gcc compile/link plan used by prebuilt builds.

A prebuilt build compiles ``user/app/**/*.c`` and the engine's ``main.c``
against the host SDK exported by ``core/tools/export_sdk.py``.  It never needs
LVGL source, third-party source, CMake or Ninja.

Everything here is data plus command construction: :class:`BuildPlan` runs the
commands through its scripted-runner seam, so unit tests can pin the selection,
flags and error mapping without a compiler.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import paths
from ..digest import sha256_bytes, sha256_file
from .errors import BuildError

SDK_SCHEMA = "lvgl-ai-host-sdk-v1"
REQUIRED_LIBS = (
    "libengine.a",
    "libadapter.a",
    "liblvgl.a",
    "liblvgl_ai_libpng.a",
    "liblvgl_ai_zlib.a",
    "libfreetype.dll.a",
)

PREBUILT_MARKER = "prebuilt.json"
OBJECT_DIR_NAME = ".prebuilt"
OBJECTS_DIR_NAME = "objects"


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise BuildError(f"host SDK manifest field {field!r} must be a string list")
    return list(value)


def _relative_entry(value: str, field: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise BuildError(f"host SDK {field} must be relative: {value!r}")
    return candidate


def _basename(value: str, field: str) -> str:
    candidate = Path(value)
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 1
        or value in ("", ".", "..")
    ):
        raise BuildError(f"host SDK {field} must be a file name: {value!r}")
    return value


def _validate_sdk_lib(
    lib_dir: Path, name: str, hashes: dict[str, Any]
) -> None:
    _basename(name, "libs")
    path = lib_dir / name
    if not path.is_file():
        raise BuildError(f"host SDK library not found: {path}")
    expected = hashes.get(name)
    if not isinstance(expected, str):
        raise BuildError(f"host SDK manifest has no sha256 for {name}")
    actual = sha256_file(path)
    if actual != expected:
        raise BuildError(
            f"host SDK hash mismatch for {name}: expected {expected}, "
            f"found {actual}"
        )


def _validate_runtime_dll(lib_dir: Path, name: str) -> None:
    _basename(name, "runtime_dlls")
    if not (lib_dir / name).is_file():
        raise BuildError(f"host SDK runtime DLL not found: {lib_dir / name}")


def _version_tuple(text: str) -> tuple[int, ...]:
    numbers = tuple(int(part) for part in re.findall(r"\d+", text)[:3])
    return numbers + (0,) * (3 - len(numbers))


def versions_match(left: str, right: str) -> bool:
    """Compare compiler versions, padding ``15.2`` to ``15.2.0``.

    An unreadable version on either side is a mismatch: the SDK ABI guard
    must not pass just because a manifest or compiler probe is incomplete.
    """
    if not left or not right or left == "unknown" or right == "unknown":
        return False
    return _version_tuple(left) == _version_tuple(right)


class HostSdk:
    """One exported host SDK directory and its validated manifest."""

    def __init__(
        self,
        root: Path,
        manifest: dict[str, Any],
        manifest_sha256: str,
        runtime_dlls: list[str] | None = None,
        *,
        shared_root: Path | None = None,
        shared_libs: list[str] | None = None,
        shared_include_dirs: list[str] | None = None,
        shared_runtime_dlls: list[str] | None = None,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.manifest_sha256 = manifest_sha256
        self.runtime_dlls = list(runtime_dlls or [])
        self.shared_root = shared_root
        self.shared_libs = list(shared_libs or [])
        self.shared_include_dirs = list(shared_include_dirs or [])
        self.shared_runtime_dlls = list(shared_runtime_dlls or [])

    @classmethod
    def load(
        cls, root: str | Path, *, expected_version: str | None = None
    ) -> "HostSdk":
        root = Path(root).expanduser().resolve()
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise BuildError(
                f"host SDK not found: {manifest_path}. "
                "Export one with: python -I core/tools/export_sdk.py "
                f"--version {expected_version or '<version>'} "
                "or use --source."
            )
        data = manifest_path.read_bytes()
        try:
            manifest = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BuildError(f"cannot read host SDK manifest {manifest_path}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise BuildError(f"host SDK manifest must be an object: {manifest_path}")
        if manifest.get("schema") != SDK_SCHEMA:
            raise BuildError(
                f"unsupported host SDK schema in {manifest_path}: "
                f"{manifest.get('schema')!r} (expected {SDK_SCHEMA!r})"
            )
        version = manifest.get("lvgl_version")
        if not isinstance(version, str):
            raise BuildError(f"host SDK manifest is missing lvgl_version: {manifest_path}")
        if expected_version is not None and version != expected_version:
            raise BuildError(
                f"host SDK version mismatch: {manifest_path} is {version}, "
                f"requested {expected_version}"
            )
        compiler = manifest.get("compiler")
        if not isinstance(compiler, dict) or not isinstance(
            compiler.get("version"), str
        ):
            raise BuildError(f"host SDK manifest is missing compiler.version: {manifest_path}")
        _string_list(manifest.get("defines"), "defines")
        _string_list(manifest.get("cflags"), "cflags")
        _string_list(manifest.get("link_flags"), "link_flags")
        include_dirs = _string_list(manifest.get("include_dirs"), "include_dirs")
        libs = _string_list(manifest.get("libs"), "libs")
        runtime_dlls = (
            _string_list(manifest.get("runtime_dlls"), "runtime_dlls")
            if "runtime_dlls" in manifest
            else []
        )
        shared_root_name = manifest.get("shared_root")
        shared_root: Path | None = None
        if shared_root_name is not None:
            if not isinstance(shared_root_name, str):
                raise BuildError(
                    f"host SDK shared_root must be a string: {manifest_path}"
                )
            shared_root = (root.parent / _basename(
                shared_root_name, "shared_root"
            )).resolve()
            if not shared_root.is_dir():
                raise BuildError(
                    f"host SDK shared root not found: {shared_root}"
                )
        shared_include_dirs = _string_list(
            manifest.get("shared_include_dirs", []), "shared_include_dirs"
        )
        shared_libs = _string_list(
            manifest.get("shared_libs", []), "shared_libs"
        )
        shared_runtime_dlls = _string_list(
            manifest.get("shared_runtime_dlls", []), "shared_runtime_dlls"
        )
        if (
            shared_include_dirs or shared_libs or shared_runtime_dlls
        ) and shared_root is None:
            raise BuildError(
                "host SDK manifest uses shared_* fields without shared_root: "
                f"{manifest_path}"
            )
        hashes = manifest.get("sha256")
        if not isinstance(hashes, dict):
            raise BuildError(f"host SDK manifest is missing sha256: {manifest_path}")

        all_libs = [*libs, *shared_libs]
        for name in REQUIRED_LIBS:
            if name not in all_libs:
                raise BuildError(
                    f"host SDK manifest is missing required library {name}: "
                    f"{manifest_path}"
                )
        if len(all_libs) != len(set(all_libs)):
            raise BuildError(f"host SDK manifest lists a library twice: {manifest_path}")
        for rel in include_dirs:
            candidate = _relative_entry(rel, "include_dirs")
            if not (root / candidate).is_dir():
                raise BuildError(f"host SDK include directory not found: {root / candidate}")
        if shared_root is not None:
            for rel in shared_include_dirs:
                candidate = _relative_entry(rel, "shared_include_dirs")
                if not (shared_root / candidate).is_dir():
                    raise BuildError(
                        "host SDK shared include directory not found: "
                        f"{shared_root / candidate}"
                    )
        for name in libs:
            _validate_sdk_lib(root / "lib", name, hashes)
        if shared_root is not None:
            for name in shared_libs:
                _validate_sdk_lib(shared_root / "lib", name, hashes)
        for rel in runtime_dlls:
            _validate_runtime_dll(root / "lib", rel)
        if shared_root is not None:
            for rel in shared_runtime_dlls:
                _validate_runtime_dll(shared_root / "lib", rel)
        lv_conf_hash = manifest.get("lv_conf_sha256")
        if isinstance(lv_conf_hash, str):
            lv_conf = root / "lv_conf.h"
            if not lv_conf.is_file():
                raise BuildError(f"host SDK lv_conf.h not found: {lv_conf}")
            if sha256_file(lv_conf) != lv_conf_hash:
                raise BuildError(
                    f"host SDK lv_conf.h hash mismatch: {lv_conf}"
                )
        return cls(
            root,
            manifest,
            sha256_bytes(data),
            runtime_dlls,
            shared_root=shared_root,
            shared_libs=shared_libs,
            shared_include_dirs=shared_include_dirs,
            shared_runtime_dlls=shared_runtime_dlls,
        )

    @property
    def lvgl_version(self) -> str:
        return str(self.manifest["lvgl_version"])

    @property
    def compiler_version(self) -> str:
        return str(self.manifest["compiler"]["version"])

    @property
    def defines(self) -> list[str]:
        return list(self.manifest["defines"])

    @property
    def cflags(self) -> list[str]:
        return list(self.manifest["cflags"])

    @property
    def include_dirs(self) -> list[str]:
        return list(self.manifest["include_dirs"])

    @property
    def link_flags(self) -> list[str]:
        return list(self.manifest["link_flags"])

    @property
    def lib_names(self) -> list[str]:
        return list(self.manifest["libs"])

    @property
    def lib_paths(self) -> list[Path]:
        paths = [self.root / "lib" / name for name in self.lib_names]
        if self.shared_root is not None:
            paths.extend(
                self.shared_root / "lib" / name for name in self.shared_libs
            )
        return paths

    @property
    def runtime_dll_paths(self) -> list[Path]:
        paths = [self.root / "lib" / name for name in self.runtime_dlls]
        if self.shared_root is not None:
            paths.extend(
                self.shared_root / "lib" / name
                for name in self.shared_runtime_dlls
            )
        return paths

    @property
    def include_paths(self) -> list[Path]:
        paths = [self.root / rel for rel in self.include_dirs]
        if self.shared_root is not None:
            paths.extend(
                self.shared_root / rel for rel in self.shared_include_dirs
            )
        return paths


def resolve_compiler(
    *,
    override: str | Path | None = None,
    version: str | None = None,
) -> tuple[str, str]:
    """Return ``(compiler_path, version)`` in the documented order.

    ``LVGL_AI_GCC`` -> ``PATH``.  ``version`` is a test seam that skips running
    ``--version``.
    """
    if override is not None:
        compiler = str(override)
    else:
        compiler = os.environ.get("LVGL_AI_GCC") or (shutil.which("gcc") or "")
    if not compiler:
        raise BuildError(
            "C compiler not found: set LVGL_AI_GCC or put gcc on PATH "
            "(MinGW-w64 64-bit, version 15.2.0)"
        )
    if version is not None:
        return compiler, version
    try:
        result = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt"
            else 0,
        )
    except OSError as exc:
        raise BuildError(f"cannot run C compiler {compiler}: {exc}") from exc
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", text)
    if result.returncode != 0 or match is None:
        raise BuildError(
            f"cannot read the C compiler version from {compiler}: "
            f"{text.strip()[:200]}"
        )
    return compiler, match.group(1)


@dataclass(frozen=True)
class CompileStep:
    source: Path
    object_path: Path
    command: list[str]


class PrebuiltBuild:
    """Compile/link commands for one SDK, user app directory and build dir."""

    def __init__(
        self,
        sdk: HostSdk,
        *,
        compiler: str,
        compiler_version: str,
        user_app_dir: str | Path,
        engine_dir: str | Path,
        build_dir: str | Path,
        engine_path: str | Path,
    ) -> None:
        self.sdk = sdk
        self.compiler = compiler
        self.compiler_version = compiler_version
        self.user_app_dir = Path(user_app_dir).expanduser().resolve()
        self.engine_dir = Path(engine_dir).expanduser().resolve()
        self.build_dir = Path(build_dir).expanduser().resolve()
        self.engine_path = Path(engine_path).expanduser().resolve()
        self.object_dir = self.build_dir / OBJECT_DIR_NAME / OBJECTS_DIR_NAME
        self._headers_digest = self._compute_headers_digest()
        self._steps: list[CompileStep] | None = None
        self._link_command: list[str] | None = None

    # ---- validation ---------------------------------------------------

    def preflight(self) -> None:
        if not self.user_app_dir.is_dir():
            raise BuildError(f"user app directory not found: {self.user_app_dir}")
        if not (self.engine_dir / "main.c").is_file():
            raise BuildError(f"engine main.c not found: {self.engine_dir / 'main.c'}")
        if not self.user_sources:
            raise BuildError(f"no C sources found in {self.user_app_dir}")

    @property
    def user_sources(self) -> list[Path]:
        return sorted(
            path for path in self.user_app_dir.rglob("*.c") if path.is_file()
        )

    # ---- commands -----------------------------------------------------

    @property
    def steps(self) -> list[CompileStep]:
        if self._steps is None:
            self.preflight()
            self._steps = []
            main_source = self.engine_dir / "main.c"
            self._steps.append(self._step(main_source, role="engine"))
            for source in self.user_sources:
                self._steps.append(self._step(source, role="user"))
        return self._steps

    @property
    def link_command(self) -> list[str]:
        if self._link_command is None:
            objects = [str(step.object_path) for step in self.steps]
            command = [
                self.compiler,
                "-o", str(self.engine_path),
                *objects,
                "-Wl,--start-group",
                *[str(path) for path in self.sdk.lib_paths],
                "-Wl,--end-group",
                *self.sdk.link_flags,
            ]
            self._link_command = command
        return self._link_command

    def _prefix_map_flags(self) -> list[str]:
        roots = {
            str(paths.REPO_ROOT),
            str(self.sdk.root),
            str(self.user_app_dir),
            str(self.engine_dir),
        }
        if self.sdk.shared_root is not None:
            roots.add(str(self.sdk.shared_root))
        return [f"-ffile-prefix-map={root}=." for root in sorted(roots)]

    def _step(self, source: Path, *, role: str) -> CompileStep:
        key = self._object_key(source, role)
        object_path = self.object_dir / f"{key}.o"
        flags = [*self.sdk.cflags, *self._prefix_map_flags()]
        defines = [f"-D{value}" for value in self.sdk.defines]
        includes = [f"-I{path}" for path in self.sdk.include_paths]
        if role == "engine":
            includes.append(f"-I{self.engine_dir}")
        else:
            includes.extend(
                [
                    f"-I{self.user_app_dir.parent}",
                    f"-I{self.user_app_dir}",
                ]
            )
        includes = list(dict.fromkeys(includes))
        command = [
            self.compiler,
            "-c", str(source),
            "-o", str(object_path),
            *flags,
            *defines,
            *includes,
        ]
        return CompileStep(source=source, object_path=object_path, command=command)

    def _object_key(self, source: Path, role: str) -> str:
        try:
            relative = source.relative_to(
                self.user_app_dir if role == "user" else self.engine_dir
            ).as_posix()
        except ValueError:
            relative = source.name
        digest = hashlib.sha256()
        digest.update(self.sdk.manifest_sha256.encode("utf-8"))
        digest.update(self.compiler_version.encode("utf-8"))
        digest.update(self._headers_digest.encode("utf-8"))
        digest.update(role.encode("utf-8"))
        digest.update(relative.encode("utf-8"))
        digest.update(source.read_bytes())
        digest.update("\0".join(self.sdk.cflags).encode("utf-8"))
        digest.update("\0".join(self.sdk.defines).encode("utf-8"))
        digest.update("\0".join(self._prefix_map_flags()).encode("utf-8"))
        return digest.hexdigest()

    def _compute_headers_digest(self) -> str:
        roots = [self.user_app_dir, self.engine_dir, *self.sdk.include_paths]
        seen: set[Path] = set()
        digest = hashlib.sha256()
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.h")):
                resolved = path.resolve()
                if resolved in seen or not resolved.is_file():
                    continue
                seen.add(resolved)
                digest.update(path.as_posix().encode("utf-8"))
                digest.update(b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
        return digest.hexdigest()

    # ---- cache and marker ---------------------------------------------

    def prune_objects(self) -> None:
        keep = {step.object_path.name for step in self.steps}
        if not self.object_dir.is_dir():
            return
        for path in self.object_dir.iterdir():
            if path.is_file() and path.name not in keep:
                try:
                    path.unlink()
                except OSError:
                    pass

    def install_runtime_dlls(self) -> None:
        """Copy SDK runtime DLLs next to the linked engine."""
        if not self.sdk.runtime_dll_paths:
            return
        self.engine_path.parent.mkdir(parents=True, exist_ok=True)
        for source in self.sdk.runtime_dll_paths:
            shutil.copy2(source, self.engine_path.parent / source.name)

    def write_marker(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": "prebuilt",
            "manifest_sha256": self.sdk.manifest_sha256,
            "compiler": self.compiler_version,
            "lvgl_version": self.sdk.lvgl_version,
        }
        (self.build_dir / PREBUILT_MARKER).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # ---- evidence -----------------------------------------------------

    def log_header(self) -> str:
        return "\n".join(
            [
                "# build mode: prebuilt",
                f"# sdk: {self.sdk.root}",
                f"# manifest: {self.sdk.root / 'manifest.json'}",
                f"# manifest_sha256: {self.sdk.manifest_sha256}",
                f"# compiler: {self.compiler} ({self.compiler_version})",
            ]
        )


def compiler_mismatch_message(
    *, expected: str, found: str, compiler: str
) -> str:
    return (
        f"host SDK compiler mismatch: manifest expects {expected}, "
        f"found {found} at {compiler}. Set LVGL_AI_GCC or rebuild the SDK "
        "with core/tools/export_sdk.py."
    )
