"""The ``lvgl-ai-annotations-v1`` write transaction.

``write_note(recording, payload)`` is the only write path: it holds the
annotation lock, reads and validates the existing document, validates and
appends the payload, then atomically replaces ``annotations.json`` through the
``Recording`` setter. Regions keep their boxes; the AI opens the frame PNG and
crops the box itself. Each anchor may also carry the composed frame + drawing
PNG the viewer uploaded, so a human sees the annotation in the saved note and
the AI can compare it with the original frame.

Errors carry no HTTP status. ``AnnotationError.code`` and
:class:`AnnotationConflict` are the whole interface the HTTP adapter maps.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from typing import Any

from ..control import session_schema
from ..control.documents import (
    DocumentError,
    DocumentTransaction,
    image_references,
)
from ..control.recording import ANNOTATIONS_SCHEMA, Recording
from ..png_codec import PngError, Region, crop_png
from .png_data import DATA_URL_PREFIX, PngDataError, decode_png_data_url

NOTE_FIELDS = ("id", "frame_no", "t_ms", "regions", "tags", "text")
NOTE_OPTIONAL_FIELDS = ("frame_start", "frame_end", "anchors", "kind", "hints")
ANCHOR_FIELDS = ("frame_no", "t_ms", "regions", "annotated")
DOCUMENT_FIELDS = ("schema", "notes")
REGION_FIELDS = ("x", "y", "w", "h", "image", "annotated")
IMAGE_PATH_RE = re.compile(
    r"^"
    + session_schema.REGIONS_DIR
    + r"/[A-Za-z0-9][A-Za-z0-9._-]*\.png$"
)

MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 4000
MAX_TAGS = 32
MAX_TAG_LENGTH = 64
MAX_REGIONS = 64
MAX_ANCHORS = 32
MAX_TOTAL_REGIONS = 128
MAX_KIND_LENGTH = 32
MAX_HINTS_BYTES = 8192
MAX_IMAGE_PATH_LENGTH = 512


class AnnotationError(ValueError):
    """The annotation contract rejected a read, payload or write.

    ``code`` names the failure so HTTP can map it to a status without
    inspecting the exception type hierarchy.
    """

    code = "invalid_annotation"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class AnnotationConflict(AnnotationError):
    """The note id already exists in the document."""

    code = "duplicate_annotation_id"


class AnnotationNotFound(AnnotationError):
    """The note id is not in the document."""

    code = "unknown_annotation"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_int(value: Any, name: str, minimum: int) -> int:
    if not _is_int(value) or value < minimum:
        raise AnnotationError(f"{name} must be an integer >= {minimum}")
    return value


def _require_string(
    value: Any, name: str, *, maximum: int, allow_empty: bool = False
) -> str:
    if not isinstance(value, str):
        raise AnnotationError(f"{name} must be a string")
    if not allow_empty and not value:
        raise AnnotationError(f"{name} must not be empty")
    if len(value) > maximum:
        raise AnnotationError(f"{name} must be at most {maximum} characters")
    return value


def _validate_region(
    value: Any, name: str, *, allow_image: bool = True
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnnotationError(f"{name} must be an object")
    unknown = sorted(set(value) - set(REGION_FIELDS))
    if unknown:
        raise AnnotationError(f"{name} has unknown fields: {', '.join(unknown)}")
    if "image" in value and not allow_image:
        raise AnnotationError(f"{name}.image is managed by the server")
    missing = [
        field for field in ("x", "y", "w", "h") if field not in value
    ]
    if missing:
        raise AnnotationError(f"{name} is missing {', '.join(missing)}")
    region: dict[str, Any] = {
        "x": _require_int(value["x"], f"{name}.x", 0),
        "y": _require_int(value["y"], f"{name}.y", 0),
        "w": _require_int(value["w"], f"{name}.w", 1),
        "h": _require_int(value["h"], f"{name}.h", 1),
    }
    for field in ("image", "annotated"):
        if field not in value:
            continue
        if not allow_image:
            raise AnnotationError(
                f"{name}.{field} is managed by the server"
            )
        path = _require_string(
            value[field], f"{name}.{field}",
            maximum=MAX_IMAGE_PATH_LENGTH,
        )
        if not IMAGE_PATH_RE.fullmatch(path):
            raise AnnotationError(
                f"{name}.{field} must look like regions/<name>.png"
            )
        region[field] = path
    return region


def _validate_regions(
    value: Any, name: str, *, allow_image: bool
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AnnotationError(f"{name} must be a list")
    if len(value) > MAX_REGIONS:
        raise AnnotationError(
            f"{name} must have at most {MAX_REGIONS} entries"
        )
    return [
        _validate_region(
            region, f"{name}[{position}]", allow_image=allow_image
        )
        for position, region in enumerate(value)
    ]


def _validate_anchor(
    value: Any,
    name: str,
    *,
    allow_image: bool,
    frame_start: int,
    frame_end: int,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnnotationError(f"{name} must be an object")
    unknown = sorted(set(value) - set(ANCHOR_FIELDS))
    if unknown:
        raise AnnotationError(f"{name} has unknown fields: {', '.join(unknown)}")
    if "frame_no" not in value:
        raise AnnotationError(f"{name}.frame_no is required")
    frame_no = _require_int(value["frame_no"], f"{name}.frame_no", 1)
    if not (frame_start <= frame_no <= frame_end):
        raise AnnotationError(
            f"{name}.frame_no must be within {frame_start}..{frame_end}"
        )
    if "t_ms" not in value:
        raise AnnotationError(f"{name}.t_ms is required")
    t_ms = _require_int(value["t_ms"], f"{name}.t_ms", 0)
    regions = _validate_regions(
        value.get("regions", []), f"{name}.regions", allow_image=allow_image
    )
    result: dict[str, Any] = {
        "frame_no": frame_no, "t_ms": t_ms, "regions": regions
    }
    if "annotated" in value:
        annotated = value["annotated"]
        if allow_image:
            if (
                not isinstance(annotated, str)
                or not IMAGE_PATH_RE.fullmatch(annotated)
            ):
                raise AnnotationError(
                    f"{name}.annotated must look like regions/<name>.png"
                )
        else:
            try:
                decode_png_data_url(annotated)
            except PngDataError as exc:
                raise AnnotationError(
                    f"{name}.annotated: {exc}"
                ) from exc
        result["annotated"] = annotated
    return result


def _validate_hints(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnnotationError(f"{name} must be an object")
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > MAX_TAG_LENGTH:
            raise AnnotationError(f"{name} keys must be short strings")
        if item is None or isinstance(item, (bool, int, float, str)):
            continue
        raise AnnotationError(f"{name}.{key} must be a scalar")
    try:
        encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AnnotationError(f"{name} is not serializable") from exc
    if len(encoded) > MAX_HINTS_BYTES:
        raise AnnotationError(f"{name} must be at most {MAX_HINTS_BYTES} bytes")
    return dict(value)


def validate_note(
    note: Any,
    *,
    index: int | None = None,
    require_id: bool = False,
    allow_images: bool = True,
) -> dict[str, Any]:
    """Validate one note and return it with the stable fields in schema order.

    A note is either a single-frame note (``frame_no`` + ``regions``) or a
    time-range note (``frame_start``..``frame_end`` + sparse ``anchors``).
    Range fields are optional on the single-frame form, so documents written
    before ranges existed keep validating unchanged.
    """
    where = "note" if index is None else f"notes[{index}]"
    if not isinstance(note, dict):
        raise AnnotationError(f"{where} must be an object")
    unknown = sorted(
        set(note) - set(NOTE_FIELDS) - set(NOTE_OPTIONAL_FIELDS)
    )
    if unknown:
        raise AnnotationError(f"{where} has unknown fields: {', '.join(unknown)}")

    note_id = note.get("id")
    if note_id is None:
        if require_id:
            raise AnnotationError(f"{where}.id is required")
        note_id = None
    else:
        note_id = _require_string(
            note_id, f"{where}.id", maximum=MAX_ID_LENGTH
        )

    if "frame_no" not in note:
        raise AnnotationError(f"{where}.frame_no is required")
    frame_no = _require_int(note["frame_no"], f"{where}.frame_no", 1)
    if "t_ms" not in note:
        raise AnnotationError(f"{where}.t_ms is required")
    t_ms = _require_int(note["t_ms"], f"{where}.t_ms", 0)

    frame_start = (
        _require_int(note["frame_start"], f"{where}.frame_start", 1)
        if "frame_start" in note
        else None
    )
    frame_end = (
        _require_int(note["frame_end"], f"{where}.frame_end", 1)
        if "frame_end" in note
        else None
    )
    if (frame_start is None) != (frame_end is None):
        raise AnnotationError(
            f"{where}.frame_start and frame_end must be provided together"
        )
    if frame_start is not None and frame_start > frame_end:
        raise AnnotationError(f"{where}.frame_start must not exceed frame_end")

    has_anchors = "anchors" in note
    if has_anchors:
        anchors_value = note["anchors"]
        if not isinstance(anchors_value, list):
            raise AnnotationError(f"{where}.anchors must be a list")
        if len(anchors_value) > MAX_ANCHORS:
            raise AnnotationError(
                f"{where}.anchors must have at most {MAX_ANCHORS} entries"
            )
        if anchors_value:
            first = anchors_value[0]
            if not isinstance(first, dict):
                raise AnnotationError(f"{where}.anchors[0] must be an object")
            if first.get("frame_no") != frame_no:
                raise AnnotationError(
                    f"{where}.frame_no must match anchors[0].frame_no"
                )
            if first.get("t_ms") != t_ms:
                raise AnnotationError(
                    f"{where}.t_ms must match anchors[0].t_ms"
                )
        if frame_start is None:
            if anchors_value:
                frames = [
                    anchor.get("frame_no")
                    for anchor in anchors_value
                    if isinstance(anchor, dict)
                ]
                if not all(_is_int(value) for value in frames):
                    raise AnnotationError(
                        f"{where}.anchors[].frame_no is required"
                    )
                frame_start, frame_end = min(frames), max(frames)
            else:
                frame_start = frame_end = frame_no
        assert frame_start is not None and frame_end is not None
        anchors = [
            _validate_anchor(
                anchor,
                f"{where}.anchors[{position}]",
                allow_image=allow_images,
                frame_start=frame_start,
                frame_end=frame_end,
            )
            for position, anchor in enumerate(anchors_value)
        ]
        total_regions = sum(len(anchor["regions"]) for anchor in anchors)
        if total_regions > MAX_TOTAL_REGIONS:
            raise AnnotationError(
                f"{where} has at most {MAX_TOTAL_REGIONS} regions across anchors"
            )
        regions = _validate_regions(
            note.get("regions", []), f"{where}.regions", allow_image=allow_images
        )
        if not regions and anchors:
            regions = [dict(region) for region in anchors[0]["regions"]]
    else:
        anchors = None
        regions = _validate_regions(
            note.get("regions"), f"{where}.regions", allow_image=allow_images
        )
        if frame_start is not None and not (frame_start <= frame_no <= frame_end):
            raise AnnotationError(
                f"{where}.frame_no must be within {frame_start}..{frame_end}"
            )

    tags_value = note.get("tags")
    if not isinstance(tags_value, list):
        raise AnnotationError(f"{where}.tags must be a list")
    if len(tags_value) > MAX_TAGS:
        raise AnnotationError(f"{where}.tags must have at most {MAX_TAGS} entries")
    tags = [
        _require_string(
            tag, f"{where}.tags[{position}]", maximum=MAX_TAG_LENGTH
        )
        for position, tag in enumerate(tags_value)
    ]

    if "text" not in note:
        raise AnnotationError(f"{where}.text is required")
    text = _require_string(
        note["text"], f"{where}.text", maximum=MAX_TEXT_LENGTH, allow_empty=True
    )

    result: dict[str, Any] = {
        "id": note_id,
        "frame_no": frame_no,
        "t_ms": t_ms,
        "regions": regions,
        "tags": tags,
        "text": text,
    }
    if has_anchors:
        result["frame_start"] = frame_start
        result["frame_end"] = frame_end
        result["anchors"] = anchors
    elif frame_start is not None:
        result["frame_start"] = frame_start
        result["frame_end"] = frame_end
    if "kind" in note:
        result["kind"] = _require_string(
            note["kind"], f"{where}.kind", maximum=MAX_KIND_LENGTH
        )
    if "hints" in note:
        result["hints"] = _validate_hints(note["hints"], f"{where}.hints")
    return result


def validate_document(document: Any) -> dict[str, Any]:
    """Validate a full ``lvgl-ai-annotations-v1`` document."""
    if not isinstance(document, dict):
        raise AnnotationError("annotations document must be an object")
    unknown = sorted(set(document) - set(DOCUMENT_FIELDS))
    if unknown:
        raise AnnotationError(
            f"annotations document has unknown fields: {', '.join(unknown)}"
        )
    schema = document.get("schema", ANNOTATIONS_SCHEMA)
    if schema != ANNOTATIONS_SCHEMA:
        raise AnnotationError(
            f"schema must be {ANNOTATIONS_SCHEMA!r}, got {schema!r}"
        )
    notes_value = document.get("notes")
    if not isinstance(notes_value, list):
        raise AnnotationError("notes must be a list")
    notes = [
        validate_note(note, index=index, require_id=True)
        for index, note in enumerate(notes_value)
    ]
    ids = [note["id"] for note in notes]
    duplicates = sorted({note_id for note_id in ids if ids.count(note_id) > 1})
    if duplicates:
        raise AnnotationError(f"duplicate note ids: {', '.join(duplicates)}")
    return {"schema": ANNOTATIONS_SCHEMA, "notes": notes}


def new_note_id(existing_ids: set[str]) -> str:
    for _ in range(100):
        candidate = f"note-{secrets.token_hex(4)}"
        if candidate not in existing_ids:
            return candidate
    raise AnnotationError("could not allocate a unique note id")


def append_note(
    document: dict[str, Any], note: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append one validated note to a validated document."""
    notes = [dict(existing) for existing in document["notes"]]
    ids = {existing["id"] for existing in notes}
    saved = dict(note)
    if saved["id"] is None:
        saved["id"] = new_note_id(ids)
    elif saved["id"] in ids:
        raise AnnotationConflict(f"duplicate note id: {saved['id']}")
    notes.append(saved)
    return {"schema": ANNOTATIONS_SCHEMA, "notes": notes}, saved


