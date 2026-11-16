from __future__ import annotations

import paths

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.tests import support

CONSOLE_ROOT = paths.CONSOLE_ROOT
REPO_ROOT = CONSOLE_ROOT.parent
CLI = paths.entrypoint_path("cli.py")
SCENARIO = REPO_ROOT / "user" / "scenarios" / "settings.json"


class PrebuiltAutoSelectionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        support.ensure_host_sdk("9.6")

    def test_missing_source_auto_selects_prebuilt_and_writes_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="lvgl-verify-loop-prebuilt-") as raw:
            root = Path(raw)
            app_dir = root / "user" / "app"
            shutil.copytree(REPO_ROOT / "user" / "app", app_dir)
            work = root / "elsewhere"
            work.mkdir()
            sessions = root / "user" / "sessions"
            env = os.environ.copy()
            env["LVGL_VERIFY_LOOP_LVGL_SRC"] = str(root / "missing-lvgl")
            env["LVGL_VERIFY_LOOP_APPS_DIR"] = str(app_dir)
            env["LVGL_VERIFY_LOOP_SESSIONS_ROOT"] = str(sessions)
            env.pop("LVGL_VERIFY_LOOP_DEMO", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(CLI),
                    "--lvgl",
                    "9.6",
                    "--scenario",
                    str(SCENARIO),
                    "--json",
                ],
                cwd=str(work),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            lines = [
                line for line in result.stdout.splitlines() if line.strip()
            ]
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["status"], "ok", msg=payload.get("error"))
            session = Path(payload["session_dir"])
            for name in (
                "manifest.json",
                "timeline.ndjson",
                "frame_diffs.ndjson",
                "engine.log",
                "build.log",
            ):
                self.assertTrue((session / name).is_file(), name)
            self.assertTrue(any((session / "frames").glob("*.png")))
            self.assertTrue(any((session / "snapshots").glob("*.png")))
            build_log = (session / "build.log").read_text(
                encoding="utf-8", errors="replace"
            )
            self.assertIn("# build mode: prebuilt", build_log)
            self.assertIn("# phase: compile", build_log)
            self.assertIn("# phase: link", build_log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
