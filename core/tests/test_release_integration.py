"""Black-box release artifact test: build the zip, unpack it, run it.

This is the artifact seam.  It does not import release.py or inspect its
internals; it executes the public script and treats the zip as a product.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path

import support
from lvgl_ai import paths

TOOL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_ROOT.parent
RELEASE = TOOL_ROOT / "tools" / "release.py"


def json_line(result: subprocess.CompletedProcess[str]) -> dict:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssertionError(
            f"expected one JSON line, got {lines!r}; stderr={result.stderr!r}"
        )
    return json.loads(lines[0])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kill(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
        )
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def serve_package(package: Path, work: Path, env: dict[str, str]) -> int:
    process = subprocess.Popen(
        [
            os.environ.get("COMSPEC", "cmd.exe"), "/c",
            str(package / "bin" / "lvgl.cmd"), "serve",
            "--host", "127.0.0.1", "--port", "0",
        ],
        cwd=str(work),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    watchdog = threading.Timer(30.0, _kill, args=(process,))
    watchdog.start()
    try:
        assert process.stdout is not None
        url = None
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                break
            match = re.search(r"\[web\] serving (http://\S+)", line)
            if match:
                url = match.group(1)
                break
        if url is None:
            raise AssertionError("release smoke: web server did not print a URL")
        with urllib.request.urlopen(url, timeout=10) as response:
            status = response.status
            body = response.read(100)
        if status != 200 or not body:
            raise AssertionError(f"GET {url} returned {status}")
        return status
    finally:
        watchdog.cancel()
        _kill(process)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


class ReleaseArtifactIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        support.ensure_host_sdk("9.6")

    def test_zip_unpacks_and_runs_from_an_unrelated_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lvgl-ai-release-test-") as raw:
            root = Path(raw)
            out_dir = root / "release"
            result = subprocess.run(
                [
                    sys.executable,
                    "-I", "-B",
                    str(RELEASE),
                    "--lvgl", "9.6",
                    "--sdk", str(paths.sdk_dir_for("9.6")),
                    "--out", str(out_dir),
                    "--json",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            summary = json_line(result)
            # The release directory itself is a usable skill directory.
            published = out_dir / "lvgl-verify-loop"
            self.assertEqual(Path(summary["package"]), published)
            self.assertTrue((published / "SKILL.md").is_file())
            self.assertEqual(
                [path.name for path in published.iterdir() if path.is_file()],
                ["SKILL.md"],
            )
            self.assertFalse((published / "CONTEXT.md").exists())
            self.assertTrue((published / "bin" / "LVGL-AI-Viewer.exe").is_file())
            self.assertTrue((published / "docs" / "intro-demo.gif").is_file())
            self.assertTrue((published / "meta" / "versions.json").is_file())
            self.assertTrue((published / "meta" / "VERSION.json").is_file())
            self.assertTrue((published / "licenses" / "LICENSE").is_file())
            self.assertTrue((published / "core" / "cli.py").is_file())
            self.assertTrue(
                (published / "build" / "lvgl_9_6" / "lvgl_engine.exe").is_file()
            )
            self.assertTrue(
                (published / "user" / "app" / "intro" / "intro.c").is_file()
            )
            self.assertFalse((published / "user" / "app" / "coffee").exists())
            self.assertFalse((published / "user" / "app" / "template").exists())
            self.assertFalse((published / "user" / "app" / "demo").exists())
            self.assertTrue(
                (published / "user" / "scenarios" / "intro.json").is_file()
            )
            self.assertFalse(
                (published / "user" / "scenarios" / "coffee.json").exists()
            )
            self.assertFalse(
                (published / "user" / "scenarios" / "settings.json").exists()
            )
            zip_path = Path(summary["zip"])
            self.assertTrue(zip_path.is_file())
            self.assertEqual(
                zip_path.with_name(zip_path.name + ".sha256")
                .read_text(encoding="utf-8")
                .split()[0],
                summary["sha256"],
            )
            release_manifest = json.loads(
                Path(summary["manifest"]).read_text(encoding="utf-8")
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
            for forbidden in (
                "lvgl-src/",
                "third_party/",
                "/sessions/",
                "core/tests/",
                "core/tools/upload_release.py",
                "chip-adapt/",
                "user/app/coffee/",
                "user/app/xiaohongshu/",
                "user/app/template/",
                "user/app/demo/",
                "user/scenarios/coffee.json",
                "user/scenarios/template.json",
                "user/scenarios/settings.json",
                "runtime/",
                "smoke/",
                "licenses/Python-3.11.txt",
                "__pycache__/",
                "/.git/",
            ):
                self.assertFalse(
                    [name for name in names if forbidden in name],
                    forbidden,
                )
            required = (
                "lvgl-verify-loop/SKILL.md",
                "lvgl-verify-loop/meta/VERSION.json",
                "lvgl-verify-loop/meta/versions.json",
                "lvgl-verify-loop/licenses/LICENSE",
                "lvgl-verify-loop/bin/LVGL-AI-Viewer.exe",
                "lvgl-verify-loop/bin/lvgl.cmd",
                "lvgl-verify-loop/core/cli.py",
                "lvgl-verify-loop/core/assets.py",
                "lvgl-verify-loop/core/lvgl_ai/assets/__init__.py",
                "lvgl-verify-loop/core/lvgl_ai/assets/vendor/freetype/libfreetype.dll",
                "lvgl-verify-loop/core/lvgl_ai/assets/vendor/png.py",
                "lvgl-verify-loop/core/engine/freetype/include/ft2build.h",
                "lvgl-verify-loop/core/engine/freetype/lib/libfreetype.dll.a",
                "lvgl-verify-loop/licenses/freetype-py.txt",
                "lvgl-verify-loop/licenses/FreeType.txt",
                "lvgl-verify-loop/licenses/pypng.txt",
                "lvgl-verify-loop/licenses/lv_font_conv-MIT.txt",
                "lvgl-verify-loop/sdk/9.6/manifest.json",
                "lvgl-verify-loop/sdk/9.6/lib/libfreetype.dll",
                "lvgl-verify-loop/sdk/9.6/lib/libfreetype.dll.a",
                "lvgl-verify-loop/build/lvgl_9_6/lvgl_engine.exe",
                "lvgl-verify-loop/build/lvgl_9_6/libfreetype.dll",
                "lvgl-verify-loop/docs/intro-demo.gif",
                "lvgl-verify-loop/user/app/intro/intro.c",
                "lvgl-verify-loop/user/scenarios/intro.json",
            )
            for name in required:
                self.assertIn(name, names)

            package = root / "unpacked"
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(package)
            pkg = package / "lvgl-verify-loop"

            # The manifest describes the files that are actually in the zip.
            manifest_names = {
                f"lvgl-verify-loop/{relative}"
                for relative in release_manifest["files"]
            }
            self.assertEqual(manifest_names, set(names))
            self.assertEqual(
                release_manifest["package"]["file_count"], len(names)
            )
            self.assertEqual(
                release_manifest["sdk"]["manifest_sha256"],
                sha256_file(pkg / "sdk" / "9.6" / "manifest.json"),
            )

            # No development absolute path survives in text or binaries.
            needles = {
                str(REPO_ROOT.resolve()).encode("utf-8"),
                str(REPO_ROOT.resolve()).replace("\\", "/").encode("utf-8"),
            }
            for path in pkg.rglob("*"):
                if not path.is_file():
                    continue
                data = path.read_bytes()
                for needle in needles:
                    self.assertNotIn(
                        needle,
                        data,
                        f"development path leaked into {path}",
                    )

            skill = (pkg / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(skill.startswith("---\n"))
            frontmatter = skill.split("\n---\n", 1)[0].splitlines()[1:]
            keys = [line.split(":", 1)[0] for line in frontmatter if line.strip()]
            self.assertEqual(keys, ["name", "description"])
            for heading in (
                "## 环境与入口",
                "## 目录",
                "## 宿主工作流",
                "## 证据读取顺序",
                "## 版本策略",
                "## SiFli 工作流",
                "## 硬规则",
            ):
                self.assertIn(heading, skill)
            version = json.loads(
                (pkg / "meta" / "VERSION.json").read_text(encoding="utf-8")
            )
            self.assertEqual(version["schema"], "lvgl-ai-version-v1")
            self.assertEqual(version["lvgl"]["host_sdk"], ["9.6"])
            self.assertNotIn("python", version)
            self.assertNotIn("python", release_manifest)
            self.assertEqual(
                version["git_commit"], release_manifest["git_commit"]
            )
            self.assertEqual(
                version["gcc"]["version"],
                release_manifest["gcc"]["version"],
            )

            work = root / "elsewhere"
            work.mkdir()
            env = os.environ.copy()
            env["LVGL_AI_SESSIONS_ROOT"] = str(root / "sessions")
            env.pop("LVGL_AI_LVGL_SRC", None)
            env.pop("LVGL_AI_DEMO", None)
            wrapper = [os.environ.get("COMSPEC", "cmd.exe"), "/c",
                       str(pkg / "bin" / "lvgl.cmd"), "run",
                       "--no-build",
                       "--scenario", str(pkg / "user" / "scenarios" / "intro.json"),
                       "--json"]
            run = subprocess.run(
                wrapper,
                cwd=str(work),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            self.assertEqual(
                run.returncode,
                0,
                msg=f"stdout={run.stdout!r} stderr={run.stderr!r}",
            )
            payload = json_line(run)
            self.assertEqual(payload["status"], "ok", msg=payload.get("error"))
            session = Path(payload["session_dir"])
            self.assertTrue((session / "manifest.json").is_file())
            self.assertTrue(any((session / "frames").glob("*.png")))

            # The same unzipped package must also build user/app without
            # LVGL source or CMake.
            build_run = subprocess.run(
                [
                    os.environ.get("COMSPEC", "cmd.exe"), "/c",
                    str(pkg / "bin" / "lvgl.cmd"), "run",
                    "--prebuilt",
                    "--scenario", str(pkg / "user" / "scenarios" / "intro.json"),
                    "--json",
                ],
                cwd=str(work),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            self.assertEqual(
                build_run.returncode,
                0,
                msg=f"stdout={build_run.stdout!r} stderr={build_run.stderr!r}",
            )
            built = json_line(build_run)
            self.assertEqual(built["status"], "ok", msg=built.get("error"))
            build_log = Path(built["session_dir"]) / "build.log"
            self.assertIn(
                "# build mode: prebuilt",
                build_log.read_text(encoding="utf-8", errors="replace"),
            )

            self.assertEqual(serve_package(pkg, work, env), 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
