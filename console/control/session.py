from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

import paths
from .errors import (
    SESSION_STATUSES,
    RuntimeCrash,
    dump_error,
    status_for_error,
)
from .retention import DEFAULT_SESSION_LIMIT, prune_sessions
from . import session_schema
from .session_schema import build_manifest, display_problem, list_pngs

DEFAULT_MAX_LOG_BYTES = 16 * 1024 * 1024

new_session_id = session_schema.new_session_id


class TailLog:
    def __init__(
        self, path: Path, *, max_bytes: int = DEFAULT_MAX_LOG_BYTES
    ) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._handle = None
        self._lock = threading.Lock()
        self._bytes = 0
        self._truncated = False

    @property
    def truncated(self) -> bool:
        return self._truncated

    def open(self) -> None:
        with self._lock:
            if self._handle is not None and not self._handle.closed:
                self._handle.close()
            self._handle = open(self.path, "w", encoding="utf-8", newline="\n")
            self._bytes = 0
            self._truncated = False

    def append(self, line: str) -> None:
        text = line + "\n"
        size = len(text.encode("utf-8"))
        with self._lock:
            handle = self._handle
            if handle is None or handle.closed:
                return
            handle.write(text)
            handle.flush()
            self._bytes += size
            if self._bytes > self.max_bytes:
                self._truncate_locked(self.max_bytes // 2 or 1)

    def tail(self, n: int = 40) -> list[str]:
        with self._lock:
            handle = self._handle
            if handle is not None and not handle.closed:
                handle.flush()
            try:
                text = self.path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return []
        lines = text.splitlines()
        return lines[-n:] if n > 0 else []

    def close(self) -> None:
        with self._lock:
            handle = self._handle
            if handle is not None and not handle.closed:
                handle.flush()
                handle.close()

    def _truncate_locked(self, keep_bytes: int) -> None:
        handle = self._handle
        if handle is None or handle.closed:
            return
        handle.flush()
        handle.close()
        try:
            raw = self.path.read_bytes()
        except OSError:
            self._handle = open(self.path, "a", encoding="utf-8", newline="\n")
            return
        tail = raw[-keep_bytes:] if keep_bytes < len(raw) else raw
        newline = tail.find(b"\n")
        if 0 <= newline < len(tail) - 1:
            tail = tail[newline + 1 :]
        self.path.write_bytes(tail)
        self._handle = open(self.path, "a", encoding="utf-8", newline="\n")
        self._bytes = len(tail)
        self._truncated = True


class SessionOutcome:
    __slots__ = ("status", "error")

    def __init__(
        self, status: str, error: BaseException | None = None
    ) -> None:
        if status not in SESSION_STATUSES:
            raise ValueError(f"unknown manifest status: {status!r}")
        self.status = status
        self.error = error

    @classmethod
    def ok(cls) -> SessionOutcome:
        return cls("ok")

    @classmethod
    def from_failure(cls, error: BaseException) -> SessionOutcome:
        return cls(status_for_error(error), error)

    @classmethod
    def resolve(
        cls,
        failure: BaseException | None,
        *,
        exit_code: int | None,
        unexpected_exit: bool,
        make_crash: Callable[[str], RuntimeCrash] | None = None,
    ) -> SessionOutcome:
        if failure is not None:
            return cls.from_failure(failure)
        if exit_code == 0 and not unexpected_exit:
            return cls.ok()
        if exit_code != 0:
            message = f"engine exited with {exit_code}"
        else:
            message = "engine exited while a command was in flight"
        error = (
            make_crash(message)
            if make_crash is not None
            else RuntimeCrash(message, exit_code=exit_code)
        )
        return cls("crash", error)


class SessionStore:
    def __init__(
        self,
        sessions_root: str | Path,
        *,
        record: bool = True,
        live_frame: bool = False,
        build: bool = True,
        retention: int | None = DEFAULT_SESSION_LIMIT,
        max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
        app: str | None = None,
        record_changed_only: bool = False,
        lvgl_src: str | Path | None = None,
        scenario: str | Path | None = None,
        tool_version: str = paths.TOOL_VERSION,
        mode: str = "headless",
    ) -> None:
        self.sessions_root = Path(sessions_root)
        self.record = bool(record)
        self.live_frame = bool(live_frame)
        self.build = bool(build)
        self.retention = retention
        self.max_log_bytes = max_log_bytes
        self.app = app
        self.record_changed_only = bool(record_changed_only)
        self.mode = mode
        self.tool_version = tool_version
        self._lvgl_src = None if lvgl_src is None else str(lvgl_src)
        self._scenario_path = (
            None if scenario is None else Path(scenario).expanduser().resolve()
        )
        self._scenario_cache: dict[str, Any] | None | bool = False
        self._source_digest_cache: dict[str, Any] | None | bool = False
        self.session_id: str | None = None
        self.session_dir: Path | None = None
        self._log: TailLog | None = None
        self._ready: dict[str, Any] = {}
        self._truncated = False
        self._checks: list[dict[str, Any]] = []

    @property
    def engine_log_path(self) -> Path | None:
        if self.session_dir is None:
            return None
        return self.session_dir / session_schema.ENGINE_LOG_FILE

    @property
    def manifest_path(self) -> Path | None:
        if self.session_dir is None:
            return None
        return self.session_dir / session_schema.MANIFEST_FILE

    @property
    def log_truncated(self) -> bool:
        return self._log is not None and self._log.truncated

    @property
    def ready(self) -> dict[str, Any] | None:
        return self._ready or None

    @property
    def lvgl_src(self) -> Path | None:
        return None if self._lvgl_src is None else Path(self._lvgl_src)

    def create(self) -> Path:
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        for _ in range(50):
            session_id = new_session_id()
            path = self.sessions_root / session_id
            try:
                path.mkdir()
            except FileExistsError:
                continue
            break
        else:
            raise RuntimeError("could not allocate a unique session id")
        self.session_id = session_id
        self.session_dir = path
        if self.record:
            (path / session_schema.FRAMES_DIR).mkdir()
        self._log = TailLog(
            path / session_schema.ENGINE_LOG_FILE,
            max_bytes=self.max_log_bytes,
        )
        self._log.open()
        return path

    def prune(self) -> list[Path]:
        if self.retention is None:
            return []
        try:
            return prune_sessions(
                self.sessions_root,
                limit=self.retention,
                keep=self.session_dir,
            )
        except OSError:
            return []

    def write_build_log(self, text: str) -> None:
        if self.session_dir is None:
            return
        if not text.endswith("\n"):
            text += "\n"
        (self.session_dir / session_schema.BUILD_LOG_FILE).write_text(
            text, encoding="utf-8"
        )

    def append_log(self, line: str) -> None:
        if self._log is not None:
            self._log.append(line)

    def log_tail(self, n: int = 40) -> list[str]:
        if self._log is None:
            return []
        return self._log.tail(n)

    def close_log(self) -> None:
        if self._log is not None:
            self._log.close()

    def discard_preview(self) -> None:
        if not self.live_frame or self.session_dir is None:
            return
        try:
            (self.session_dir / session_schema.PREVIEW_FILE).unlink(
                missing_ok=True
            )
        except OSError:
            pass

    def note_ready(self, ready: Mapping[str, Any]) -> None:
        self._ready = dict(ready)
        self._truncated = bool(ready.get("truncated"))

    def note_mode(self, mode: str) -> None:
        self.mode = mode

    def note_truncated(self) -> None:
        self._truncated = True

    def append_check(self, command: str, ok: bool, frame_no: Any) -> None:
        self._checks.append(
            {"cmd": command, "ok": bool(ok), "frame_no": frame_no}
        )

    def write_manifest(
        self,
        outcome: SessionOutcome,
        *,
        build_status: str | None = None,
    ) -> None:
        if self.session_dir is None or self.manifest_path is None:
            return
        ready = self._ready
        frames = self._frames()
        payload = build_manifest(
            id=self.session_id,
            status=outcome.status,
            app=self.app,
            scenario=self._scenario_metadata(),
            source_digest=self._source_digest(),
            record_changed_only=self.record_changed_only,
            mode=ready.get("mode", self.mode),
            input=list(ready.get("inputs", ["real", "virtual"])),
            build={
                "status": (
                    build_status
                    if build_status is not None
                    else ("ok" if self.build else "skipped")
                ),
                "log": session_schema.BUILD_LOG_FILE,
            },
            lvgl=ready.get("lvgl"),
            lvgl_src=ready.get("lvgl_src") or self._lvgl_src,
            adapter=ready.get("adapter", "9x"),
            display=_display_metadata(ready),
            tool_version=self.tool_version,
            frame_count=len(frames),
            truncated=self._truncated,
            log_truncated=self.log_truncated,
            checks=[dict(item) for item in self._checks],
            error=dump_error(outcome.error),
            artifacts=self._artifacts(frames),
        )
        tmp = self.manifest_path.with_name(self.manifest_path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.manifest_path)

    def _scenario_metadata(self) -> dict[str, Any] | None:
        if self._scenario_cache is not False:
            return self._scenario_cache  # type: ignore[return-value]
        metadata = None
        if self.build and self._scenario_path is not None:
            try:
                data = self._scenario_path.read_bytes()
            except OSError:
                data = None
            if data is not None:
                metadata = {
                    "path": _relative_to_repo(self._scenario_path),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
        self._scenario_cache = metadata
        return metadata

    def _source_digest(self) -> dict[str, Any] | None:
        if self._source_digest_cache is not False:
            return self._source_digest_cache  # type: ignore[return-value]
        digest = None
        if self.build:
            digest = _directory_digest(paths.apps_dir_from_env())
        self._source_digest_cache = digest
        return digest

    def _frames(self) -> list[Path]:
        if self.session_dir is None:
            return []
        return list_pngs(self.session_dir / session_schema.FRAMES_DIR)

    def _artifacts(self, frames: list[Path]) -> dict[str, Any]:
        assert self.session_dir is not None
        artifacts: dict[str, Any] = {"manifest": session_schema.MANIFEST_FILE}
        for filename, key in session_schema.ARTIFACT_FILES:
            if (self.session_dir / filename).is_file():
                artifacts[key] = filename
        if frames:
            artifacts["frames"] = [
                path.relative_to(self.session_dir).as_posix()
                for path in frames
            ]
        snapshots = list_pngs(self.session_dir / session_schema.SNAPSHOTS_DIR)
        if snapshots:
            artifacts["snapshots"] = [
                path.relative_to(self.session_dir).as_posix()
                for path in snapshots
            ]
        return artifacts


def _display_metadata(ready: Mapping[str, Any]) -> dict[str, int] | None:
    display = ready.get("display")
    if (
        not isinstance(display, Mapping)
        or display_problem(display) is not None
    ):
        return None
    return {"width": display["width"], "height": display["height"]}


def _relative_to_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(paths.REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.resolve().as_posix()


def _directory_digest(directory: Path) -> dict[str, Any] | None:
    if not directory.is_dir():
        return None
    digest = hashlib.sha256()
    files = 0
    try:
        entries = sorted(
            path for path in directory.rglob("*") if path.is_file()
        )
    except OSError:
        return None
    for path in entries:
        try:
            relative = path.relative_to(directory).as_posix()
            data = path.read_bytes()
        except (OSError, ValueError):
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        files += 1
    return {
        "dir": _relative_to_repo(directory),
        "sha256": digest.hexdigest(),
        "files": files,
    }
