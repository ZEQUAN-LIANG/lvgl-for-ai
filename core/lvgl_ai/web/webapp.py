"""HTTP/UI adapter for live sessions and recorded evidence.

The server is a thin shell over the Python control layer:

- live start/stop/input/status route through :class:`LiveSession`, which owns
  the Runtime, raw preview hub, ticker and temporary test-session root;
- replay reads sessions with ``Recording`` and never starts an engine;
- annotation writes go through ``annotations.write_note``; this module only
  resolves the session and maps the domain error code to a status.

There is no second protocol client: this module never reads or writes stdin /
stdout and never spawns a process.
"""

from __future__ import annotations

import json
import re
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from .. import apps as app_store
from .. import paths
from ..apps.trash import InvalidTrashId
from ..control.input import TOKEN_PATTERN, is_token
from ..control.recording import Recording
from ..control.runtime import Runtime
from ..control.session_schema import SESSION_ID_RE, is_session_id
from ..scenario import scenario_index
from . import page_render, replay_model, whiteboards
from .annotations import AnnotationError, delete_note, write_note
from .live_session import (
    LiveError,
    LiveSession,
    validate_live_kind,
)
from .urls import page_url

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 1024 * 1024
# A whiteboard payload carries a base64 PNG plus the Fabric object tree.
WHITEBOARD_BODY_BYTES = 12 * 1024 * 1024
# An annotation payload may carry one composed PNG per anchor frame.
ANNOTATION_BODY_BYTES = 12 * 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"
# Page tracking for --exit-on-close: the page refreshes its id every 10 s (the
# interval lives in web/wire.py); a page unseen for two minutes is treated as
# gone. Closing the last browser page stops the server after a short grace so a
# reload can re-open it.
PAGE_HEARTBEAT_TTL_S = 120.0
PAGE_CLOSE_GRACE_S = 0.5
# Reasonable oversized bodies are drained before the 413 so Windows does not
# reset the connection while the client is still writing (which would hide the
# 4xx response behind a ConnectionAbortedError).
MAX_DRAIN_BYTES = 16 * 1024 * 1024
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.png$")
PAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
APP_REQUEST_HEADER = "X-LVGL-AI-Request"
APP_REQUEST_VALUE = "1"
# The app domain carries no HTTP status; the adapter maps the domain code to
# the status it has always returned. ``invalid_trash`` covers both a malformed
# id (400) and corrupt metadata (409); ``InvalidTrashId`` selects the former.
APP_ERROR_STATUS = {
    "app_c_missing": 500,
    "app_conflict": 409,
    "app_exists": 409,
    "app_invalid": 500,
    "app_io_error": 500,
    "app_registry_invalid": 500,
    "confirmation_required": 400,
    "invalid_name": 400,
    "invalid_trash": 409,
    "name_reserved": 400,
    "protected_app": 403,
    "protected_scenario": 403,
    "restore_conflict": 409,
    "unknown_app": 404,
    "unknown_trash": 404,
    "unsafe_path": 400,
}
# The live domain carries no HTTP status either; this adapter maps each code
# to the status the routes have always returned.
LIVE_ERROR_STATUS = {
    "invalid_input": 400,
    "invalid_key": 400,
    "invalid_live_mode": 400,
    "live_input_error": 500,
    "live_not_running": 409,
    "live_running": 409,
    "live_start_error": 500,
    "live_starting": 409,
    "live_stop_error": 500,
}
# The annotation transaction carries no HTTP status either; this adapter maps
# its domain codes to the statuses the route has always returned.
# ``internal_error`` is the historical generic 500 for an unexpected I/O
# failure while reading or preparing evidence; the JSON is unchanged.
ANNOTATION_ERROR_STATUS = {
    "annotations_unreadable": 409,
    "annotations_write_error": 500,
    "duplicate_annotation_id": 409,
    "internal_error": 500,
    "invalid_annotation": 400,
    "region_image_error": 400,
    "unknown_annotation": 404,
}
WHITEBOARD_ERROR_STATUS = {
    "invalid_whiteboard": 400,
    "whiteboards_unreadable": 409,
    "whiteboards_write_error": 500,
    "unknown_whiteboard": 404,
}
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
    "base-uri 'none'; form-action 'self'"
)


