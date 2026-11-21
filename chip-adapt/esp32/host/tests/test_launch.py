from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import launch  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ProbeTest(unittest.TestCase):
    def test_returns_status_of_our_host(self) -> None:
        payload = {"ok": True, "transport": "dual"}
        with mock.patch(
            "launch.urllib.request.urlopen", return_value=FakeResponse(payload)
        ):
            self.assertEqual(launch.probe("http://127.0.0.1:8767"), payload)

    def test_none_when_nothing_listens(self) -> None:
        error = urllib.error.URLError("connection refused")
        with mock.patch("launch.urllib.request.urlopen", side_effect=error):
            self.assertIsNone(launch.probe("http://127.0.0.1:8767"))

    def test_none_for_a_foreign_service(self) -> None:
        with mock.patch(
            "launch.urllib.request.urlopen",
            return_value=FakeResponse({"hello": "world"}),
        ):
            self.assertIsNone(launch.probe("http://127.0.0.1:8767"))

    def test_none_for_invalid_json(self) -> None:
        class Broken(FakeResponse):
            def read(self) -> bytes:
                return b"<html>not json</html>"

        with mock.patch(
            "launch.urllib.request.urlopen", return_value=Broken({})
        ):
            self.assertIsNone(launch.probe("http://127.0.0.1:8767"))


class CommandTest(unittest.TestCase):
    def test_default_args(self) -> None:
        args = launch.parse_args([])
        self.assertEqual(args.port, launch.DEFAULT_PORT)
        self.assertFalse(args.fake)
        self.assertEqual(args.transport, "")

    def test_host_command_targets_host_serve(self) -> None:
        args = launch.parse_args(["--port", "8799"])
        with (
            mock.patch("launch.open_host_log", return_value=mock.MagicMock()),
            mock.patch(
                "launch.subprocess.Popen", return_value=mock.MagicMock()
            ) as popen,
        ):
            launch.start_host(args)
        command = popen.call_args[0][0]
        self.assertEqual(Path(command[2]).name, "host.py")
        self.assertIn("serve", command)
        self.assertIn("--http-port", command)
        self.assertIn("8799", command)
        self.assertNotIn("--fake", command)

    def test_host_command_passes_fake_and_transport(self) -> None:
        args = launch.parse_args(
            ["--fake", "--transport", "ble", "--port", "8799"]
        )
        with (
            mock.patch("launch.open_host_log", return_value=mock.MagicMock()),
            mock.patch(
                "launch.subprocess.Popen", return_value=mock.MagicMock()
            ) as popen,
        ):
            launch.start_host(args)
        command = popen.call_args[0][0]
        self.assertIn("--fake", command)
        self.assertEqual(command[command.index("--transport") + 1], "ble")

    def test_host_python_is_windowed(self) -> None:
        name = Path(launch.windowed_python()).name
        self.assertIn(name, ("pythonw.exe", "python.exe"))


class WaitForHostTest(unittest.TestCase):
    def test_true_as_soon_as_probe_succeeds(self) -> None:
        with mock.patch("launch.probe", return_value={"transport": "dual"}):
            self.assertTrue(launch.wait_for_host("http://x", None, 5.0))

    def test_false_when_the_host_process_dies(self) -> None:
        process = mock.MagicMock()
        process.poll.return_value = 1
        with mock.patch("launch.probe", return_value=None):
            self.assertFalse(launch.wait_for_host("http://x", process, 5.0))

    def test_false_after_timeout(self) -> None:
        with (
            mock.patch("launch.probe", return_value=None),
            mock.patch("launch.time.sleep"),
        ):
            self.assertFalse(launch.wait_for_host("http://x", None, 0.0))


class StopHostTest(unittest.TestCase):
    def test_terminates_a_running_host(self) -> None:
        process = mock.MagicMock()
        process.poll.return_value = None
        launch.stop_host(process)
        process.terminate.assert_called_once()

    def test_kills_when_terminate_times_out(self) -> None:
        process = mock.MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [
            launch.subprocess.TimeoutExpired("host", 1),
            0,
        ]
        launch.stop_host(process)
        process.kill.assert_called_once()

    def test_ignores_a_finished_host(self) -> None:
        process = mock.MagicMock()
        process.poll.return_value = 0
        launch.stop_host(process)
        process.terminate.assert_not_called()

    def test_none_is_a_no_op(self) -> None:
        launch.stop_host(None)


if __name__ == "__main__":
    unittest.main()
