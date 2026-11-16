"""The ``lvgl-verify-loop-whiteboards-v1`` read/write transaction.

A whiteboard explains what a note expects. Its scope is ``global``, a single
``frame`` or a ``range`` of frames. The PNG is the human drawing; ``text`` and
``labels`` are the contract an AI agent reads, so a whiteboard without either
is rejected.

``save_whiteboard`` is the only write path: it validates the payload, writes
the image under a content-addressed name, then atomically replaces
``whiteboards.json``. A failed document write removes the new image.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
import threading
from typing import Any

from control import session_schema
from control.documents import DocumentError, image_references
from control.recording import Recording

WHITEBOARDS_FILE = session_schema.WHITEBOARDS_FILE
WHITEBOARDS_DIR = session_schema.WHITEBOARDS_DIR
WHITEBOARDS_SCHEMA = session_schema.WHITEBOARDS_SCHEMA
SCOPE_KINDS = ("global", "frame", "range")
ITEM_FIELDS = (
    "id",
    "scope",
    "text",
    "labels",
    "image",
    "objects",
    "confirmed",
)
SCOPE_FIELDS = {
    "global": ("kind",),
    "frame": ("kind", "frame_no"),
    "range": ("kind", "frame_start", "frame_end"),
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA_URL_PREFIX = "data:image/png;base64,"

MAX_TEXT_LENGTH = 4000
MAX_LABELS = 64
MAX_LABEL_LENGTH = 200
MAX_OBJECTS_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096


class WhiteboardError(ValueError):
    code = "invalid_whiteboard"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class WhiteboardNotFound(WhiteboardError):
    pass

    code = "unknown_whiteboard"


def empty_document() -> dict[str, Any]:
    return {"schema": session_schema.WHITEBOARDS_SCHEMA, "whiteboards": []}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_int(value: Any, name: str, minimum: int) -> int:
    if not _is_int(value) or value < minimum:
        raise WhiteboardError(f"{name} must be an integer >= {minimum}")
    return value


def _validate_scope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WhiteboardError("scope must be an object")
    kind = value.get("kind")
    if kind not in SCOPE_KINDS:
        raise WhiteboardError(
            "scope.kind must be one of " + ", ".join(SCOPE_KINDS)
        )
    allowed = SCOPE_FIELDS[kind]
    missing = [field for field in allowed if field not in value]
    unexpected = sorted(set(value) - set(allowed))
    if missing:
        raise WhiteboardError(f"scope is missing {', '.join(missing)}")
    if unexpected:
        raise WhiteboardError(
            f"scope has unknown fields: {', '.join(unexpected)}"
        )
    result = {"kind": kind}
    if kind == "frame":
        result["frame_no"] = _require_int(
            value["frame_no"], "scope.frame_no", 1
        )
    elif kind == "range":
        start = _require_int(value["frame_start"], "scope.frame_start", 1)
        end = _require_int(value["frame_end"], "scope.frame_end", 1)
        if start > end:
            raise WhiteboardError(
                "scope.frame_start must not exceed frame_end"
            )
        result["frame_start"] = start
        result["frame_end"] = end
    return result


def _validate_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise WhiteboardError("labels must be a list")
    if len(value) > MAX_LABELS:
        raise WhiteboardError(f"labels must have at most {MAX_LABELS} entries")
    labels = []
    for position, label in enumerate(value):
        if not isinstance(label, str):
            raise WhiteboardError(f"labels[{position}] must be a string")
        if len(label) > MAX_LABEL_LENGTH:
            raise WhiteboardError(
                f"labels[{position}] must be at most {MAX_LABEL_LENGTH} characters"
            )
        if label.strip():
            labels.append(label)
    return labels


def _decode_png(value: Any) -> bytes:
    if not isinstance(value, str) or not value.startswith(DATA_URL_PREFIX):
        raise WhiteboardError("image must be a data:image/png;base64 URL")
    encoded = value[len(DATA_URL_PREFIX) :]
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WhiteboardError("image is not valid base64") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise WhiteboardError(f"image must be at most {MAX_IMAGE_BYTES} bytes")
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24:
        raise WhiteboardError("image is not a PNG")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if (
        width < 1
        or height < 1
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
    ):
        raise WhiteboardError(
            f"image must be at most {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
        )
    return data


def validate_whiteboard(payload: Any) -> tuple[dict[str, Any], bytes]:
    if not isinstance(payload, dict):
        raise WhiteboardError("whiteboard must be an object")
    unknown = sorted(set(payload) - set(ITEM_FIELDS))
    if unknown:
        raise WhiteboardError(
            f"whiteboard has unknown fields: {', '.join(unknown)}"
        )

    item_id = payload.get("id")
    if item_id is None:
        item_id = f"wb-{secrets.token_hex(4)}"
    elif not isinstance(item_id, str) or not ID_RE.fullmatch(item_id):
        raise WhiteboardError("id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")

    scope = _validate_scope(payload.get("scope"))
    text_value = payload.get("text", "")
    if not isinstance(text_value, str):
        raise WhiteboardError("text must be a string")
    if len(text_value) > MAX_TEXT_LENGTH:
        raise WhiteboardError(
            f"text must be at most {MAX_TEXT_LENGTH} characters"
        )
    labels = _validate_labels(payload.get("labels", []))

    objects = payload.get("objects")
    if objects is None:
        objects = {}
    if not isinstance(objects, dict):
        raise WhiteboardError("objects must be an object")
    try:
        encoded = json.dumps(objects, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WhiteboardError("objects is not serializable") from exc
    if len(encoded) > MAX_OBJECTS_BYTES:
        raise WhiteboardError(
            f"objects must be at most {MAX_OBJECTS_BYTES} bytes"
        )

    if not text_value.strip() and not labels:
        raise WhiteboardError(
            "a whiteboard needs text or labels: the drawing alone is not readable"
        )

    confirmed = payload.get("confirmed", False)
    if not isinstance(confirmed, bool):
        raise WhiteboardError("confirmed must be a boolean")

    image = _decode_png(payload.get("image"))
    item = {
        "id": item_id,
        "scope": scope,
        "text": text_value,
        "labels": labels,
        "objects": objects,
        "confirmed": confirmed,
    }
    return item, image


def _read_document(recording: Recording) -> dict[str, Any]:
    try:
        return recording.whiteboards
    except DocumentError as exc:
        raise WhiteboardError(str(exc), code="whiteboards_unreadable") from exc


def read_whiteboards(recording: Recording) -> dict[str, Any]:
    return _read_document(recording)


_WRITE_LOCK = threading.Lock()


def _image_name(item_id: str, data: bytes) -> str:
    stem = (
        re.sub(r"[^A-Za-z0-9._-]+", "_", item_id).strip("._-") or "whiteboard"
    )
    digest = hashlib.sha1(data).hexdigest()[:8]
    return f"{stem}-{digest}.png"


def _prune_images(store: Any, document: dict[str, Any]) -> None:
    store.remove_unreferenced(
        session_schema.WHITEBOARDS_DIR,
        image_references(document, "whiteboards"),
    )


def save_whiteboard(
    recording: Recording, payload: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    with _WRITE_LOCK:
        store = recording.whiteboards_store
        try:
            with store.transaction() as transaction:
                document = _read_document(recording)
                item, image = validate_whiteboard(payload)
                filename = _image_name(item["id"], image)
                relative = f"{session_schema.WHITEBOARDS_DIR}/{filename}"
                transaction.write_image(relative, image)
                saved = dict(item)
                saved["image"] = relative
                items = [
                    dict(existing) for existing in document["whiteboards"]
                ]
                replaced = False
                for position, existing in enumerate(items):
                    if existing.get("id") == saved["id"]:
                        items[position] = saved
                        replaced = True
                        break
                if not replaced:
                    items.append(saved)
                document = {
                    "schema": session_schema.WHITEBOARDS_SCHEMA,
                    "whiteboards": items,
                }
                store.write(document)
        except WhiteboardError:
            raise
        except DocumentError as exc:
            raise WhiteboardError(
                str(exc), code="whiteboards_write_error"
            ) from exc
        except OSError as exc:
            raise WhiteboardError(
                str(exc), code="whiteboards_write_error"
            ) from exc
        _prune_images(store, document)
        return document, saved


def delete_whiteboard(
    recording: Recording, whiteboard_id: str
) -> dict[str, Any]:
    if not isinstance(whiteboard_id, str) or not whiteboard_id:
        raise WhiteboardNotFound("whiteboard id is required")
    with _WRITE_LOCK:
        store = recording.whiteboards_store
        document = _read_document(recording)
        remaining: list[dict[str, Any]] = []
        found = False
        for item in document["whiteboards"]:
            if item.get("id") == whiteboard_id:
                found = True
                continue
            remaining.append(item)
        if not found:
            raise WhiteboardNotFound(f"unknown whiteboard id: {whiteboard_id}")
        document = {
            "schema": session_schema.WHITEBOARDS_SCHEMA,
            "whiteboards": remaining,
        }
        try:
            store.write(document)
        except DocumentError as exc:
            raise WhiteboardError(
                str(exc), code="whiteboards_write_error"
            ) from exc
        _prune_images(store, document)
    return document
