from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = TOOL_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import contract_snapshot as cs

# Side effect: install the Windows-safe TemporaryDirectory before setUp runs.
import support  # noqa: F401,E402


class ContractSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = cs.record_snapshot()
        cls.snapshot_bytes = cs.snapshot_bytes(cls.snapshot)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _section(self, name: str) -> dict:
        return self.snapshot["sections"][name]

    def _probe(self, name: str) -> dict:
        probes = {
            probe["name"]: probe for probe in self._section("http")["probes"]
        }
        return probes[name]

    def test_snapshot_has_the_six_contract_sections(self) -> None:
        self.assertEqual(self.snapshot["schema"], cs.SNAPSHOT_SCHEMA)
        self.assertEqual(
            sorted(self.snapshot["sections"]),
            ["cli", "http", "page", "protocol", "python", "session"],
        )

    def test_http_routes_methods_statuses_and_json_keys(self) -> None:
        http = self._section("http")
        names = {probe["name"] for probe in http["probes"]}
        self.assertTrue(
            {
                "page_session",
                "session",
                "session_timeline",
                "annotation_create",
                "apps_list",
                "app_create",
                "live_start",
                "live_pointer",
                "live_stream",
                "unknown_path",
            }.issubset(names)
        )
        self.assertEqual(self._probe("session_missing")["status"], 404)
        self.assertEqual(
            self._probe("session_missing")["error_code"], "unknown_session"
        )
        self.assertEqual(
            self._probe("app_create_no_header")["error_code"],
            "invalid_request_header",
        )
        self.assertEqual(
            self._probe("app_delete_protected")["error_code"],
            "protected_app",
        )
        self.assertEqual(self._probe("method_get_start")["status"], 405)
        self.assertEqual(self._probe("method_post_live")["status"], 405)
        self.assertEqual(self._probe("method_get_apps_create")["status"], 405)
        self.assertEqual(self._probe("method_post_timeline")["status"], 405)
        self.assertEqual(self._probe("method_put")["status"], 501)
        self.assertEqual(self._probe("method_delete")["status"], 405)
        create = self._probe("app_create")
        self.assertEqual(create["status"], 201)
        self.assertIn("action", create["json_shape"]["object"])
        self.assertIn("files", create["json_shape"]["object"])
        paths = {probe["path"] for probe in http["probes"]}
        self.assertIn("/api/live/start", paths)
        self.assertIn("/api/apps/trash/delete", paths)
        self.assertIn("/api/sessions/<session>/timeline", paths)

        stream = self._probe("live_stream")
        self.assertEqual(stream["status"], 200)
        self.assertEqual(stream["magic"], "LVFR")
        self.assertEqual(stream["header_size"], 20)
        self.assertEqual(stream["width"], 2)
        self.assertEqual(stream["height"], 2)
        self.assertEqual(stream["pixel_bytes"], 16)

        self.assertEqual(http["trash_meta_schema"], "lvgl-ai-app-trash-v1")
        self.assertEqual(
            http["trash_layout"],
            [
                "app",
                "app/alpha.c",
                "meta.json",
                "scenarios",
                "scenarios/alpha.json",
            ],
        )

    def test_cli_parsers_help_exit_codes_and_json(self) -> None:
        cli = self._section("cli")
        self.assertEqual(
            sorted(cli), ["cli", "new_app", "session_report", "web"]
        )
        options = {
            option
            for action in cli["cli"]["parser"]["actions"]
            for option in action["option_strings"]
        }
        self.assertTrue(
            {
                "--record",
                "--no-record",
                "--build",
                "--scenario",
                "--idle",
                "--json",
            }.issubset(options)
        )
        self.assertEqual(cli["cli"]["help"]["exit"], 0)
        self.assertNotIn("--record-changed-only", cli["cli"]["help"]["text"])
        self.assertEqual(cli["cli"]["invalid_exit"], 2)
        self.assertEqual(cli["cli"]["json_success"]["exit"], 0)
        self.assertEqual(
            cli["cli"]["json_success"]["keys"],
            ["app", "error", "manifest_path", "session_id"],
        )
        self.assertEqual(cli["cli"]["json_build_error"]["exit"], 1)
        self.assertEqual(
            cli["cli"]["json_build_error"]["error_code"], "build_error"
        )
        self.assertTrue(cli["cli"]["json_build_error"]["session_id_present"])
        self.assertTrue(cli["cli"]["json_build_error"]["session_dir_present"])
        self.assertIn("schema", cli["cli"]["json_build_error"]["keys"])
        report = cli["session_report"]
        self.assertEqual(report["json_index"]["exit"], 0)
        self.assertIn("schema", report["json_index"]["keys"])
        self.assertIn("counts", report["json_index"]["keys"])
        self.assertIn("next_reads", report["json_index"]["keys"])
        self.assertEqual(report["full_exit"], 2)
        self.assertEqual(report["timeline"]["exit"], 0)
        self.assertEqual(
            report["timeline"]["keys"],
            [
                "returned",
                "rows",
                "schema",
                "session_dir",
                "total",
                "truncated",
            ],
        )
        web_options = {
            option
            for action in cli["web"]["parser"]["actions"]
            for option in action["option_strings"]
        }
        self.assertTrue(
            {
                "--host",
                "--port",
                "--sessions-root",
                "--lvgl",
                "--build",
                "--app",
                "--manage",
                "--open",
                "--exit-on-close",
            }.issubset(web_options)
        )
        self.assertEqual(cli["new_app"]["json_success"]["exit"], 0)
        self.assertIn(
            "files", cli["new_app"]["json_success"]["json_shape"]["object"]
        )
        self.assertEqual(cli["new_app"]["error_exit"], 1)
        self.assertTrue(cli["new_app"]["error_stdout_empty"])

    def test_protocol_commands_replies_and_ready_fields(self) -> None:
        protocol = self._section("protocol")
        commands = protocol["commands"]
        self.assertEqual(commands[0], "pointer down 10 20")
        self.assertIn("key press 10 ENTER", commands)
        self.assertIn("encoder turn -2", commands)
        self.assertIn("wait frames 2", commands)
        self.assertIn("snapshot direct_shot", commands)
        self.assertIn("snapshot drag_end", commands)
        self.assertIn("key press 18 DOWN", commands)
        self.assertIn("encoder turn 1", commands)
        self.assertEqual(commands[-1], "quit")
        self.assertEqual(protocol["seq_starts_at"], 1)
        self.assertTrue(protocol["seq_contiguous"])
        self.assertEqual(protocol["ready_seq"], 0)
        self.assertEqual(protocol["ready_protocol"], "lvgl-ai-engine-v1")
        self.assertTrue(protocol["protocol_versions"]["lvgl-ai-engine-v1"])
        self.assertFalse(protocol["protocol_versions"]["lvgl-ai-engine-v0"])
        required = set(protocol["required_ready_keys"])
        self.assertTrue(
            {
                "protocol",
                "seq",
                "lvgl",
                "display",
                "mode",
                "inputs",
                "capabilities",
                "frames",
            }.issubset(required)
        )
        self.assertTrue(
            {"adapter", "max_frames", "truncated"}.issubset(
                protocol["optional_ready_keys"]
            )
        )
        self.assertEqual(
            protocol["required_reply_fields"]["pointer"], ["hit", "hit_class"]
        )
        self.assertEqual(
            protocol["required_reply_fields"]["key"], ["delivered"]
        )
        self.assertEqual(
            protocol["required_reply_fields"]["snapshot"], ["file"]
        )
        self.assertEqual(
            protocol["reply_shapes"]["wait"]["object"]["changed"], "boolean"
        )
        self.assertEqual(protocol["error_reply_outcome"], "ProtocolError")
        self.assertIn("error", protocol["error_reply_shape"]["object"])
        self.assertEqual(
            protocol["engine_args"],
            [
                "--session",
                "<session>",
                "--record",
                "--diff-threshold",
                "12",
                "--max-frames",
                "42",
                "--async-encode",
                "--headless",
                "--live-frame",
                "--record-changed-only",
                "--reference",
                "<reference>",
            ],
        )

    def test_session_files_manifest_and_recording_contract(self) -> None:
        session = self._section("session")
        self.assertTrue(
            {
                "manifest.json",
                "timeline.ndjson",
                "frame_diffs.ndjson",
                "reference_diffs.ndjson",
                "annotations.json",
                "engine.log",
                "build.log",
                "frames/000001.png",
                "frames/000002.png",
                "snapshots/001_static.png",
            }.issubset(set(session["complete_files"]))
        )
        self.assertEqual(
            session["plain_files"],
            [
                "build.log",
                "engine.log",
                "frame_diffs.ndjson",
                "frames/000001.png",
                "frames/000002.png",
                "manifest.json",
                "timeline.ndjson",
            ],
        )
        self.assertEqual(
            session["record_false_files"],
            ["build.log", "engine.log", "manifest.json"],
        )
        self.assertEqual(
            session["required_files"],
            [
                "engine.log",
                "frame_diffs.ndjson",
                "manifest.json",
                "timeline.ndjson",
            ],
        )
        self.assertIn("build.log", session["optional_files"])
        self.assertIn("annotations.json", session["optional_files"])
        self.assertEqual(
            session["optional_manifest_fields"],
            ["app", "display", "record_changed_only"],
        )
        self.assertIn("artifacts", session["required_manifest_fields"])
        self.assertEqual(
            session["manifest_values"]["schema"], "lvgl-ai-session-v1"
        )
        self.assertEqual(session["manifest_values"]["status"], "ok")
        self.assertEqual(
            session["manifest_values"]["display"],
            {"width": 800, "height": 600},
        )
        self.assertEqual(
            session["manifest_values"]["build"],
            {"status": "skipped", "log": "build.log"},
        )
        self.assertEqual(session["manifest_values"]["frame_count"], 2)
        self.assertIn("timeline", session["complete_artifacts"])
        self.assertIn("frames", session["complete_artifacts"])
        self.assertIn("snapshots", session["complete_artifacts"])
        self.assertIn("annotations", session["complete_artifacts"])
        self.assertIn("reference_diffs", session["complete_artifacts"])
        self.assertIn("timeline", session["plain_artifacts"])
        self.assertNotIn("annotations", session["plain_artifacts"])
        self.assertNotIn("reference_diffs", session["plain_artifacts"])
        self.assertEqual(
            session["record_false_artifacts"],
            {
                "manifest": "manifest.json",
                "build_log": "build.log",
                "engine_log": "engine.log",
            },
        )
        self.assertEqual(
            session["accepted_statuses"],
            ["ok", "build_error", "link_error", "crash", "harness_error"],
        )
        self.assertEqual(
            session["rejected_statuses"], ["pass", "fail", "unverified"]
        )
        for row_type in ("frame", "input", "wait", "mark", "snapshot", "end"):
            self.assertTrue(session["timeline_types"][row_type])
        self.assertFalse(session["timeline_types"]["other"])
        self.assertTrue(session["live_rgba"]["present_while_recording"])
        self.assertTrue(session["live_rgba"]["removed_after_stop"])
        self.assertTrue(session["live_rgba"]["present_while_record_false"])
        self.assertTrue(
            session["live_rgba"]["removed_after_stop_record_false"]
        )

    def test_page_dom_ids_classes_copy_and_endpoints(self) -> None:
        page = self._section("page")
        self.assertEqual(
            page["statuses"], {"replay": 200, "error": 200, "empty": 200}
        )
        replay = page["replay"]
        for element_id in (
            "replay",
            "stage",
            "timeline",
            "app-manager",
            "live-app",
            "app-create-form",
            "annotation-save",
        ):
            self.assertIn(element_id, replay["ids"])
        self.assertIn("LVGL 检视台", replay["texts"])
        self.assertIn("应用管理", replay["texts"])
        self.assertIn("section.replay-panel", replay["classes"])
        self.assertIn("/api/live/stream", replay["endpoints"])
        self.assertIn(
            "/frames/20260102-030405-abcd/000001.png", replay["endpoints"]
        )
        self.assertIn("app-manager", page["empty"]["ids"])
        self.assertIn("session_unreadable", page["error"]["texts"])

    def test_public_python_interface(self) -> None:
        python = self._section("python")
        exports = python["lvgl_ai"]["exports"]
        for name in (
            "Runtime",
            "Recording",
            "play_scenario",
            "LatError",
            "BuildError",
            "LinkError",
            "RuntimeCrash",
            "ProtocolError",
            "ScenarioError",
            "EngineNotFound",
        ):
            self.assertIn(name, exports)
        runtime = python["lvgl_ai"]["members"]["Runtime"]
        self.assertEqual(runtime["kind"], "class")
        for method in (
            "start",
            "stop",
            "pointer",
            "key",
            "encoder",
            "tick",
            "wait",
            "snapshot",
            "mark",
            "input",
            "record_error",
            "log_tail",
        ):
            self.assertIn(method, runtime["members"])
        self.assertEqual(runtime["members"]["recording"], "property")
        hierarchy = python["lvgl_ai"]["error_hierarchy"]
        for name in (
            "BuildError",
            "LinkError",
            "RuntimeCrash",
            "ProtocolError",
            "ScenarioError",
            "EngineNotFound",
        ):
            self.assertIn("LatError", hierarchy[name])
        self.assertEqual(hierarchy["LatError"], [])
        recording = python["lvgl_ai"]["members"]["Recording"]
        for method in (
            "open",
            "manifest",
            "timeline",
            "frame_diffs",
            "reference_diffs",
            "frames",
            "snapshots",
            "log",
            "log_tail",
            "build_log",
            "annotations",
        ):
            self.assertIn(method, recording["members"])
        apps = python["apps"]
        for name in (
            "AppError",
            "list_apps",
            "app_tree",
            "recent_apps",
            "list_trash",
            "scaffold_app",
            "delete_app",
            "restore_app",
            "permanently_delete",
        ):
            self.assertIn(name, apps)

    def test_snapshot_is_deterministic(self) -> None:
        second = cs.record_snapshot()
        self.assertEqual(
            cs.snapshot_bytes(second),
            self.snapshot_bytes,
            "two recordings must be byte-identical",
        )

    def test_snapshot_has_no_machine_state(self) -> None:
        text = self.snapshot_bytes.decode("utf-8")
        self.assertIsNone(
            re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", text),
            "snapshot must not contain absolute drive paths",
        )
        self.assertNotIn(tempfile.gettempdir(), text)
        self.assertNotIn(str(Path.home()), text)
        self.assertNotIn("\r", text)
        urls = set(re.findall(r"http://127\.0\.0\.1:\d+", text))
        self.assertLessEqual(urls, {"http://127.0.0.1:8765"})

    def test_committed_snapshot_matches_current_code(self) -> None:
        reference = cs.load_snapshot(cs.DEFAULT_SNAPSHOT_PATH)
        differences = cs.compare_snapshots(reference, self.snapshot)
        self.assertEqual(
            differences,
            [],
            cs.render_diff_report(differences),
        )

    def test_compare_reports_no_difference_for_identical_values(self) -> None:
        self.assertEqual(
            cs.compare_snapshots(self.snapshot, copy.deepcopy(self.snapshot)),
            [],
        )
        self.assertEqual(
            cs.render_diff_report([], reference="snapshot.json"),
            "[contract] snapshot: snapshot.json\n[contract] differences: 0",
        )

    def test_compare_reports_changed_missing_and_unexpected_paths(
        self,
    ) -> None:
        changed = copy.deepcopy(self.snapshot)
        changed["sections"]["http"]["probes"][0]["status"] = 599
        differences = cs.compare_snapshots(self.snapshot, changed)
        self.assertTrue(
            any(
                item["path"].endswith("probes[0].status")
                and item["kind"] == "changed"
                for item in differences
            ),
            differences,
        )
        report = cs.render_diff_report(differences)
        self.assertIn("599", report)

        missing = copy.deepcopy(self.snapshot)
        del missing["sections"]["cli"]["web"]["help"]
        differences = cs.compare_snapshots(self.snapshot, missing)
        self.assertTrue(any(item["kind"] == "missing" for item in differences))

        unexpected = copy.deepcopy(self.snapshot)
        unexpected["sections"]["python"]["lvgl_ai"]["members"]["extra"] = {
            "kind": "function"
        }
        differences = cs.compare_snapshots(self.snapshot, unexpected)
        self.assertTrue(
            any(item["kind"] == "unexpected" for item in differences)
        )

    def test_record_and_compare_commands(self) -> None:
        recorded_path = self.root / "recorded.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = cs.main(["record", "--out", str(recorded_path)])
        self.assertEqual(code, 0)
        self.assertEqual(recorded_path.read_bytes(), self.snapshot_bytes)

        output = io.StringIO()
        report_path = self.root / "report.txt"
        with contextlib.redirect_stdout(output):
            code = cs.main(
                [
                    "compare",
                    "--snapshot",
                    str(recorded_path),
                    "--report",
                    str(report_path),
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("differences: 0", output.getvalue())
        self.assertIn(
            "differences: 0", report_path.read_text(encoding="utf-8")
        )

        changed = copy.deepcopy(self.snapshot)
        changed["sections"]["session"]["manifest_values"]["status"] = "crash"
        changed_path = self.root / "changed.json"
        cs.write_snapshot(changed_path, changed)
        with contextlib.redirect_stdout(io.StringIO()):
            code = cs.main(["compare", "--snapshot", str(changed_path)])
        self.assertEqual(code, 1)

        with contextlib.redirect_stderr(io.StringIO()):
            code = cs.main(
                ["compare", "--snapshot", str(self.root / "missing.json")]
            )
        self.assertEqual(code, 2)

    def test_committed_snapshot_has_the_expected_schema(self) -> None:
        self.assertTrue(cs.DEFAULT_SNAPSHOT_PATH.is_file())
        reference = json.loads(
            cs.DEFAULT_SNAPSHOT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(reference["schema"], cs.SNAPSHOT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
