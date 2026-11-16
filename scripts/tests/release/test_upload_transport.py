from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from scripts import upload_release

ZIP_NAME = "lvgl-verify-loop-0.2.0-full-win64.zip"
ZIP_BYTES = b"zip payload"
TOKEN = "secret-token"


class _Handler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append(
            (self.command, self.path, body, dict(self.headers))
        )
        status, payload = self.server.responder(self.command, self.path, body)
        if payload is None:
            self.send_response(status)
            self.end_headers()
            return
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _handle
    do_POST = _handle
    do_PATCH = _handle
    do_DELETE = _handle

    def log_message(self, *args) -> None:
        pass


class FakeService:
    def __init__(self, responder) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.responder = responder
        self.httpd.requests = []
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True
        )
        self.thread.start()
        host, port = self.httpd.server_address[:2]
        self.base = f"http://{host}:{port}"

    @property
    def requests(self):
        return self.httpd.requests

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def split(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urllib.parse.urlsplit(path)
    return parsed.path, urllib.parse.parse_qs(parsed.query)


class UploadTransportTest(unittest.TestCase):
    def make_asset(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / ZIP_NAME
        path.write_bytes(ZIP_BYTES)
        return directory, path

    def test_github_creates_a_missing_release_and_uploads(self) -> None:
        def responder(method, path, body):
            route, _query = split(path)
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/tags/v0.2.0"
            ):
                return 404, {"message": "not found"}
            if method == "POST" and route == "/repos/acme/repo/releases":
                return 201, {
                    "id": 42,
                    "html_url": "https://example.test/releases/v0.2.0",
                    "assets": [],
                }
            if (
                method == "POST"
                and route == "/repos/acme/repo/releases/42/assets"
            ):
                return 201, {"size": len(body)}
            raise AssertionError(f"unexpected {method} {path}")

        service = FakeService(responder)
        self.addCleanup(service.close)
        _directory, asset = self.make_asset()

        url = upload_release.upload_github(
            repo="acme/repo",
            tag="v0.2.0",
            version="0.2.0",
            notes="release notes",
            assets=[asset],
            token=TOKEN,
            replace=False,
            dry_run=False,
            api_base=service.base,
            uploads_base=service.base,
        )

        self.assertEqual(url, "https://example.test/releases/v0.2.0")
        self.assertEqual(
            [
                (method, split(path)[0])
                for method, path, _body, _headers in service.requests
            ],
            [
                ("GET", "/repos/acme/repo/releases/tags/v0.2.0"),
                ("POST", "/repos/acme/repo/releases"),
                ("POST", "/repos/acme/repo/releases/42/assets"),
            ],
        )
        create_body = json.loads(service.requests[1][2].decode("utf-8"))
        self.assertEqual(create_body["tag_name"], "v0.2.0")
        self.assertEqual(create_body["name"], "LVGL Verify Loop 0.2.0")
        self.assertEqual(create_body["body"], "release notes")
        self.assertFalse(create_body["draft"])
        self.assertFalse(create_body["prerelease"])
        _route, query = split(service.requests[2][1])
        self.assertEqual(query["name"], [ZIP_NAME])
        self.assertEqual(service.requests[2][2], ZIP_BYTES)
        self.assertEqual(
            service.requests[1][3].get("Authorization"), f"Bearer {TOKEN}"
        )

    def test_github_updates_an_existing_release(self) -> None:
        def responder(method, path, body):
            route, _query = split(path)
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/tags/v0.2.0"
            ):
                return 200, {
                    "id": 7,
                    "html_url": "https://example.test/old",
                    "assets": [],
                }
            if method == "PATCH" and route == "/repos/acme/repo/releases/7":
                return 200, {"id": 7}
            if (
                method == "POST"
                and route == "/repos/acme/repo/releases/7/assets"
            ):
                return 201, {"size": len(body)}
            raise AssertionError(f"unexpected {method} {path}")

        service = FakeService(responder)
        self.addCleanup(service.close)
        _directory, asset = self.make_asset()

        upload_release.upload_github(
            repo="acme/repo",
            tag="v0.2.0",
            version="0.2.0",
            notes="new notes",
            assets=[asset],
            token=TOKEN,
            replace=False,
            dry_run=False,
            api_base=service.base,
            uploads_base=service.base,
        )

        self.assertEqual(
            [method for method, _path, _body, _headers in service.requests],
            ["GET", "PATCH", "POST"],
        )
        patch_body = json.loads(service.requests[1][2].decode("utf-8"))
        self.assertEqual(
            patch_body, {"name": "LVGL Verify Loop 0.2.0", "body": "new notes"}
        )

    def test_github_replace_deletes_the_same_named_asset(self) -> None:
        def responder(method, path, body):
            route, _query = split(path)
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/tags/v0.2.0"
            ):
                return 200, {
                    "id": 7,
                    "html_url": "https://example.test/release",
                    "assets": [{"name": ZIP_NAME, "id": 99, "size": 1}],
                }
            if method == "PATCH" and route == "/repos/acme/repo/releases/7":
                return 200, {"id": 7}
            if (
                method == "DELETE"
                and route == "/repos/acme/repo/releases/assets/99"
            ):
                return 204, None
            if (
                method == "POST"
                and route == "/repos/acme/repo/releases/7/assets"
            ):
                return 201, {"size": len(body)}
            raise AssertionError(f"unexpected {method} {path}")

        service = FakeService(responder)
        self.addCleanup(service.close)
        _directory, asset = self.make_asset()

        upload_release.upload_github(
            repo="acme/repo",
            tag="v0.2.0",
            version="0.2.0",
            notes=None,
            assets=[asset],
            token=TOKEN,
            replace=True,
            dry_run=False,
            api_base=service.base,
            uploads_base=service.base,
        )

        self.assertEqual(
            [method for method, _path, _body, _headers in service.requests],
            ["GET", "PATCH", "DELETE", "POST"],
        )
        self.assertEqual(
            split(service.requests[2][1])[0],
            "/repos/acme/repo/releases/assets/99",
        )

    def test_gitee_creates_a_missing_release_and_uploads(self) -> None:
        def responder(method, path, body):
            route, query = split(path)
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/tags/v0.2.0"
            ):
                return 404, {"message": "not found"}
            if method == "POST" and route == "/repos/acme/repo/releases":
                return 201, {"id": 9}
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/9/attach_files"
            ):
                return 200, []
            if (
                method == "POST"
                and route == "/repos/acme/repo/releases/9/attach_files"
            ):
                return 201, {"id": 1}
            raise AssertionError(f"unexpected {method} {path}")

        service = FakeService(responder)
        self.addCleanup(service.close)
        _directory, asset = self.make_asset()

        url = upload_release.upload_gitee(
            repo="acme/repo",
            tag="v0.2.0",
            version="0.2.0",
            notes="gitee notes",
            target_commitish=None,
            assets=[asset],
            token=TOKEN,
            replace=False,
            dry_run=False,
            api_base=service.base,
        )

        self.assertEqual(
            url, "https://gitee.com/acme/repo/releases/tag/v0.2.0"
        )
        self.assertEqual(
            [
                (method, split(path)[0])
                for method, path, _body, _headers in service.requests
            ],
            [
                ("GET", "/repos/acme/repo/releases/tags/v0.2.0"),
                ("POST", "/repos/acme/repo/releases"),
                ("GET", "/repos/acme/repo/releases/9/attach_files"),
                ("POST", "/repos/acme/repo/releases/9/attach_files"),
            ],
        )
        for method, path, _body, _headers in service.requests:
            _route, query = split(path)
            if method in ("GET", "POST") and path:
                self.assertEqual(query.get("access_token"), [TOKEN])
        create_form = urllib.parse.parse_qs(
            service.requests[1][2].decode("utf-8")
        )
        self.assertEqual(create_form["tag_name"], ["v0.2.0"])
        self.assertEqual(create_form["name"], ["LVGL Verify Loop 0.2.0"])
        self.assertEqual(create_form["body"], ["gitee notes"])
        self.assertEqual(create_form["target_commitish"], ["dev"])
        multipart = service.requests[3][2]
        self.assertIn(
            b'name="file"; filename="' + ZIP_NAME.encode() + b'"', multipart
        )
        self.assertIn(ZIP_BYTES, multipart)

    def test_gitee_updates_and_replaces_an_existing_attachment(self) -> None:
        def responder(method, path, body):
            route, _query = split(path)
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/tags/v0.2.0"
            ):
                return 200, {"id": 9}
            if method == "PATCH" and route == "/repos/acme/repo/releases/9":
                return 200, {"id": 9}
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/9/attach_files"
            ):
                return 200, [{"name": ZIP_NAME, "id": 3}]
            if (
                method == "DELETE"
                and route == "/repos/acme/repo/releases/9/attach_files/3"
            ):
                return 204, None
            if (
                method == "POST"
                and route == "/repos/acme/repo/releases/9/attach_files"
            ):
                return 201, {"id": 4}
            raise AssertionError(f"unexpected {method} {path}")

        service = FakeService(responder)
        self.addCleanup(service.close)
        _directory, asset = self.make_asset()

        upload_release.upload_gitee(
            repo="acme/repo",
            tag="v0.2.0",
            version="0.2.0",
            notes="updated",
            target_commitish="dev",
            assets=[asset],
            token=TOKEN,
            replace=True,
            dry_run=False,
            api_base=service.base,
        )

        self.assertEqual(
            [method for method, _path, _body, _headers in service.requests],
            ["GET", "PATCH", "GET", "DELETE", "POST"],
        )
        patch_form = urllib.parse.parse_qs(
            service.requests[1][2].decode("utf-8")
        )
        self.assertEqual(patch_form["body"], ["updated"])
        self.assertEqual(patch_form["target_commitish"], ["dev"])

    def test_gitee_update_without_notes_reuses_the_online_body(self) -> None:
        def responder(method, path, body):
            route, _query = split(path)
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/tags/v0.2.0"
            ):
                return 200, {"id": 9, "body": "online body"}
            if method == "PATCH" and route == "/repos/acme/repo/releases/9":
                return 200, {"id": 9}
            if (
                method == "GET"
                and route == "/repos/acme/repo/releases/9/attach_files"
            ):
                return 200, []
            if (
                method == "POST"
                and route == "/repos/acme/repo/releases/9/attach_files"
            ):
                return 201, {"id": 4}
            raise AssertionError(f"unexpected {method} {path}")

        service = FakeService(responder)
        self.addCleanup(service.close)
        _directory, asset = self.make_asset()

        upload_release.upload_gitee(
            repo="acme/repo",
            tag="v0.2.0",
            version="0.2.0",
            notes=None,
            target_commitish=None,
            assets=[asset],
            token=TOKEN,
            replace=False,
            dry_run=False,
            api_base=service.base,
        )

        self.assertEqual(
            [method for method, _path, _body, _headers in service.requests],
            ["GET", "PATCH", "GET", "POST"],
        )
        patch_form = urllib.parse.parse_qs(
            service.requests[1][2].decode("utf-8")
        )
        self.assertEqual(patch_form["body"], ["online body"])


