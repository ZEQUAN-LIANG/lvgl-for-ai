from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from lvgl_ai import paths
from tools import release_all, release_bundle

SDK_MANIFEST = {
    "schema": "lvgl-ai-host-sdk-v1",
    "lvgl_version": "9.6",
    "lvgl_tag": "v9.6.0",
    "compiler": {"version": "15.2.0"},
    "libs": ["lvgl"],
    "sha256": "sdk-digest",
}


def make_package(root: Path) -> Path:
    package = root / "lvgl-verify-loop"
    (package / "core").mkdir(parents=True)
    (package / "meta").mkdir()
    (package / "sdk" / "9.6").mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (package / "core" / "cli.py").write_text("print('x')\n", encoding="utf-8")
    (package / "meta" / "VERSION.json").write_text("{}\n", encoding="utf-8")
    (package / "sdk" / "9.6" / "manifest.json").write_text(
        json.dumps(SDK_MANIFEST, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return package


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ZipContractTest(unittest.TestCase):
    def test_zip_members_and_checksum_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = make_package(root)
            zip_path = root / "out" / "lvgl-verify-loop-0.2.0-9.6.zip"

            digest = release_bundle.build_zip(package, zip_path)

            self.assertEqual(digest, sha256(zip_path))
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(
                    archive.namelist(),
                    [
                        "lvgl-verify-loop/SKILL.md",
                        "lvgl-verify-loop/core/cli.py",
                        "lvgl-verify-loop/meta/VERSION.json",
                        "lvgl-verify-loop/sdk/9.6/manifest.json",
                    ],
                )
                self.assertEqual(
                    archive.getinfo("lvgl-verify-loop/SKILL.md").date_time,
                    (1980, 1, 1, 0, 0, 0),
                )

    def test_checksum_file_has_the_coreutils_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            zip_path = root / "lvgl-verify-loop-0.2.0-full-win64.zip"
            zip_path.write_bytes(b"archive bytes")
            digest = hashlib.sha256(b"archive bytes").hexdigest()

            written = release_bundle.write_checksum(zip_path, digest)

            self.assertEqual(
                written, zip_path.with_name(zip_path.name + ".sha256")
            )
            self.assertEqual(
                written.read_text(encoding="utf-8"),
                f"{digest}  {zip_path.name}\n",
            )


class ManifestContractTest(unittest.TestCase):
    def test_manifest_hashes_the_packaged_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = make_package(root)
            zip_path = root / "out" / "lvgl-verify-loop-0.2.0-9.6.zip"
            digest = release_bundle.build_zip(package, zip_path)

            manifest, manifest_path = release_bundle.write_manifest(
                package,
                zip_path,
                tool_version="0.2.0",
                git_commit="deadbeef",
                lvgl_version="9.6",
                gcc_version="15.2.0",
                adapters=[],
            )

            self.assertEqual(
                manifest_path,
                zip_path.with_name("lvgl-verify-loop-0.2.0-9.6.release.json"),
            )
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "lvgl-ai-release-v1")
            self.assertEqual(payload["tool_version"], "0.2.0")
            self.assertEqual(payload["git_commit"], "deadbeef")
            self.assertEqual(payload["lvgl_version"], "9.6")
            self.assertEqual(payload["gcc"], {"version": "15.2.0"})
            self.assertEqual(payload["adapters"], [])
            self.assertEqual(
                payload["sdk"],
                {
                    "schema": "lvgl-ai-host-sdk-v1",
                    "lvgl_version": "9.6",
                    "lvgl_tag": "v9.6.0",
                    "manifest_sha256": sha256(
                        package / "sdk" / "9.6" / "manifest.json"
                    ),
                    "compiler": {"version": "15.2.0"},
                    "libs": ["lvgl"],
                    "sha256": "sdk-digest",
                },
            )
            self.assertEqual(
                payload["package"],
                {
                    "root": "lvgl-verify-loop",
                    "file_count": 4,
                    "unpacked_bytes": sum(
                        path.stat().st_size
                        for path in package.rglob("*")
                        if path.is_file()
                    ),
                    "archive_bytes": zip_path.stat().st_size,
                },
            )
            self.assertEqual(payload["sha256"], digest)
            self.assertEqual(
                payload["files"],
                {
                    relative: sha256(package / relative)
                    for relative in (
                        "SKILL.md",
                        "core/cli.py",
                        "meta/VERSION.json",
                        "sdk/9.6/manifest.json",
                    )
                },
            )
            self.assertEqual(manifest, payload)


class ReleaseAllArtifactsTest(unittest.TestCase):
    def test_each_zip_gets_checksum_manifest_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            out = root / "out"
            (repo / "meta").mkdir(parents=True)
            shutil.copy2(
                paths.REPO_ROOT / "meta" / "versions.json",
                repo / "meta" / "versions.json",
            )
            source_before = (repo / "meta" / "versions.json").read_bytes()

            def fake_stage(
                repo_arg, package, *, tool_version, smoke, force_build, plan
            ):
                self.assertEqual(
                    tuple(plan["supported"]),
                    ("9.6", "9.5", "9.4", "9.1", "8.4", "8.3"),
                )
                package.mkdir(parents=True)
                (package / "SKILL.md").write_text("skill\n", encoding="utf-8")
                (package / "meta").mkdir()
                (package / "meta" / "versions.json").write_text(
                    "{}\n", encoding="utf-8"
                )
                (package / "sdk" / "9.6").mkdir(parents=True)
                (package / "sdk" / "9.6" / "manifest.json").write_text(
                    json.dumps(SDK_MANIFEST) + "\n", encoding="utf-8"
                )
                return {
                    "engine": {"status": "reused"},
                    "shared": {},
                    "engines": {},
                    "sdk_manifest": SDK_MANIFEST,
                    "version": {
                        "git_commit": "cafebabe",
                        "gcc": {"version": "15.2.0"},
                    },
                }

            def fake_overlay(package, repo_arg, tool_version):
                (package / "chip-adapt").mkdir()
                (package / "chip-adapt" / "sifli.txt").write_text(
                    "sifli\n", encoding="utf-8"
                )

            with (
                mock.patch.object(
                    release_all,
                    "_ensure_launchers",
                    return_value={"status": "reused"},
                ),
                mock.patch.object(
                    release_all, "_stage_full_package", side_effect=fake_stage
                ),
                mock.patch.object(
                    release_all, "_overlay_sifli", side_effect=fake_overlay
                ),
            ):
                summary = release_all.build_release(
                    repo_root=repo,
                    out_dir=out,
                    tool_version="0.2.0",
                    smoke=False,
                )

            self.assertEqual(
                (repo / "meta" / "versions.json").read_bytes(), source_before
            )
            self.assertEqual(summary["schema"], "lvgl-verify-loop-release-v2")
            expected = {
                "full": (
                    "lvgl-verify-loop-0.2.0-full-win64.zip",
                    {
                        "SKILL.md",
                        "meta/versions.json",
                        "sdk/9.6/manifest.json",
                    },
                ),
                "full_sifli": (
                    "lvgl-verify-loop-0.2.0-full-sifli-win64.zip",
                    {
                        "SKILL.md",
                        "meta/versions.json",
                        "sdk/9.6/manifest.json",
                        "chip-adapt/sifli.txt",
                    },
                ),
            }
            for key, (name, files) in expected.items():
                zip_path = out / name
                self.assertTrue(zip_path.is_file(), key)
                digest = sha256(zip_path)
                self.assertEqual(summary[key]["zip"], str(zip_path))
                self.assertEqual(summary[key]["sha256"], digest)
                self.assertEqual(
                    summary[key]["bytes"], zip_path.stat().st_size
                )
                checksum = zip_path.with_name(zip_path.name + ".sha256")
                self.assertEqual(
                    checksum.read_text(encoding="utf-8"),
                    f"{digest}  {name}\n",
                )
                manifest_path = zip_path.with_name(
                    zip_path.stem + ".release.json"
                )
                self.assertEqual(summary[key]["manifest"], str(manifest_path))
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema"], "lvgl-ai-release-v1")
                self.assertEqual(set(payload["files"]), files)
                self.assertEqual(payload["sha256"], digest)
                self.assertEqual(payload["package"]["file_count"], len(files))
                self.assertEqual(payload["git_commit"], "cafebabe")
                self.assertEqual(payload["gcc"], {"version": "15.2.0"})

            summary_path = out / "release.json"
            self.assertTrue(summary_path.is_file())
            self.assertEqual(
                json.loads(summary_path.read_text(encoding="utf-8")), summary
            )


if __name__ == "__main__":
    unittest.main()
