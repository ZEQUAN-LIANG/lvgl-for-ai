
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from lvgl_ai import Recording
from lvgl_ai.control.errors import BuildError, RuntimeCrash, ScenarioError
from lvgl_ai.control.session import (
    SessionOutcome,
    SessionStore,
    TailLog,
    new_session_id,
)
from lvgl_ai.control.session_schema import (
    MANIFEST_FIELDS,
    MANIFEST_REQUIRED_FIELDS,
    MANIFEST_SCHEMA,
)
from support import write_png_rgb

SESSION_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


class TailLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "engine.log"

    def test_append_and_tail(self) -> None:
        log = TailLog(self.path, max_bytes=1024)
        log.open()
        log.append("one")
        log.append("two")
        log.append("three")

        self.assertEqual(log.tail(1), ["three"])
        self.assertEqual(log.tail(2), ["two", "three"])
        self.assertEqual(log.tail(0), [])
        self.assertEqual(
            self.path.read_text(encoding="utf-8"), "one\ntwo\nthree\n"
        )
        self.assertFalse(log.truncated)

        log.close()
        self.assertEqual(log.tail(1), ["three"])

    def test_append_before_open_is_dropped(self) -> None:
        log = TailLog(self.path, max_bytes=1024)
        log.append("dropped")
        self.assertEqual(log.tail(5), [])
        self.assertFalse(self.path.exists())

    def test_truncation_keeps_a_line_aligned_tail_and_sets_the_flag(self) -> None:
        log = TailLog(self.path, max_bytes=600)
        log.open()
        for index in range(200):
            log.append(f"[fake_engine] log line {index:05d}")
        log.close()

        self.assertLessEqual(self.path.stat().st_size, 600)
        self.assertTrue(log.truncated)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^\[fake_engine\] log line \d{5}$")
        self.assertEqual(lines[-1], "[fake_engine] log line 00199")
        self.assertEqual(log.tail(1), [lines[-1]])

    def test_close_is_idempotent(self) -> None:
        log = TailLog(self.path, max_bytes=1024)
        log.open()
        log.append("line")
        log.close()
        log.close()
        log.append("after close")
        self.assertEqual(log.tail(5), ["line"])

    def test_open_starts_with_a_clean_truncation_flag(self) -> None:
        log = TailLog(self.path, max_bytes=200)
        log.open()
        for index in range(50):
            log.append(f"[fake_engine] line {index:03d}")
        self.assertTrue(log.truncated)
        log.open()
        self.assertFalse(log.truncated)
        log.close()


