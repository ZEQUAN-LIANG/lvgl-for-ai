"""One JSON document plus its managed image files, stored in a session.

Annotations and whiteboards share this module: read and validate the
document, stage images, atomically replace the document, roll back images
written by a failed transaction, and remove images the document no longer
references. The document-specific note/whiteboard validation stays with the
caller; this module owns the envelope, file names and side effects.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


class DocumentError(ValueError):
    """A session document or one of its image files could not be handled.

    ``code`` is the stable name the web adapter maps to an HTTP status, so a
    failed read and a failed write stay distinguishable without exception
    type inspection.
    """

    def __init__(self, message: str, *, code: str = "invalid_document") -> None:
        super().__init__(message)
        self.code = code


class DocumentStore:
    """The JSON document and image transaction for one session file.

    ``read`` returns an empty document when the file is absent. ``write``
    validates the envelope and replaces the file atomically. ``transaction``
    tracks images created inside it and removes them again when the block
    raises, so a failed save cannot leave a crop or whiteboard PNG behind.
    """

    def __init__(
        self,
        session_dir: str | Path,
        *,
        filename: str,
        schema: str,
        collection: str,
        unreadable_code: str = "document_unreadable",
        write_code: str = "document_write_error",
        error_type: type[DocumentError] = DocumentError,
        keep_extra_fields: bool = True,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.filename = filename
        self.schema = schema
        self.collection = collection
        self.unreadable_code = unreadable_code
        self.write_code = write_code
        self.error_type = error_type
        self.keep_extra_fields = keep_extra_fields

    @property
    def path(self) -> Path:
        """The document file inside the session directory."""
        return self.session_dir / self.filename

    def empty(self) -> dict[str, Any]:
        """The document shape a missing file reads as."""
        return {"schema": self.schema, self.collection: []}

    def read(self) -> dict[str, Any]:
        """Read and validate the document; a missing file is empty."""
        if not self.path.is_file():
            return self.empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise self.error_type(
                f"{self.path}: invalid JSON: {exc.msg}",
                code=self.unreadable_code,
            ) from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise self.error_type(
                f"cannot read {self.path}: {exc}",
                code=self.unreadable_code,
            ) from exc
        return self._normalize(data, code=self.unreadable_code)

    def write(self, document: Any) -> dict[str, Any]:
        """Validate ``document`` and replace the file atomically."""
        data = self._normalize(document, code=self.write_code)
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise self.error_type(str(exc), code=self.write_code) from exc
        return data

    def image_path(self, relative: str) -> Path:
        """Resolve an image path and keep it inside the session directory."""
        path = self.session_dir / relative
        try:
            path.resolve().relative_to(self.session_dir.resolve())
        except (OSError, ValueError) as exc:
            raise self.error_type(
                f"{relative!r} must stay inside the session directory",
                code=self.write_code,
            ) from exc
        return path

    def write_image(self, relative: str, data: bytes) -> bool:
        """Write one image; return True when it did not exist before."""
        path = self.image_path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        created = not path.exists()
        path.write_bytes(data)
        return created

    def read_image(self, relative: str) -> bytes | None:
        """Image bytes, or ``None`` when the file is missing or unreadable."""
        try:
            return self.image_path(relative).read_bytes()
        except OSError:
            return None

    def remove_image(self, relative: str) -> None:
        """Best-effort unlink of one image."""
        try:
            self.image_path(relative).unlink(missing_ok=True)
        except OSError:
            pass

    def remove_unreferenced(
        self, folder: str, referenced: Iterable[str]
    ) -> list[Path]:
        """Delete PNGs directly under ``folder`` that the document lost.

        Non-PNG files and files outside the folder are never touched. A file
        that cannot be removed is left in place and not reported.
        """
        directory = self.session_dir / folder
        if not directory.is_dir():
            return []
        keep = {
            str(relative).replace("\\", "/")
            for relative in referenced
            if isinstance(relative, str) and relative
        }
        removed: list[Path] = []
        for path in sorted(directory.glob("*.png")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.session_dir).as_posix()
            if relative in keep:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed.append(path)
        return removed

    @contextmanager
    def transaction(self) -> Iterator[DocumentTransaction]:
        """Track created images and roll them back when the block raises."""
        transaction = DocumentTransaction(self)
        try:
            yield transaction
        except BaseException:
            transaction.rollback()
            raise
        transaction.commit()

    def _normalize(self, value: Any, *, code: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise self.error_type(
                f"{self.path}: document must be a JSON object", code=code
            )
        schema = value.get("schema", self.schema)
        if schema != self.schema:
            raise self.error_type(
                f"{self.path}: schema must be {self.schema!r}, got {schema!r}",
                code=code,
            )
        items = value.get(self.collection)
        if not isinstance(items, list):
            raise self.error_type(
                f"{self.path}: {self.collection} must be a list", code=code
            )
        if not all(isinstance(item, dict) for item in items):
            raise self.error_type(
                f"{self.path}: {self.collection} entries must be objects",
                code=code,
            )
        data = dict(value) if self.keep_extra_fields else {}
        data["schema"] = self.schema
        data[self.collection] = items
        return data


class DocumentTransaction:
    """Image side effects staged for one document write."""

    def __init__(self, store: DocumentStore) -> None:
        self._store = store
        self._created: list[str] = []

    def write_image(self, relative: str, data: bytes) -> Path:
        """Write an image and remember it if this transaction created it."""
        created = self._store.write_image(relative, data)
        if created:
            self._created.append(relative)
        return self._store.image_path(relative)

    def read_image(self, relative: str) -> bytes | None:
        return self._store.read_image(relative)

    def image_path(self, relative: str) -> Path:
        return self._store.image_path(relative)

    def commit(self) -> None:
        """Forget the created images; they belong to the saved document."""
        self._created = []

    def rollback(self) -> None:
        """Remove every image this transaction created, newest first."""
        for relative in reversed(self._created):
            self._store.remove_image(relative)
        self._created = []


def image_references(
    document: Mapping[str, Any], collection: str
) -> set[str]:
    """Every ``image`` / ``annotated`` path string in one collection.

    The collector walks the stored note or whiteboard entries, so both
    documents feed :meth:`DocumentStore.remove_unreferenced` the same way.
    """
    references: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in ("image", "annotated") and isinstance(item, str):
                    references.add(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    items = document.get(collection)
    if isinstance(items, list):
        for item in items:
            collect(item)
    return references


__all__ = [
    "DocumentError",
    "DocumentStore",
    "DocumentTransaction",
    "image_references",
]
