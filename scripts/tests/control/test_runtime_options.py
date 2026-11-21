from __future__ import annotations

from scripts.tests import support

import sys
import tempfile
import unittest
from pathlib import Path

from scripts.tests.fake_runtime import FakeRuntime
from control import Runtime
from control.runtime import RuntimeLike

FAKE_ENGINE = support.FAKE_ENGINE


class RuntimeOptionCharacterizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sessions_root = self.root / "user" / "sessions"
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_all_eighteen_keywords_reach_the_runtime_and_the_store(
        self,
    ) -> None:
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
        self.assertEqual(rt.build_mode, "prebuilt")
        self.assertIs(rt.headless, True)
        self.assertIs(rt.window, False)
        self.assertEqual(rt.mode, "headless")
        self.assertEqual(rt.timeout, 5.0)
        self.assertEqual(rt.diff_threshold, 12)
        self.assertEqual(rt.reference, self.reference.resolve())
        self.assertEqual(rt.max_frames, 42)

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


class RuntimeLikeBehaviorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _fake_engine_runtime(self) -> Runtime:
        return Runtime(
            lvgl="9.6",
            build=False,
            record=False,
            sessions_root=self.sessions_root,
            _engine_command=[sys.executable, "-I", str(FAKE_ENGINE)],
        )

    def _exercise(self, rt: RuntimeLike) -> dict:
        rt.start()
        try:
            replies = {
                "tick": rt.tick(16, track_check=False),
                "wait": rt.wait(ms=16),
                "pointer": rt.pointer("down", 1, 2),
                "key": rt.key("press", "ENTER"),
                "encoder": rt.encoder("turn", 1),
                "mark": rt.mark("protocol"),
                "snapshot": rt.snapshot("protocol"),
            }
            self.assertTrue(rt.is_running)
            self.assertIsInstance(rt.frame_count, int)
            self.assertIsInstance(rt.t_ms, int)
            self.assertIsInstance(rt.log_tail(1), list)
            self.assertIsNotNone(rt.session_dir)
            self.assertIsNotNone(rt.session_id)
            rt.record_error(RuntimeError("recorded"))
        finally:
            rt.stop()
        self.assertFalse(rt.is_running)
        return replies

    def test_runtime_and_fake_runtime_share_the_calls_live_session_makes(
        self,
    ) -> None:
        for label, factory in (
            ("console", self._fake_engine_runtime),
            ("fake", FakeRuntime),
        ):
            with self.subTest(double=label):
                replies = self._exercise(factory())
                self.assertEqual(replies["tick"]["t_ms"], 16)
                self.assertEqual(replies["pointer"]["hit"], "fake_button")
                self.assertIs(replies["key"]["delivered"], True)
                self.assertIs(replies["encoder"]["delivered"], True)
                self.assertTrue(
                    replies["snapshot"]["file"].startswith("snapshots/")
                )

    def test_protocol_stays_out_of_public_exports(self) -> None:
        import control

        self.assertNotIn("RuntimeLike", control.__all__)
        self.assertFalse(hasattr(control, "RuntimeLike"))


class FakeRuntimeBehaviorTest(unittest.TestCase):
    def test_fake_runtime_tick_records_the_command_and_advances_time(
        self,
    ) -> None:
        fake = FakeRuntime()
        reply = fake.tick(33, track_check=False)
        self.assertEqual(fake.commands, [("tick", 33)])
        self.assertEqual(fake.t_ms, 33)
        self.assertEqual(reply["t_ms"], 33)
        self.assertEqual(reply["frames"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
