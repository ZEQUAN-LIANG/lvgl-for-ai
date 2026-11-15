import tempfile
import unittest
from pathlib import Path

import paths
from control import BuildError
from control.engine_guard import (
    ensure_engine_stopped,
    engine_pid_path,
    write_engine_pid,
)


class EngineGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.engine = Path(self._tmp.name) / paths.engine_filename()
        self.engine.write_bytes(b"")

    def test_stale_pid_is_removed(self) -> None:
        write_engine_pid(self.engine, 12345)
        ensure_engine_stopped(
            self.engine,
            check_alive=lambda pid: False,
            image_of=lambda pid: str(self.engine),
        )
        self.assertFalse(engine_pid_path(self.engine).exists())

    def test_live_engine_is_terminated_and_cleared(self) -> None:
        write_engine_pid(self.engine, 12345)
        state = {"alive": True}
        terminated: list[int] = []

        def terminate(pid: int) -> None:
            terminated.append(pid)
            state["alive"] = False

        ensure_engine_stopped(
            self.engine,
            timeout=0.05,
            terminate_wait=0.05,
            check_alive=lambda pid: state["alive"],
            image_of=lambda pid: str(self.engine),
            terminate=terminate,
        )
        self.assertEqual(terminated, [12345])
        self.assertFalse(engine_pid_path(self.engine).exists())

    def test_unrelated_image_is_not_terminated(self) -> None:
        write_engine_pid(self.engine, 12345)
        other = Path(self._tmp.name) / "other.exe"
        ensure_engine_stopped(
            self.engine,
            check_alive=lambda pid: True,
            image_of=lambda pid: str(other),
            terminate=lambda pid: self.fail("must not terminate"),
        )
        self.assertFalse(engine_pid_path(self.engine).exists())

    def test_unresponsive_engine_raises_and_keeps_pid(self) -> None:
        write_engine_pid(self.engine, 12345)
        with self.assertRaises(BuildError):
            ensure_engine_stopped(
                self.engine,
                timeout=0.01,
                terminate_wait=0.01,
                check_alive=lambda pid: True,
                image_of=lambda pid: str(self.engine),
                terminate=lambda pid: None,
            )
        self.assertTrue(engine_pid_path(self.engine).exists())


if __name__ == "__main__":
    unittest.main()
