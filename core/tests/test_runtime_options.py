"""RuntimeOptions and RuntimeLike: the runtime assembly and double seams."""

from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from lvgl_ai import Runtime
from lvgl_ai.control.runtime import RuntimeLike, RuntimeOptions

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# The surface LiveSession and scenario execution share with a Runtime double.
RUNTIME_LIKE_MEMBERS = {
    "app",
    "encoder",
    "engine_log_path",
    "exit_code",
    "frame_count",
    "is_running",
    "key",
    "log_tail",
    "manifest_path",
    "mark",
    "mode",
    "pid",
    "pointer",
    "ready",
    "record_error",
    "session_dir",
    "session_id",
    "snapshot",
    "start",
    "stop",
    "t_ms",
    "tick",
    "wait",
}
OPTION_NAMES = {
    "app",
    "build",
    "build_mode",
    "diff_threshold",
    "headless",
    "height",
    "live_frame",
    "lvgl",
    "max_frames",
    "max_log_bytes",
    "record",
    "record_changed_only",
    "reference",
    "session_retention",
    "sessions_root",
    "timeout",
    "width",
    "window",
}


class RuntimeOptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def test_only_provided_options_are_forwarded(self) -> None:
        self.assertEqual(
            RuntimeOptions(app="coffee", record=False).as_kwargs(),
            {"app": "coffee", "record": False},
        )

    def test_width_and_height_are_forwarded_together(self) -> None:
        kwargs = RuntimeOptions(width=640, height=480).as_kwargs()
        self.assertEqual((kwargs["width"], kwargs["height"]), (640, 480))

    def test_as_kwargs_are_accepted_by_runtime(self) -> None:
        options = RuntimeOptions(
            lvgl="9.6",
            app="coffee",
            build=False,
            record=False,
            live_frame=True,
            record_changed_only=True,
            headless=True,
            sessions_root=self.sessions_root,
            timeout=5.0,
            diff_threshold=12,
            max_frames=42,
            max_log_bytes=1024,
            session_retention=None,
        )
        rt = Runtime(**options.as_kwargs())
        self.addCleanup(rt.stop)

        self.assertEqual(rt.lvgl, "9.6")
        self.assertEqual(rt.app, "coffee")
        self.assertIs(rt.build, False)
        self.assertIs(rt.record, False)
        self.assertIs(rt.live_frame, True)
        self.assertIs(rt.record_changed_only, True)
        self.assertEqual(rt.mode, "headless")
        self.assertEqual(rt.timeout, 5.0)
        self.assertEqual(rt.diff_threshold, 12)
        self.assertEqual(rt.max_frames, 42)
        self.assertEqual(rt.max_log_bytes, 1024)
        self.assertIsNone(rt.session_retention)
        self.assertEqual(rt.sessions_root, self.sessions_root.resolve())

    def test_options_exclude_the_private_runtime_seams(self) -> None:
        names = set(inspect.signature(RuntimeOptions).parameters)
        self.assertEqual(names, OPTION_NAMES)
        self.assertFalse(
            names
            & {
                "_engine_path",
                "_engine_command",
                "_configure_command",
                "_build_command",
            }
        )


class RuntimeLikeTest(unittest.TestCase):
    def test_protocol_members_are_the_agreed_surface(self) -> None:
        annotated = set(getattr(RuntimeLike, "__annotations__", {}))
        methods = {
            name
            for name, value in vars(RuntimeLike).items()
            if not name.startswith("_") and callable(value)
        }
        self.assertEqual(annotated | methods, RUNTIME_LIKE_MEMBERS)

    def test_protocol_and_options_stay_out_of_public_exports(self) -> None:
        import lvgl_ai

        for name in ("RuntimeLike", "RuntimeOptions"):
            with self.subTest(name=name):
                self.assertNotIn(name, lvgl_ai.__all__)
                self.assertFalse(hasattr(lvgl_ai, name))

    def test_runtime_implements_every_protocol_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime(build=False, sessions_root=Path(tmp) / "sessions")
        self.addCleanup(rt.stop)
        missing = sorted(
            name for name in RUNTIME_LIKE_MEMBERS if not hasattr(rt, name)
        )
        self.assertEqual(missing, [])


class FakeRuntimeContractTest(unittest.TestCase):
    def test_fake_runtime_implements_every_protocol_member(self) -> None:
        fake = FakeRuntime()
        missing = sorted(
            name for name in RUNTIME_LIKE_MEMBERS if not hasattr(fake, name)
        )
        self.assertEqual(missing, [])

    def test_fake_runtime_tick_records_the_command_and_advances_time(self) -> None:
        fake = FakeRuntime()
        reply = fake.tick(33, track_check=False)
        self.assertEqual(fake.commands, [("tick", 33)])
        self.assertEqual(fake.t_ms, 33)
        self.assertEqual(reply["t_ms"], 33)
        self.assertEqual(reply["frames"], 0)


class ContractSnapshotStubTest(unittest.TestCase):
    def test_contract_stubs_carry_the_runtime_like_surface(self) -> None:
        import contract_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            stubs = {
                "_LiveStub": contract_snapshot._LiveStub(Path(tmp)),
                "_FakeRuntime": contract_snapshot._FakeRuntime(),
            }
        for label, stub in stubs.items():
            with self.subTest(stub=label):
                missing = sorted(
                    name for name in RUNTIME_LIKE_MEMBERS
                    if not hasattr(stub, name)
                )
                self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
