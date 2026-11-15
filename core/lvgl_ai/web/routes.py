"""HTTP route table for the web adapter.

The table lives here so ``webapp.py`` stays a domain adapter.  ``_WebHandler``
delegates each request to :func:`route`; these literals are the single source
checked by ``test_docs_single_source``.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from .live_session import validate_live_kind
from .webapp import (
    ANNOTATION_BODY_BYTES,
    PAGE_ID_RE,
    WHITEBOARD_BODY_BYTES,
    HttpError,
    _input_app,
)


def route(
    web: Any, method: str, path: str, query: dict[str, list[str]]
) -> None:
    if path == "/":
        web._require(method, ("GET",))
        session_id = (query.get("session") or [None])[0]
        app = _input_app((query.get("app") or [None])[0])
        status, html_text = web.app.render_page(session_id, app)
        return web._send_html(status, html_text)

    if path == "/api/sessions":
        web._require(method, ("GET",))
        return web._send_json(HTTPStatus.OK, {"sessions": web.app.sessions()})

    if path == "/static/fabric.min.js":
        web._require(method, ("GET",))
        return web._serve_static("fabric.min.js")

    if path == "/api/live":
        web._require(method, ("GET",))
        return web._send_json(HTTPStatus.OK, web.app.live.status())

    if path == "/api/live/stream":
        web._require(method, ("GET",))
        return web._serve_live_stream()

    if path == "/api/live/start":
        web._require(method, ("POST",))
        return _start_live(web, query)

    if path == "/api/live/stop":
        web._require(method, ("POST",))
        return web._send_json(HTTPStatus.OK, web.app.live.stop())

    if path == "/api/live/pointer":
        web._require(method, ("POST",))
        return web._send_json(
            HTTPStatus.OK,
            web.app.live.pointer(web._read_json_body()),
        )

    if path == "/api/live/key":
        web._require(method, ("POST",))
        return web._send_json(
            HTTPStatus.OK,
            web.app.live.key(web._read_json_body()),
        )

    if path == "/api/apps":
        web._require(method, ("GET",))
        return web._send_json(HTTPStatus.OK, web.app.apps_payload())

    if path == "/api/apps/tree":
        web._require(method, ("GET",))
        name = (query.get("name") or [None])[0]
        return web._send_json(HTTPStatus.OK, web.app.app_tree_payload(name))

    if path == "/api/apps/create":
        web._require(method, ("POST",))
        web._require_app_mutation_headers()
        body = web._read_json_body()
        return web._send_json(
            HTTPStatus.CREATED, web.app.create_app(body.get("name"))
        )

    if path == "/api/apps/delete":
        web._require(method, ("POST",))
        web._require_app_mutation_headers()
        body = web._read_json_body()
        return web._send_json(
            HTTPStatus.OK, web.app.delete_app(body.get("name"))
        )

    if path == "/api/apps/trash/restore":
        web._require(method, ("POST",))
        web._require_app_mutation_headers()
        body = web._read_json_body()
        return web._send_json(
            HTTPStatus.OK, web.app.restore_app(body.get("trash_id"))
        )

    if path == "/api/apps/trash/delete":
        web._require(method, ("POST",))
        web._require_app_mutation_headers()
        body = web._read_json_body()
        return web._send_json(
            HTTPStatus.OK,
            web.app.purge_app(
                body.get("trash_id"), confirm=body.get("confirm") is True
            ),
        )

    if path in ("/api/page/open", "/api/page/close"):
        web._require(method, ("POST",))
        body = web._read_json_body()
        page_id = body.get("id")
        if not isinstance(page_id, str) or not PAGE_ID_RE.fullmatch(page_id):
            raise HttpError(
                HTTPStatus.BAD_REQUEST,
                "invalid_page",
                "id must match [A-Za-z0-9_-]{1,64}",
            )
        if path.endswith("open"):
            return web._send_json(HTTPStatus.OK, web.app.page_open(page_id))
        return web._send_json(HTTPStatus.OK, web.app.page_close(page_id))

    if path.startswith("/api/sessions/"):
        parts = path.strip("/").split("/")
        if len(parts) == 3:
            web._require(method, ("GET",))
            return web._send_json(
                HTTPStatus.OK, web.app.session_payload(parts[2])
            )
        if len(parts) == 4:
            session_id, sub = parts[2], parts[3]
            if sub == "annotations":
                if method == "GET":
                    return web._send_json(
                        HTTPStatus.OK,
                        web.app.annotations_payload(session_id),
                    )
                if method == "POST":
                    body = web._read_json_body(ANNOTATION_BODY_BYTES)
                    status, payload = web.app.add_annotation(session_id, body)
                    return web._send_json(status, payload)
                raise HttpError(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    "method_not_allowed",
                    f"{method} is not allowed here",
                )
            if sub == "whiteboards":
                if method == "GET":
                    return web._send_json(
                        HTTPStatus.OK,
                        web.app.whiteboards_payload(session_id),
                    )
                if method == "POST":
                    body = web._read_json_body(WHITEBOARD_BODY_BYTES)
                    status, payload = web.app.save_whiteboard(session_id, body)
                    return web._send_json(status, payload)
                raise HttpError(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    "method_not_allowed",
                    f"{method} is not allowed here",
                )
            handlers = {
                "timeline": web.app.timeline_payload,
                "diffs": web.app.diffs_payload,
                "log": web.app.log_payload,
            }
            handler = handlers.get(sub)
            if handler is None:
                raise HttpError(
                    HTTPStatus.NOT_FOUND,
                    "not_found",
                    f"unknown path: {path}",
                )
            web._require(method, ("GET",))
            return web._send_json(HTTPStatus.OK, handler(session_id))
        if len(parts) == 5:
            session_id, sub = parts[2], parts[3]
            if sub == "annotations":
                web._require(method, ("DELETE",))
                status, payload = web.app.delete_annotation(
                    session_id, unquote(parts[4])
                )
                return web._send_json(status, payload)
            if sub == "whiteboards":
                web._require(method, ("DELETE",))
                status, payload = web.app.delete_whiteboard(
                    session_id, unquote(parts[4])
                )
                return web._send_json(status, payload)
            raise HttpError(
                HTTPStatus.NOT_FOUND, "not_found", f"unknown path: {path}"
            )
        raise HttpError(
            HTTPStatus.NOT_FOUND, "not_found", f"unknown path: {path}"
        )

    if (
        path.startswith("/frames/")
        or path.startswith("/snapshots/")
        or path.startswith("/regions/")
        or path.startswith("/whiteboards/")
    ):
        web._require(method, ("GET",))
        kind = path.strip("/").split("/")[0]
        parts = path.strip("/").split("/")
        if len(parts) != 3:
            raise HttpError(
                HTTPStatus.NOT_FOUND, "not_found", f"unknown path: {path}"
            )
        return web._serve_png(kind, parts[1], parts[2])

    raise HttpError(HTTPStatus.NOT_FOUND, "not_found", f"unknown path: {path}")


def _start_live(web: Any, query: dict[str, list[str]]) -> None:
    mode = (query.get("mode") or ["record"])[0]
    app = (query.get("app") or [None])[0]
    validate_live_kind(mode)
    app = _input_app(app)
    display = web.app._scenario_display(app)
    return web._send_json(
        HTTPStatus.OK, web.app.live.start(mode, app, display=display)
    )
