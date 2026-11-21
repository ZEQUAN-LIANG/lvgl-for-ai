from __future__ import annotations

import hashlib
import re
import threading
from typing import Any

from . import session_schema
from .anchors import derive_anchor, resolve_anchor
from .documents import (
    DocumentError,
    DocumentTransaction,
    image_references,
)
from .locks import (
    ANNOTATIONS_LOCK_FILE_NAME,
    ANNOTATIONS_LOCK_TIMEOUT_S,
    FileLock,
)
from .recording import ANNOTATIONS_SCHEMA, Recording
from png_codec import PngError, Region, crop_png
from .png_data import DATA_URL_PREFIX, PngDataError, decode_png_data_url

NOTE_FIELDS = (
    "id",
    "frame_no",
    "t_ms",
    "regions",
    "tags",
    "text",
    "author",
    "source",
    "feedback_anchor",
)
NOTE_OPTIONAL_FIELDS = (
    "frame_start",
    "frame_end",
    "anchors",
    "kind",
    "hints",
    "transcribed_by",
)
ANCHOR_FIELDS = ("frame_no", "t_ms", "regions", "annotated")
DOCUMENT_FIELDS = ("schema", "notes")
REGION_FIELDS = ("x", "y", "w", "h", "image", "annotated")
AUTHORS = ("human",)
SOURCES = ("web", "chat")
TRANSCRIBERS = ("ai",)
IMAGE_PATH_RE = re.compile(
    r"^" + session_schema.REGIONS_DIR + r"/[A-Za-z0-9][A-Za-z0-9._-]*\.png$"
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
MAX_ANCHOR_TEXT_LENGTH = 128


class AnnotationError(ValueError):
    code = "invalid_annotation"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class AnnotationConflict(AnnotationError):
    pass

    code = "duplicate_annotation_id"


class AnnotationNotFound(AnnotationError):
    pass

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
        raise AnnotationError(
            f"{name} has unknown fields: {', '.join(unknown)}"
        )
    if "image" in value and not allow_image:
        raise AnnotationError(f"{name}.image is managed by the server")
    missing = [field for field in ("x", "y", "w", "h") if field not in value]
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
            raise AnnotationError(f"{name}.{field} is managed by the server")
        path = _require_string(
            value[field],
            f"{name}.{field}",
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
        raise AnnotationError(
            f"{name} has unknown fields: {', '.join(unknown)}"
        )
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
        "frame_no": frame_no,
        "t_ms": t_ms,
        "regions": regions,
    }
    if "annotated" in value:
        annotated = value["annotated"]
        if allow_image:
            if not isinstance(annotated, str) or not IMAGE_PATH_RE.fullmatch(
                annotated
            ):
                raise AnnotationError(
                    f"{name}.annotated must look like regions/<name>.png"
                )
        else:
            try:
                decode_png_data_url(annotated)
            except PngDataError as exc:
                raise AnnotationError(f"{name}.annotated: {exc}") from exc
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
    return dict(value)


_ANCHOR_FIELDS = {
    "click": {"kind", "seq_down", "seq_up", "offset_ms"},
    "input": {"kind", "seq", "offset_ms"},
    "mark": {"kind", "id", "offset_ms"},
    "t_ms": {"kind", "t_ms"},
    "step": {"kind", "index"},
}


def _validate_feedback_anchor(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnnotationError(f"{name} must be an object")
    kind = value.get("kind")
    if kind not in _ANCHOR_FIELDS:
        raise AnnotationError(
            f"{name}.kind must be one of {', '.join(_ANCHOR_FIELDS)}"
        )
    unknown = sorted(set(value) - _ANCHOR_FIELDS[kind])
    if unknown:
        raise AnnotationError(
            f"{name} has unknown fields: {', '.join(unknown)}"
        )
    result: dict[str, Any] = {"kind": kind}
    if kind == "click":
        for field in ("seq_down", "seq_up"):
            if field not in value:
                raise AnnotationError(f"{name}.{field} is required")
            result[field] = _require_int(value[field], f"{name}.{field}", 1)
    elif kind == "input":
        if "seq" not in value:
            raise AnnotationError(f"{name}.seq is required")
        result["seq"] = _require_int(value["seq"], f"{name}.seq", 1)
    elif kind == "mark":
        if "id" not in value:
            raise AnnotationError(f"{name}.id is required")
        result["id"] = _require_string(
            value["id"], f"{name}.id", maximum=MAX_ANCHOR_TEXT_LENGTH
        )
    elif kind == "t_ms":
        if "t_ms" not in value:
            raise AnnotationError(f"{name}.t_ms is required")
        result["t_ms"] = _require_int(value["t_ms"], f"{name}.t_ms", 0)
    else:
        if "index" not in value:
            raise AnnotationError(f"{name}.index is required")
        result["index"] = _require_int(value["index"], f"{name}.index", 0)
    if kind != "t_ms" and "offset_ms" in value:
        result["offset_ms"] = _require_int(
            value["offset_ms"], f"{name}.offset_ms", 0
        )
    return result


def validate_note(
    note: Any,
    *,
    index: int | None = None,
    require_id: bool = False,
    allow_images: bool = True,
) -> dict[str, Any]:
    where = "note" if index is None else f"notes[{index}]"
    if not isinstance(note, dict):
        raise AnnotationError(f"{where} must be an object")
    unknown = sorted(set(note) - set(NOTE_FIELDS) - set(NOTE_OPTIONAL_FIELDS))
    if unknown:
        raise AnnotationError(
            f"{where} has unknown fields: {', '.join(unknown)}"
        )

    note_id = note.get("id")
    if note_id is None:
        if require_id:
            raise AnnotationError(f"{where}.id is required")
        note_id = None
    else:
        note_id = _require_string(
            note_id, f"{where}.id", maximum=MAX_ID_LENGTH
        )

    if "t_ms" not in note:
        raise AnnotationError(f"{where}.t_ms is required")
    t_ms = _require_int(note["t_ms"], f"{where}.t_ms", 0)

    has_anchors = "anchors" in note
    anchors_value = note.get("anchors") if has_anchors else None
    if has_anchors and not isinstance(anchors_value, list):
        raise AnnotationError(f"{where}.anchors must be a list")
    unpositioned = (
        note.get("frame_no") in (None, 0)
        and not note.get("regions")
        and not anchors_value
    )
    if unpositioned:
        frame_no = 0
    else:
        if "frame_no" not in note:
            raise AnnotationError(f"{where}.frame_no is required")
        frame_no = _require_int(note["frame_no"], f"{where}.frame_no", 1)

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

    if has_anchors:
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
            note.get("regions", []),
            f"{where}.regions",
            allow_image=allow_images,
        )
        if not regions and anchors:
            regions = [dict(region) for region in anchors[0]["regions"]]
    else:
        anchors = None
        regions = _validate_regions(
            note.get("regions"), f"{where}.regions", allow_image=allow_images
        )
        if frame_start is not None and not (
            frame_start <= frame_no <= frame_end
        ):
            raise AnnotationError(
                f"{where}.frame_no must be within {frame_start}..{frame_end}"
            )

    tags_value = note.get("tags")
    if not isinstance(tags_value, list):
        raise AnnotationError(f"{where}.tags must be a list")
    if len(tags_value) > MAX_TAGS:
        raise AnnotationError(
            f"{where}.tags must have at most {MAX_TAGS} entries"
        )
    tags = [
        _require_string(
            tag, f"{where}.tags[{position}]", maximum=MAX_TAG_LENGTH
        )
        for position, tag in enumerate(tags_value)
    ]

    if "text" not in note:
        raise AnnotationError(f"{where}.text is required")
    text = _require_string(
        note["text"],
        f"{where}.text",
        maximum=MAX_TEXT_LENGTH,
        allow_empty=True,
    )

    author = note.get("author")
    if author not in AUTHORS:
        raise AnnotationError(
            f"{where}.author must be one of {', '.join(AUTHORS)}"
        )
    source = note.get("source")
    if source not in SOURCES:
        raise AnnotationError(
            f"{where}.source must be one of {', '.join(SOURCES)}"
        )
    transcribed_by = note.get("transcribed_by")
    if transcribed_by is not None and transcribed_by not in TRANSCRIBERS:
        raise AnnotationError(
            f"{where}.transcribed_by must be one of {', '.join(TRANSCRIBERS)}"
        )
    if "feedback_anchor" not in note:
        raise AnnotationError(f"{where}.feedback_anchor is required")
    feedback_anchor = _validate_feedback_anchor(
        note["feedback_anchor"], f"{where}.feedback_anchor"
    )

    result: dict[str, Any] = {
        "id": note_id,
        "frame_no": frame_no,
        "t_ms": t_ms,
        "regions": regions,
        "tags": tags,
        "text": text,
        "author": author,
        "source": source,
        "feedback_anchor": feedback_anchor,
    }
    if transcribed_by is not None:
        result["transcribed_by"] = transcribed_by
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
    import secrets

    for _ in range(100):
        candidate = f"note-{secrets.token_hex(4)}"
        if candidate not in existing_ids:
            return candidate
    raise AnnotationError("could not allocate a unique note id")


def append_note(
    document: dict[str, Any], note: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    notes = [dict(existing) for existing in document["notes"]]
    ids = {existing["id"] for existing in notes}
    saved = dict(note)
    if saved["id"] is None:
        saved["id"] = new_note_id(ids)
    elif saved["id"] in ids:
        raise AnnotationConflict(f"duplicate note id: {saved['id']}")
    notes.append(saved)
    return {"schema": ANNOTATIONS_SCHEMA, "notes": notes}, saved


_WRITE_LOCK = threading.Lock()


def _read_existing(recording: Recording) -> dict[str, Any]:
    try:
        document = recording.annotations
    except ValueError as exc:
        raise AnnotationError(str(exc), code="annotations_unreadable") from exc
    return validate_document(document)


def _lock_path(recording: Recording) -> Any:
    store = recording.annotations_store
    return store.session_dir / ANNOTATIONS_LOCK_FILE_NAME


def _source_bytes(
    recording: Recording, frame_no: Any, t_ms: Any
) -> tuple[str | None, bytes | None]:
    root = recording.annotations_store.session_dir
    if _is_int(frame_no):
        for path in recording.frames:
            if path.stem.isdigit() and int(path.stem) == frame_no:
                try:
                    return (
                        path.resolve().relative_to(root.resolve()).as_posix(),
                        path.read_bytes(),
                    )
                except (OSError, ValueError):
                    break
    try:
        views = recording.snapshot_views()
    except (AttributeError, OSError, ValueError):
        views = []
    target = t_ms if _is_int(t_ms) else None
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for view in views:
        frame_value = view.get("frame_no")
        t_value = view.get("t_ms")
        if target is not None and t_value == target:
            candidates.append((0, 0, view))
        elif _is_int(frame_no) and frame_value == frame_no:
            candidates.append((1, 0, view))
        elif target is not None and _is_int(t_value):
            candidates.append((2, abs(t_value - target), view))
    if candidates:
        view = sorted(candidates, key=lambda item: (item[0], item[1]))[0][2]
        file = view.get("file")
        if isinstance(file, str):
            try:
                return file, (root / file).read_bytes()
            except OSError:
                pass
    if target is not None:
        try:
            anchor = resolve_anchor(
                recording, {"kind": "t_ms", "t_ms": target}
            )
        except (AttributeError, OSError, ValueError):
            anchor = None
        image = None if anchor is None else anchor.get("image")
        if isinstance(image, str):
            try:
                path = (root / image).resolve()
                path.relative_to(root.resolve())
                return path.relative_to(
                    root.resolve()
                ).as_posix(), path.read_bytes()
            except (OSError, ValueError):
                pass
    return None, None


def _crop_png_bytes(data: bytes, region: dict[str, Any], name: str) -> bytes:
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
            _relative, frame_data = _source_bytes(
                recording, anchor.get("frame_no"), anchor.get("t_ms")
            )
            annotated_path = anchor.get("annotated")
            annotated_data = None
            if frame_data is None and not isinstance(annotated_path, str):
                raise AnnotationError(
                    f"anchors[{ai}]: no evidence image for frame "
                    f"{anchor.get('frame_no')}",
                    code="region_image_error",
                )
            if isinstance(annotated_path, str):
                annotated_data = transaction.read_image(annotated_path)
            for ri, region in enumerate(anchor.get("regions") or []):
                if not isinstance(region, dict):
                    continue
                if frame_data is not None:
                    relative = (
                        f"{session_schema.REGIONS_DIR}/{stem}-a{ai}-r{ri}.png"
                    )
                    transaction.write_image(
                        relative,
                        _crop_png_bytes(
                            frame_data,
                            region,
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
                            annotated_data,
                            region,
                            f"anchors[{ai}].regions[{ri}].annotated",
                        ),
                    )
                    region["annotated"] = relative
        note["regions"] = [dict(region) for region in anchors[0]["regions"]]
        return

    regions = note.get("regions")
    if not isinstance(regions, list) or not regions:
        return
    _relative, frame_data = _source_bytes(
        recording, note.get("frame_no"), note.get("t_ms")
    )
    if frame_data is None:
        raise AnnotationError(
            f"no evidence image for frame {note.get('frame_no')}",
            code="region_image_error",
        )
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        relative = f"{session_schema.REGIONS_DIR}/{stem}-{index}.png"
        transaction.write_image(
            relative,
            _crop_png_bytes(frame_data, region, f"regions[{index}]"),
        )
        region["image"] = relative


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
            f"{session_schema.REGIONS_DIR}/{stem}-a{index}-annotated.png"
        )
        transaction.write_image(relative, data)
        anchor["annotated"] = relative


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
    store.remove_unreferenced(
        session_schema.REGIONS_DIR, image_references(document, "notes")
    )


def _derive(recording: Recording, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return derive_anchor(
            recording,
            frame_no=payload.get("frame_no"),
            t_ms=payload.get("t_ms"),
        )
    except Exception:  # noqa: BLE001 - a read-only seam may lack a timeline
        t_ms = payload.get("t_ms")
        return {"kind": "t_ms", "t_ms": t_ms if _is_int(t_ms) else 0}


def add_note(
    recording: Recording,
    payload: Any,
    *,
    source: str,
    author: str = "human",
    transcribed_by: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise AnnotationError("note must be an object")
    data = dict(payload)
    data.setdefault("author", author)
    data.setdefault("source", source)
    if transcribed_by is not None:
        data.setdefault("transcribed_by", transcribed_by)
    if "feedback_anchor" not in data:
        data["feedback_anchor"] = _derive(recording, data)
    lock = FileLock(_lock_path(recording), timeout=ANNOTATIONS_LOCK_TIMEOUT_S)
    with _WRITE_LOCK:
        try:
            with lock:
                return _write_locked(recording, data)
        except TimeoutError as exc:
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc
        except OSError as exc:
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc


def _write_locked(
    recording: Recording, data: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    store = recording.annotations_store
    try:
        with store.transaction() as transaction:
            document = _read_existing(recording)
            note = validate_note(data, allow_images=False)
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
        raise AnnotationError(str(exc), code="internal_error") from exc
    try:
        current = _read_existing(recording)
    except AnnotationError:
        current = document
    _prune_images(store, current)
    return document, saved


def write_note(
    recording: Recording, payload: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    return add_note(recording, payload, source="web")


def delete_note(recording: Recording, note_id: str) -> dict[str, Any]:
    if not isinstance(note_id, str) or not note_id:
        raise AnnotationNotFound("note id is required")
    lock = FileLock(_lock_path(recording), timeout=ANNOTATIONS_LOCK_TIMEOUT_S)
    with _WRITE_LOCK:
        try:
            with lock:
                return _delete_locked(recording, note_id)
        except TimeoutError as exc:
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc
        except OSError as exc:
            raise AnnotationError(
                str(exc), code="annotations_write_error"
            ) from exc


def _delete_locked(recording: Recording, note_id: str) -> dict[str, Any]:
    store = recording.annotations_store
    try:
        document = _read_existing(recording)
    except OSError as exc:
        raise AnnotationError(str(exc), code="internal_error") from exc
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
    try:
        current = _read_existing(recording)
    except AnnotationError:
        current = document
    _prune_images(store, current)
    return document


def human_notes(recording: Recording) -> list[dict[str, Any]]:
    try:
        document = recording.annotations
    except (OSError, ValueError):
        return []
    notes = document.get("notes") if isinstance(document, dict) else None
    if not isinstance(notes, list):
        return []
    return [
        note
        for note in notes
        if isinstance(note, dict) and note.get("author") == "human"
    ]


__all__ = [
    "ANCHOR_FIELDS",
    "AnnotationConflict",
    "AnnotationError",
    "AnnotationNotFound",
    "NOTE_FIELDS",
    "NOTE_OPTIONAL_FIELDS",
    "add_note",
    "delete_note",
    "human_notes",
    "validate_document",
    "validate_note",
    "write_note",
]
