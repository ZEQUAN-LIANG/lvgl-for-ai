"""Warm/cold launch decisions for the zero-console web viewer.

``open-web.vbs`` only starts ``web.pyw`` hidden; the port probe, the page URL
and the choice between reusing a running viewer and starting the server live in
Python. These tests cover that decision without a real browser, a spawned
process or any Windows-only API: the probe is exercised against real sockets
and the launcher seam is replaced where a process would start.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_ROOT.parent
PYW_LAUNCHER = TOOL_ROOT / "web.pyw"
VBS_LAUNCHER = REPO_ROOT / "open-web.vbs"

from lvgl_ai.web import DEFAULT_HOST, DEFAULT_PORT, create_server  # noqa: E402
from lvgl_ai.web import launcher  # noqa: E402
from lvgl_ai.web.urls import page_url  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((DEFAULT_HOST, 0))
        return int(sock.getsockname()[1])


def _listening_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((DEFAULT_HOST, 0))
    sock.listen(1)
    return sock


def _load_web_pyw():
    spec = importlib.util.spec_from_file_location(
        "test_web_pyw_launcher", PYW_LAUNCHER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PYW_LAUNCHER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PageUrlTest(unittest.TestCase):
    def test_default_page_url_is_the_documented_address(self) -> None:
        self.assertEqual(
            page_url(DEFAULT_HOST, DEFAULT_PORT), "http://127.0.0.1:8765/"
        )

    def test_page_url_accepts_a_bound_ephemeral_port(self) -> None:
        self.assertEqual(page_url(DEFAULT_HOST, 8766), "http://127.0.0.1:8766/")


class PortProbeTest(unittest.TestCase):
    def test_a_listening_socket_is_detected(self) -> None:
        sock = _listening_socket()
        self.addCleanup(sock.close)
        port = int(sock.getsockname()[1])
        self.assertTrue(launcher.port_is_open(DEFAULT_HOST, port))

    def test_a_closed_port_is_not_detected(self) -> None:
        port = _free_port()
        self.assertFalse(launcher.port_is_open(DEFAULT_HOST, port))

    def test_the_real_web_server_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = create_server(sessions_root=tmp, host=DEFAULT_HOST, port=0)
            self.addCleanup(server.server_close)
            port = int(server.server_address[1])
            self.assertTrue(launcher.port_is_open(DEFAULT_HOST, port))


class ReuseRunningViewerTest(unittest.TestCase):
    def test_a_running_viewer_is_reused_by_opening_its_page(self) -> None:
        with mock.patch.object(
            launcher, "port_is_open", return_value=True
        ), mock.patch.object(launcher.webbrowser, "open") as open_page:
            self.assertTrue(launcher.reuse_running_viewer())
        open_page.assert_called_once_with("http://127.0.0.1:8765/")

    def test_a_closed_port_reports_a_cold_start_without_opening(self) -> None:
        with mock.patch.object(
            launcher, "port_is_open", return_value=False
        ), mock.patch.object(launcher.webbrowser, "open") as open_page:
            self.assertFalse(launcher.reuse_running_viewer())
        open_page.assert_not_called()

    def test_a_browser_error_is_reported_instead_of_exiting_silently(self) -> None:
        with mock.patch.object(
            launcher, "port_is_open", return_value=True
        ), mock.patch.object(
            launcher.webbrowser, "open", side_effect=OSError("no browser")
        ):
            with self.assertRaises(OSError):
                launcher.reuse_running_viewer()

    def test_a_browser_that_does_not_open_is_reported(self) -> None:
        with mock.patch.object(
            launcher, "port_is_open", return_value=True
        ), mock.patch.object(
            launcher.webbrowser, "open", return_value=False
        ):
            with self.assertRaises(OSError):
                launcher.reuse_running_viewer()


class WebPywDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_web_pyw()

    def test_a_running_viewer_is_reused_without_starting_the_server(self) -> None:
        with mock.patch.object(sys, "argv", [str(PYW_LAUNCHER)]), mock.patch.object(
            self.module.launcher, "port_is_open", return_value=True
        ), mock.patch.object(
            self.module.launcher.webbrowser, "open"
        ) as open_page, mock.patch.object(
            self.module, "main"
        ) as start_server:
            self.assertEqual(self.module._run(), 0)
        open_page.assert_called_once_with("http://127.0.0.1:8765/")
        start_server.assert_not_called()

    def test_a_cold_start_runs_the_server_which_opens_the_page(self) -> None:
        with mock.patch.object(sys, "argv", [str(PYW_LAUNCHER)]), mock.patch.object(
            self.module.launcher, "port_is_open", return_value=False
        ), mock.patch.object(
            self.module.launcher.webbrowser, "open"
        ) as open_page, mock.patch.object(
            self.module, "main", return_value=0
        ) as start_server:
            self.assertEqual(self.module._run(), 0)
        open_page.assert_not_called()
        start_server.assert_called_once_with(["--open", "--exit-on-close"])

    def test_a_browser_error_shows_the_launcher_error(self) -> None:
        with mock.patch.object(sys, "argv", [str(PYW_LAUNCHER)]), mock.patch.object(
            self.module.launcher, "port_is_open", return_value=True
        ), mock.patch.object(
            self.module.launcher.webbrowser,
            "open",
            side_effect=OSError("no browser"),
        ), mock.patch.object(
            self.module, "main"
        ) as start_server, mock.patch.object(
            self.module, "_show_error"
        ) as show_error:
            self.assertEqual(self.module._run(), 1)
        start_server.assert_not_called()
        show_error.assert_called_once()
        self.assertIn("网页端启动失败", show_error.call_args.args[0])

    def test_explicit_flags_keep_the_existing_startup_path(self) -> None:
        for flags in (
            ["--app", "coffee"],
            ["--manage"],
            ["--open"],
            ["--exit-on-close"],
            ["--port", "0"],
        ):
            with self.subTest(flags=flags):
                with mock.patch.object(
                    sys, "argv", [str(PYW_LAUNCHER), *flags]
                ), mock.patch.object(
                    self.module.launcher, "port_is_open", return_value=True
                ) as probe, mock.patch.object(
                    self.module.launcher.webbrowser, "open"
                ) as open_page, mock.patch.object(
                    self.module, "main", return_value=0
                ) as start_server:
                    self.assertEqual(self.module._run(), 0)
                probe.assert_not_called()
                open_page.assert_not_called()
                start_server.assert_called_once_with(
                    ["--open", "--exit-on-close", *flags]
                )


class OpenWebVbsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = VBS_LAUNCHER.read_text(encoding="utf-8")

    def test_the_vbs_only_starts_the_python_launcher(self) -> None:
        self.assertIn("pythonw.exe -I core\\web.pyw", self.text)
        self.assertNotIn("http://", self.text)
        lowered = self.text.lower()
        for retired in ("netstat", "findstr", "cmd.exe"):
            self.assertNotIn(retired, lowered)


if __name__ == "__main__":
    unittest.main()
