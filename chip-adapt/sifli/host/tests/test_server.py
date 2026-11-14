from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from server import HostHandler  # noqa: E402


class RouteTableTest(unittest.TestCase):
    def test_get_routes(self) -> None:
        cases = {
            "/": "_get_index",
            "/index.html": "_get_index",
            "/favicon.ico": "_get_favicon",
            "/assets/favicon.ico": "_get_favicon",
            "/api/health": "_get_health",
            "/api/ports": "_get_ports",
            "/api/status": "_get_status",
            "/api/suggest": "_get_suggest",
            "/api/events": "_get_events",
            "/api/events/stream": "_get_events_stream",
            "/api/read": "_get_read",
            "/api/stream": "_get_stream",
            "/api/jobs": "_get_jobs",
            "/api/jobs/abc": "_get_job",
            "/api/jobs/abc/stream": "_get_job",
            "/api/logs": "_get_logs",
            "/api/logs/run/serial.log": "_get_log",
            "/firmware": "_get_firmware",
            "/firmware/fw.zip": "_get_firmware",
            "/tools/sftool": "_get_flasher_redirect",
            "/tools/sftool/": "_get_flasher_index",
            "/tools/sftool/index.html": "_get_flasher_asset",
            "/vendor/xterm/xterm.js": "_get_vendor_asset",
            "/app.js": "_get_static",
            "/style.css": "_get_static",
            "/nope": None,
        }
        for path, expected in cases.items():
            self.assertEqual(HostHandler.route_for_get(path), expected, path)

    def test_post_routes(self) -> None:
        cases = {
            "/api/open": "_post_open",
            "/api/close": "_post_close",
            "/api/serial/auto_reconnect": "_post_auto_reconnect",
            "/api/serial/handoff": "_post_handoff",
            "/api/send": "_post_send",
            "/api/expect": "_post_expect",
            "/api/reset": "_post_reset",
            "/api/build": "_post_build",
            "/api/flash": "_post_flash",
            "/api/jobs/abc/cancel": "_post_job_action",
            "/api/shutdown": "_post_shutdown",
            "/api/flasher/prepare": "_post_flasher_prepare",
            "/nope": None,
        }
        for path, expected in cases.items():
            self.assertEqual(HostHandler.route_for_post(path), expected, path)

    def test_every_route_names_a_handler(self) -> None:
        names = set(HostHandler.GET_ROUTES.values())
        names.update(name for _, name in HostHandler.GET_PREFIX_ROUTES)
        names.update(HostHandler.POST_ROUTES.values())
        names.update(name for _, name in HostHandler.POST_PREFIX_ROUTES)
        names.add("_get_favicon")
        for name in names:
            self.assertTrue(callable(getattr(HostHandler, name, None)), name)


if __name__ == "__main__":
    unittest.main()