def _input_app(value: Any) -> str | None:
    """Validate an optional app name from the query string or a test call."""
    if value is None or value == "":
        return None
    if not is_token(value):
        raise HttpError(
            HTTPStatus.BAD_REQUEST,
            "invalid_app",
            f"app must match {TOKEN_PATTERN}",
        )
    return value


class HttpError(Exception):
    """An error that maps directly to an HTTP status and JSON body."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = int(status)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
            }
        }


def _live_http_error(exc: LiveError) -> HttpError:
    status = LIVE_ERROR_STATUS.get(
        exc.code, HTTPStatus.INTERNAL_SERVER_ERROR
    )
    return HttpError(status, exc.code, exc.message, detail=exc.detail)


class WebApp:
    """State and behavior behind the HTTP routes."""

    def __init__(
        self,
        sessions_root: str | Path,
        *,
        runtime_factory: Callable[[], Runtime] | None = None,
        lvgl: str | None = None,
        build: bool = True,
        scenarios_dir: str | Path | None = None,
        repo_root: str | Path | None = None,
        page_clock: Callable[[], float] | None = None,
    ) -> None:
        self.sessions_root = Path(sessions_root).expanduser().resolve()
        self.lvgl = lvgl
        self.build = bool(build)
        self.repo_root = (
            Path(repo_root).expanduser().resolve()
            if repo_root is not None
            else paths.REPO_ROOT
        )
        self.scenarios_dir = (
            Path(scenarios_dir).expanduser().resolve()
            if scenarios_dir is not None
            else self.repo_root / "user" / "scenarios"
        )
        self._apps_lock = threading.RLock()
        self._last_app_operation: dict[str, Any] | None = None
        # The live runtime, hub, ticker, test-session root, selected app and
        # state machine all live behind this seam; WebApp only composes it.
        self.live = LiveSession(
            self.sessions_root,
            runtime_factory=runtime_factory,
            lvgl=self.lvgl,
            build=self.build,
        )
        # Browser page tracking; the exit watchdog only reads this in
        # --exit-on-close mode, but registering is harmless otherwise. The
        # clock is injectable so heartbeat/grace behavior is testable without
        # patching the global ``time`` module.
        self._page_clock = page_clock if page_clock is not None else time.monotonic
        self._page_lock = threading.Lock()
        self._pages: dict[str, float] = {}
        self._seen_page = False
        self._last_page_change = 0.0

    # ---- sessions and replay ------------------------------------------

    def sessions(self) -> list[dict[str, Any]]:
        root = self.sessions_root
        if not root.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for child in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
            if not child.is_dir() or not is_session_id(child.name):
                continue
            if not (child / "manifest.json").is_file():
                continue
            entry: dict[str, Any] = {
                "id": child.name,
                "valid": False,
                "status": None,
                "mode": None,
                "app": None,
                "frame_count": 0,
                "error": None,
            }
            try:
                recording = Recording.open(child)
                manifest = recording.manifest
                entry.update(
                    valid=True,
                    status=manifest["status"],
                    mode=manifest["mode"],
                    app=manifest.get("app"),
                    frame_count=manifest["frame_count"],
                )
            except (OSError, ValueError) as exc:
                entry["error"] = str(exc)
            entries.append(entry)
        return entries

    def scenario_apps(self) -> list[dict[str, Any]]:
        """Apps declared by user scenarios, for the live app selector.

        The tool does not know app names: whichever scenario declares ``app``
        becomes a choice. Invalid scenarios are ignored so one broken file
        cannot take down the page.
        """
        with self._apps_lock:
            return self._scenario_apps_locked()

    def _scenario_apps_locked(self) -> list[dict[str, Any]]:
        apps: dict[str, dict[str, Any]] = {}
        for item in scenario_index(
            self.repo_root,
            scenarios_dir=self.scenarios_dir,
            include_symlinks=True,
        ):
            if not item["valid"]:
                continue
            app = item["app"]
            if not isinstance(app, str) or not app or app in apps:
                continue
            apps[app] = {
                "app": app,
                "name": item["name"] or app,
                "scenario": item["basename"],
                "display": item["display"],
            }
        return sorted(apps.values(), key=lambda entry: (entry["name"], entry["app"]))

    def _scenario_display(self, app: str | None) -> tuple[int, int] | None:
        """The display declared by the first sorted scenario for ``app``."""
        if app is None:
            return None
        with self._apps_lock:
            for entry in self._scenario_apps_locked():
                if entry["app"] == app:
                    display = entry.get("display")
                    if display is None:
                        return None
                    return display["width"], display["height"]
        return None

    # ---- app management -------------------------------------------------

    @staticmethod
    def _app_error(exc: app_store.AppError) -> HttpError:
        status = APP_ERROR_STATUS.get(exc.code, HTTPStatus.BAD_REQUEST)
        if isinstance(exc, InvalidTrashId):
            status = HTTPStatus.BAD_REQUEST
        return HttpError(status, exc.code, exc.message, detail=exc.detail)

    def _reject_app_mutation_while_live(self) -> None:
        if self.live.is_active():
            raise HttpError(
                HTTPStatus.CONFLICT,
                "live_active",
                "停止当前测试或录制后再修改应用",
            )

    def _run_app_mutation(
        self, operation: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        with self._apps_lock:
            self._reject_app_mutation_while_live()
            try:
                result = operation()
            except app_store.AppError as exc:
                raise self._app_error(exc) from exc
            except OSError as exc:
                raise HttpError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "app_io_error",
                    str(exc),
                ) from exc
            self._last_app_operation = result
            if result.get("action") in ("delete", "purge"):
                self.live.forget_app(result.get("name"))
            return result

    def apps_payload(self) -> dict[str, Any]:
        with self._apps_lock:
            payload = app_store.list_apps(self.repo_root)
            payload["trash"] = app_store.list_trash(self.repo_root)
            payload["recent"] = app_store.recent_apps(
                self.repo_root, limit=12
            )
            payload["last_operation"] = self._last_app_operation
            payload["roots"] = {
                "app": "user/app",
                "scenarios": "user/scenarios",
                "app_c": "user/app/app.c",
                "trash": "user/.trash/apps",
            }
            return payload

    def app_tree_payload(self, name: Any) -> dict[str, Any]:
        with self._apps_lock:
            try:
                return app_store.app_tree(self.repo_root, name)
            except app_store.AppError as exc:
                raise self._app_error(exc) from exc

    def create_app(self, name: Any) -> dict[str, Any]:
        return self._run_app_mutation(
            lambda: app_store.scaffold_app(self.repo_root, name)
        )

    def delete_app(self, name: Any) -> dict[str, Any]:
        return self._run_app_mutation(
            lambda: app_store.delete_app(self.repo_root, name)
        )

    def restore_app(self, trash_id: Any) -> dict[str, Any]:
        return self._run_app_mutation(
            lambda: app_store.restore_app(self.repo_root, trash_id)
        )

    def purge_app(self, trash_id: Any, *, confirm: bool) -> dict[str, Any]:
        return self._run_app_mutation(
            lambda: app_store.permanently_delete(
                self.repo_root, trash_id, confirm=confirm
            )
        )

    def session_path(self, session_id: Any) -> Path:
        if not is_session_id(session_id):
            raise HttpError(
                HTTPStatus.NOT_FOUND,
                "unknown_session",
                f"unknown session: {session_id!r}",
            )
        path = self.sessions_root / session_id
        if not path.is_dir():
            raise HttpError(
                HTTPStatus.NOT_FOUND,
                "unknown_session",
                f"unknown session: {session_id!r}",
            )
        return path

    def open_recording(self, session_id: Any) -> Recording:
        path = self.session_path(session_id)
        try:
            return Recording.open(path)
        except FileNotFoundError as exc:
            raise HttpError(
                HTTPStatus.NOT_FOUND, "session_unreadable", str(exc)
            ) from exc
        except (OSError, ValueError) as exc:
            raise HttpError(
                HTTPStatus.CONFLICT, "session_unreadable", str(exc)
            ) from exc

    def render_page(
        self, session_id: str | None, app: str | None = None
    ) -> tuple[int, str]:
        sessions = self.sessions()
        apps = self.scenario_apps()
        selected_app = self.live.selected_app(app)
        selected = session_id
        if selected is None:
            # Prefer a replayable session; a failed build can leave the
            # newest directory with no frames at all.
            selected = next(
                (
                    entry["id"]
                    for entry in sessions
                    if entry["valid"] and entry["frame_count"] > 0
                ),
                None,
            )
            if selected is None:
                selected = next(
                    (entry["id"] for entry in sessions if entry["valid"]), None
                )
        replay = None
        page_error = None
        if selected is not None:
            try:
                recording = self.open_recording(selected)
            except HttpError as exc:
                if exc.code == "unknown_session":
                    return exc.status, page_render.render_page(
                        sessions=sessions,
                        selected_id=selected,
                        apps=apps,
                        selected_app=selected_app,
                        replay=None,
                        page_error={"code": exc.code, "message": exc.message},
                    )
                page_error = {"code": exc.code, "message": exc.message}
            else:
                try:
                    replay = replay_model.load(recording)
                    # The page renders every section; prime them so a bad
                    # evidence file still turns into the same notice page.
                    replay.prime()
                except (OSError, ValueError) as exc:
                    page_error = {
                        "code": "session_unreadable",
                        "message": str(exc),
                    }
        return HTTPStatus.OK, page_render.render_page(
            sessions=sessions,
            selected_id=selected,
            apps=apps,
            selected_app=selected_app,
            replay=replay,
            page_error=page_error,
        )

    def _load_replay_model(self, session_id: str) -> replay_model.ReplayModel:
        return replay_model.load(self.open_recording(session_id))

    def session_payload(self, session_id: str) -> dict[str, Any]:
        recording = self.open_recording(session_id)
        model = replay_model.load(recording)
        return {
            "id": model.session_id,
            "session_dir": str(recording.path),
            "manifest": model.manifest,
            "frame_count": model.manifest["frame_count"],
            "frames_available": len(model.frames),
            "frames": model.frames,
            "snapshots": model.snapshots,
            "annotations_count": model.note_count,
        }

    def timeline_payload(self, session_id: str) -> dict[str, Any]:
        model = self._load_replay_model(session_id)
        if model.timeline_error is not None:
            raise model.timeline_error
        return {"timeline": model.timeline}

    def diffs_payload(self, session_id: str) -> dict[str, Any]:
        model = self._load_replay_model(session_id)
        if model.frame_diffs_error is not None:
            raise model.frame_diffs_error
        if model.reference_diffs_error is not None:
            raise model.reference_diffs_error
        return {
            "frame_diffs": model.frame_diffs,
            "reference_diffs": model.reference_diffs,
        }

    def log_payload(self, session_id: str) -> dict[str, Any]:
        model = self._load_replay_model(session_id)
        return {
            "log_tail": model.log_tail,
            "log_truncated": model.manifest["log_truncated"],
        }

    def annotations_payload(self, session_id: str) -> dict[str, Any]:
        model = self._load_replay_model(session_id)
        if model.annotations_error is not None:
            raise HttpError(
                HTTPStatus.CONFLICT,
                "annotations_unreadable",
                str(model.annotations_error),
            ) from model.annotations_error
        return {"annotations": model.annotations}

    # ---- annotations ---------------------------------------------------

    def add_annotation(
        self, session_id: str, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        recording = self.open_recording(session_id)
        try:
            document, note = write_note(recording, payload)
        except AnnotationError as exc:
            status = ANNOTATION_ERROR_STATUS.get(
                exc.code, HTTPStatus.BAD_REQUEST
            )
            raise HttpError(status, exc.code, str(exc)) from exc
        return HTTPStatus.CREATED, {"annotations": document, "note": note}

    def delete_annotation(
        self, session_id: str, note_id: str
    ) -> tuple[int, dict[str, Any]]:
        recording = self.open_recording(session_id)
        try:
            document = delete_note(recording, note_id)
        except AnnotationError as exc:
            status = ANNOTATION_ERROR_STATUS.get(
                exc.code, HTTPStatus.BAD_REQUEST
            )
            raise HttpError(status, exc.code, str(exc)) from exc
        return HTTPStatus.OK, {
            "annotations": document,
            "deleted": note_id,
        }

    # ---- whiteboards ---------------------------------------------------

    def whiteboards_payload(self, session_id: str) -> dict[str, Any]:
        recording = self.open_recording(session_id)
        try:
            return {"whiteboards": whiteboards.read_whiteboards(recording)}
        except whiteboards.WhiteboardError as exc:
            status = WHITEBOARD_ERROR_STATUS.get(
                exc.code, HTTPStatus.BAD_REQUEST
            )
            raise HttpError(status, exc.code, str(exc)) from exc

    def save_whiteboard(
        self, session_id: str, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        recording = self.open_recording(session_id)
        try:
            document, item = whiteboards.save_whiteboard(recording, payload)
        except whiteboards.WhiteboardError as exc:
            status = WHITEBOARD_ERROR_STATUS.get(
                exc.code, HTTPStatus.BAD_REQUEST
            )
            raise HttpError(status, exc.code, str(exc)) from exc
        return HTTPStatus.CREATED, {
            "whiteboards": document,
            "whiteboard": item,
        }

    def delete_whiteboard(
        self, session_id: str, whiteboard_id: str
    ) -> tuple[int, dict[str, Any]]:
        recording = self.open_recording(session_id)
        try:
            document = whiteboards.delete_whiteboard(recording, whiteboard_id)
        except whiteboards.WhiteboardError as exc:
            status = WHITEBOARD_ERROR_STATUS.get(
                exc.code, HTTPStatus.BAD_REQUEST
            )
            raise HttpError(status, exc.code, str(exc)) from exc
        return HTTPStatus.OK, {
            "whiteboards": document,
            "deleted": whiteboard_id,
        }

    # ---- browser page tracking ----------------------------------------

    def page_open(self, page_id: str) -> dict[str, Any]:
        """Register a page or refresh its heartbeat."""
        now = self._page_clock()
        with self._page_lock:
            self._pages[page_id] = now
            self._seen_page = True
            self._last_page_change = now
        return {"ok": True}

    def page_close(self, page_id: str) -> dict[str, Any]:
        """Forget a page the browser says it is leaving."""
        now = self._page_clock()
        with self._page_lock:
            self._pages.pop(page_id, None)
            self._last_page_change = now
        return {"ok": True}

    def should_exit_on_close(self) -> bool:
        """True once every registered page has closed or gone stale."""
        now = self._page_clock()
        with self._page_lock:
            if not self._seen_page:
                return False
            for page_id, seen in list(self._pages.items()):
                if now - seen > PAGE_HEARTBEAT_TTL_S:
                    self._pages.pop(page_id, None)
            if self._pages:
                return False
            return now - self._last_page_change >= PAGE_CLOSE_GRACE_S

    def shutdown(self) -> None:
        """Stop the live Runtime when the HTTP server goes away.

        Ctrl+C on ``web.py`` must follow the documented quit -> wait ->
        terminate path, otherwise the engine is left with an unfinished
        manifest. A start that is still building gets a short grace period;
        interrupting ``Runtime.start()`` from another thread would race.
        """
        deadline = time.monotonic() + 5.0
        while self.live.is_starting() and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.live.is_starting():
            return
        try:
            self.live.stop()
        except LiveError:
            pass


class _WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    verbose = False
    app: WebApp


class _WebHandler(BaseHTTPRequestHandler):
    server_version = "web/0.1"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> WebApp:
        return self.server.app

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    # ---- dispatch ------------------------------------------------------

    def _dispatch(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
            self._route(method, path, query)
        except HttpError as exc:
            self._send_json(exc.status, exc.payload())
        except LiveError as exc:
            error = _live_http_error(exc)
            self._send_json(error.status, error.payload())
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001 - keep the server alive
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": {
                        "code": "internal_error",
                        "message": str(exc),
                        "detail": {},
                    }
                },
            )

    def _route(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        # The route table lives in ``routes.py``; import lazily so webapp can
        # import the route module's shared constants without a cycle.
        from .routes import route

        return route(self, method, path, query)

    @staticmethod
    def _require(method: str, allowed: tuple[str, ...]) -> None:
        if method not in allowed:
            raise HttpError(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "method_not_allowed",
                f"{method} is not allowed here",
            )

    def _require_app_mutation_headers(self) -> None:
        media_type = (
            self.headers.get("Content-Type", "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if media_type != "application/json":
            self._discard_request_body()
            raise HttpError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "unsupported_media_type",
                "Content-Type must be application/json",
            )
        if self.headers.get(APP_REQUEST_HEADER) != APP_REQUEST_VALUE:
            self._discard_request_body()
            raise HttpError(
                HTTPStatus.FORBIDDEN,
                "invalid_request_header",
                f"{APP_REQUEST_HEADER}: {APP_REQUEST_VALUE} is required",
            )

    def _discard_request_body(self) -> None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return
        try:
            length = int(raw_length)
        except ValueError:
            return
        if 0 <= length <= MAX_DRAIN_BYTES:
            self._discard_body(length)

    def _read_json_body(
        self, limit: int = MAX_BODY_BYTES
    ) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise HttpError(
                HTTPStatus.LENGTH_REQUIRED,
                "length_required",
                "Content-Length is required",
            )
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise HttpError(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must be an integer",
            ) from exc
        if length < 0:
            raise HttpError(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must not be negative",
            )
        if length > limit:
            if length <= MAX_DRAIN_BYTES:
                self._discard_body(length)
            raise HttpError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "payload_too_large",
                f"body must be at most {limit} bytes",
            )
        data = self.rfile.read(length)
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(
                HTTPStatus.BAD_REQUEST, "invalid_json", str(exc)
            ) from exc
        if not isinstance(payload, dict):
            raise HttpError(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "expected a JSON object",
            )
        return payload

    def _discard_body(self, length: int) -> None:
        remaining = length
        try:
            self.connection.settimeout(10.0)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    return
                remaining -= len(chunk)
        except OSError:
            return
        finally:
            try:
                self.connection.settimeout(None)
            except OSError:
                pass

    def _serve_live_stream(self) -> None:
        """Stream raw preview frames until the live session or client ends.

        The body is close-delimited HTTP/1.1: there is no Content-Length and
        each frame is a fixed header plus pixels. The handler writes on its own
        thread and never holds the live lock; the stream handle keeps this
        response bound to the session that was running when it connected.
        """
        stream = self.app.live.open_stream()
        self.close_connection = True
        try:
            self.connection.settimeout(10.0)
        except OSError:
            pass
        self.send_response(int(HTTPStatus.OK))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Connection", "close")
        self.end_headers()
        sent = 0
        try:
            self.wfile.flush()
            while True:
                frame = stream.wait_frame(sent, timeout=1.0)
                if frame is None:
                    if stream.closed:
                        return
                    continue
                self.wfile.write(frame.to_bytes())
                self.wfile.flush()
                sent = frame.seq
        except Exception:  # noqa: BLE001 - headers are already streaming
            return

    def _serve_static(self, name: str) -> None:
        path = STATIC_DIR / name
        if not path.is_file():
            raise HttpError(
                HTTPStatus.NOT_FOUND, "not_found", "file not found"
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise HttpError(
                HTTPStatus.INTERNAL_SERVER_ERROR, "read_error", str(exc)
            ) from exc
        self._send(
            HTTPStatus.OK,
            data,
            "text/javascript; charset=utf-8",
            cache_control="public, max-age=31536000, immutable",
        )

    def _serve_png(self, kind: str, session_id: str, filename: str) -> None:
        session_dir = self.app.session_path(session_id)
        if not FILE_NAME_RE.fullmatch(filename):
            raise HttpError(
                HTTPStatus.NOT_FOUND, "not_found", "file not found"
            )
        path = session_dir / kind / filename
        if not path.is_file():
            raise HttpError(
                HTTPStatus.NOT_FOUND, "not_found", "file not found"
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise HttpError(
                HTTPStatus.INTERNAL_SERVER_ERROR, "read_error", str(exc)
            ) from exc
        # Frames and snapshots are immutable once written; caching lets the
        # replay viewer preload a frame and swap it without a black gap.
        self._send(
            HTTPStatus.OK,
            data,
            "image/png",
            cache_control="public, max-age=31536000, immutable",
        )

    # ---- responses -----------------------------------------------------

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_html(self, status: int, text: str) -> None:
        self._send(
            status, text.encode("utf-8"), "text/html; charset=utf-8"
        )


def create_server(
    *,
    sessions_root: str | Path | None = None,
    scenarios_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    runtime_factory: Callable[[], Runtime] | None = None,
    lvgl: str | None = None,
    build: bool = True,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    page_clock: Callable[[], float] | None = None,
) -> _WebServer:
    root = (
        Path(sessions_root).expanduser().resolve()
        if sessions_root is not None
        else paths.sessions_root_from_env()
    )
    app = WebApp(
        root,
        runtime_factory=runtime_factory,
        lvgl=lvgl,
        build=build,
        scenarios_dir=scenarios_dir,
        repo_root=repo_root,
        page_clock=page_clock,
    )
    server = _WebServer((host, int(port)), _WebHandler)
    server.app = app
    return server


def serve(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    sessions_root: str | Path | None = None,
    scenarios_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    runtime_factory: Callable[[], Runtime] | None = None,
    lvgl: str | None = None,
    build: bool = True,
    open_browser: bool = False,
    exit_on_close: bool = False,
    app: str | None = None,
    manage: bool = False,
) -> None:
    server = create_server(
        sessions_root=sessions_root,
        scenarios_dir=scenarios_dir,
        repo_root=repo_root,
        runtime_factory=runtime_factory,
        lvgl=lvgl,
        build=build,
        host=host,
        port=port,
    )
    bound_host, bound_port = server.server_address[:2]
    url = page_url(bound_host, bound_port)
    params: list[tuple[str, str]] = []
    if app:
        params.append(("app", app))
    if manage:
        params.append(("manage", "1"))
    viewer_url = url + ("?" + urlencode(params) if params else "")
    print(f"[web] serving {viewer_url}", flush=True)
    if open_browser:
        try:
            webbrowser.open(viewer_url)
        except Exception:  # noqa: BLE001 - a missing browser must not stop us
            pass
    watch_stop = threading.Event()
    if exit_on_close:
        def watch_pages() -> None:
            while not watch_stop.wait(0.2):
                if server.app.should_exit_on_close():
                    server.shutdown()
                    return

        threading.Thread(
            target=watch_pages, name="web-exit-watch", daemon=True
        ).start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        watch_stop.set()
        server.app.shutdown()
        server.server_close()


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "HttpError",
    "WebApp",
    "create_server",
    "serve",
]
