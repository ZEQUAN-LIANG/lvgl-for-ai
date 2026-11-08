"""The ``lvgl-ai-annotations-v1`` write transaction.

``write_note(recording, payload)`` is the only write path: it holds the
annotation lock, reads and validates the existing document, validates and
appends the payload, crops every region, atomically replaces
``annotations.json`` through the ``Recording`` setter, and removes the crops
created by this call if the document cannot be written. A rejected payload
never reaches the filesystem.

Errors carry no HTTP status. ``AnnotationError.code`` and
:class:`AnnotationConflict` are the whole interface the HTTP adapter maps.
"""

from __future__ import annotations

import re
import secrets
import threading
from typing import Any

from ..control.recording import ANNOTATIONS_SCHEMA, Recording
from .annotation_crops import (
    RegionImageError,
    prepare_region_images,
    rollback_region_crops,
    write_region_crops,
)

NOTE_FIELDS = ("id", "frame_no", "t_ms", "regions", "tags", "text")
DOCUMENT_FIELDS = ("schema", "notes")
REGION_FIELDS = ("x", "y", "w", "h", "image")
IMAGE_PATH_RE = re.compile(r"^regions/[A-Za-z0-9][A-Za-z0-9._-]*\.png$")

MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 4000
MAX_TAGS = 32
MAX_TAG_LENGTH = 64
MAX_REGIONS = 64
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
    if "image" in value:
        image = _require_string(
            value["image"], f"{name}.image",
            maximum=MAX_IMAGE_PATH_LENGTH,
        )
        if not IMAGE_PATH_RE.fullmatch(image):
            raise AnnotationError(
                f"{name}.image must look like regions/<name>.png"
            )
        region["image"] = image
    return region


def validate_note(
    note: Any,
    *,
    index: int | None = None,
    require_id: bool = False,
    allow_images: bool = True,
) -> dict[str, Any]:
    """Validate one note and return it with the six fields in schema order."""
    where = "note" if index is None else f"notes[{index}]"
    if not isinstance(note, dict):
        raise AnnotationError(f"{where} must be an object")
    unknown = sorted(set(note) - set(NOTE_FIELDS))
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

    regions_value = note.get("regions")
    if not isinstance(regions_value, list):
        raise AnnotationError(f"{where}.regions must be a list")
    if len(regions_value) > MAX_REGIONS:
        raise AnnotationError(
            f"{where}.regions must have at most {MAX_REGIONS} entries"
        )
    regions = [
        _validate_region(
            region,
            f"{where}.regions[{position}]",
            allow_image=allow_images,
        )
        for position, region in enumerate(regions_value)
    ]

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

    return {
        "id": note_id,
        "frame_no": frame_no,
        "t_ms": t_ms,
        "regions": regions,
        "tags": tags,
        "text": text,
    }


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
    existing document, validate the payload, append the note, decode every
    crop, validate the resulting document, write the crops, and atomically
    replace ``annotations.json``. If anything fails after the crops are
    written, the transaction is rolled back: new crop files are removed and
    overwritten ones get their previous bytes back.

    Expected failures raise :class:`AnnotationError` with a ``code``. A plain
    ``OSError`` while reading or preparing evidence keeps the historical
    generic 500 (``internal_error``) response.
    """
    with _WRITE_LOCK:
        try:
            document = _read_existing(recording)
            note = validate_note(payload, allow_images=False)
            document, saved = append_note(document, note)
            try:
                saved, prepared = prepare_region_images(recording, saved)
            except RegionImageError as exc:
                raise AnnotationError(
                    str(exc), code="region_image_error"
                ) from exc
            # append_note puts the new note last; swap in the cropped copy.
            document["notes"][-1] = saved
            document = validate_document(document)
            journal = write_region_crops(prepared)
        except OSError as exc:
            raise AnnotationError(
                str(exc), code="internal_error"
            ) from exc

        try:
            recording.annotations = document
        except Exception as exc:
            rollback_region_crops(journal)
            if not isinstance(exc, OSError):
                raise
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc
        return document, saved
