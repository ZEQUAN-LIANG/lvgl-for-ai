"""EngineLink: the engine process seam and the line protocol.

These tests drive ``EngineLink`` with scripted pipes instead of a real child
process, so out-of-order/late replies, EOF, timeouts, ready validation and
quit -> terminate -> kill can be exercised directly and quickly.
"""

from __future__ import annotations

import json
import queue
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from lvgl_ai import ProtocolError, RuntimeCrash
from lvgl_ai.control.engine_link import PROTOCOL_VERSION, EngineLink

_STOP = object()


def ready_line(**overrides: object) -> str:
    payload = {
        "protocol": PROTOCOL_VERSION,
        "ready": True,
        "seq": 0,
        "lvgl": "9.6.0",
        "lvgl_src": "/fake/lvgl-src/9.6",
        "display": {"width": 800, "height": 600},
        "mode": "headless",
        "inputs": ["real", "virtual"],
        "capabilities": ["pointer", "tick", "record"],
        "frames": 1,
        "max_frames": 600,
        "truncated": False,
    }
    payload.update(overrides)
    return json.dumps(payload)


def reply_line(seq: int, **overrides: object) -> str:
    payload = {
        "protocol": PROTOCOL_VERSION,
        "seq": seq,
        "ok": True,
        "frames": seq,
        "t_ms": seq * 16,
    }
    payload.update(overrides)
    return json.dumps(payload)


class ScriptedPipe:
    """Iterable line pipe; tests feed lines or close it to signal EOF."""

    def __init__(self) -> None:
        self._lines: queue.Queue[object] = queue.Queue()

    def feed(self, *lines: str) -> None:
        for line in lines:
            self._lines.put(line if line.endswith("\n") else line + "\n")

    def close(self) -> None:
        self._lines.put(_STOP)

    def __iter__(self) -> ScriptedPipe:
        return self

    def __next__(self) -> str:
        item = self._lines.get()
        if item is _STOP:
            raise StopIteration
        return str(item)


class ScriptedStdin:
    def __init__(self, process: ScriptedProcess) -> None:
        self.process = process
        self.lines: list[str] = []

    def write(self, text: str) -> int:
        self.lines.append(text)
        self.process.on_line(text.rstrip("\n"))
        return len(text)

    def flush(self) -> None:
        pass


class BrokenStdin:
    def write(self, text: str) -> int:
        raise BrokenPipeError("engine stdin is closed")

    def flush(self) -> None:
        pass


class ScriptedProcess:
    """Popen double with scripted stdout/stderr and controllable exit."""

    def __init__(self, *, exit_on_terminate: bool = True) -> None:
        self.stdout = ScriptedPipe()
        self.stderr = ScriptedPipe()
        self.stdin: ScriptedStdin | BrokenStdin = ScriptedStdin(self)
        self.returncode: int | None = None
        self.pid = 4321
        self.terminated = False
        self.killed = False
        self.exit_on_terminate = exit_on_terminate
        self.on_line = lambda line: None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is not None:
            return self.returncode
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.returncode is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(["engine"], timeout)
            time.sleep(0.001)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.exit_on_terminate:
            self.exit(0)

    def kill(self) -> None:
        self.killed = True
        self.exit(-9)

    def exit(self, code: int = 0) -> None:
        self.returncode = code
        self.stdout.close()
        self.stderr.close()


class EngineLinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.process = ScriptedProcess()
        self.logs: list[str] = []
        self.checks: list[tuple[str, bool, dict | None, bool]] = []
        self.ready: dict | None = None

    def _link(self, **kwargs: object) -> EngineLink:
        options = {
            "timeout": 0.5,
            "quit_timeout": 0.02,
            "log": self.logs.append,
            "on_check": self._on_check,
        }
        options.update(kwargs)
        return EngineLink(
            ["engine", "--headless"],
            env={"LVGL_AI_DEMO": "coffee"},
            cwd="C:/repo",
            process_factory=lambda command, env, cwd: self.process,
            **options,
        )

    def _on_check(
        self, command: str, ok: bool, reply: dict | None, track_check: bool
    ) -> None:
        self.checks.append((command, ok, reply, track_check))

    def _started_link(self, **kwargs: object) -> EngineLink:
        self.process.stdout.feed(ready_line())
        link = self._link(**kwargs)
        link.start()
        self.ready = link.await_ready(0.5)
        self.addCleanup(self._shutdown, link)
        return link

    def _shutdown(self, link: EngineLink) -> None:
        self.process.exit(0)
        link.shutdown(send_quit=False)

    # ---- spawn and pumps ----------------------------------------------

    def test_start_passes_command_environment_and_cwd_to_spawn(self) -> None:
        captured: dict[str, object] = {}

        def factory(command, env, cwd):
            captured.update(command=command, env=env, cwd=cwd)
            return self.process

        self.process.stdout.feed(ready_line())
        link = EngineLink(
            ["engine", "--headless"],
            env={"LVGL_AI_DEMO": "coffee"},
            cwd="C:/repo",
            process_factory=factory,
        )
        link.start()
        link.await_ready(0.5)
        self.assertEqual(captured["command"], ["engine", "--headless"])
        self.assertEqual(captured["env"], {"LVGL_AI_DEMO": "coffee"})
        self.assertEqual(captured["cwd"], "C:/repo")
        self._shutdown(link)

    def test_pumps_log_stdout_and_prefixed_stderr(self) -> None:
        self.process.stdout.feed(
            "[app] boot",
            '{"hello": "world"}',
            ready_line(),
        )
        self.process.stderr.feed("warning: x")
        link = self._link()
        link.start()
        link.await_ready(0.5)
        self._shutdown(link)

        stdout_lines = [line for line in self.logs if not line.startswith("[stderr]")]
        self.assertEqual(stdout_lines, ["[app] boot", '{"hello": "world"}'])
        self.assertIn("[stderr] warning: x", self.logs)

    def test_protocol_lines_are_not_logged(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.feed(reply_line(1))
        link.command("tick", "16")
        self._shutdown(link)
        self.assertEqual(self.logs, [])

    # ---- ready validation ---------------------------------------------

    def test_valid_ready_is_returned(self) -> None:
        link = self._started_link()
        self.assertIsNotNone(self.ready)
        self.assertEqual(self.ready["seq"], 0)
        self.assertEqual(self.ready["protocol"], PROTOCOL_VERSION)
        self.assertTrue(link.is_running)
        self.assertEqual(link.pid, 4321)

    def test_ready_frames_callback_runs_before_later_ready_checks(self) -> None:
        self.process.stdout.feed(ready_line(max_frames=-1))
        link = self._link()
        link.start()
        frames: list[int] = []
        with self.assertRaises(ProtocolError) as caught:
            link.await_ready(0.5, on_frames=frames.append)
        self.assertIn("ready.max_frames", str(caught.exception))
        self.assertEqual(frames, [1])
        self._shutdown(link)

    def test_malformed_ready_is_a_protocol_error_with_raw_and_seq(self) -> None:
        raw = json.dumps(
            {"protocol": PROTOCOL_VERSION, "ready": True, "seq": 0, "lvgl": "9.6.0"}
        )
        self.process.stdout.feed(raw)
        link = self._link()
        link.start()
        with self.assertRaises(ProtocolError) as caught:
            link.await_ready(0.5)
        self.assertEqual(caught.exception.seq, 0)
        self.assertEqual(caught.exception.raw, raw)
        self.assertIn("ready is missing", str(caught.exception))
        self._shutdown(link)

    def test_ready_display_must_be_positive_integers(self) -> None:
        cases = [
            {"width": 0, "height": 600},
            {"width": 800, "height": -1},
            {"width": True, "height": 600},
            {"width": 800, "height": 1.5},
        ]
        for display in cases:
            with self.subTest(display=display):
                self.process = ScriptedProcess()
                self.process.stdout.feed(ready_line(display=display))
                link = self._link()
                link.start()
                with self.assertRaises(ProtocolError) as caught:
                    link.await_ready(0.5)
                self.assertIn("ready.display", str(caught.exception))
                self._shutdown(link)

    def test_ready_with_a_nonzero_seq_is_rejected(self) -> None:
        self.process.stdout.feed(ready_line(seq=1))
        link = self._link()
        link.start()
        with self.assertRaises(ProtocolError) as caught:
            link.await_ready(0.5)
        self.assertIn("ready must carry seq=0", str(caught.exception))
        self._shutdown(link)

    def test_reply_before_ready_is_an_unexpected_protocol_line(self) -> None:
        self.process.stdout.feed(reply_line(1))
        link = self._link()
        link.start()
        with self.assertRaises(ProtocolError) as caught:
            link.await_ready(0.5)
        self.assertIn("unexpected protocol line before ready", str(caught.exception))
        self.assertEqual(caught.exception.seq, 1)
        self._shutdown(link)

    def test_eof_before_ready_is_a_crash_and_marks_unexpected_exit(self) -> None:
        self.process.stdout.feed("[boot] starting")
        self.process.stdout.close()
        link = self._link(log_tail=lambda: list(self.logs))
        link.start()
        with self.assertRaises(RuntimeCrash) as caught:
            link.await_ready(0.5)
        self.assertIn("closed stdout before announcing ready", str(caught.exception))
        self.assertTrue(link.unexpected_exit)
        self.assertEqual(caught.exception.log_tail, ["[boot] starting"])
        self._shutdown(link)

    # ---- request/reply sequencing -------------------------------------

    def test_late_and_duplicate_replies_are_skipped(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.feed(
            reply_line(0), reply_line(1), reply_line(1)
        )
        first = link.command("tick", "16")
        self.assertEqual(first["seq"], 1)

        self.process.on_line = lambda line: self.process.stdout.feed(reply_line(2))
        second = link.command("tick", "16")
        self.assertEqual(second["seq"], 2)

    def test_reply_with_a_higher_seq_is_a_protocol_error(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.feed(reply_line(2))
        with self.assertRaises(ProtocolError) as caught:
            link.command("tick", "16")
        self.assertIn("expected 1, got 2", str(caught.exception))
        self.assertEqual(caught.exception.seq, 2)

    def test_rejected_command_is_a_protocol_error(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.feed(
            reply_line(1, ok=False, error="unknown_command")
        )
        with self.assertRaises(ProtocolError) as caught:
            link.command("tick", "16")
        self.assertIn("engine rejected", str(caught.exception))
        self.assertIn("unknown_command", str(caught.exception))

    def test_missing_reply_times_out_as_a_runtime_crash(self) -> None:
        link = self._started_link()
        started = time.monotonic()
        with self.assertRaises(RuntimeCrash) as caught:
            link.command("tick", "16", timeout=0.05)
        self.assertGreaterEqual(time.monotonic() - started, 0.04)
        self.assertIn("engine did not reply to", str(caught.exception))
        self.assertFalse(link.unexpected_exit)

    def test_eof_during_a_reply_is_a_crash_and_marks_unexpected_exit(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.close()
        with self.assertRaises(RuntimeCrash) as caught:
            link.command("tick", "16")
        self.assertIn("exited before replying", str(caught.exception))
        self.assertTrue(link.unexpected_exit)

    def test_broken_pipe_on_send_is_a_crash_and_marks_unexpected_exit(self) -> None:
        link = self._started_link()
        self.process.stdin = BrokenStdin()
        with self.assertRaises(RuntimeCrash) as caught:
            link.command("tick", "16")
        self.assertIn("cannot send", str(caught.exception))
        self.assertTrue(link.unexpected_exit)

    def test_command_on_a_stopped_engine_is_a_crash(self) -> None:
        link = self._started_link()
        self.process.exit(3)
        with self.assertRaises(RuntimeCrash) as caught:
            link.command("tick", "16")
        self.assertIn("engine is not running", str(caught.exception))
        self.assertEqual(caught.exception.exit_code, 3)
        self.assertTrue(link.unexpected_exit)

    # ---- check accounting ---------------------------------------------

    def test_check_hook_receives_each_command_and_reply(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.feed(reply_line(1))
        reply = link.command("tick", "16")
        self.assertEqual(len(self.checks), 1)
        self.assertTrue(self.checks[0][1])
        self.assertIs(self.checks[0][2], reply)
        self.assertTrue(self.checks[0][3])

        self.process.on_line = lambda line: self.process.stdout.feed(reply_line(2))
        link.command("tick", "16", track_check=False)
        self.assertTrue(self.checks[-1][1])
        self.assertEqual(self.checks[-1][2]["seq"], 2)
        self.assertFalse(self.checks[-1][3])

    def test_failed_command_is_recorded_even_without_track_check(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self.process.stdout.feed(reply_line(5))
        with self.assertRaises(ProtocolError):
            link.command("mark", "x", track_check=False)
        self.assertFalse(self.checks[-1][1])
        self.assertIsNone(self.checks[-1][2])
        self.assertTrue(self.checks[-1][3])

    # ---- shutdown ------------------------------------------------------

    def test_shutdown_sends_quit_and_does_not_terminate(self) -> None:
        link = self._started_link()
        self.process.on_line = lambda line: self._answer_quit(line, exit_code=0)
        code = link.shutdown(send_quit=True)
        self.assertEqual(code, 0)
        self.assertFalse(self.process.terminated)
        self.assertFalse(self.process.killed)
        self.assertEqual(self.checks[-1][0], "quit")
        self.assertFalse(link.is_started)
        self.assertFalse(link.is_running)
        self.assertIsNone(link.exit_code)

    def test_shutdown_terminates_when_quit_is_not_answered(self) -> None:
        link = self._started_link()
        code = link.shutdown(send_quit=True)
        self.assertEqual(code, 0)
        self.assertTrue(self.process.terminated)
        self.assertFalse(self.process.killed)

    def test_shutdown_kills_when_terminate_is_ignored(self) -> None:
        self.process.exit_on_terminate = False
        link = self._started_link()
        code = link.shutdown(send_quit=True)
        self.assertEqual(code, -9)
        self.assertTrue(self.process.terminated)
        self.assertTrue(self.process.killed)

    def test_shutdown_without_quit_terminates_a_live_engine(self) -> None:
        link = self._started_link()
        code = link.shutdown(send_quit=False)
        self.assertEqual(code, 0)
        self.assertTrue(self.process.terminated)
        self.assertNotIn("quit", [check[0] for check in self.checks])

    # ---- crash completion ---------------------------------------------

    def test_crash_factory_carries_exit_code_tail_and_path(self) -> None:
        link = self._started_link(
            log_tail=lambda: ["last line"], log_path="engine.log"
        )
        self.process.returncode = 7
        crash = link.crash("boom")
        self.assertEqual(crash.exit_code, 7)
        self.assertEqual(crash.log_tail, ["last line"])
        self.assertEqual(crash.log_path, "engine.log")

    def test_complete_crash_fills_fields_after_the_pumps_join(self) -> None:
        self.process.stdout.feed("[boot] line", ready_line())
        link = self._link(log_tail=lambda: list(self.logs), log_path="engine.log")
        link.start()
        link.await_ready(0.5)
        self.process.on_line = lambda line: self.process.stdout.close()
        with self.assertRaises(RuntimeCrash) as caught:
            link.command("tick", "16")
        self.assertIsNone(caught.exception.exit_code)

        self.process.returncode = 3
        exit_code = link.shutdown(send_quit=False)
        self.assertEqual(exit_code, 3)
        link.complete_crash(caught.exception, exit_code=exit_code)
        self.assertEqual(caught.exception.exit_code, 3)
        self.assertEqual(caught.exception.log_tail, ["[boot] line"])
        self.assertEqual(caught.exception.log_path, "engine.log")

    def _answer_quit(self, line: str, *, exit_code: int) -> None:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "quit":
            self.process.stdout.feed(reply_line(int(parts[0])))
            self.process.exit(exit_code)


class EnginePidFileTest(unittest.TestCase):
    def test_start_writes_pid_and_shutdown_clears_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "lvgl_engine.exe"
            engine.write_bytes(b"")
            process = ScriptedProcess()
            process.exit(0)
            link = EngineLink(
                [str(engine)],
                process_factory=lambda command, env, cwd: process,
            )
            link.quit_timeout = 0.05
            link.start()
            pid_path = root / ".engine.pid"
            self.assertTrue(pid_path.is_file())
            payload = json.loads(pid_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["pid"], process.pid)
            link.shutdown(send_quit=False)
            self.assertFalse(pid_path.exists())

    def test_start_writes_the_session_identity_to_the_pid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "lvgl_engine.exe"
            engine.write_bytes(b"")
            process = ScriptedProcess()
            process.exit(0)
            link = EngineLink(
                [str(engine)],
                session_id="20260101-000000-abcd",
                app="coffee",
                process_factory=lambda command, env, cwd: process,
            )
            link.quit_timeout = 0.05
            link.start()
            payload = json.loads(
                (root / ".engine.pid").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["session_id"], "20260101-000000-abcd")
            self.assertEqual(payload["app"], "coffee")
            self.assertTrue(payload["session_id"])
            self.assertTrue(payload["app"])
            link.shutdown(send_quit=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
