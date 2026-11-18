from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import build_flash
from config import ensure_runtime_dirs, load_config
from server import HostHandler, HostServer


def write_project_build(
    project: Path,
    *,
    board: str = "sf32lb52-lchspi-ulp",
) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    (project / "SConstruct").write_text("", encoding="utf-8")
    build = project / f"build_{board}_hcpu"
    build.mkdir(parents=True, exist_ok=True)
    (build / "bootloader.bin").write_bytes(b"B" * 32)
    (build / "main.bin").write_bytes(b"M" * 64)
    (build / "sftool_param.json").write_text(
        json.dumps(
            {
                "chip": "SF32LB52",
                "memory": "NOR",
                "write_flash": {
                    "verify": True,
                    "files": [
                        {
                            "path": "bootloader.bin",
                            "address": "0x12010000",
                        },
                        {
                            "path": "main.bin",
                            "address": "0x12020000",
                        },
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return build


class FlashPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.build = write_project_build(self.project)
        self.exports = self.root / "exports"
        self.sftool = self.root / "sftool.exe"
        self.sftool.write_bytes(b"")
        self.config = {
            "repo_root": str(self.root),
            "board": "sf32lb52-lchspi-ulp",
            "exports_root": str(self.exports),
            "project_dir": "",
            "sftool": str(self.sftool),
            "toolchain_root": str(self.root / "toolchain"),
            "sdk_root": str(self.root / "sdk"),
            "flash_baud": 1_000_000,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_plan_from_build_dir(self) -> None:
        plan = build_flash.flash_plan(
            self.config,
            build_dir=self.build,
        )
        self.assertEqual(plan["chip"], "SF32LB52")
        self.assertEqual(plan["memory"], "nor")
        self.assertEqual(len(plan["entries"]), 2)
        self.assertEqual(
            [entry["address"] for entry in plan["entries"]],
            ["0x12010000", "0x12020000"],
        )
        self.assertEqual(plan["entries"][0]["size"], 32)
        self.assertEqual(plan["build_dir"], str(self.build.resolve()))

    def test_plan_from_project(self) -> None:
        plan = build_flash.flash_plan(
            self.config,
            project_dir=self.project,
        )
        self.assertEqual(plan["build_dir"], str(self.build.resolve()))
        self.assertEqual(len(plan["entries"]), 2)

    def test_plan_from_app(self) -> None:
        exported = self.exports / "demo" / "project"
        build = write_project_build(exported)
        plan = build_flash.flash_plan(self.config, app="demo")
        self.assertEqual(plan["build_dir"], str(build.resolve()))
        self.assertEqual(plan["app"], "demo")

    def test_app_wins_over_stale_project_dir(self) -> None:
        exported = self.exports / "demo" / "project"
        build = write_project_build(exported)
        plan = build_flash.flash_plan(
            self.config,
            app="demo",
            project_dir=self.project,
        )
        self.assertEqual(plan["build_dir"], str(build.resolve()))

    def test_plan_requires_source(self) -> None:
        with self.assertRaises(build_flash.BuildFlashError):
            build_flash.flash_plan(self.config)

    def test_environment_reports_sftool(self) -> None:
        payload = build_flash.flash_environment(self.config)
        self.assertEqual(payload["backend"]["kind"], "sftool")
        self.assertTrue(payload["backend"]["found"])
        self.assertEqual(payload["sources"], ["build_dir", "project"])
        self.assertIn("soft_reset", payload["options"]["after"])
        self.assertEqual(payload["default_baud"], 1_000_000)

    def test_environment_handles_missing_sftool(self) -> None:
        error = build_flash.BuildFlashError(
            "missing",
            code="sftool_missing",
        )
        with mock.patch(
            "build_flash.find_sftool",
            side_effect=error,
        ):
            payload = build_flash.flash_environment(self.config)
        self.assertFalse(payload["backend"]["found"])
        self.assertIn("hint", payload)


def read_bytes(url: str) -> tuple[int, bytes, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return (
            response.status,
            response.read(),
            response.headers.get("Content-Type", ""),
        )


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class FlashWebHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.build = write_project_build(self.project)
        self.sftool = self.root / "sftool.exe"
        self.sftool.write_bytes(b"")
        self.config = load_config()
        self.config.update(
            {
                "log_dir": str(self.root / "logs"),
                "firmware_cache_dir": str(self.root / "firmware"),
                "web_flasher_dir": str(self.root / "flasher"),
                "exports_root": str(self.root / "exports"),
                "project_dir": "",
                "sftool": str(self.sftool),
            }
        )
        ensure_runtime_dirs(self.config)
        self.server = HostServer(
            ("127.0.0.1", 0),
            HostHandler,
            self.config,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.broker.close()
        self.temp.cleanup()

    def test_shared_page_is_served(self) -> None:
        status, body, content_type = read_bytes(f"{self.base}/flash/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("烧录器".encode("utf-8"), body)

        status, body, content_type = read_bytes(
            f"{self.base}/flash/flasher.js"
        )
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)
        self.assertIn(b"/api/flash/env", body)

    def test_env_and_plan(self) -> None:
        status, body, _ = read_bytes(f"{self.base}/api/flash/env")
        self.assertEqual(status, 200)
        env = json.loads(body.decode("utf-8"))["env"]
        self.assertEqual(env["backend"]["kind"], "sftool")
        self.assertEqual(env["sources"], ["build_dir", "project"])

        status, plan = post_json(
            f"{self.base}/api/flash/plan",
            {"build_dir": str(self.build)},
        )
        self.assertEqual(status, 200)
        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["entries"]), 2)
        self.assertEqual(plan["entries"][0]["name"], "bootloader.bin")


if __name__ == "__main__":
    unittest.main()
