from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import http_layer
from broker import BrokerError
from build_flash import BuildFlashError
from serial_backend import SerialError


class OriginTest(unittest.TestCase):
    def test_missing_origin_is_allowed(self) -> None:
        self.assertTrue(http_layer.origin_allowed(None, 8766))
        self.assertTrue(http_layer.origin_allowed("", 8766))

    def test_local_origins_on_the_server_port(self) -> None:
        for origin in (
            "http://127.0.0.1:8766",
            "http://localhost:8766",
            "https://127.0.0.1:8766",
            "http://[::1]:8766",
        ):
            self.assertTrue(http_layer.origin_allowed(origin, 8766), origin)

    def test_foreign_or_wrong_port_is_rejected(self) -> None:
        for origin in (
            "http://evil.example:8766",
            "http://localhost:8767",
            "http://localhost",
            "file:///tmp/page.html",
        ):
            self.assertFalse(http_layer.origin_allowed(origin, 8766), origin)


class ActorTest(unittest.TestCase):
    def test_known_actors_are_normalized(self) -> None:
        self.assertEqual(http_layer.actor_from(" AI "), "ai")
        self.assertEqual(http_layer.actor_from("CLI"), "cli")

    def test_missing_or_unknown_actor(self) -> None:
        self.assertEqual(http_layer.actor_from(None), "web")
        self.assertEqual(http_layer.actor_from(""), "web")
        self.assertEqual(http_layer.actor_from("intruder"), "external")


class SafeJoinTest(unittest.TestCase):
    def test_relative_paths_stay_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.txt").write_text("x", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.txt").write_text("y", encoding="utf-8")

            self.assertEqual(
                http_layer.safe_join(root, "a.txt"),
                (root / "a.txt").resolve(),
            )
            self.assertEqual(
                http_layer.safe_join(root, "sub/b.txt"),
                (root / "sub" / "b.txt").resolve(),
            )
            self.assertEqual(http_layer.safe_join(root, ""), root.resolve())
            self.assertIsNone(http_layer.safe_join(root, "../escape.txt"))
            self.assertIsNone(
                http_layer.safe_join(root, "sub/../../escape.txt")
            )


class BodyTest(unittest.TestCase):
    def test_valid_object(self) -> None:
        body = http_layer.read_json_body(
            io.BytesIO(b'{"port":"COM12"}'),
            "17",
        )
        self.assertEqual(body, {"port": "COM12"})

    def test_empty_body(self) -> None:
        self.assertEqual(http_layer.read_json_body(io.BytesIO(b""), None), {})

    def test_invalid_json(self) -> None:
        with self.assertRaises(ValueError):
            http_layer.read_json_body(io.BytesIO(b"{nope"), "5")

    def test_non_object_json(self) -> None:
        with self.assertRaises(ValueError):
            http_layer.read_json_body(io.BytesIO(b"[1, 2]"), "6")

    def test_body_limit(self) -> None:
        with self.assertRaises(ValueError):
            http_layer.read_json_body(
                io.BytesIO(b""),
                str(http_layer.MAX_BODY + 1),
            )


class MappingTest(unittest.TestCase):
    def test_content_types(self) -> None:
        self.assertTrue(
            http_layer.content_type_for(Path("app.js")).startswith(
                "application/javascript"
            )
        )
        self.assertTrue(
            http_layer.content_type_for(Path("style.css")).startswith(
                "text/css"
            )
        )
        self.assertTrue(
            http_layer.content_type_for(Path("index.html")).startswith(
                "text/html"
            )
        )
        self.assertIn(
            http_layer.content_type_for(Path("firmware.zip")),
            ("application/zip", "application/x-zip-compressed"),
        )
        self.assertEqual(
            http_layer.content_type_for(Path("noext")),
            "application/octet-stream",
        )

    def test_query_int(self) -> None:
        self.assertEqual(http_layer.query_int({}, "since", 7), 7)
        self.assertEqual(http_layer.query_int({"since": ["3"]}, "since", 7), 3)
        with self.assertRaises(ValueError):
            http_layer.query_int({"since": ["nope"]}, "since", 7)

    def test_error_status_mapping(self) -> None:
        status, payload = http_layer.error_response(
            BrokerError("busy", code="port_busy")
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "port_busy")
        self.assertFalse(payload["ok"])

        status, payload = http_layer.error_response(
            SerialError("gone", code="not_open")
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "not_open")

        status, payload = http_layer.error_response(
            BuildFlashError("bad", code="flash_config_invalid")
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "flash_config_invalid")

        status, payload = http_layer.error_response(ValueError("bad request"))
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "bad_request")

        status, payload = http_layer.error_response(KeyError("missing"))
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "bad_request")

        status, payload = http_layer.error_response(RuntimeError("boom"))
        self.assertEqual(status, 500)
        self.assertEqual(payload["code"], "internal_error")

    def test_json_bytes_is_compact_utf8(self) -> None:
        self.assertEqual(
            http_layer.json_bytes({"ok": True, "text": "你好"}),
            json.dumps(
                {"ok": True, "text": "你好"},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )


class SseWriterTest(unittest.TestCase):
    def test_frames(self) -> None:
        stream = io.BytesIO()
        writer = http_layer.SseWriter(stream)
        writer.start()
        writer.send({"a": 1})
        writer.send({"done": True}, event="done")
        writer.ping()
        self.assertEqual(
            stream.getvalue(),
            b'retry: 1000\n\ndata: {"a":1}\n\n'
            b'event: done\ndata: {"done":true}\n\n: ping\n\n',
        )


if __name__ == "__main__":
    unittest.main()
