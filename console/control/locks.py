from __future__ import annotations

import os
import time
from pathlib import Path
from typing import IO

from .errors import BuildError

LOCK_FILE_NAME = ".build.lock"
ANNOTATIONS_LOCK_FILE_NAME = ".annotations.lock"
BUILD_LOCK_TIMEOUT_S = 660.0
ANNOTATIONS_LOCK_TIMEOUT_S = 30.0
RETRY_INTERVAL_S = 0.1

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class BuildLock:
    def __init__(
        self, build_dir: str | Path, *, timeout: float = BUILD_LOCK_TIMEOUT_S
    ) -> None:
        self.path = Path(build_dir) / LOCK_FILE_NAME
        self.timeout = float(timeout)
        self._handle: IO[bytes] | None = None

    def __enter__(self) -> "BuildLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                _try_lock(handle)
            except OSError as exc:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise BuildError(
                        f"build lock timeout: {self.path}",
                        command=["build-lock", str(self.path)],
                    ) from exc
                time.sleep(RETRY_INTERVAL_S)
                continue
            self._handle = handle
            return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        handle = self._handle
        self._handle = None
        if handle is None:
            return False
        try:
            _unlock(handle)
        finally:
            handle.close()
        return False


def build_lock(
    build_dir: str | Path, *, timeout: float = BUILD_LOCK_TIMEOUT_S
) -> BuildLock:
    return BuildLock(build_dir, timeout=timeout)


class FileLock:
    def __init__(self, path: str | Path, *, timeout: float) -> None:
        self.path = Path(path)
        self.timeout = float(timeout)
        self._handle: IO[bytes] | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                _try_lock(handle)
            except OSError as exc:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError(
                        f"file lock timeout: {self.path}"
                    ) from exc
                time.sleep(RETRY_INTERVAL_S)
                continue
            self._handle = handle
            return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        handle = self._handle
        self._handle = None
        if handle is None:
            return False
        try:
            _unlock(handle)
        finally:
            handle.close()
        return False


def _try_lock(handle: IO[bytes]) -> None:
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: IO[bytes]) -> None:
    if os.name == "nt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
