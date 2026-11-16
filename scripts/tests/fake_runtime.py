from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.tests import support  # noqa: F401

FAKE_SESSION_ID = "20260102-030405-abcd"
FAKE_PID = 4242


class FakeRuntime:
    def __init__(
        self,
        lvgl: str | None = None,
        *,
        build: bool = True,
        record: bool = True,
        headless: bool = True,
        start_error: BaseException | None = None,
        stop_error: BaseException | None = None,
        errors: dict[str, BaseException] | None = None,
        session_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        self.lvgl = lvgl or "9.6"
        self.build = build
        self.record = record
        self.headless = headless
        self.extra_kwargs = dict(kwargs)
        self.app = kwargs.get("app")
        self.start_error = start_error
        self.stop_error = stop_error
        self.errors = dict(errors or {})
        self._session_dir = None if session_dir is None else Path(session_dir)

        self.commands: list[tuple[Any, ...]] = []
        self.recorded_errors: list[BaseException] = []
        self.start_calls = 0
        self.stop_calls = 0
        self.is_running = False
        self.pid: int | None = None
        self.mode = "headless"
        self.exit_code: int | None = None
        self.session_id: str | None = None
        self.session_dir: Path | None = None
        self.manifest_path: Path | None = None
        self.engine_log_path: Path | None = None
        self.ready: dict[str, Any] | None = None
        self.frame_count = 0
        self.t_ms = 0
        self._snapshots = 0

    def start(self) -> FakeRuntime:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        if not self.is_running:
            self.is_running = True
            self.pid = FAKE_PID
            self.session_dir = (
                Path("/fake/sessions") / FAKE_SESSION_ID
                if self._session_dir is None
                else self._session_dir
            )
            self.session_id = self.session_dir.name
            self.manifest_path = self.session_dir / "manifest.json"
            self.engine_log_path = self.session_dir / "engine.log"
        return self

    def log_tail(self, n: int = 40) -> list[str]:
        return []

    def record_error(self, error: BaseException) -> None:
        if not self.recorded_errors or self.recorded_errors[-1] is not error:
            self.recorded_errors.append(error)

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error
        self.is_running = False
        self.pid = None

    def __enter__(self) -> FakeRuntime:
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.stop()
        return False

    def _raise_if(self, name: str) -> None:
        error = self.errors.get(name)
        if error is not None:
            raise error

    def pointer(self, action: str, x: int, y: int) -> dict[str, Any]:
        self._raise_if("pointer")
        self.commands.append(("pointer", action, x, y))
        return {
            "seq": len(self.commands),
            "hit": "fake_button",
            "hit_class": "lv_button",
        }

    def key(self, action: str, key: str) -> dict[str, Any]:
        self._raise_if("key")
        self.commands.append(("key", action, key))
        return {"seq": len(self.commands), "delivered": True, "key": key}

    def encoder(self, action: str, diff: int) -> dict[str, Any]:
        self._raise_if("encoder")
        self.commands.append(("encoder", action, diff))
        return {"seq": len(self.commands), "delivered": True, "diff": diff}

    def tick(self, ms: int, *, track_check: bool = True) -> dict[str, Any]:
        self._raise_if("tick")
        self.commands.append(("tick", ms))
        self.t_ms += ms
        return {
            "seq": len(self.commands),
            "frames": self.frame_count,
            "t_ms": self.t_ms,
        }

    def wait(
        self, ms: int | None = None, *, frames: int | None = None
    ) -> dict[str, Any]:
        self._raise_if("wait")
        if (ms is None) == (frames is None):
            raise ValueError("wait needs exactly one of ms or frames")
        if frames is not None:
            self.commands.append(("wait", "frames", frames))
        else:
            self.commands.append(("wait", ms))
        return {"seq": len(self.commands)}

    def wait_stable(self, max_ms: int, stable_frames: int) -> dict[str, Any]:
        self._raise_if("wait_stable")
        self.commands.append(("wait_stable", max_ms, stable_frames))
        return {
            "seq": len(self.commands),
            "waited_ms": max_ms,
            "stable_frames": stable_frames,
            "stable": True,
        }

    def mark(self, mark_id: str) -> dict[str, Any]:
        self._raise_if("mark")
        self.commands.append(("mark", mark_id))
        return {"seq": len(self.commands)}

    def snapshot(self, label: str) -> dict[str, Any]:
        self._raise_if("snapshot")
        self._snapshots += 1
        self.commands.append(("snapshot", label))
        return {
            "seq": len(self.commands),
            "file": f"snapshots/{self._snapshots:03d}_{label}.png",
        }
