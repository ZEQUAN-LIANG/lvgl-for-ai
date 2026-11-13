"""Build/flash job orchestration, independent of HTTP.

The server only parses a request body into ``BuildRequest`` / ``FlashRequest``
and hands the job to ``JobRunner``.  Keeping the orchestration here makes the
serial detach/reconnect and state-recording rules testable without a handler.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build_flash import BuildFlashError, run_build, run_flash
from jobs import Job


@dataclass(frozen=True)
class BuildRequest:
    app: str = ""
    project_dir: str | None = None
    board: str | None = None

    @classmethod
    def from_body(cls, body: dict[str, Any]) -> "BuildRequest":
        return cls(
            app=str(body.get("app") or ""),
            project_dir=body.get("project_dir") or None,
            board=body.get("board") or None,
        )


@dataclass(frozen=True)
class FlashRequest:
    app: str = ""
    project_dir: str | None = None
    build_dir: str | None = None
    board: str | None = None
    build: bool = False
    port: str | None = None
    baud: int | None = None
    verify: bool | None = None
    erase_all: bool | None = None
    after: str | None = None
    reconnect: bool = True

    @classmethod
    def from_body(cls, body: dict[str, Any]) -> "FlashRequest":
        return cls(
            app=str(body.get("app") or ""),
            project_dir=body.get("project_dir") or None,
            build_dir=body.get("build_dir") or None,
            board=body.get("board") or None,
            build=bool(body.get("build")),
            port=body.get("port") or None,
            baud=body.get("baud") or None,
            verify=body.get("verify"),
            erase_all=body.get("erase_all"),
            after=body.get("after"),
            reconnect=bool(body.get("reconnect", True)),
        )


class JobRunner:
    def __init__(self, config: dict[str, Any], broker, state_store) -> None:
        self._config = config
        self._broker = broker
        self._state = state_store

    # -- build ---------------------------------------------------------

    def build(self, job: Job, request: BuildRequest) -> None:
        try:
            result = run_build(
                self._config,
                job,
                app=request.app or None,
                project_dir=request.project_dir,
                board=request.board,
            )
            if request.app:
                self._state.record_build(
                    app=request.app,
                    project_dir=result["project_dir"],
                    build_dir=result["build_dir"],
                )
            else:
                self._state.update(
                    project_dir=result["project_dir"],
                    build_dir=result["build_dir"],
                )
            job.finish(ok=True, result=result)
        except BuildFlashError as exc:
            self._fail(job, exc)
        except Exception as exc:  # noqa: BLE001 - job boundary
            self._crash(job, exc)

    # -- flash ---------------------------------------------------------

    def flash(self, job: Job, request: FlashRequest) -> None:
        saved: dict[str, Any] | None = None
        result: dict[str, Any] | None = None
        try:
            build_dir = request.build_dir
            if request.build:
                build_result = run_build(
                    self._config,
                    job,
                    app=request.app or None,
                    project_dir=request.project_dir,
                    board=request.board,
                )
                build_dir = build_result["build_dir"]
                job.append("status", "build ok; starting flash")

            saved = self._broker.detach_for_flash()
            if saved.get("was_open"):
                job.append(
                    "status",
                    f"serial released ({saved.get('port')} @ {saved.get('baud')})",
                )

            result = run_flash(
                self._config,
                job,
                port=request.port or saved.get("port") or None,
                baud=request.baud or saved.get("baud") or None,
                build_dir=build_dir,
                project_dir=request.project_dir,
                board=request.board,
                verify=request.verify,
                erase_all=request.erase_all,
                after=request.after,
            )
            self._record_flash_state(request.app, result)
            self._state.record_open(
                port=result["port"],
                baud=result["baud"],
            )
            job.finish(ok=True, result=result)
        except BuildFlashError as exc:
            self._fail(job, exc)
        except Exception as exc:  # noqa: BLE001 - job boundary
            self._crash(job, exc)
        finally:
            if saved is not None and request.reconnect:
                self._reconnect(job, request, saved, result)

    # -- helpers -------------------------------------------------------

    def _record_flash_state(self, app: str, result: dict[str, Any]) -> None:
        project_dir = str(Path(result["build_dir"]).parent)
        if app:
            self._state.record_build(
                app=app,
                project_dir=project_dir,
                build_dir=result["build_dir"],
            )
        else:
            self._state.update(
                project_dir=project_dir,
                build_dir=result["build_dir"],
            )

    def _reconnect(
        self,
        job: Job,
        request: FlashRequest,
        saved: dict[str, Any],
        result: dict[str, Any] | None,
    ) -> None:
        port = (
            (result or {}).get("port")
            or request.port
            or saved.get("port")
        )
        baud = (
            (result or {}).get("baud")
            or request.baud
            or saved.get("baud")
        )
        if not port:
            return
        try:
            self._broker.open(port, baud)
            job.append("status", "serial reconnected")
        except Exception as exc:  # noqa: BLE001 - best effort
            job.append("stderr", f"serial reconnect failed: {exc}")

    def _fail(self, job: Job, exc: BuildFlashError) -> None:
        job.append("stderr", str(exc))
        job.finish(
            ok=False,
            error=str(exc),
            cancelled=exc.code == "cancelled",
        )

    def _crash(self, job: Job, exc: Exception) -> None:
        traceback.print_exc()
        job.append("stderr", str(exc))
        job.finish(ok=False, error=str(exc))