class TransportInjectionTest(unittest.TestCase):
    def test_custom_transport_receives_the_requests(self) -> None:
        calls = []

        class FakeTransport:
            def request(
                self,
                method,
                url,
                *,
                token,
                bearer=False,
                data=None,
                content_type=None,
                allow_404=False,
            ):
                calls.append((method, url, bearer, data))
                if method == "GET":
                    return 404, None
                if method == "POST" and url.endswith("/releases"):
                    return 201, {"id": 5, "assets": []}
                return 201, {"size": 1}

        with tempfile.TemporaryDirectory() as raw:
            asset = Path(raw) / ZIP_NAME
            asset.write_bytes(ZIP_BYTES)
            upload_release.upload_github(
                repo="acme/repo",
                tag="v0.2.0",
                version="0.2.0",
                notes=None,
                assets=[asset],
                token=TOKEN,
                replace=False,
                dry_run=False,
                transport=FakeTransport(),
            )
        self.assertEqual(
            [method for method, _url, _bearer, _data in calls],
            ["GET", "POST", "POST"],
        )
        self.assertTrue(calls[0][2])

    def test_dry_run_does_not_use_the_network(self) -> None:
        def responder(method, path, body):
            raise AssertionError(
                f"dry run touched the network: {method} {path}"
            )

        service = FakeService(responder)
        self.addCleanup(service.close)
        with tempfile.TemporaryDirectory() as raw:
            (Path(raw) / ZIP_NAME).write_bytes(ZIP_BYTES)
            stdout = io.StringIO()
            with (
                mock.patch.object(upload_release, "GITHUB_API", service.base),
                mock.patch.object(
                    upload_release, "GITHUB_UPLOADS", service.base
                ),
                mock.patch.object(upload_release, "GITEE_API", service.base),
                mock.patch.dict(os.environ, {}, clear=True),
                contextlib.redirect_stdout(stdout),
            ):
                code = upload_release.main(
                    [
                        "--dry-run",
                        "--assets-dir",
                        raw,
                        "--version",
                        "0.2.0",
                        "--json",
                    ]
                )
        self.assertEqual(code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["version"], "0.2.0")
        self.assertEqual(service.requests, [])

    def test_missing_token_fails_before_the_network(self) -> None:
        def responder(method, path, body):
            raise AssertionError(
                f"token check touched the network: {method} {path}"
            )

        service = FakeService(responder)
        self.addCleanup(service.close)
        with tempfile.TemporaryDirectory() as raw:
            (Path(raw) / ZIP_NAME).write_bytes(ZIP_BYTES)
            stderr = io.StringIO()
            with (
                mock.patch.object(upload_release, "GITHUB_API", service.base),
                mock.patch.object(
                    upload_release, "GITHUB_UPLOADS", service.base
                ),
                mock.patch.dict(os.environ, {}, clear=True),
                contextlib.redirect_stderr(stderr),
            ):
                code = upload_release.main(
                    [
                        "--assets-dir",
                        raw,
                        "--version",
                        "0.2.0",
                        "--target",
                        "github",
                    ]
                )
        self.assertEqual(code, 1)
        self.assertIn("GITHUB_TOKEN", stderr.getvalue())
        self.assertEqual(service.requests, [])


if __name__ == "__main__":
    unittest.main()
