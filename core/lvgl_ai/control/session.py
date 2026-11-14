"""SessionStore: the only writer of one session's evidence directory.

A session is one directory under the sessions root. The store reserves it,
opens ``engine.log``, writes ``build.log`` and ``manifest.json``, removes the
transient ``live.rgba`` preview and applies the retention policy. The engine
writes the frames and ndjson evidence itself; the store accounts for those
files through the shared :mod:`~lvgl_ai.control.session_schema` layout.

:class:`TailLog` owns the byte-capped, line-aligned ``engine.log``;
:class:`SessionOutcome` owns the final manifest status (failure > crash > ok).
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from .. import paths
from .errors import SESSION_STATUSES, RuntimeCrash, dump_error, status_for_error
from .retention import DEFAULT_SESSION_LIMIT, prune_sessions
from .session_schema import (
    ARTIFACT_FILES,
    BUILD_LOG_FILE,
    ENGINE_LOG_FILE,
    FRAMES_DIR,
    MANIFEST_FILE,
    PREVIEW_FILE,
    SNAPSHOTS_DIR,
    build_manifest,
    display_problem,
    list_pngs,
)

DEFAULT_MAX_LOG_BYTES = 16 * 1024 * 1024


def new_session_id(now: _dt.datetime | None = None) -> str:
    """Return ``YYYYMMDD-HHMMSS-4hex`` in local time."""
    stamp = (now or _dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


class TailLog:
    """Append-only ``engine.log`` with a byte cap and a line-aligned tail.

    ``append`` keeps the last ``max_bytes`` by rewriting to roughly half the
    cap when it overflows, so a crash still leaves a usable
    ``RuntimeCrash.log_tail``. ``tail`` reads the file, so it also works after
    ``close``. All handle access is serialized because the engine's stdout and
    stderr pumps append from two threads.
    """

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
        """True once the cap forced a tail rewrite."""
        return self._truncated

    def open(self) -> None:
        """Create (or truncate) the log file for a new session."""
        with self._lock:
            if self._handle is not None and not self._handle.closed:
                self._handle.close()
            self._handle = open(
                self.path, "w", encoding="utf-8", newline="\n"
            )
            self._bytes = 0
            self._truncated = False

    def append(self, line: str) -> None:
        """Append one line; silently drop it once the log is closed."""
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
        """Last ``n`` lines; ``n <= 0`` returns ``[]``."""
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
        """Flush and close the handle; later appends are dropped."""
        with self._lock:
            handle = self._handle
            if handle is not None and not handle.closed:
                handle.flush()
                handle.close()

    def _truncate_locked(self, keep_bytes: int) -> None:
        """Keep the last ``keep_bytes``, aligned to a line start."""
        handle = self._handle
        if handle is None or handle.closed:
            return
        handle.flush()
        handle.close()
        try:
            raw = self.path.read_bytes()
        except OSError:
            self._handle = open(
                self.path, "a", encoding="utf-8", newline="\n"
            )
            return
        tail = raw[-keep_bytes:] if keep_bytes < len(raw) else raw
        newline = tail.find(b"\n")
        if 0 <= newline < len(tail) - 1:
            tail = tail[newline + 1 :]
        self.path.write_bytes(tail)
        self._handle = open(
            self.path, "a", encoding="utf-8", newline="\n"
        )
        self._bytes = len(tail)
        self._truncated = True


class SessionOutcome:
    """Final status for one session: a recorded failure beats a crash, a crash
    beats ``ok``.

    The status vocabulary only describes what the tool did. ``error`` is the
    typed exception that explains a non-``ok`` status.
    """

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
        """Map a failure outside the exit-code path to its manifest status."""
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
        """Decide the final status after the engine stopped.

        ``make_crash`` fills the exit code and log tail once the pumps joined;
        without it a plain :class:`RuntimeCrash` is recorded.
        """
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
    """One session directory and every file the control layer writes into it.

    ``create`` reserves the directory (with ``frames/`` when recording) and
    opens ``engine.log``; ``prune`` applies the retention policy right after,
    so the current session is never touched. Manifest metadata is collected
    from the constructor options, the validated ``ready`` announcement and the
    on-disk evidence, then written atomically by :meth:`write_manifest`.
    """

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
        self.session_id: str | None = None
        self.session_dir: Path | None = None
        self._log: TailLog | None = None
        self._ready: dict[str, Any] = {}
        self._truncated = False
        # Protocol commands that actually ran and reached a successful reply
        # (or failed). ``checks`` only says whether the command executed.
        self._checks: list[dict[str, Any]] = []

    # ---- session directory --------------------------------------------

    @property
    def engine_log_path(self) -> Path | None:
        if self.session_dir is None:
            return None
        return self.session_dir / ENGINE_LOG_FILE

    @property
    def manifest_path(self) -> Path | None:
        if self.session_dir is None:
            return None
        return self.session_dir / MANIFEST_FILE

    @property
    def log_truncated(self) -> bool:
        """True once ``engine.log`` was capped during this session."""
        return self._log is not None and self._log.truncated

    @property
    def ready(self) -> dict[str, Any] | None:
        """The validated ``ready`` announcement, or ``None`` before startup."""
        return self._ready or None

    @property
    def lvgl_src(self) -> Path | None:
        """The LVGL source tree as recorded, or ``None`` for the default."""
        return None if self._lvgl_src is None else Path(self._lvgl_src)

    @property
    def session_retention(self) -> int | None:
        """Public name for the retention limit owned by the store."""
        return self.retention

    def create(self) -> Path:
        """Reserve a unique session directory and open its engine log."""
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
            (path / FRAMES_DIR).mkdir()
        self._log = TailLog(path / ENGINE_LOG_FILE, max_bytes=self.max_log_bytes)
        self._log.open()
        return path

    def prune(self) -> list[Path]:
        """Delete expired sessions; deletion is best effort and never fatal."""
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

    # ---- logs ----------------------------------------------------------

    def write_build_log(self, text: str) -> None:
        """Write ``build.log``; the caller passes the whole phase output."""
        if self.session_dir is None:
            return
        if not text.endswith("\n"):
            text += "\n"
        (self.session_dir / BUILD_LOG_FILE).write_text(text, encoding="utf-8")

    def append_log(self, line: str) -> None:
        """Append one engine stdout/stderr line."""
        if self._log is not None:
            self._log.append(line)

    def log_tail(self, n: int = 40) -> list[str]:
        """Last ``n`` lines of engine.log (stdout and stderr)."""
        if self._log is None:
            return []
        return self._log.tail(n)

    def close_log(self) -> None:
        if self._log is not None:
            self._log.close()

    # ---- preview -------------------------------------------------------

    def discard_preview(self) -> None:
        """Remove the transient raw preview; it is not session evidence."""
        if not self.live_frame or self.session_dir is None:
            return
        try:
            (self.session_dir / PREVIEW_FILE).unlink(missing_ok=True)
        except OSError:
            pass

    # ---- manifest ------------------------------------------------------

    def note_ready(self, ready: Mapping[str, Any]) -> None:
        """Record the validated ``ready`` announcement for later manifests."""
        self._ready = dict(ready)
        self._truncated = bool(ready.get("truncated"))

    def note_mode(self, mode: str) -> None:
        """Record the mode the engine actually reported."""
        self.mode = mode

    def note_truncated(self) -> None:
        """Remember that the engine dropped frames or rows at the cap."""
        self._truncated = True

    def append_check(self, command: str, ok: bool, frame_no: Any) -> None:
        """Record that a protocol command ran; never judges the picture."""
        self._checks.append(
            {"cmd": command, "ok": bool(ok), "frame_no": frame_no}
        )

    def write_manifest(
        self,
        outcome: SessionOutcome,
        *,
        build_status: str | None = None,
    ) -> None:
        """Atomically write ``manifest.json`` for ``outcome``.

        Artifacts and ``frame_count`` come from the files actually on disk, so
        a partially written session stays self-describing.
        """
        if self.session_dir is None or self.manifest_path is None:
            return
        ready = self._ready
        frames = self._frames()
        payload = build_manifest(
            id=self.session_id,
            status=outcome.status,
            app=self.app,
            record_changed_only=self.record_changed_only,
            mode=ready.get("mode", self.mode),
            input=list(ready.get("inputs", ["real", "virtual"])),
            build={
                "status": (
                    build_status
                    if build_status is not None
                    else ("ok" if self.build else "skipped")
                ),
                "log": BUILD_LOG_FILE,
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
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.manifest_path)

    def _frames(self) -> list[Path]:
        if self.session_dir is None:
            return []
        return list_pngs(self.session_dir / FRAMES_DIR)

    def _artifacts(self, frames: list[Path]) -> dict[str, Any]:
        assert self.session_dir is not None
        artifacts: dict[str, Any] = {"manifest": MANIFEST_FILE}
        for filename, key in ARTIFACT_FILES:
            if (self.session_dir / filename).is_file():
                artifacts[key] = filename
        if frames:
            artifacts["frames"] = [
                path.relative_to(self.session_dir).as_posix() for path in frames
            ]
        snapshots = list_pngs(self.session_dir / SNAPSHOTS_DIR)
        if snapshots:
            artifacts["snapshots"] = [
                path.relative_to(self.session_dir).as_posix()
                for path in snapshots
            ]
        return artifacts


def _display_metadata(ready: Mapping[str, Any]) -> dict[str, int] | None:
    """The actual display size from ``ready``; ``None`` before startup."""
    display = ready.get("display")
    if not isinstance(display, Mapping) or display_problem(display) is not None:
        return None
    return {"width": display["width"], "height": display["height"]}