class SessionOutcomeTest(unittest.TestCase):
    def test_ok(self) -> None:
        outcome = SessionOutcome.ok()
        self.assertEqual(outcome.status, "ok")
        self.assertIsNone(outcome.error)

    def test_from_failure_maps_every_error_layer(self) -> None:
        cases = [
            (BuildError("compile failed"), "build_error"),
            (ScenarioError("bad step", step=1), "harness_error"),
            (ValueError("other"), "harness_error"),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                outcome = SessionOutcome.from_failure(error)
                self.assertEqual(outcome.status, expected)
                self.assertIs(outcome.error, error)

    def test_resolve_prefers_a_recorded_failure_over_the_exit_code(self) -> None:
        error = ScenarioError("bad step")
        outcome = SessionOutcome.resolve(
            error, exit_code=1, unexpected_exit=True
        )
        self.assertEqual(outcome.status, "harness_error")
        self.assertIs(outcome.error, error)

    def test_resolve_exit_zero_is_ok(self) -> None:
        outcome = SessionOutcome.resolve(None, exit_code=0, unexpected_exit=False)
        self.assertEqual(outcome.status, "ok")
        self.assertIsNone(outcome.error)

    def test_resolve_non_zero_exit_is_a_completed_crash(self) -> None:
        seen: list[str] = []

        def make_crash(message: str) -> RuntimeCrash:
            seen.append(message)
            return RuntimeCrash(message, exit_code=3, log_tail=["tail"])

        outcome = SessionOutcome.resolve(
            None,
            exit_code=3,
            unexpected_exit=False,
            make_crash=make_crash,
        )
        self.assertEqual(outcome.status, "crash")
        self.assertEqual(seen, ["engine exited with 3"])
        self.assertEqual(outcome.error.exit_code, 3)
        self.assertEqual(outcome.error.log_tail, ["tail"])

    def test_resolve_in_flight_exit_is_a_crash(self) -> None:
        outcome = SessionOutcome.resolve(
            None, exit_code=0, unexpected_exit=True
        )
        self.assertEqual(outcome.status, "crash")
        self.assertEqual(
            str(outcome.error), "engine exited while a command was in flight"
        )

    def test_unknown_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SessionOutcome("failed")


class SessionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sessions_root = self.root / "sessions"

    def make_store(self, **kwargs) -> SessionStore:
        options = dict(
            record=True,
            live_frame=False,
            build=False,
            retention=None,
            max_log_bytes=1024,
            app="coffee",
            record_changed_only=False,
            lvgl_src=self.root / "lvgl-src" / "9.6",
            mode="headless",
        )
        options.update(kwargs)
        store = SessionStore(self.sessions_root, **options)
        self.addCleanup(store.close_log)
        return store

    def test_create_reserves_the_session_directory_and_engine_log(self) -> None:
        store = self.make_store()
        path = store.create()

        self.assertEqual(path, store.session_dir)
        self.assertRegex(store.session_id, SESSION_ID_RE)
        self.assertEqual(path.parent, self.sessions_root)
        self.assertTrue(path.is_dir())
        self.assertTrue((path / "frames").is_dir())
        self.assertEqual(store.engine_log_path, path / "engine.log")
        self.assertEqual(store.manifest_path, path / "manifest.json")
        self.assertTrue(store.engine_log_path.is_file())

        store.append_log("[app] hello")
        store.close_log()
        self.assertEqual(store.log_tail(1), ["[app] hello"])

    def test_record_false_creates_no_frames_directory(self) -> None:
        store = self.make_store(record=False)
        path = store.create()
        self.assertFalse((path / "frames").exists())

    def test_write_build_log_appends_a_newline_and_replaces(self) -> None:
        store = self.make_store()
        path = store.create()

        store.write_build_log("# phase: build\nok")
        self.assertEqual(
            (path / "build.log").read_text(encoding="utf-8"),
            "# phase: build\nok\n",
        )
        store.write_build_log("# second\n")
        self.assertEqual(
            (path / "build.log").read_text(encoding="utf-8"), "# second\n"
        )

    def test_discard_preview_removes_live_rgba(self) -> None:
        store = self.make_store(live_frame=True)
        path = store.create()
        preview = path / "live.rgba"
        preview.write_bytes(b"\x00\x01")
        store.discard_preview()
        self.assertFalse(preview.exists())
        store.discard_preview()

    def test_discard_preview_is_a_no_op_without_live_frame(self) -> None:
        store = self.make_store(live_frame=False)
        path = store.create()
        preview = path / "live.rgba"
        preview.write_bytes(b"\x00\x01")
        store.discard_preview()
        self.assertTrue(preview.exists())

    def test_prune_keeps_the_newest_sessions(self) -> None:
        for seq in range(3):
            old = self.sessions_root / f"20260101-0000{seq:02d}-{seq:04x}"
            old.mkdir(parents=True)
            (old / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": MANIFEST_SCHEMA,
                        "id": old.name,
                        "status": "ok",
                    }
                ),
                encoding="utf-8",
            )
        store = self.make_store(retention=2)
        store.create()
        removed = store.prune()

        self.assertEqual(
            sorted(path.name for path in removed),
            ["20260101-000000-0000", "20260101-000001-0001"],
        )
        self.assertTrue(store.session_dir.is_dir())
        self.assertEqual(len(list(self.sessions_root.iterdir())), 2)

    def test_prune_none_disables_cleanup(self) -> None:
        old = self.sessions_root / "20260101-000000-0000"
        old.mkdir(parents=True)
        (old / "manifest.json").write_text(
            json.dumps({"schema": MANIFEST_SCHEMA, "id": old.name, "status": "ok"}),
            encoding="utf-8",
        )
        store = self.make_store(retention=None)
        store.create()
        self.assertEqual(store.prune(), [])
        self.assertTrue(old.is_dir())

    def test_manifest_round_trips_through_recording_with_the_same_fields(self) -> None:
        store = self.make_store(build=True)
        path = store.create()
        store.write_build_log("# phase: build\nok\n")
        (path / "timeline.ndjson").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "end",
                    "frame_count": 1,
                    "t_ms": 0,
                    "truncated": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (path / "frame_diffs.ndjson").write_text("", encoding="utf-8")
        (path / "frames").mkdir(exist_ok=True)
        write_png_rgb(path / "frames" / "000001.png", 1, 1, [(1, 2, 3)])
        (path / "snapshots").mkdir()
        write_png_rgb(path / "snapshots" / "001_done.png", 1, 1, [(4, 5, 6)])
        (path / "annotations.json").write_text(
            json.dumps({"schema": "lvgl-ai-annotations-v1", "notes": []}),
            encoding="utf-8",
        )
        store.note_ready(
            {
                "mode": "headless",
                "inputs": ["real", "virtual"],
                "lvgl": "9.6.0",
                "lvgl_src": str(self.root / "lvgl-src" / "9.6"),
                "adapter": "9x",
                "display": {
                    "width": 640,
                    "height": 480,
                    "format": "XRGB8888",
                },
            }
        )
        store.append_check("tick 16", True, 1)
        store.note_truncated()
        store.write_manifest(SessionOutcome.ok())
        store.close_log()

        recording = Recording.open(path)
        manifest = recording.manifest
        self.assertEqual(list(manifest), list(MANIFEST_FIELDS))
        self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
        self.assertEqual(manifest["id"], store.session_id)
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["app"], "coffee")
        self.assertIs(manifest["record_changed_only"], False)
        self.assertEqual(manifest["mode"], "headless")
        self.assertEqual(manifest["input"], ["real", "virtual"])
        self.assertEqual(manifest["build"], {"status": "ok", "log": "build.log"})
        self.assertEqual(manifest["lvgl"], "9.6.0")
        self.assertEqual(
            manifest["lvgl_src"], str(self.root / "lvgl-src" / "9.6")
        )
        self.assertEqual(manifest["adapter"], "9x")
        self.assertEqual(manifest["display"], {"width": 640, "height": 480})
        self.assertEqual(manifest["frame_count"], 1)
        self.assertIs(manifest["truncated"], True)
        self.assertIs(manifest["log_truncated"], False)
        self.assertEqual(
            manifest["checks"], [{"cmd": "tick 16", "ok": True, "frame_no": 1}]
        )
        self.assertIsNone(manifest["error"])
        self.assertEqual(
            manifest["artifacts"],
            {
                "manifest": "manifest.json",
                "build_log": "build.log",
                "engine_log": "engine.log",
                "timeline": "timeline.ndjson",
                "frame_diffs": "frame_diffs.ndjson",
                "annotations": "annotations.json",
                "frames": ["frames/000001.png"],
                "snapshots": ["snapshots/001_done.png"],
            },
        )
        self.assertEqual(recording.frames, [path / "frames" / "000001.png"])
        self.assertEqual(
            recording.snapshots, [path / "snapshots" / "001_done.png"]
        )
        self.assertFalse((path / "manifest.json.tmp").exists())

    def test_manifest_before_ready_uses_the_fallbacks(self) -> None:
        store = self.make_store(build=False)
        path = store.create()
        store.write_build_log("# build skipped (build=False)\n")
        store.write_manifest(SessionOutcome.ok())
        store.close_log()

        manifest = json.loads(
            (path / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["mode"], "headless")
        self.assertEqual(manifest["input"], ["real", "virtual"])
        self.assertIsNone(manifest["lvgl"])
        self.assertEqual(
            manifest["lvgl_src"], str(self.root / "lvgl-src" / "9.6")
        )
        self.assertEqual(manifest["adapter"], "9x")
        self.assertIsNone(manifest["display"])
        self.assertEqual(manifest["build"], {"status": "skipped", "log": "build.log"})
        self.assertEqual(manifest["frame_count"], 0)
        self.assertEqual(
            manifest["artifacts"],
            {
                "manifest": "manifest.json",
                "build_log": "build.log",
                "engine_log": "engine.log",
            },
        )

    def test_build_failure_manifest_is_readable(self) -> None:
        store = self.make_store(build=True)
        path = store.create()
        store.write_build_log("# build failed\n")
        error = BuildError("compile failed", log_text="app.c:2: error")
        store.write_manifest(
            SessionOutcome.from_failure(error), build_status="error"
        )
        store.close_log()

        manifest = Recording.open(path).manifest
        self.assertEqual(manifest["status"], "build_error")
        self.assertEqual(manifest["build"]["status"], "error")
        self.assertEqual(manifest["error"]["code"], "build_error")
        self.assertEqual(manifest["error"]["message"], "compile failed")
        self.assertEqual(manifest["error"]["detail"]["diagnostics"], [])

    def test_write_manifest_before_create_is_a_no_op(self) -> None:
        store = self.make_store()
        store.write_manifest(SessionOutcome.ok())
        self.assertFalse(self.sessions_root.exists())

    def test_ready_and_mode_are_written_back_to_the_store(self) -> None:
        store = self.make_store(mode="window")
        self.assertIsNone(store.ready)

        store.note_ready({"mode": "headless", "frames": 1})
        store.note_mode("headless")

        self.assertEqual(store.mode, "headless")
        self.assertEqual(store.ready["mode"], "headless")
        self.assertEqual(store.ready["frames"], 1)

    def test_session_options_keep_their_public_names(self) -> None:
        store = self.make_store(
            retention=3, lvgl_src=self.root / "lvgl-src" / "9.6"
        )
        self.assertEqual(store.retention, 3)
        self.assertEqual(store.lvgl_src, self.root / "lvgl-src" / "9.6")


class SessionSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write_session(self, manifest: dict) -> Path:
        session = self.root / "20260102-030405-abcd"
        session.mkdir()
        (session / "engine.log").write_text("[app] hello\n", encoding="utf-8")
        (session / "timeline.ndjson").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "end",
                    "frame_count": 0,
                    "t_ms": 0,
                    "truncated": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (session / "frame_diffs.ndjson").write_text("", encoding="utf-8")
        (session / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return session

    def legacy_manifest(self, **overrides) -> dict:
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "id": "20260102-030405-abcd",
            "status": "ok",
            "scenario": None,
            "source_digest": None,
            "mode": "headless",
            "input": ["real", "virtual"],
            "build": {"status": "ok", "log": "build.log"},
            "lvgl": "9.6.0",
            "lvgl_src": "I:/lvgl-src/9.6",
            "adapter": "9x",
            "tool_version": "0.1.0",
            "frame_count": 0,
            "truncated": False,
            "log_truncated": False,
            "checks": [],
            "error": None,
            "artifacts": {"manifest": "manifest.json", "engine_log": "engine.log"},
        }
        manifest.update(overrides)
        return manifest

    def test_legacy_sessions_without_app_fields_still_open(self) -> None:
        session = self.write_session(self.legacy_manifest())
        recording = Recording.open(session)
        self.assertEqual(recording.manifest["schema"], MANIFEST_SCHEMA)
        self.assertNotIn("app", recording.manifest)
        self.assertNotIn("display", recording.manifest)
        self.assertNotIn("record_changed_only", recording.manifest)

    def test_invalid_manifest_display_is_rejected(self) -> None:
        cases = [
            "640x480",
            {"width": 0, "height": 480},
            {"width": 640, "height": -1},
            {"width": True, "height": 480},
            {"width": 640, "height": 1.5},
            {"width": 640},
        ]
        for display in cases:
            with self.subTest(display=display):
                session = self.write_session(
                    self.legacy_manifest(display=display)
                )
                with self.assertRaises(ValueError) as caught:
                    Recording.open(session)
                self.assertIn("display", str(caught.exception))
                shutil.rmtree(session)

    def test_required_fields_and_schema_are_shared_with_recording(self) -> None:
        from lvgl_ai.control import recording

        self.assertIs(recording.MANIFEST_SCHEMA, MANIFEST_SCHEMA)
        self.assertIs(recording.MANIFEST_REQUIRED_FIELDS, MANIFEST_REQUIRED_FIELDS)

    def test_missing_required_manifest_field_is_rejected_with_path(self) -> None:
        manifest = self.legacy_manifest()
        manifest.pop("checks")
        session = self.write_session(manifest)
        with self.assertRaises(ValueError) as caught:
            Recording.open(session)
        self.assertIn("manifest.json", str(caught.exception))
        self.assertIn("checks", str(caught.exception))

    def test_corrupt_manifest_degrades_to_value_error_with_path(self) -> None:
        session = self.write_session(self.legacy_manifest())
        (session / "manifest.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            Recording.open(session)
        self.assertIn("manifest.json", str(caught.exception))
        self.assertIn("invalid JSON", str(caught.exception))


class NewSessionIdTest(unittest.TestCase):
    def test_session_id_has_the_documented_shape(self) -> None:
        self.assertRegex(new_session_id(), SESSION_ID_RE)
        self.assertNotEqual(new_session_id(), new_session_id())


if __name__ == "__main__":
    unittest.main(verbosity=2)
