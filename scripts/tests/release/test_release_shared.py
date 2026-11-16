from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import paths
from control.errors import BuildError
from scripts import release, release_all, release_bundle

SDK_MANIFEST = {
    "schema": "lvgl-verify-loop-host-sdk-v1",
    "lvgl_version": "9.6",
    "lvgl_tag": "v9.6.0",
    "compiler": {"version": "15.2.0"},
    "libs": ["lvgl"],
    "sha256": "sdk-digest",
}


def completed(
    stdout: str, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class JsonReplyTest(unittest.TestCase):
    def test_one_json_line_is_required(self) -> None:
        self.assertEqual(
            release_bundle.json_line(
                completed('{"status":"ok"}\n'), label="smoke"
            ),
            {"status": "ok"},
        )
        with self.assertRaises(BuildError):
            release_bundle.json_line(
                completed('{"a":1}\n{"b":2}\n'), label="smoke"
            )
        with self.assertRaises(BuildError):
            release_bundle.json_line(completed("not json\n"), label="smoke")
        with self.assertRaises(BuildError):
            release_bundle.json_line(completed("[1]\n"), label="smoke")


class SmokeEnvironmentTest(unittest.TestCase):
    def test_development_overrides_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            with mock.patch.dict(
                os.environ,
                {
                    "LVGL_VERIFY_LOOP_LVGL_SRC": "source",
                    "LVGL_VERIFY_LOOP_DEMO": "demo",
                    "LVGL_VERIFY_LOOP_KEEP": "yes",
                },
                clear=False,
            ):
                env = release_bundle.smoke_environment(workspace)
            self.assertEqual(
                env["LVGL_VERIFY_LOOP_SESSIONS_ROOT"], str(workspace / "sessions")
            )
            self.assertNotIn("LVGL_VERIFY_LOOP_LVGL_SRC", env)
            self.assertNotIn("LVGL_VERIFY_LOOP_DEMO", env)
            self.assertEqual(env["LVGL_VERIFY_LOOP_KEEP"], "yes")


class ScenarioSmokeTest(unittest.TestCase):
    def test_wrapper_run_reuses_environment_and_checks_markers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = root / "package"
            (package / "bin").mkdir(parents=True)
            (package / "bin" / "lvgl.cmd").write_text("", encoding="utf-8")
            scenario = package / "user" / "scenarios" / "intro.json"
            scenario.parent.mkdir(parents=True)
            scenario.write_text("{}\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            calls = []

            def fake_run(
                command, *, cwd, env, timeout
            ) -> subprocess.CompletedProcess[str]:
                calls.append((list(command), Path(cwd), dict(env), timeout))
                session = Path(env["LVGL_VERIFY_LOOP_SESSIONS_ROOT"]) / "session"
                session.mkdir(parents=True)
                (session / "engine.log").write_text(
                    "[app] app=intro\n[intro] ui created\n", encoding="utf-8"
                )
                return completed(
                    json.dumps(
                        {
                            "status": "ok",
                            "session_id": "session",
                            "session_dir": str(session),
                        }
                    )
                )

            payload = release_bundle.smoke_scenario(
                package,
                "9.6",
                scenario,
                workspace,
                via_wrapper=True,
                extra=("--no-build",),
                markers=("[app] app=intro",),
                label="9.6",
                run=fake_run,
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(len(calls), 1)
            command, cwd, env, timeout = calls[0]
            self.assertEqual(cwd, workspace)
            self.assertEqual(
                env["LVGL_VERIFY_LOOP_SESSIONS_ROOT"], str(workspace / "sessions")
            )
            self.assertEqual(timeout, 180.0)
            if os.name == "nt":
                self.assertEqual(
                    command[:2], [os.environ.get("COMSPEC", "cmd.exe"), "/c"]
                )
            self.assertIn(str(package / "bin" / "lvgl.cmd"), command)
            self.assertIn("run", command)
            self.assertEqual(command[command.index("--lvgl") + 1], "9.6")
            self.assertEqual(
                command[command.index("--scenario") + 1], str(scenario)
            )
            self.assertIn("--json", command)

    def test_missing_marker_is_a_build_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = root / "package"
            (package / "bin").mkdir(parents=True)
            (package / "bin" / "lvgl.cmd").write_text("", encoding="utf-8")
            scenario = package / "user" / "scenarios" / "intro.json"
            scenario.parent.mkdir(parents=True)
            scenario.write_text("{}\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()

            def fake_run(command, *, cwd, env, timeout):
                session = Path(env["LVGL_VERIFY_LOOP_SESSIONS_ROOT"]) / "session"
                session.mkdir(parents=True)
                (session / "engine.log").write_text(
                    "nothing\n", encoding="utf-8"
                )
                return completed(
                    json.dumps({"status": "ok", "session_dir": str(session)})
                )

            with self.assertRaises(BuildError):
                release_bundle.smoke_scenario(
                    package,
                    "9.6",
                    scenario,
                    workspace,
                    markers=("[app] app=intro",),
                    label="9.6",
                    run=fake_run,
                )


class ReleaseAllDelegationTest(unittest.TestCase):
    def test_smoke_uses_the_shared_scenario_runner(self) -> None:
        with mock.patch.object(
            release_all.release_bundle,
            "smoke_scenario",
            return_value={"session_id": "shared"},
        ) as shared:
            payload = release_all._smoke(
                Path("package"),
                "9.6",
                Path("scenario.json"),
                markers=("[app] app=intro",),
            )
        self.assertEqual(
            payload,
            {
                "version": "9.6",
                "session_id": "shared",
                "frame_count": None,
                "markers": ["[app] app=intro"],
            },
        )
        shared.assert_called_once()
        kwargs = shared.call_args.kwargs
        self.assertTrue(kwargs["via_wrapper"])
        self.assertEqual(kwargs["markers"], ("[app] app=intro",))


def stage_tiny_package(package: Path, tool_version: str) -> dict:
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (package / "scripts" / "meta").mkdir(parents=True)
    (package / "scripts" / "meta" / "versions.json").write_text("{}\n", encoding="utf-8")
    (package / "console" / "entrypoints").mkdir(parents=True)
    (package / "console" / "entrypoints" / "cli.py").write_text("print('x')\n", encoding="utf-8")
    (package / "dist" / "lvgl" / "9.6").mkdir(parents=True)
    (package / "dist" / "lvgl" / "9.6" / "manifest.json").write_text(
        json.dumps(SDK_MANIFEST) + "\n", encoding="utf-8"
    )
    return {
        "engine": {"status": "reused"},
        "sdk_manifest": SDK_MANIFEST,
        "version": {"git_commit": "abc123", "gcc": {"version": "15.2.0"}},
    }


class ArtifactContractTest(unittest.TestCase):
    def test_single_and_double_bundles_write_the_same_package_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            (repo / "scripts" / "meta").mkdir(parents=True)
            shutil.copy2(
                paths.REPO_ROOT / "scripts" / "meta" / "versions.json",
                repo / "scripts" / "meta" / "versions.json",
            )
            sdk = repo / "dist" / "lvgl" / "9.6"
            sdk.mkdir(parents=True)
            (sdk / "manifest.json").write_text(
                json.dumps(SDK_MANIFEST) + "\n", encoding="utf-8"
            )
            out_single = root / "single"
            out_double = root / "double"

            def fake_stage_package(**kwargs):
                return stage_tiny_package(
                    kwargs["package"], kwargs["tool_version"]
                )

            def fake_stage_full(
                repo_arg, package, *, tool_version, smoke, force_build, plan
            ):
                staged = stage_tiny_package(package, tool_version)
                staged.update({"shared": {}, "engines": {}})
                return staged

            with (
                mock.patch.object(
                    release, "stage_package", side_effect=fake_stage_package
                ),
                mock.patch.object(release, "smoke_package"),
                mock.patch.object(release, "clean_build_dir"),
                mock.patch.object(release, "purge_caches"),
            ):
                single = release.release(
                    repo_root=repo,
                    out_dir=out_single,
                    tool_version="0.2.0",
                    lvgl_version="9.6",
                    sdk_dir=sdk,
                    smoke=False,
                )
            with (
                mock.patch.object(
                    release_all,
                    "_ensure_launchers",
                    return_value={"status": "reused"},
                ),
                mock.patch.object(
                    release_all,
                    "_stage_full_package",
                    side_effect=fake_stage_full,
                ),
                mock.patch.object(release_all, "_overlay_sifli"),
            ):
                double = release_all.build_release(
                    repo_root=repo,
                    out_dir=out_double,
                    tool_version="0.2.0",
                    smoke=False,
                )

            single_zip = Path(single["zip"])
            full_zip = Path(double["full"]["zip"])
            with (
                zipfile.ZipFile(single_zip) as left,
                zipfile.ZipFile(full_zip) as right,
            ):
                self.assertEqual(left.namelist(), right.namelist())
                self.assertEqual(
                    [left.read(name) for name in left.namelist()],
                    [right.read(name) for name in right.namelist()],
                )
            single_manifest = json.loads(
                Path(single["manifest"]).read_text(encoding="utf-8")
            )
            full_manifest = json.loads(
                Path(double["full"]["manifest"]).read_text(encoding="utf-8")
            )
            self.assertEqual(single_manifest, full_manifest)
            for key in (
                "schema",
                "tool_version",
                "git_commit",
                "lvgl_version",
                "sdk",
                "gcc",
                "adapters",
                "package",
                "sha256",
                "files",
            ):
                self.assertIn(key, single_manifest)


if __name__ == "__main__":
    unittest.main()
