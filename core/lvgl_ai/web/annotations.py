"""HTTP adapter exports for the annotation write transaction.

The validation and write transaction live in
:mod:`lvgl_ai.control.notes`; the web layer keeps only the import surface its
routes and tests use.
"""

from __future__ import annotations

from ..control.notes import (
    ANCHOR_FIELDS,
    NOTE_FIELDS,
    AnnotationConflict,
    AnnotationError,
    AnnotationNotFound,
    add_note,
    delete_note,
    validate_document,
    validate_note,
    write_note,
)

__all__ = [
    "ANCHOR_FIELDS",
    "NOTE_FIELDS",
    "AnnotationConflict",
    "AnnotationError",
    "AnnotationNotFound",
    "add_note",
    "delete_note",
    "validate_document",
    "validate_note",
    "write_note",
]