# One lock for the whole transaction: two concurrent posts must never append
# from the same document snapshot or interleave crop files for one note.
_WRITE_LOCK = threading.Lock()


def _read_existing(recording: Recording) -> dict[str, Any]:
    """Read the current document and validate every note in it.

    A file the ``Recording`` cannot parse is unreadable evidence (the old 409
    path); a parsed document with bad note fields is an invalid payload (the
    old 400 path).
    """
    try:
        document = recording.annotations
    except ValueError as exc:
        raise AnnotationError(str(exc), code="annotations_unreadable") from exc
    return validate_document(document)


def write_note(
    recording: Recording, payload: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append one note as a single transaction and return ``(document, note)``.

    The steps run under one lock and in this order: read and validate the
    existing document, validate the payload, append the note, validate the
    resulting document, and atomically replace ``annotations.json``.

    Expected failures raise :class:`AnnotationError` with a ``code``. A plain
    ``OSError`` while reading evidence keeps the historical generic 500
    (``internal_error``) response.
    """
    with _WRITE_LOCK:
        store = recording.annotations_store
        try:
            with store.transaction() as transaction:
                document = _read_existing(recording)
                note = validate_note(payload, allow_images=False)
                document, saved = append_note(document, note)
                _save_annotated_images(transaction, saved)
                _save_region_crops(transaction, recording, saved)
                document = validate_document(document)
                recording.annotations = document
        except AnnotationError:
            raise
        except DocumentError as exc:
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc
        except OSError as exc:
            raise AnnotationError(
                str(exc), code="internal_error"
            ) from exc
        _prune_images(store, document)
        return document, saved


def _safe_note_stem(note_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", note_id).strip("._-")
    if not safe:
        safe = "note"
    if safe != note_id or len(safe) > 64:
        digest = hashlib.sha1(note_id.encode("utf-8")).hexdigest()[:8]
        safe = f"{safe[:48]}-{digest}"
    if not safe[0].isalnum():
        safe = f"n-{safe}"
    return safe


def _prune_images(store: Any, document: dict[str, Any]) -> None:
    """Remove region crops no note references any more."""
    store.remove_unreferenced(
        session_schema.REGIONS_DIR, image_references(document, "notes")
    )


def _save_annotated_images(
    transaction: DocumentTransaction, note: dict[str, Any]
) -> None:
    anchors = note.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        return
    stem = _safe_note_stem(str(note.get("id") or "note"))
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            continue
        value = anchor.get("annotated")
        if not isinstance(value, str) or not value.startswith(DATA_URL_PREFIX):
            continue
        try:
            data = decode_png_data_url(value)
        except PngDataError as exc:
            raise AnnotationError(
                f"anchors[{index}].annotated: {exc}"
            ) from exc
        relative = (
            f"{session_schema.REGIONS_DIR}/"
            f"{stem}-a{index}-annotated.png"
        )
        transaction.write_image(relative, data)
        anchor["annotated"] = relative


def _frame_bytes(recording: Recording, frame_no: Any) -> bytes | None:
    if isinstance(frame_no, bool) or not isinstance(frame_no, int):
        return None
    for path in recording.frames:
        if path.stem.isdigit() and int(path.stem) == frame_no:
            try:
                return path.read_bytes()
            except OSError:
                return None
    return None


def _crop_png_bytes(
    data: bytes, region: dict[str, Any], name: str
) -> bytes:
    try:
        cropped, _clipped, _image = crop_png(
            data,
            Region(
                int(region["x"]),
                int(region["y"]),
                int(region["w"]),
                int(region["h"]),
            ),
        )
    except (PngError, KeyError, TypeError, ValueError) as exc:
        raise AnnotationError(
            f"{name} cannot be cropped: {exc}", code="region_image_error"
        ) from exc
    return cropped


def _save_region_crops(
    transaction: DocumentTransaction,
    recording: Recording,
    note: dict[str, Any],
) -> None:
    stem = _safe_note_stem(str(note.get("id") or "note"))
    anchors = note.get("anchors")
    if isinstance(anchors, list) and anchors:
        for ai, anchor in enumerate(anchors):
            if not isinstance(anchor, dict):
                continue
            frame_data = _frame_bytes(recording, anchor.get("frame_no"))
            annotated_path = anchor.get("annotated")
            annotated_data = None
            if (
                frame_data is None
                and not isinstance(annotated_path, str)
            ):
                continue
            if isinstance(annotated_path, str):
                annotated_data = transaction.read_image(annotated_path)
            if frame_data is None and annotated_data is None:
                continue
            for ri, region in enumerate(anchor.get("regions") or []):
                if not isinstance(region, dict):
                    continue
                if frame_data is not None:
                    relative = (
                        f"{session_schema.REGIONS_DIR}/"
                        f"{stem}-a{ai}-r{ri}.png"
                    )
                    transaction.write_image(
                        relative,
                        _crop_png_bytes(
                            frame_data, region,
                            f"anchors[{ai}].regions[{ri}]",
                        ),
                    )
                    region["image"] = relative
                if annotated_data is not None:
                    relative = (
                        f"{session_schema.REGIONS_DIR}/"
                        f"{stem}-a{ai}-r{ri}-annotated.png"
                    )
                    transaction.write_image(
                        relative,
                        _crop_png_bytes(
                            annotated_data, region,
                            f"anchors[{ai}].regions[{ri}].annotated",
                        ),
                    )
                    region["annotated"] = relative
        note["regions"] = [dict(region) for region in anchors[0]["regions"]]
        return

    regions = note.get("regions")
    if not isinstance(regions, list) or not regions:
        return
    frame_data = _frame_bytes(recording, note.get("frame_no"))
    if frame_data is None:
        return
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        relative = f"{session_schema.REGIONS_DIR}/{stem}-{index}.png"
        transaction.write_image(
            relative,
            _crop_png_bytes(frame_data, region, f"regions[{index}]"),
        )
        region["image"] = relative


def delete_note(recording: Recording, note_id: str) -> dict[str, Any]:
    """Remove one note and return the new document.

    Crop files the deleted note referenced are unreferenced after the write,
    so the shared document transaction removes them. A failed unlink never
    blocks the deletion.
    """
    if not isinstance(note_id, str) or not note_id:
        raise AnnotationNotFound("note id is required")
    with _WRITE_LOCK:
        store = recording.annotations_store
        try:
            document = _read_existing(recording)
        except OSError as exc:
            raise AnnotationError(
                str(exc), code="internal_error"
            ) from exc
        remaining: list[dict[str, Any]] = []
        found = False
        for note in document["notes"]:
            if note.get("id") == note_id:
                found = True
                continue
            remaining.append(note)
        if not found:
            raise AnnotationNotFound(f"unknown note id: {note_id}")
        document = {
            "schema": session_schema.ANNOTATIONS_SCHEMA,
            "notes": remaining,
        }
        try:
            recording.annotations = document
        except DocumentError as exc:
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc
        _prune_images(store, document)
    return document
