from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import cli


class FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.paths: list[str] = []

    def get(self, path: str, **kwargs) -> dict:
        self.paths.append(path)
        return self.payloads.pop(0)


class ParserTest(unittest.TestCase):
    def test_every_command_parses(self) -> None:
        cases = {
            "serve": [],
            "ports": [],
            "status": [],
            "open": [],
            "close": [],
            "send": ["hello"],
            "read": [],
            "tail": [],
            "expect": ["nsh>"],
            "reset": [],
            "build": [],
            "flash": [],
            "flasher": [],
            "logs": [],
            "suggest": [],
            "auto-reconnect": ["on"],
            "events": [],
            "shutdown": [],
        }
        parser = cli.build_parser()
        self.assertEqual(
            {command.name for command in cli.COMMANDS},
            set(cases),
        )
        for name, extra in cases.items():
            args = parser.parse_args([name, *extra])
            self.assertEqual(args.command, name)
            self.assertTrue(callable(args.func))
            self.assertEqual(args.actor, "cli")
            self.assertFalse(args.json)

    def test_flash_flags(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "flash",
                "--build-dir",
                "B",
                "--actor",
                "ai",
                "--json",
                "--no-verify",
                "--erase-all",
                "--after",
                "no_reset",
                "--no-reconnect",
            ]
        )
        self.assertEqual(args.build_dir, "B")
        self.assertEqual(args.actor, "ai")
        self.assertTrue(args.json)
        self.assertIs(args.verify, False)
        self.assertIs(args.erase_all, True)
        self.assertEqual(args.after, "no_reset")
        self.assertTrue(args.no_reconnect)

        args = parser.parse_args(["flash", "--verify"])
        self.assertIs(args.verify, True)
        self.assertIsNone(args.erase_all)
        self.assertFalse(args.no_reconnect)

    def test_serve_flags(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["serve", "--host", "0.0.0.0", "--port", "9000"])
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9000)
        self.assertFalse(args.open)


class JobFollowTest(unittest.TestCase):
    def test_job_wait_prints_stdout_and_returns_terminal(self) -> None:
        client = FakeClient(
            [
                {
                    "job": {
                        "status": "running",
                        "events": [
                            {"seq": 1, "stream": "stdout", "text": "one"}
                        ],
                        "next": 1,
                    }
                },
                {
                    "job": {
                        "status": "ok",
                        "events": [
                            {"seq": 2, "stream": "stdout", "text": "two"}
                        ],
                        "next": 2,
                    }
                },
            ]
        )
        out = io.StringIO()
        with redirect_stdout(out):
            job = cli._job_wait(client, "abc", as_json=False, poll_s=0)
        self.assertEqual(job["status"], "ok")
        self.assertEqual(out.getvalue().splitlines(), ["one", "two"])
        self.assertEqual(
            client.paths,
            ["/api/jobs/abc?since=0", "/api/jobs/abc?since=1"],
        )

    def test_job_wait_routes_stderr(self) -> None:
        client = FakeClient(
            [
                {
                    "job": {
                        "status": "failed",
                        "events": [
                            {"seq": 1, "stream": "stderr", "text": "boom"}
                        ],
                        "next": 1,
                    }
                }
            ]
        )
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            job = cli._job_wait(client, "abc", as_json=False, poll_s=0)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(out.getvalue(), "")
        self.assertIn("boom", err.getvalue())

    def test_job_wait_json_prints_only_terminal_job(self) -> None:
        client = FakeClient(
            [
                {
                    "job": {
                        "status": "ok",
                        "events": [{"seq": 1, "stream": "stdout", "text": "x"}],
                        "next": 1,
                    }
                }
            ]
        )
        out = io.StringIO()
        with redirect_stdout(out):
            cli._job_wait(client, "abc", as_json=True, poll_s=0)
        self.assertIn('"status":"ok"', out.getvalue())

    def test_job_exit_codes(self) -> None:
        client = FakeClient(
            [{"job": {"status": "ok", "events": [], "next": 0}}]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli._job_exit(client, "abc", as_json=True), 0)
        client = FakeClient(
            [{"job": {"status": "failed", "events": [], "next": 0}}]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli._job_exit(client, "abc", as_json=True), 1)


if __name__ == "__main__":
    unittest.main()
