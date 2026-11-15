from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import runner
from build_flash import BuildFlashError
from jobs import Job


class FakeBroker:
    def __init__(self) -> None:
        self.detached = 0
        self.opened: list[tuple[str, int]] = []
        self.fail_open = False
        self.release = {
            "was_open": True,
            "port": "COM12",
            "baud": 1_000_000,
        }

    def detach_for_flash(self) -> dict:
        self.detached += 1
        return dict(self.release)

    def open(self, port: str, baud: int) -> dict:
        if self.fail_open:
            raise RuntimeError("no port")
        self.opened.append((port, baud))
        return {"ok": True}


class FakeState:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def record_build(self, **fields) -> None:
        self.calls.append(("record_build", fields))

    def record_open(self, **fields) -> None:
        self.calls.append(("record_open", fields))

    def update(self, **fields) -> None:
        self.calls.append(("update", fields))


def _job(kind: str = "build") -> Job:
    job = Job(kind, kind)
    job.start()
    return job


def _stream_text(job: Job, stream: str) -> list[str]:
    return [
        event["text"]
        for event in job.snapshot(0)["events"]
        if event["stream"] == stream
    ]


class RequestTest(unittest.TestCase):
    def test_build_request_normalizes_empty_fields(self) -> None:
        request = runner.BuildRequest.from_body({})
        self.assertEqual(request.app, "")
        self.assertIsNone(request.project_dir)
        self.assertIsNone(request.board)

        request = runner.BuildRequest.from_body(
            {"app": "sift_watch", "project_dir": "P", "board": "B"}
        )
        self.assertEqual(request.app, "sift_watch")
        self.assertEqual(request.project_dir, "P")
        self.assertEqual(request.board, "B")

    def test_flash_request_defaults(self) -> None:
        request = runner.FlashRequest.from_body({})
        self.assertTrue(request.reconnect)
        self.assertFalse(request.build)
        self.assertIsNone(request.verify)
        self.assertIsNone(request.erase_all)
        self.assertIsNone(request.baud)

        request = runner.FlashRequest.from_body(
            {
                "build": True,
                "port": "",
                "baud": 0,
                "verify": False,
                "erase_all": True,
                "reconnect": False,
            }
        )
        self.assertTrue(request.build)
        self.assertIsNone(request.port)
        self.assertIsNone(request.baud)
        self.assertFalse(request.verify)
        self.assertTrue(request.erase_all)
        self.assertFalse(request.reconnect)


class JobRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = FakeBroker()
        self.state = FakeState()
        self.runner = runner.JobRunner({}, self.broker, self.state)

    def test_build_records_app_state(self) -> None:
        job = _job()
        result = {"project_dir": "P", "build_dir": "B"}
        with mock.patch.object(
            runner, "run_build", return_value=result
        ) as build:
            self.runner.build(
                job,
                runner.BuildRequest.from_body({"app": "sift_watch"}),
            )
        build.assert_called_once()
        self.assertEqual(job.status, "ok")
        self.assertEqual(job.result, result)
        self.assertEqual(
            self.state.calls,
            [
                (
                    "record_build",
                    {
                        "app": "sift_watch",
                        "project_dir": "P",
                        "build_dir": "B",
                    },
                )
            ],
        )

    def test_build_without_app_updates_state(self) -> None:
        job = _job()
        result = {"project_dir": "P", "build_dir": "B"}
        with mock.patch.object(runner, "run_build", return_value=result):
            self.runner.build(job, runner.BuildRequest.from_body({}))
        self.assertEqual(self.state.calls, [("update", result)])

    def test_build_cancelled_marks_job_cancelled(self) -> None:
        job = _job()
        with mock.patch.object(
            runner,
            "run_build",
            side_effect=BuildFlashError("cancelled", code="cancelled"),
        ):
            self.runner.build(job, runner.BuildRequest.from_body({}))
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(_stream_text(job, "stderr"), ["cancelled"])

    def test_build_unexpected_error_fails_job(self) -> None:
        job = _job()
        with (
            mock.patch.object(
                runner,
                "run_build",
                side_effect=RuntimeError("boom"),
            ),
            redirect_stderr(io.StringIO()),
        ):
            self.runner.build(job, runner.BuildRequest.from_body({}))
        self.assertEqual(job.status, "failed")
        self.assertEqual(_stream_text(job, "stderr"), ["boom"])

    def test_flash_records_state_and_reconnects(self) -> None:
        job = _job("flash")
        result = {
            "port": "COM13",
            "baud": 921_600,
            "build_dir": str(Path("C:/work/project/build")),
        }
        with mock.patch.object(
            runner,
            "run_flash",
            return_value=result,
        ) as flash:
            self.runner.flash(
                job,
                runner.FlashRequest.from_body(
                    {"app": "sift_watch", "build_dir": result["build_dir"]}
                ),
            )

        self.assertEqual(self.broker.detached, 1)
        self.assertEqual(flash.call_args.kwargs["port"], "COM12")
        self.assertEqual(flash.call_args.kwargs["baud"], 1_000_000)
        self.assertEqual(
            self.state.calls,
            [
                (
                    "record_build",
                    {
                        "app": "sift_watch",
                        "project_dir": str(Path(result["build_dir"]).parent),
                        "build_dir": result["build_dir"],
                    },
                ),
                ("record_open", {"port": "COM13", "baud": 921_600}),
            ],
        )
        self.assertEqual(self.broker.opened, [("COM13", 921_600)])
        self.assertIn("serial reconnected", _stream_text(job, "status"))
        self.assertEqual(job.status, "ok")

    def test_flash_without_app_updates_state(self) -> None:
        job = _job("flash")
        result = {
            "port": "COM13",
            "baud": 1_000_000,
            "build_dir": str(Path("C:/work/project/build")),
        }
        with mock.patch.object(runner, "run_flash", return_value=result):
            self.runner.flash(
                job,
                runner.FlashRequest.from_body(
                    {"build_dir": result["build_dir"]}
                ),
            )
        self.assertEqual(self.state.calls[0][0], "update")
        self.assertEqual(
            self.state.calls[0][1]["project_dir"],
            str(Path(result["build_dir"]).parent),
        )

    def test_flash_build_first_uses_built_directory(self) -> None:
        job = _job("flash")
        built = {"build_dir": str(Path("C:/work/project/build"))}
        flashed = {
            "port": "COM13",
            "baud": 1_000_000,
            "build_dir": built["build_dir"],
        }
        with (
            mock.patch.object(
                runner,
                "run_build",
                return_value=built,
            ) as build,
            mock.patch.object(
                runner,
                "run_flash",
                return_value=flashed,
            ) as flash,
        ):
            self.runner.flash(
                job,
                runner.FlashRequest.from_body(
                    {"build": True, "app": "sift_watch"}
                ),
            )
        build.assert_called_once()
        self.assertEqual(
            flash.call_args.kwargs["build_dir"], built["build_dir"]
        )
        self.assertIn("build ok; starting flash", _stream_text(job, "status"))

    def test_flash_without_reconnect_skips_reopen(self) -> None:
        job = _job("flash")
        result = {
            "port": "COM13",
            "baud": 1_000_000,
            "build_dir": str(Path("C:/work/project/build")),
        }
        with mock.patch.object(runner, "run_flash", return_value=result):
            self.runner.flash(
                job,
                runner.FlashRequest.from_body(
                    {"build_dir": result["build_dir"], "reconnect": False}
                ),
            )
        self.assertEqual(self.broker.opened, [])

    def test_flash_reconnect_failure_is_reported(self) -> None:
        self.broker.fail_open = True
        job = _job("flash")
        result = {
            "port": "COM13",
            "baud": 1_000_000,
            "build_dir": str(Path("C:/work/project/build")),
        }
        with mock.patch.object(runner, "run_flash", return_value=result):
            self.runner.flash(
                job,
                runner.FlashRequest.from_body(
                    {"build_dir": result["build_dir"]}
                ),
            )
        self.assertEqual(job.status, "ok")
        self.assertEqual(
            _stream_text(job, "stderr"),
            ["serial reconnect failed: no port"],
        )

    def test_cancelled_flash_still_reconnects(self) -> None:
        job = _job("flash")
        with mock.patch.object(
            runner,
            "run_flash",
            side_effect=BuildFlashError("cancelled", code="cancelled"),
        ):
            self.runner.flash(
                job,
                runner.FlashRequest.from_body({"build_dir": "B"}),
            )
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(self.broker.opened, [("COM12", 1_000_000)])


if __name__ == "__main__":
    unittest.main()
