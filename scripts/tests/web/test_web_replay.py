from __future__ import annotations

import paths

import contextlib
import io
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from web import DEFAULT_HOST, DEFAULT_PORT
from web import webapp as web_server
from scripts.tests.support import write_png_rgb
from scripts.tests.web_support import SESSION_ID, WebHarness, make_web_session

CONSOLE_ROOT = paths.CONSOLE_ROOT
README_PATH = CONSOLE_ROOT / "README.md"
WEB_LAUNCHER = CONSOLE_ROOT / "entrypoints" / "serve.py"

PASS_FAIL_RE = re.compile(r"\b(pass(?:ed)?|fail(?:ed)?)\b", re.IGNORECASE)
VERDICT_ZH_RE = re.compile(r"通过|失败|合格|不合格")
DETAILS_TAG_RE = re.compile(r"<details\b[^>]*>", re.IGNORECASE)


class ReplayPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root, frame_count=3)
        self.manifest = json.loads(
            (self.session / "manifest.json").read_text(encoding="utf-8")
        )
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)

    def test_get_root_returns_200_html(self) -> None:
        status, headers, html = self.harness.html("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"].lower())
        self.assertIn("<title>", html)
        self.assertIn("frame-image", html)

    def test_page_frame_count_matches_manifest_frame_count(self) -> None:
        status, _, html = self.harness.html("/")
        self.assertEqual(status, 200)
        self.assertEqual(self.manifest["frame_count"], 3)
        self.assertIn(
            f'data-frame-count="{self.manifest["frame_count"]}"', html
        )
        self.assertRegex(
            html,
            rf'id="frame-total"[^>]*>{self.manifest["frame_count"]}<',
        )
        for number in range(1, self.manifest["frame_count"] + 1):
            self.assertIn(f"/frames/{SESSION_ID}/{number:06d}.png", html)

    def test_page_exposes_frames_snapshots_and_timeline(self) -> None:
        _, _, html = self.harness.html("/")
        self.assertIn('id="frame-slider"', html)
        self.assertIn('id="frame-prev"', html)
        self.assertIn('id="frame-next"', html)
        self.assertIn('id="snapshots"', html)
        self.assertIn("001_after_click.png", html)
        self.assertIn('id="timeline"', html)
        self.assertIn("after_click", html)
        self.assertIn("lv_button", html)

    def test_diff_overlay_starts_hidden(self) -> None:
        _, _, html = self.harness.html("/")
        diff_layer = re.search(r"<div[^>]*id=\"diff-layer\"[^>]*>", html)
        self.assertIsNotNone(diff_layer)
        self.assertIn("hidden", diff_layer.group(0))
        toggle = re.search(r"<input[^>]*id=\"diff-toggle\"[^>]*>", html)
        self.assertIsNotNone(toggle)
        self.assertNotIn("checked", toggle.group(0))

    def test_page_shows_no_pass_or_fail_verdict(self) -> None:
        _, _, html = self.harness.html("/")
        self.assertIsNone(PASS_FAIL_RE.search(html))
        self.assertIsNone(VERDICT_ZH_RE.search(html))
        self.assertIn("仅证据", html)

    def test_annotation_board_has_tools_and_save(self) -> None:
        _, _, html = self.harness.html("/")
        for needle in (
            'id="annotation-form"',
            'id="annotation-save"',
            'id="annotation-text"',
            'id="draw-canvas"',
            'id="draw-tools"',
            'id="draw-colors"',
            'id="wb-colors"',
            'data-draw-color="#00c8ff"',
            'id="range-start"',
            'id="range-start-chip"',
            'data-draw-tool="paint"',
            'src="/static/fabric.min.js"',
            'id="whiteboard"',
            'id="wb-save"',
            'id="wb-ref-list"',
            'id="snapshots"',
            f"/api/sessions/{SESSION_ID}/annotations",
        ):
            self.assertIn(needle, html)
        self.assertNotIn('id="annotation-tags"', html)
        self.assertNotIn('id="wb-confirm"', html)

    def test_engine_log_is_not_rendered_in_the_page(self) -> None:
        _, _, html = self.harness.html("/")
        self.assertNotIn("[app] marker line", html)
        self.assertNotIn("engine.log", html)
        self.assertNotIn("manifest", html)
        self.assertNotIn("frame_diff", html)

    def test_session_selector_lists_the_session(self) -> None:
        _, _, html = self.harness.html("/")
        self.assertIn('name="session"', html)
        self.assertIn(f'value="{SESSION_ID}"', html)
        self.assertIn("selected", html)

    def test_empty_sessions_root_still_serves_the_page_and_live_controls(
        self,
    ) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        harness = WebHarness(empty)
        self.addCleanup(harness.close)
        status, _, html = harness.html("/")
        self.assertEqual(status, 200)
        self.assertIn("没有可回放的会话", html)
        self.assertIn('id="live-record"', html)
        self.assertIn('id="live-test"', html)

    def test_unknown_session_query_returns_404(self) -> None:
        status, headers, body = self.harness.request(
            "GET", "/?session=does-not-exist"
        )
        self.assertEqual(status, 404)
        self.assertIn("text/html", headers["Content-Type"].lower())
        self.assertIn("unknown_session", body.decode("utf-8"))

    def test_unknown_session_wins_over_app_query(self) -> None:
        status, headers, body = self.harness.request(
            "GET", "/?session=does-not-exist&app=coffee"
        )
        self.assertEqual(status, 404)
        self.assertIn("text/html", headers["Content-Type"].lower())
        self.assertIn("unknown_session", body.decode("utf-8"))


class ReplayApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(
            self.root, frame_count=3, with_reference_diffs=True
        )
        self.manifest = json.loads(
            (self.session / "manifest.json").read_text(encoding="utf-8")
        )
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)

    def test_sessions_endpoint_lists_the_session(self) -> None:
        status, _, payload = self.harness.json("GET", "/api/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["sessions"]), 1)
        entry = payload["sessions"][0]
        self.assertEqual(entry["id"], SESSION_ID)
        self.assertTrue(entry["valid"])
        self.assertEqual(entry["frame_count"], self.manifest["frame_count"])
        self.assertEqual(entry["status"], "ok")

    def test_session_detail_reports_frames_snapshots_and_annotations(
        self,
    ) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["frame_count"], self.manifest["frame_count"])
        self.assertEqual(payload["frames_available"], 3)
        self.assertEqual(len(payload["frames"]), 3)
        self.assertEqual(payload["frames"][0]["frame_no"], 1)
        self.assertEqual(payload["frames"][1]["t_ms"], 16)
        self.assertEqual(len(payload["snapshots"]), 1)
        self.assertEqual(payload["annotations_count"], 0)
        self.assertEqual(
            payload["manifest"]["schema"], "lvgl-verify-loop-session-v1"
        )

    def test_timeline_endpoint_returns_rows(self) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/timeline"
        )
        self.assertEqual(status, 200)
        types = [row["type"] for row in payload["timeline"]]
        self.assertEqual(types[0], "frame")
        self.assertIn("input", types)
        self.assertIn("mark", types)
        self.assertEqual(types[-1], "end")

    def test_diffs_endpoint_returns_frame_and_reference_rows(self) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/diffs"
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["frame_diffs"]), 2)
        self.assertEqual(payload["frame_diffs"][0]["frame_no"], 2)
        self.assertEqual(len(payload["reference_diffs"]), 3)

    def test_log_endpoint_returns_a_tail(self) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/log"
        )
        self.assertEqual(status, 200)
        self.assertIn("[app] marker line", payload["log_tail"])
        self.assertFalse(payload["log_truncated"])

    def test_frames_and_snapshots_are_served_byte_for_byte(self) -> None:
        cases = [
            (
                f"/frames/{SESSION_ID}/000001.png",
                self.session / "frames" / "000001.png",
            ),
            (
                f"/snapshots/{SESSION_ID}/001_after_click.png",
                self.session / "snapshots" / "001_after_click.png",
            ),
        ]
        for url, path in cases:
            with self.subTest(url=url):
                status, headers, body = self.harness.request("GET", url)
                self.assertEqual(status, 200)
                self.assertIn("image/png", headers["Content-Type"].lower())
                self.assertEqual(body, path.read_bytes())

    def test_unknown_paths_and_sessions_are_404_json(self) -> None:
        for path in (
            "/api/nope",
            "/api/sessions/does-not-exist",
            f"/frames/{SESSION_ID}/missing.png",
        ):
            with self.subTest(path=path):
                status, _, payload = self.harness.json("GET", path)
                self.assertEqual(status, 404, payload)
                self.assertIn("error", payload)

    def test_path_traversal_is_rejected(self) -> None:
        for path in (
            "/frames/%2e%2e%2fmanifest.json",
            f"/frames/{SESSION_ID}/..%2fmanifest.json",
            f"/frames/{SESSION_ID}/..%5cmanifest.json",
            "/frames/%2e%2e/%2e%2e/manifest.json",
        ):
            with self.subTest(path=path):
                status, _, _ = self.harness.request("GET", path)
                self.assertIn(status, (400, 404))

    def test_wrong_methods_are_405(self) -> None:
        cases = [
            ("POST", f"/api/sessions/{SESSION_ID}"),
            ("GET", "/api/live/start"),
            ("GET", "/api/live/stop"),
            ("POST", "/api/sessions"),
            ("POST", "/api/apps"),
            ("GET", "/api/apps/create"),
            ("GET", "/api/apps/trash/delete"),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                status, _, payload = self.harness.json(method, path)
                self.assertEqual(status, 405, payload)
                self.assertIn("error", payload)

    def test_replay_never_spawns_an_engine(self) -> None:
        with mock.patch(
            "subprocess.Popen",
            side_effect=AssertionError("replay must not spawn a process"),
        ):
            self.assertEqual(self.harness.html("/")[0], 200)
            self.assertEqual(self.harness.json("GET", "/api/sessions")[0], 200)
            self.assertEqual(
                self.harness.request(
                    "GET", f"/frames/{SESSION_ID}/000001.png"
                )[0],
                200,
            )
            self.assertEqual(self.harness.json("GET", "/api/live")[0], 200)


def _page_model(html: str) -> dict:
    prefix = "const MODEL = "
    for line in html.splitlines():
        if line.startswith(prefix):
            return json.loads(line[len(prefix) :].rstrip(";"))
    raise AssertionError("the page must embed MODEL")


def _write_note_with_crop(session: Path) -> None:
    regions = session / "regions"
    regions.mkdir(exist_ok=True)
    write_png_rgb(
        regions / "001_region.png",
        2,
        2,
        [(7, 7, 7), (7, 7, 7), (7, 7, 7), (7, 7, 7)],
    )
    (session / "annotations.json").write_text(
        json.dumps(
            {
                "schema": "lvgl-verify-loop-annotations-v1",
                "notes": [
                    {
                        "id": "seed-note",
                        "frame_no": 1,
                        "t_ms": 0,
                        "regions": [
                            {
                                "x": 0,
                                "y": 0,
                                "w": 1,
                                "h": 1,
                                "image": "regions/001_region.png",
                            }
                        ],
                        "tags": ["seed", "layout"],
                        "text": "existing note",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class SharedReplayModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(
            self.root, frame_count=3, with_annotations=True
        )
        _write_note_with_crop(self.session)
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)

    def test_page_model_frames_match_the_session_api(self) -> None:
        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}"
        )
        self.assertEqual(status, 200)
        _, _, html = self.harness.html(f"/?session={SESSION_ID}")
        model = _page_model(html)

        self.assertEqual(model["sessionId"], payload["id"])
        self.assertEqual(model["frameCount"], payload["frame_count"])
        self.assertEqual(model["frames"], payload["frames"])
        self.assertEqual(model["notesCount"], payload["annotations_count"])

    def test_page_snapshots_and_timeline_render_the_api_rows(self) -> None:
        _, _, payload = self.harness.json("GET", f"/api/sessions/{SESSION_ID}")
        _, _, timeline = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/timeline"
        )
        _, _, html = self.harness.html(f"/?session={SESSION_ID}")

        self.assertIn(f'src="{payload["frames"][0]["url"]}"', html)
        for snapshot in payload["snapshots"]:
            self.assertIn(f'data-snapshot-label="{snapshot["label"]}"', html)
            self.assertIn(f'data-snapshot-url="{snapshot["url"]}"', html)
        for row in timeline["timeline"]:
            self.assertIn(f"kind-{row['type']}", html)

    def test_page_renders_notes_from_the_same_annotation_document(
        self,
    ) -> None:
        _, _, annotations = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/annotations"
        )
        _, _, html = self.harness.html(f"/?session={SESSION_ID}")
        notes = annotations["annotations"]["notes"]

        self.assertEqual(len(notes), 1)
        self.assertIn(f'id="annotation-total">{len(notes)}<', html)
        self.assertEqual(
            html.count('data-note-id="seed-note"'),
            1,
            "the page must render each note exactly once",
        )
        self.assertIn(f"/frames/{SESSION_ID}/000002.png", html)
        self.assertIn('class="note-frame"', html)
        self.assertIn('class="note-delete"', html)


class NotesSingleRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root, frame_count=3)
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)

    def _post_note(self) -> dict:
        status, _, payload = self.harness.json(
            "POST",
            f"/api/sessions/{SESSION_ID}/annotations",
            payload={
                "id": "saved-note",
                "frame_no": 2,
                "t_ms": 16,
                "regions": [{"x": 0, "y": 0, "w": 2, "h": 2}],
                "tags": ["layout", "color"],
                "text": "button is too low",
            },
        )
        self.assertEqual(status, 201, payload)
        return payload

    def test_saved_note_is_rendered_by_the_server_renderer(self) -> None:
        saved = self._post_note()
        _, _, html = self.harness.html(f"/?session={SESSION_ID}")

        self.assertEqual(
            html.count('data-note-id="saved-note"'),
            1,
            "a saved note must be rendered exactly once, by the server renderer",
        )
        self.assertIn('data-note-frame="2"', html)
        self.assertIn('<span class="note-meta">帧 2 · t=16 ms</span>', html)
        self.assertIn('<span class="tags">#layout #color</span>', html)
        self.assertIn("<p>button is too low</p>", html)
        self.assertIn('<code class="note-regions">(0, 0) 2×2</code>', html)
        image = saved["note"]["regions"][0]["image"]
        filename = image.rsplit("/", 1)[-1]
        self.assertIn(f'href="/regions/{SESSION_ID}/{filename}"', html)
        self.assertIn('class="note-crop"', html)


class ReplayDegradationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.session = make_web_session(self.root, frame_count=3)
        self.harness = WebHarness(self.root)
        self.addCleanup(self.harness.close)

    def test_corrupt_timeline_page_degrades_but_the_api_reports_it(
        self,
    ) -> None:
        (self.session / "timeline.ndjson").write_text(
            "{broken\n", encoding="utf-8"
        )
        status, _, html = self.harness.html(f"/?session={SESSION_ID}")
        self.assertEqual(status, 200)
        self.assertIn("时间轴为空。", html)
        self.assertIn('data-frame-count="3"', html)
        for number in (1, 2, 3):
            self.assertIn(f"/frames/{SESSION_ID}/{number:06d}.png", html)

        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/timeline"
        )
        self.assertEqual(status, 500, payload)
        self.assertEqual(payload["error"]["code"], "internal_error")

    def test_corrupt_annotations_page_and_api_keep_their_fallbacks(
        self,
    ) -> None:
        (self.session / "annotations.json").write_text(
            "{broken\n", encoding="utf-8"
        )
        status, _, html = self.harness.html(f"/?session={SESSION_ID}")
        self.assertEqual(status, 200)
        self.assertIn("标注文件不可读", html)
        self.assertIn("暂无标注。", html)

        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}/annotations"
        )
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "annotations_unreadable")

        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["annotations_count"], 0)

    def test_note_missing_t_ms_renders_an_empty_value_like_before(
        self,
    ) -> None:
        (self.session / "annotations.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-verify-loop-annotations-v1",
                    "notes": [
                        {
                            "id": "partial",
                            "frame_no": 1,
                            "regions": [],
                            "tags": [],
                            "text": "partial note",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        status, _, html = self.harness.html(f"/?session={SESSION_ID}")
        self.assertEqual(status, 200)
        self.assertIn("帧 1 · t= ms", html)
        self.assertNotIn("t=None ms", html)

    def test_missing_frame_diffs_keeps_the_unreadable_session_notice(
        self,
    ) -> None:
        (self.session / "frame_diffs.ndjson").unlink()
        status, _, html = self.harness.html(f"/?session={SESSION_ID}")
        self.assertEqual(status, 200)
        self.assertIn("session_unreadable", html)

        status, _, payload = self.harness.json(
            "GET", f"/api/sessions/{SESSION_ID}"
        )
        self.assertEqual(status, 404, payload)
        self.assertEqual(payload["error"]["code"], "session_unreadable")


class LauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_default_port_is_fixed_and_documented(self) -> None:
        self.assertEqual(DEFAULT_PORT, 8765)
        self.assertEqual(DEFAULT_HOST, "127.0.0.1")
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("python -I console/entrypoints/serve.py", readme)
        self.assertIn("8765", readme)
        self.assertIn("http://127.0.0.1:8765/", readme)

    def test_help_works_from_another_directory_with_isolated_python(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(WEB_LAUNCHER), "--help"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("serve.py", result.stdout)
        self.assertIn("--port", result.stdout)
        self.assertIn("--exit-on-close", result.stdout)
        self.assertIn("--app", result.stdout)
        self.assertIn("--manage", result.stdout)

    def _serve_with_mock(self, **kwargs):
        fake = mock.Mock()
        fake.server_address = (DEFAULT_HOST, DEFAULT_PORT)
        fake.serve_forever.side_effect = KeyboardInterrupt
        with (
            mock.patch.object(web_server, "create_server", return_value=fake),
            mock.patch.object(web_server.webbrowser, "open") as open_browser,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(KeyboardInterrupt):
                web_server.serve(open_browser=True, **kwargs)
        return open_browser

    def test_serve_opens_page_with_app_query(self) -> None:
        open_browser = self._serve_with_mock(app="hello")
        open_browser.assert_called_once_with(
            "http://127.0.0.1:8765/?app=hello"
        )

    def test_serve_without_app_opens_base_url(self) -> None:
        open_browser = self._serve_with_mock()
        open_browser.assert_called_once_with("http://127.0.0.1:8765/")

    def test_serve_opens_page_with_manage_query(self) -> None:
        open_browser = self._serve_with_mock(manage=True)
        open_browser.assert_called_once_with("http://127.0.0.1:8765/?manage=1")

    def test_serve_combines_app_and_manage(self) -> None:
        open_browser = self._serve_with_mock(app="hello", manage=True)
        open_browser.assert_called_once_with(
            "http://127.0.0.1:8765/?app=hello&manage=1"
        )

    def test_launcher_serves_get_root_from_another_directory(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        sessions_root = self.root / "user" / "sessions"
        make_web_session(sessions_root)
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(WEB_LAUNCHER),
                "--port",
                str(port),
                "--sessions-root",
                str(sessions_root),
            ],
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.addCleanup(_terminate, process)
        url = f"http://127.0.0.1:{port}/"
        deadline = time.monotonic() + 30.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("LVGL", body)
                    break
            except (urllib.error.URLError, ConnectionError, OSError) as exc:
                last_error = exc
                time.sleep(0.1)
        else:
            process.terminate()
            out, err = process.communicate(timeout=10)
            self.fail(
                f"server did not answer: {last_error}\nstdout={out}\nstderr={err}"
            )


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
