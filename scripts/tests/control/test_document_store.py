from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control.documents import DocumentError, DocumentStore


class DocumentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = DocumentStore(
            self.root,
            filename="doc.json",
            schema="test-document-v1",
            collection="items",
            unreadable_code="test_unreadable",
            write_code="test_write_error",
        )
        self.path = self.root / "doc.json"

    def test_missing_document_reads_as_an_empty_document(self) -> None:
        self.assertEqual(
            self.store.read(),
            {"schema": "test-document-v1", "items": []},
        )
        self.assertFalse(self.path.exists())

    def test_write_round_trips_and_leaves_no_temporary_file(self) -> None:
        document = {
            "schema": "test-document-v1",
            "items": [{"id": "one"}],
        }
        self.assertEqual(self.store.write(document), document)

        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")), document
        )
        self.assertEqual(self.store.read(), document)
        self.assertEqual(list(self.root.glob("doc.json.*.tmp")), [])

    def test_extra_top_level_fields_follow_the_store_option(self) -> None:
        document = {
            "schema": "test-document-v1",
            "items": [],
            "extra": "kept",
        }
        self.assertEqual(self.store.write(document), document)
        self.assertEqual(self.store.read(), document)

        dropping = DocumentStore(
            self.root,
            filename="dropped.json",
            schema="test-document-v1",
            collection="items",
            keep_extra_fields=False,
        )
        self.assertEqual(
            dropping.write(document),
            {"schema": "test-document-v1", "items": []},
        )

    def test_corrupt_document_raises_the_configured_code(self) -> None:
        self.path.write_bytes(b"{broken\n")

        with self.assertRaises(DocumentError) as caught:
            self.store.read()

        self.assertEqual(caught.exception.code, "test_unreadable")

    def test_write_failure_keeps_the_previous_document(self) -> None:
        self.store.write(
            {"schema": "test-document-v1", "items": [{"id": "old"}]}
        )
        before = self.path.read_bytes()
        real_replace = Path.replace

        def failing_replace(path: Path, target: Path):
            if path.name.startswith("doc.json.") and path.name.endswith(
                ".tmp"
            ):
                raise OSError("disk full")
            return real_replace(path, target)

        with mock.patch.object(Path, "replace", failing_replace):
            with self.assertRaises(DocumentError) as caught:
                self.store.write(
                    {"schema": "test-document-v1", "items": [{"id": "new"}]}
                )

        self.assertEqual(caught.exception.code, "test_write_error")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob("doc.json.*.tmp")), [])

    def test_transaction_rolls_back_images_it_created(self) -> None:
        existing = self.root / "images" / "existing.png"
        existing.parent.mkdir()
        existing.write_bytes(b"existing")

        with self.assertRaises(RuntimeError):
            with self.store.transaction() as transaction:
                transaction.write_image("images/new.png", b"new")
                self.assertTrue((self.root / "images" / "new.png").is_file())
                raise RuntimeError("transaction failed")

        self.assertFalse((self.root / "images" / "new.png").exists())
        self.assertTrue(existing.is_file())

    def test_transaction_keeps_images_after_success(self) -> None:
        with self.store.transaction() as transaction:
            transaction.write_image("images/new.png", b"new")

        self.assertEqual(
            (self.root / "images" / "new.png").read_bytes(), b"new"
        )

    def test_remove_unreferenced_deletes_only_unlisted_pngs(self) -> None:
        folder = self.root / "images"
        folder.mkdir()
        (folder / "keep.png").write_bytes(b"keep")
        (folder / "drop.png").write_bytes(b"drop")
        (folder / "note.txt").write_bytes(b"not an image")

        removed = self.store.remove_unreferenced("images", {"images/keep.png"})

        self.assertEqual(removed, [folder / "drop.png"])
        self.assertTrue((folder / "keep.png").is_file())
        self.assertFalse((folder / "drop.png").exists())
        self.assertTrue((folder / "note.txt").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
