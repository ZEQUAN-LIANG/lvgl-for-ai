from __future__ import annotations

import paths

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CONSOLE_ROOT = paths.CONSOLE_ROOT
SCRIPTS_DIR = paths.SCRIPTS_DIR
for path in (str(CONSOLE_ROOT), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import new_app
import appmgr as app_domain
from appmgr import common as app_common
from appmgr import discovery
from scenario import load_scenario

REPO_ROOT = CONSOLE_ROOT.parent
APP_C = REPO_ROOT / "user" / "app" / "app.c"
NEW_APP = SCRIPTS_DIR / "new_app.py"


class NewAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "user" / "app").mkdir(parents=True)
        (self.root / "user" / "scenarios").mkdir(parents=True)
        shutil.copy2(APP_C, self.root / "user" / "app" / "app.c")
        coffee = self.root / "user" / "app" / "coffee"
        coffee.mkdir()
        (coffee / "app.json").write_text(
            json.dumps({"entry": "coffee_create", "default": True}),
            encoding="utf-8",
        )

    @property
    def app_c(self) -> Path:
        return self.root / "user" / "app" / "app.c"

    def _main(self, *args: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = new_app.main([*args, "--repo-root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def _entries(self) -> list[discovery.AppEntry]:
        return discovery.scan_apps(self.root / "user" / "app")[0]

    def test_creates_files_without_metadata(self) -> None:
        original = self.app_c.read_bytes()
        code, out, err = self._main("hello")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertIn("[new-app] created user/app/hello/hello.c", out)

        header = (self.root / "user/app/hello/hello.h").read_text(
            encoding="utf-8"
        )
        source = (self.root / "user/app/hello/hello.c").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6",
            header,
        )
        self.assertIn("void hello_create(void);", header)
        self.assertIn('printf("[hello] created\\n");', source)
        self.assertIn('app_obj_set_name(button, "hello_button");', source)

        self.assertEqual(self.app_c.read_bytes(), original)
        self.assertFalse((self.root / "user/app/hello/app.json").exists())
        self.assertEqual(
            [entry.name for entry in self._entries()],
            ["coffee", "hello"],
        )

        scenario = load_scenario(self.root / "user/scenarios/hello.json")
        self.assertEqual(scenario["app"], "hello")
        self.assertEqual(scenario["name"], "hello")
        self.assertEqual(len(scenario["steps"]), 7)

    def test_json_is_one_line_with_expected_fields(self) -> None:
        code, out, err = self._main("hello", "--json")
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 1, out)
        payload = json.loads(lines[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["name"], "hello")
        self.assertFalse(payload["dry_run"])
        self.assertEqual(
            payload["created"],
            [
                "user/app/hello/hello.h",
                "user/app/hello/hello.c",
                "user/scenarios/hello.json",
            ],
        )
        self.assertIsNone(payload["files"]["metadata"])
        self.assertEqual(payload["updated"], [])
        self.assertTrue(payload["build_required"])
        self.assertTrue(payload["commands"])

    def test_dry_run_writes_nothing(self) -> None:
        original = self.app_c.read_bytes()
        code, out, err = self._main("hello", "--dry-run", "--json")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["updated"], [])
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertFalse((self.root / "user/scenarios/hello.json").exists())
        self.assertEqual(self.app_c.read_bytes(), original)

    def test_invalid_names_rejected(self) -> None:
        for name in (
            "Hello",
            "hello-world",
            "1hello",
            "a" * 33,
            "con",
            "com1",
        ):
            with self.subTest(name=name):
                code, _, err = self._main(name)
                self.assertEqual(code, 1)
                self.assertIn("[new-app] error:", err)
                if name not in app_domain.WINDOWS_DEVICE_NAMES:
                    self.assertFalse(
                        (self.root / "user" / "app" / name).exists()
                    )

    def test_existing_files_require_force(self) -> None:
        (self.root / "user/app/hello").mkdir()
        (self.root / "user/app/hello/keep.txt").write_text(
            "keep\n", encoding="utf-8"
        )
        original = self.app_c.read_bytes()
        code, _, err = self._main("hello")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.app_c.read_bytes(), original)

        code, _, err = self._main("hello", "--force")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "user/app/hello/keep.txt").is_file())
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())

    def test_existing_symbol_rejected(self) -> None:
        other = self.root / "user/app/other"
        other.mkdir()
        (other / "other.c").write_text(
            "void hello_create(void) { }\n",
            encoding="utf-8",
        )
        original = self.app_c.read_bytes()
        code, _, err = self._main("hello")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.app_c.read_bytes(), original)

    def test_symbol_owned_by_another_app_is_rejected(self) -> None:
        other = self.root / "user/app/other"
        other.mkdir()
        (other / "app.json").write_text(
            json.dumps({"entry": "hello_create"}), encoding="utf-8"
        )
        code, _, err = self._main("hello")
        self.assertEqual(code, 1)
        self.assertIn("already used", err)

    def test_force_is_idempotent(self) -> None:
        self.assertEqual(self._main("hello")[0], 0)
        first = (self.root / "user/app/hello/hello.c").read_bytes()
        code, out, err = self._main("hello", "--force", "--json")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["created"], [])
        self.assertEqual(payload["updated"], [])
        self.assertEqual(
            (self.root / "user/app/hello/hello.c").read_bytes(), first
        )

    def test_app_c_is_not_touched(self) -> None:
        text = self.app_c.read_text(encoding="utf-8")
        self.app_c.write_bytes(
            b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        )
        original = self.app_c.read_bytes()
        code, _, err = self._main("hello")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.app_c.read_bytes(), original)

    def test_rollback_on_write_failure(self) -> None:
        original = self.app_c.read_bytes()
        real_replace = app_common._replace_bytes

        def flaky(path: Path, data: bytes) -> None:
            if path.name == "hello.json":
                raise OSError("simulated write failure")
            real_replace(path, data)

        with mock.patch.object(
            app_common, "_replace_bytes", side_effect=flaky
        ):
            code, _, err = self._main("hello")
        self.assertEqual(code, 1)
        self.assertIn("simulated write failure", err)
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertFalse((self.root / "user/scenarios/hello.json").exists())
        self.assertEqual(self.app_c.read_bytes(), original)

    def test_missing_app_c_fails_without_files(self) -> None:
        self.app_c.unlink()
        code, _, err = self._main("hello")
        self.assertEqual(code, 1)
        self.assertIn("app.c not found", err)
        self.assertFalse((self.root / "user/app/hello").exists())
        self.assertFalse((self.root / "user/scenarios/hello.json").exists())

    def test_help_works_from_another_directory(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(NEW_APP), "--help"],
            cwd=str(Path(self._tmp.name)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("new_app.py", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--force", result.stdout)
        self.assertIn("--json", result.stdout)


if __name__ == "__main__":
    unittest.main()
