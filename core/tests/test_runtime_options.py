"""RuntimeOptions and RuntimeLike: the runtime assembly and double seams."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from lvgl_ai import Runtime
from lvgl_ai.control.runtime import RuntimeLike

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
class RuntimeOptionCharacterizationTest(unittest.TestCase):
    """Lock the 18 Runtime keywords and the SessionStore values they produce."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sessions_root = self.root / "sessions"
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_all_eighteen_keywords_reach_the_runtime_and_the_store(self) -> None:
        rt = Runtime(
            lvgl="9.5",
            app="coffee",
            width=640,
            height=480,
            build=False,
            build_mode="prebuilt",
            record=False,
            live_frame=True,
            record_changed_only=False,
            headless=True,
            window=False,
            sessions_root=self.sessions_root,
            timeout=5.0,
            diff_threshold=12,
            reference=self.reference,
            max_frames=42,
            max_log_bytes=1024,
            session_retention=None,
        )
        self.addCleanup(rt.stop)

        self.assertEqual(rt.lvgl, "9.5")
        self.assertEqual(rt.app, "coffee")
        self.assertEqual((rt.width, rt.height), (640, 480))
        self.assertIs(rt.build, False)
        self.assertEqual(rt.build_mode, "prebuilt")
        self.assertIs(rt.record, False)
        self.assertIs(rt.live_frame, True)
        self.assertIs(rt.record_changed_only, False)
        self.assertIs(rt.headless, True)
        self.assertIs(rt.window, False)
        self.assertEqual(rt.mode, "headless")
        self.assertEqual(rt.sessions_root, self.sessions_root.resolve())
        self.assertEqual(rt.timeout, 5.0)
        self.assertEqual(rt.diff_threshold, 12)
        self.assertEqual(rt.reference, self.reference.resolve())
        self.assertEqual(rt.max_frames, 42)
        self.assertEqual(rt.max_log_bytes, 1024)
        self.assertIsNone(rt.session_retention)

        store = rt._store
        self.assertEqual(store.app, "coffee")
        self.assertIs(store.build, False)
        self.assertIs(store.record, False)
        self.assertIs(store.live_frame, True)
        self.assertIs(store.record_changed_only, False)
        self.assertIsNone(store.retention)
        self.assertEqual(store.max_log_bytes, 1024)
        self.assertEqual(store.mode, "headless")
        self.assertEqual(store.sessions_root, self.sessions_root.resolve())
        self.assertEqual(store.lvgl_src.name, "9.5")


class RuntimeOptionBagRemovedTest(unittest.TestCase):
    def test_the_option_bag_and_duplicate_name_list_are_gone(self) -> None:
        from lvgl_ai.control import runtime as runtime_module

        self.assertFalse(hasattr(runtime_module, "RuntimeOptions"))
        self.assertFalse(hasattr(runtime_module, "_SESSION_OPTIONS"))
        self.assertFalse(hasattr(runtime_module, "_UNSET"))


class RuntimeLikeTest(unittest.TestCase):
    def test_protocol_members_are_the_agreed_surface(self) -> None:
        annotated = set(getattr(RuntimeLike, "__annotations__", {}))
        methods = {
            name
            for name, value in vars(RuntimeLike).items()
            if not name.startswith("_") and callable(value)
        }
        self.assertEqual(annotated | methods, RUNTIME_LIKE_MEMBERS)

    def test_protocol_stays_out_of_public_exports(self) -> None:
        import lvgl_ai

        self.assertNotIn("RuntimeLike", lvgl_ai.__all__)
        self.assertFalse(hasattr(lvgl_ai, "RuntimeLike"))

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
