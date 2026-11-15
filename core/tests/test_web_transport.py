
from __future__ import annotations

import http.client
import json
import re
import struct
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from lvgl_ai.web.transport import (
    HEADER_SIZE,
    MAX_FRAME_BYTES,
    STREAM_MAGIC,
    LiveFrameHub,
    encode_frame,
)
from lvgl_ai.web.wire import page_config
from web_support import WebHarness

RGBA = bytes([10, 20, 30, 255])


class EncodeFrameTest(unittest.TestCase):
    def test_header_is_little_endian_and_followed_by_pixels(self) -> None:
        frame = encode_frame(1, 1, 7, 9, RGBA)
        self.assertEqual(len(frame), HEADER_SIZE + 4)
        magic, width, height, frame_no, t_ms = struct.unpack(
            "<4sIIII", frame[:HEADER_SIZE]
        )
        self.assertEqual(
            (magic, width, height, frame_no, t_ms),
            (STREAM_MAGIC, 1, 1, 7, 9),
        )
        self.assertEqual(frame[HEADER_SIZE:], RGBA)

    def test_rejects_a_pixel_count_that_does_not_match(self) -> None:
        with self.assertRaises(ValueError):
            encode_frame(2, 2, 1, 0, RGBA)
        with self.assertRaises(ValueError):
            encode_frame(0, 1, 1, 0, b"")


class LiveFrameHubTest(unittest.TestCase):
    def test_keeps_only_the_newest_frame(self) -> None:
        hub = LiveFrameHub()
        first = hub.publish(1, 1, 10, RGBA)
        self.assertIsNotNone(first)
        self.assertEqual(first.seq, 1)
        self.assertIs(hub.wait_next(0, timeout=0.1), first)
        self.assertIsNone(hub.wait_next(1, timeout=0.01))

        second = hub.publish(1, 1, 20, bytes([1, 2, 3, 255]))
        self.assertIsNotNone(second)
        self.assertIs(hub.wait_next(1, timeout=0.1), second)

    def test_close_wakes_waiters_and_drops_later_frames(self) -> None:
        hub = LiveFrameHub()
        hub.close()
        self.assertTrue(hub.closed)
        self.assertIsNone(hub.wait_next(0, timeout=0.1))
        self.assertIsNone(hub.publish(1, 1, 0, RGBA))

    def test_rejects_a_frame_that_does_not_match_its_dimensions(self) -> None:
        hub = LiveFrameHub()
        with self.assertRaises(ValueError):
            hub.publish(2, 2, 0, RGBA)

    def test_rejects_a_frame_larger_than_the_page_declared_limit(self) -> None:
        config = page_config()
        self.assertEqual(config["maxFrameBytes"], MAX_FRAME_BYTES)
        too_tall = config["maxFrameBytes"] // config["pixelStride"] + 1
        with self.assertRaises(ValueError):
            LiveFrameHub().publish(1, too_tall, 0, b"")


class _StreamRuntime(FakeRuntime):

    def __init__(self, session_dir: Path, width: int = 2, height: int = 1):
        super().__init__(record=False)
        self._session = session_dir
        self._width = width
        self._height = height
        self.ready = {"display": {"width": width, "height": height}}
        self.frame_count = 1
        self.t_ms = 0

    def start(self) -> _StreamRuntime:
        super().start()
        self.session_id = self._session.name
        self.session_dir = self._session
        self._session.mkdir(parents=True, exist_ok=True)
        (self._session / "live.rgba").write_bytes(
            RGBA * (self._width * self._height)
        )
        return self

    def tick(self, ms, *, track_check=True):
        self.t_ms += ms
        return {
            "seq": 0,
            "frames": self.frame_count,
            "t_ms": self.t_ms,
            "truncated": False,
        }


class LiveStreamHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.session = Path(self._tmp.name) / "20260102-030405-abcd"
        self.runtime = _StreamRuntime(self.session)
        self.harness = WebHarness(
            self._tmp.name, runtime_factory=lambda: self.runtime
        )
        self.addCleanup(self.harness.close)
        self.addCleanup(self._quiet_stop)

    def _quiet_stop(self) -> None:
        try:
            self.harness.server.app.live.stop()
        except Exception:  # noqa: BLE001 - cleanup must not mask the result
            pass

    def _start_test_live(self) -> None:
        status, _, live = self.harness.json(
            "POST", "/api/live/start?mode=test"
        )
        self.assertEqual(status, 200, live)

    def test_stream_sends_one_framed_rgba_payload(self) -> None:
        self._start_test_live()

        connection = http.client.HTTPConnection(
            self.harness.host, self.harness.port, timeout=5.0
        )
        try:
            connection.request("GET", "/api/live/stream")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(
                response.getheader("Content-Type"), "application/octet-stream"
            )
            self.assertIsNone(response.getheader("Content-Length"))
            header = response.read(HEADER_SIZE)
            self.assertEqual(len(header), HEADER_SIZE)
            magic, width, height, frame_no, _t_ms = struct.unpack(
                "<4sIIII", header
            )
            self.assertEqual(magic, STREAM_MAGIC)
            self.assertEqual((width, height), (2, 1))
            self.assertGreaterEqual(frame_no, 1)
            pixels = response.read(width * height * 4)
            self.assertEqual(pixels, RGBA * 2)
        finally:
            connection.close()

    def test_the_pages_parser_config_decodes_the_live_stream(self) -> None:
        self._start_test_live()

        status, _, html = self.harness.html("/")
        self.assertEqual(status, 200)
        self.assertEqual(
            html.count("const LIVE_WIRE ="),
            1,
            "the page must define its stream parser config exactly once",
        )
        match = re.search(r"const LIVE_WIRE = (\{.*?\});", html)
        self.assertIsNotNone(match, "the page must inject its stream parser config")
        assert match is not None
        config = json.loads(match.group(1))
        self.assertGreater(
            config["heartbeatMs"],
            0,
            "the page must keep refreshing its page id",
        )

        connection = http.client.HTTPConnection(
            self.harness.host, self.harness.port, timeout=5.0
        )
        try:
            connection.request("GET", "/api/live/stream")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            header = response.read(config["headerSize"])
            self.assertEqual(
                len(header),
                config["headerSize"],
                "the stream header must match the page's declared header size",
            )

            def uint_field(name: str) -> int:
                offset = config["headerFields"][name]
                return int.from_bytes(header[offset:offset + 4], "little")

            magic_start = config["headerFields"]["magic"]
            magic = header[magic_start:magic_start + len(config["magic"])]
            self.assertEqual(
                magic.decode("ascii"),
                config["magic"],
                "the stream magic must match the page's declared magic",
            )
            width, height = uint_field("width"), uint_field("height")
            self.assertEqual((width, height), (2, 1))
            self.assertGreaterEqual(
                uint_field("frameNo"),
                1,
                "the page must know which frame it is showing",
            )
            payload_size = width * height * config["pixelStride"]
            self.assertLessEqual(
                payload_size,
                config["maxFrameBytes"],
                "the streamed frame must fit the page's declared limit",
            )
            self.assertEqual(response.read(payload_size), RGBA * 2)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
