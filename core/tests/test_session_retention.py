from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lvgl_ai import Runtime
from lvgl_ai.control.retention import DEFAULT_SESSION_LIMIT, prune_sessions


def session_id(seq: int) -> str:
    return f"20260101-0000{seq:02d}-{seq:04x}"


class PruneSessionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make_session(
        self,
        name: str,
        status: str = "ok",
        *,
        manifest: bool = True,
    ) -> Path:
        path = self.root / name
        path.mkdir()
        if manifest:
            (path / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "lvgl-ai-session-v1",
                        "id": name,
                        "status": status,
                    }
                ),
                encoding="utf-8",
            )
        return path

    def names(self) -> list[str]:
        return sorted(path.name for path in self.root.iterdir())

    def test_keeps_newest_ten(self) -> None:
        for seq in range(13):
            self.make_session(session_id(seq))

        removed = prune_sessions(self.root)

        self.assertEqual(len(removed), 3)
        self.assertEqual(
            self.names(), [session_id(seq) for seq in range(3, 13)]
        )

    def test_build_error_is_removed_even_when_newest(self) -> None:
        for seq in range(10):
            self.make_session(session_id(seq))
        broken = self.make_session(session_id(10), status="build_error")

        self.assertEqual(prune_sessions(self.root), [broken])
        self.assertEqual(self.names(), [session_id(seq) for seq in range(10)])

    def test_session_without_manifest_is_left_alone(self) -> None:
        incomplete = self.make_session(session_id(20), manifest=False)
        for seq in range(12):
            self.make_session(session_id(seq))

        prune_sessions(self.root)

        self.assertIn(incomplete.name, self.names())
        self.assertEqual(len(self.names()), 11)

    def test_keep_survives_and_counts_toward_the_limit(self) -> None:
        keep = self.make_session(session_id(0))
        for seq in range(1, 5):
            self.make_session(session_id(seq))

        prune_sessions(self.root, limit=2, keep=keep)

        self.assertEqual(self.names(), [session_id(0), session_id(4)])

    def test_empty_annotations_do_not_protect_old_sessions(self) -> None:
        old = self.make_session(session_id(0))
        (old / "annotations.json").write_text(
            json.dumps({"schema": "lvgl-ai-annotations-v1", "notes": []}),
            encoding="utf-8",
        )
        for seq in range(1, 12):
            self.make_session(session_id(seq))

        prune_sessions(self.root, limit=10)

        self.assertNotIn(old.name, self.names())

    def test_non_empty_notes_protect_old_sessions(self) -> None:
        old = self.make_session(session_id(0))
        self.write_note(old)
        for seq in range(1, 12):
            self.make_session(session_id(seq))

        prune_sessions(self.root, limit=10)

        self.assertIn(old.name, self.names())

    def test_non_empty_whiteboards_protect_old_sessions(self) -> None:
        old = self.make_session(session_id(0))
        (old / "whiteboards.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-whiteboards-v1",
                    "whiteboards": [{"id": "wb1"}],
                }
            ),
            encoding="utf-8",
        )
        for seq in range(1, 12):
            self.make_session(session_id(seq))

        prune_sessions(self.root, limit=10)

        self.assertIn(old.name, self.names())

    def test_unreadable_annotations_count_as_protected(self) -> None:
        old = self.make_session(session_id(0))
        (old / "annotations.json").write_text("{broken", encoding="utf-8")
        for seq in range(1, 12):
            self.make_session(session_id(seq))

        prune_sessions(self.root, limit=10)

        self.assertIn(old.name, self.names())

    def test_protected_sessions_do_not_count_toward_the_limit(self) -> None:
        protected = [self.make_session(session_id(seq)) for seq in range(2)]
        for path in protected:
            self.write_note(path)
        for seq in range(2, 14):
            self.make_session(session_id(seq))

        prune_sessions(self.root, limit=10)

        self.assertEqual(
            sorted(self.names()),
            sorted(
                [path.name for path in protected]
                + [session_id(seq) for seq in range(4, 14)]
            ),
        )

    def test_build_error_with_notes_is_protected(self) -> None:
        broken = self.make_session(session_id(10), status="build_error")
        self.write_note(broken)
        for seq in range(10):
            self.make_session(session_id(seq))

        prune_sessions(self.root)

        self.assertIn(broken.name, self.names())

    def write_note(self, path: Path) -> None:
        (path / "annotations.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-annotations-v1",
                    "notes": [
                        {
                            "id": "note-1",
                            "frame_no": 1,
                            "t_ms": 0,
                            "regions": [],
                            "tags": [],
                            "text": "keep me",
                            "author": "human",
                            "source": "chat",
                            "feedback_anchor": {"kind": "t_ms", "t_ms": 0},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_unrelated_directories_are_left_alone(self) -> None:
        notes = self.root / "notes"
        notes.mkdir()
        for seq in range(12):
            self.make_session(session_id(seq))

        prune_sessions(self.root)

        self.assertTrue(notes.is_dir())

    def test_none_disables_pruning(self) -> None:
        for seq in range(12):
            self.make_session(session_id(seq))

        self.assertEqual(prune_sessions(self.root, limit=None), [])
        self.assertEqual(len(self.names()), 12)


class RuntimeRetentionConfigTest(unittest.TestCase):
    def test_default_limit_is_ten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(
                lvgl="9.6",
                build=False,
                sessions_root=Path(tmp) / "sessions",
            )
            self.assertEqual(runtime._store.retention, DEFAULT_SESSION_LIMIT)

    def test_none_disables_and_negative_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(
                lvgl="9.6",
                build=False,
                sessions_root=Path(tmp) / "sessions",
                session_retention=None,
            )
            self.assertIsNone(runtime._store.retention)
            with self.assertRaises(ValueError):
                Runtime(
                    lvgl="9.6",
                    build=False,
                    sessions_root=Path(tmp) / "sessions",
                    session_retention=-1,
                )


if __name__ == "__main__":
    unittest.main()
