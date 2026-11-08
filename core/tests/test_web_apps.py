"""HTTP tests for the app manager: list, tree, create, trash, restore, purge."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fake_runtime import FakeRuntime
from web_support import WebHarness

TOOL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_ROOT.parent
APP_C = REPO_ROOT / "user" / "app" / "app.c"
REQUEST_HEADER = "X-LVGL-AI-Request"


class WebAppsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "user" / "app").mkdir(parents=True)
        (self.root / "user" / "scenarios").mkdir(parents=True)
        shutil.copy2(APP_C, self.root / "user" / "app" / "app.c")
        self.sessions = Path(self._tmp.name) / "sessions"
        self.sessions.mkdir()
        self.harness = WebHarness(
            self.sessions,
            repo_root=self.root,
            scenarios_dir=self.root / "user" / "scenarios",
            runtime_factory=lambda: FakeRuntime(),
        )
        self.addCleanup(self.harness.close)

    def _write_scenario(self, name: str, app: str) -> None:
        path = self.root / "user" / "scenarios" / f"{name}.json"
        path.write_text(
            json.dumps({
                "schema": "lvgl-ai-scenario-v1",
                "name": name,
                "app": app,
                "steps": [{"type": "wait", "ms": 16}],
            }),
            encoding="utf-8",
        )

    def _post(self, path: str, payload: dict):
        return self.harness.json(
            "POST", path, payload=payload, headers={REQUEST_HEADER: "1"}
        )

    def _create(self, name: str):
        return self._post("/api/apps/create", {"name": name})

    def test_list_and_tree_use_the_temp_repo(self) -> None:
        status, _, payload = self.harness.json("GET", "/api/apps")
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["app_c_present"])
        names = {entry["name"] for entry in payload["apps"]}
        self.assertIn("coffee", names)
        self.assertIn("spectrum", names)
        self.assertEqual(payload["roots"]["app"], "user/app")
        self.assertIn("trash", payload)

        status, _, created = self._create("hello")
        self.assertEqual(status, 201, created)
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        status, _, tree = self.harness.json(
            "GET", "/api/apps/tree?name=hello"
        )
        self.assertEqual(status, 200, tree)
        self.assertTrue(tree["registered"])
        self.assertEqual(tree["tree"]["type"], "dir")
        child_names = {child["name"] for child in tree["tree"]["children"]}
        self.assertIn("hello.c", child_names)

        status, _, payload = self.harness.json("GET", "/api/apps")
        self.assertEqual(payload["last_operation"]["action"], "create")

    def test_create_conflicts_and_reserved_names(self) -> None:
        self.assertEqual(self._create("hello")[0], 201)
        status, _, payload = self._create("hello")
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "app_exists")

        status, _, payload = self._create("coffee")
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "name_reserved")

        status, _, payload = self._create("Bad-Name")
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_name")

    def test_mutation_header_and_content_type_guards(self) -> None:
        status, _, payload = self.harness.json(
            "POST", "/api/apps/create", payload={"name": "hello"}
        )
        self.assertEqual(status, 403, payload)
        self.assertEqual(payload["error"]["code"], "invalid_request_header")

        status, _, payload = self.harness.request(
            "POST",
            "/api/apps/create",
            raw=b'{"name":"hello"}',
            headers={
                "Content-Type": "text/plain",
                REQUEST_HEADER: "1",
            },
        )
        self.assertEqual(status, 415)
        self.assertEqual(
            json.loads(payload.decode("utf-8"))["error"]["code"],
            "unsupported_media_type",
        )

    def test_delete_trash_restore_and_purge(self) -> None:
        self.assertEqual(self._create("hello")[0], 201)
        self._write_scenario("hello_alt", "hello")
        status, _, deleted = self._post(
            "/api/apps/delete", {"name": "hello"}
        )
        self.assertEqual(status, 200, deleted)
        self.assertEqual(deleted["action"], "delete")
        self.assertTrue((self.root / deleted["trash_dir"] / "meta.json").is_file())
        self.assertFalse((self.root / "user/app/hello").exists())
        status, _, payload = self.harness.json("GET", "/api/apps")
        self.assertEqual(payload["trash"][0]["name"], "hello")

        status, _, restored = self._post(
            "/api/apps/trash/restore", {"trash_id": deleted["trash_id"]}
        )
        self.assertEqual(status, 200, restored)
        self.assertTrue((self.root / "user/app/hello/hello.c").is_file())
        self.assertTrue((self.root / "user/scenarios/hello_alt.json").is_file())

        status, _, undeleted = self._post(
            "/api/apps/delete", {"name": "hello"}
        )
        self.assertEqual(status, 200, undeleted)
        status, _, payload = self._post(
            "/api/apps/trash/delete",
            {"trash_id": undeleted["trash_id"]},
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "confirmation_required")
        status, _, purged = self._post(
            "/api/apps/trash/delete",
            {"trash_id": undeleted["trash_id"], "confirm": True},
        )
        self.assertEqual(status, 200, purged)
        self.assertFalse((self.root / purged["path"]).exists())

    def test_protected_unknown_and_traversal(self) -> None:
        status, _, payload = self._post(
            "/api/apps/delete", {"name": "coffee"}
        )
        self.assertEqual(status, 403, payload)
        self.assertEqual(payload["error"]["code"], "protected_app")

        status, _, payload = self._post(
            "/api/apps/delete", {"name": "missing"}
        )
        self.assertEqual(status, 404, payload)
        self.assertEqual(payload["error"]["code"], "unknown_app")

        status, _, payload = self._post(
            "/api/apps/delete", {"name": "../escape"}
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_name")

        status, _, payload = self._post(
            "/api/apps/trash/restore", {"trash_id": "../../escape"}
        )
        self.assertEqual(status, 400, payload)

    def test_invalid_trash_id_and_corrupt_meta_keep_their_statuses(self) -> None:
        status, _, payload = self._post(
            "/api/apps/trash/restore", {"trash_id": "../../escape"}
        )
        self.assertEqual(status, 400, payload)
        self.assertEqual(payload["error"]["code"], "invalid_trash")

        self.assertEqual(self._create("hello")[0], 201)
        _, _, deleted = self._post(
            "/api/apps/delete", {"name": "hello"}
        )
        meta_path = self.root / deleted["trash_dir"] / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["schema"] = "other"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        status, _, payload = self._post(
            "/api/apps/trash/restore", {"trash_id": deleted["trash_id"]}
        )
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "invalid_trash")

    def test_mutation_is_refused_while_live_is_running(self) -> None:
        status, _, live = self.harness.json(
            "POST", "/api/live/start?mode=test&app=coffee"
        )
        self.assertEqual(status, 200, live)
        self.assertTrue(live["running"])

        status, _, payload = self._create("hello")
        self.assertEqual(status, 409, payload)
        self.assertEqual(payload["error"]["code"], "live_active")
        status, _, listing = self.harness.json("GET", "/api/apps")
        self.assertEqual(status, 200, listing)
        self.harness.json("POST", "/api/live/stop")

    def test_page_contains_manager_and_no_forbidden_words(self) -> None:
        status, _, html = self.harness.html("/")
        self.assertEqual(status, 200)
        for needle in (
            'id="app-manage"',
            'id="app-manager"',
            "/api/apps",
            "应用管理",
        ):
            self.assertIn(needle, html)
        for forbidden in (
            "manifest",
            "engine.log",
            "frame_diff",
            "pass/fail",
            "通过",
            "失败",
            "合格",
            "不合格",
        ):
            self.assertNotIn(forbidden, html)
        status, _, managed = self.harness.html("/?manage=1")
        self.assertEqual(status, 200)
        self.assertIn('id="app-manager"', managed)

    def test_page_keeps_the_manager_inline_under_csp(self) -> None:
        status, headers, html = self.harness.html("/")
        self.assertEqual(status, 200)
        self.assertEqual(html.count("<dialog"), 1)
        # The app manager partials stay inline: one style and one script
        # element, so the existing CSP and browser loading behaviour are
        # unchanged.
        self.assertEqual(html.count("<style>"), 1)
        self.assertEqual(html.count("<script>"), 1)
        policy = headers.get("Content-Security-Policy", "")
        self.assertIn("style-src 'self' 'unsafe-inline'", policy)
        self.assertIn("script-src 'self' 'unsafe-inline'", policy)

    def test_open_web_launcher_keeps_manage_opt_in(self) -> None:
        text = (REPO_ROOT / "open-web.vbs").read_text(encoding="utf-8")
        self.assertNotIn("?manage=1", text)
        self.assertNotIn("--manage", text)


if __name__ == "__main__":
    unittest.main()
