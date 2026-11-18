from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import paths

GITEE_PR = paths.SCRIPTS_DIR / "gitee_pr.py"


def load_module():
    spec = importlib.util.spec_from_file_location("gitee_pr_test", GITEE_PR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {GITEE_PR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def pr_payload(title: str, body: str) -> dict[str, object]:
    return {
        "number": 24,
        "state": "open",
        "title": title,
        "body": body,
        "html_url": "https://gitee.com/o/r/pulls/24",
        "head": {"ref": "feat/x"},
        "base": {"ref": "dev"},
    }


class GiteePrTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name: str, text: str, *, encoding: str = "utf-8") -> str:
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return str(path)

    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.module.main(argv)
        return code, buffer.getvalue()

    def test_read_utf8_file_preserves_chinese(self) -> None:
        path = self.write("body.md", "## 变更\n\n固件与双链路。\n")
        text = self.module._read_utf8_file(path, "body")
        self.assertIn("变更", text)
        self.assertIn("双链路", text)

    def test_rejects_non_utf8_file(self) -> None:
        path = self.write("body.md", "变更", encoding="gbk")
        with self.assertRaises(self.module.CliError) as context:
            self.module._read_utf8_file(path, "body")
        self.assertEqual(context.exception.code, "file_not_utf8")

    def test_create_posts_utf8_form(self) -> None:
        title = "feat: 双链路"
        body = "## 变更\n\n固件 BLE + UART。\n"
        title_path = self.write("title.txt", title)
        body_path = self.write("body.md", body)
        response = FakeResponse(pr_payload(title, body))
        argv = [
            "create",
            "--repo",
            "o/r",
            "--head",
            "feat/x",
            "--base",
            "dev",
            "--title-file",
            title_path,
            "--body-file",
            body_path,
            "--json",
        ]
        with mock.patch.dict(os.environ, {"GITEE_TOKEN": "secret"}):
            with mock.patch(
                "urllib.request.urlopen", return_value=response
            ) as urlopen:
                code, output = self.run_cli(argv)
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["number"], 24)
        self.assertTrue(payload["verified"])
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "POST")
        self.assertTrue(request.full_url.endswith("/repos/o/r/pulls"))
        content_type = request.get_header("Content-type") or ""
        self.assertIn("charset=utf-8", content_type)
        form = urllib.parse.parse_qs(
            request.data.decode("utf-8"), encoding="utf-8"
        )
        self.assertEqual(form["title"], [title])
        self.assertEqual(form["body"], [body])
        self.assertEqual(form["access_token"], ["secret"])

    def test_update_patches_utf8_body(self) -> None:
        body = "## 验证\n\n中文正常。\n"
        body_path = self.write("body.md", body)
        response = FakeResponse(pr_payload("title", body))
        argv = [
            "update",
            "24",
            "--repo",
            "o/r",
            "--body-file",
            body_path,
            "--json",
        ]
        with mock.patch.dict(os.environ, {"GITEE_TOKEN": "secret"}):
            with mock.patch(
                "urllib.request.urlopen", return_value=response
            ) as urlopen:
                code, output = self.run_cli(argv)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["verified"])
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "PATCH")
        self.assertTrue(request.full_url.endswith("/pulls/24"))
        form = urllib.parse.parse_qs(
            request.data.decode("utf-8"), encoding="utf-8"
        )
        self.assertEqual(form["body"], [body])

    def test_verify_detects_replacement_chars(self) -> None:
        expected = "## 变更\n\n正常。\n"
        body_path = self.write("body.md", expected)
        response = FakeResponse(pr_payload("title", "## \ufffd\ufffd\ufffd\ufffd\n"))
        argv = [
            "verify",
            "24",
            "--repo",
            "o/r",
            "--body-file",
            body_path,
            "--json",
        ]
        with mock.patch.dict(os.environ, {"GITEE_TOKEN": "secret"}):
            with mock.patch(
                "urllib.request.urlopen", return_value=response
            ):
                code, output = self.run_cli(argv)
        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertFalse(payload["ok"])
        self.assertIn("replacement_chars", payload["issues"])
        self.assertFalse(payload["exact"])

    def test_verify_tolerates_gitee_emoji_stripping(self) -> None:
        expected = "## 变更\n\n🤖 Generated with Claude Code\n"
        body_path = self.write("body.md", expected)
        response = FakeResponse(
            pr_payload("title", "## 变更\n\n Generated with Claude Code\n")
        )
        argv = [
            "verify",
            "24",
            "--repo",
            "o/r",
            "--body-file",
            body_path,
            "--json",
        ]
        with mock.patch.dict(os.environ, {"GITEE_TOKEN": "secret"}):
            with mock.patch(
                "urllib.request.urlopen", return_value=response
            ):
                code, output = self.run_cli(argv)
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["exact"])
        self.assertEqual(payload["replacement_chars"], 0)

    def test_missing_token(self) -> None:
        title_path = self.write("title.txt", "title")
        body_path = self.write("body.md", "body")
        argv = [
            "create",
            "--repo",
            "o/r",
            "--head",
            "feat/x",
            "--title-file",
            title_path,
            "--body-file",
            body_path,
            "--json",
        ]
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITEE_TOKEN", None)
            code, output = self.run_cli(argv)
        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertEqual(payload["error"], "token_missing")

    def test_dry_run_does_not_call_api(self) -> None:
        title_path = self.write("title.txt", "title")
        body_path = self.write("body.md", "body")
        argv = [
            "create",
            "--repo",
            "o/r",
            "--head",
            "feat/x",
            "--title-file",
            title_path,
            "--body-file",
            body_path,
            "--dry-run",
            "--json",
        ]
        with mock.patch.dict(os.environ, {"GITEE_TOKEN": "secret"}):
            with mock.patch(
                "urllib.request.urlopen"
            ) as urlopen:
                code, output = self.run_cli(argv)
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        payload = json.loads(output)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["method"], "POST")

    def test_infer_repo_from_gitee_remote(self) -> None:
        for remote in (
            "https://gitee.com/o/r.git",
            "git@gitee.com:o/r.git",
        ):
            match = self.module._GITEE_REMOTE_RE.search(remote)
            self.assertIsNotNone(match)
            self.assertEqual(match.group("owner"), "o")
            self.assertEqual(match.group("repo"), "r")


if __name__ == "__main__":
    unittest.main()
