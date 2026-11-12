from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from state import StateStore, suggest  # noqa: E402


class StateSuggestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / "user" / "app" / "sift_watch"
        self.app.mkdir(parents=True)
        (self.app / "sift_watch.c").write_text("", encoding="utf-8")
        self.project = self.root / "chip-adapt" / "sifli" / "sift_watch" / "project"
        self.project.mkdir(parents=True)
        (self.project / "SConstruct").write_text("", encoding="utf-8")
        self.build = self.project / "build_sf32lb52-lchspi-ulp_hcpu"
        self.build.mkdir()
        (self.build / "sftool_param.json").write_text(
            json.dumps({"chip": "SF32LB52", "write_flash": {"files": []}}),
            encoding="utf-8",
        )
        self.store = StateStore(self.root / ".cache" / "state.json")
        self.config = {
            "repo_root": str(self.root),
            "app": "",
            "project_dir": "",
            "default_baud": 1_000_000,
            "auto_reconnect": True,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_scan_fills_missing_state(self) -> None:
        payload = suggest(self.config, self.store)
        self.assertEqual(payload["app"], "sift_watch")
        self.assertEqual(Path(payload["build_dir"]), self.build)
        self.assertIn("sift_watch", payload["apps"])
        self.assertTrue(payload["builds"])

    def test_state_overrides_scan(self) -> None:
        self.store.record_build(
            app="sift_watch",
            project_dir=str(self.project),
            build_dir=str(self.build),
        )
        self.store.record_open(port="COM12", baud=921_600)
        payload = suggest(self.config, self.store)
        self.assertEqual(payload["app"], "sift_watch")
        self.assertEqual(payload["baud"], 921_600)
        self.assertEqual(Path(payload["project_dir"]), self.project)

    def test_stale_app_is_cleared_for_sdk_project(self) -> None:
        hello_project = self.root / "vendor" / "sdk" / "hello" / "project"
        hello_build = hello_project / "build_sf32lb52-lchspi-ulp_hcpu"
        hello_build.mkdir(parents=True)
        (hello_project / "SConstruct").write_text("", encoding="utf-8")
        (hello_build / "sftool_param.json").write_text(
            json.dumps({"chip": "SF32LB52", "write_flash": {"files": []}}),
            encoding="utf-8",
        )
        self.store.update(
            app="sift_watch",
            project_dir=str(hello_project),
            build_dir=str(hello_build),
        )
        payload = suggest(self.config, self.store)
        self.assertEqual(payload["app"], "")
        self.assertEqual(Path(payload["project_dir"]), hello_project)


if __name__ == "__main__":
    unittest.main()
