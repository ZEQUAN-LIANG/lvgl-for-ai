from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import build_flash


class BuildFlashTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "SConstruct").write_text("", encoding="utf-8")
        self.build = self.project / "build_sf32lb52-lchspi-ulp_hcpu"
        self.build.mkdir()
        (self.build / "app.bin").write_bytes(b"ABCD" * 16)
        (self.build / "sftool_param.json").write_text(
            json.dumps(
                {
                    "chip": "SF32LB52",
                    "memory": "NOR",
                    "write_flash": {
                        "verify": True,
                        "files": [
                            {
                                "path": "app.bin",
                                "address": "0x12020000",
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        self.sftool = self.root / "sftool.exe"
        self.sftool.write_bytes(b"")
        self.config = {
            "repo_root": str(self.root),
            "sftool": str(self.sftool),
            "toolchain_root": str(self.root / "toolchain"),
            "sdk_root": str(self.root / "sdk"),
            "export_script": str(self.root / "export.py"),
            "export_ps1": str(self.root / "export.ps1"),
            "build_timeout_sec": 5,
            "flash_timeout_sec": 5,
            "flash_baud": 1_000_000,
            "flash_verify": True,
            "flash_erase_all": False,
            "flash_after": "soft_reset",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_read_sftool_param(self) -> None:
        parsed = build_flash.read_sftool_param(self.build)
        self.assertEqual(parsed["chip"], "SF32LB52")
        self.assertEqual(parsed["memory"], "nor")
        self.assertEqual(len(parsed["entries"]), 1)
        self.assertEqual(parsed["entries"][0]["address"], "0x12020000")

    def test_build_sftool_command(self) -> None:
        parsed = build_flash.read_sftool_param(self.build)
        command = build_flash.build_sftool_command(
            self.sftool,
            port="12",
            baud=1_000_000,
            chip=parsed["chip"],
            memory=parsed["memory"],
            entries=parsed["entries"],
            verify=True,
            erase_all=True,
            after="soft_reset",
        )
        self.assertIn("COM12", command)
        self.assertIn("--verify", command)
        self.assertIn("-e", command)
        self.assertTrue(command[-1].endswith("app.bin@0x12020000"))

    def test_find_build_dir(self) -> None:
        found = build_flash.find_build_dir(
            self.project,
            "sf32lb52-lchspi-ulp",
        )
        self.assertEqual(found, self.build)

    def test_package_firmware(self) -> None:
        cache = self.root / "cache"
        packed = build_flash.package_firmware(self.build, cache)
        zip_path = Path(packed["zip_path"])
        self.assertTrue(zip_path.is_file())
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            self.assertIn("app.bin", names)
            self.assertIn("sftool_param.json", names)
            config = json.loads(
                archive.read("sftool_param.json").decode("utf-8")
            )
            self.assertEqual(
                config["write_flash"]["files"][0]["path"],
                "app.bin",
            )

    def test_package_firmware_flattens_subdirs(self) -> None:
        build = self.root / "nested-build"
        (build / "bootloader").mkdir(parents=True)
        (build / "ftab").mkdir()
        (build / "bootloader" / "bootloader.bin").write_bytes(b"BOOT")
        (build / "ftab" / "ftab.bin").write_bytes(b"FTAB")
        (build / "sftool_param.json").write_text(
            json.dumps(
                {
                    "chip": "SF32LB52",
                    "memory": "NOR",
                    "write_flash": {
                        "verify": True,
                        "files": [
                            {
                                "path": "bootloader/bootloader.bin",
                                "address": "0x12010000",
                            },
                            {
                                "path": "ftab/ftab.bin",
                                "address": "0x12000000",
                            },
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        packed = build_flash.package_firmware(build, self.root / "cache")
        with zipfile.ZipFile(packed["zip_path"]) as archive:
            names = set(archive.namelist())
            self.assertIn("bootloader.bin", names)
            self.assertIn("ftab.bin", names)
            config = json.loads(
                archive.read("sftool_param.json").decode("utf-8")
            )
            paths = [
                item["path"] for item in config["write_flash"]["files"]
            ]
            self.assertEqual(paths, ["bootloader.bin", "ftab.bin"])

    def test_package_firmware_requires_address(self) -> None:
        build = self.root / "no-address"
        build.mkdir()
        (build / "app.bin").write_bytes(b"ABCD")
        (build / "sftool_param.json").write_text(
            json.dumps(
                {
                    "chip": "SF32LB52",
                    "memory": "NOR",
                    "write_flash": {
                        "files": [{"path": "app.bin"}],
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(build_flash.BuildFlashError):
            build_flash.package_firmware(build, self.root / "cache")

    def test_flasher_page_url(self) -> None:
        url = build_flash.flasher_page_url(
            "http://127.0.0.1:8766",
            chip="SF32LB52",
            memory="NOR",
            zip_name="fw.zip",
        )
        self.assertIn("chip=SF32LB52", url)
        self.assertIn("flash=nor", url)
        self.assertIn("zip=http%3A%2F%2F127.0.0.1%3A8766", url)

    def test_find_sftool(self) -> None:
        self.assertEqual(
            build_flash.find_sftool(self.config),
            self.sftool,
        )

    def test_environment(self) -> None:
        env = build_flash.environment(self.config)
        self.assertEqual(env["sftool_found"], str(self.sftool))

    def test_resolve_build_command_from_config_list(self) -> None:
        self.config["build_command"] = ["my-scons", "--board={board}"]
        plan = build_flash.resolve_build_command(self.config, "demo")
        self.assertEqual(plan.argv, ["my-scons", "--board=demo"])
        self.assertFalse(plan.uses_export_shell)

    def test_resolve_build_command_from_config_string(self) -> None:
        self.config["build_command"] = "scons --board={board} -j8"
        plan = build_flash.resolve_build_command(self.config, "demo")
        self.assertEqual(plan.argv, ["scons", "--board=demo", "-j8"])
        self.assertFalse(plan.uses_export_shell)

    def test_resolve_build_command_from_uv_lock(self) -> None:
        lock = Path(self.config["sdk_root"]) / "tools" / "locks" / "default"
        lock.mkdir(parents=True)
        (lock / "uv.lock").write_text("", encoding="utf-8")

        def which(name: str) -> str | None:
            return "C:/bin/uv.exe" if name == "uv" else None

        with mock.patch("build_flash.shutil.which", side_effect=which):
            plan = build_flash.resolve_build_command(self.config, "demo")

        self.assertEqual(
            plan.argv,
            [
                "C:/bin/uv.exe",
                "run",
                "--project",
                str(lock),
                "scons",
                "--board=demo",
                "-j8",
            ],
        )
        self.assertFalse(plan.uses_export_shell)

    @unittest.skipUnless(os.name == "nt", "Windows export.ps1 fallback")
    def test_resolve_build_command_from_export_shell(self) -> None:
        export_ps1 = Path(self.config["export_ps1"])
        export_ps1.write_text("", encoding="utf-8")

        def which(name: str) -> str | None:
            return "C:/ps/powershell.exe" if name == "powershell" else None

        with mock.patch("build_flash.shutil.which", side_effect=which):
            plan = build_flash.resolve_build_command(self.config, "demo")

        self.assertTrue(plan.uses_export_shell)
        self.assertEqual(plan.argv[0], "C:/ps/powershell.exe")
        self.assertIn("scons --board=demo -j8", plan.argv[-1])

    def test_resolve_build_command_missing(self) -> None:
        with mock.patch("build_flash.shutil.which", return_value=None):
            with self.assertRaises(build_flash.BuildFlashError) as caught:
                build_flash.resolve_build_command(self.config, "demo")
        self.assertEqual(caught.exception.code, "scons_missing")

    def test_find_sftool_in_official_tools_layout(self) -> None:
        toolchain_root = self.root / ".sifli"
        sftool = (
            toolchain_root
            / "tools"
            / "sftool"
            / "0.2.5"
            / "sftool.exe"
        )
        sftool.parent.mkdir(parents=True)
        sftool.write_bytes(b"")
        config = dict(self.config, toolchain_root=str(toolchain_root), sftool="")
        self.assertEqual(build_flash.find_sftool(config), sftool)

    def test_find_sftool_honors_env_override(self) -> None:
        explicit = self.root / "env-sftool.exe"
        explicit.write_bytes(b"")
        with mock.patch.dict(
            os.environ, {"SFTOOL_BIN": str(explicit)}, clear=False
        ):
            config = dict(self.config, sftool="")
            self.assertEqual(build_flash.find_sftool(config), explicit)

    def test_toolchain_env_discovers_official_layout(self) -> None:
        root = self.root / ".sifli"
        gcc_bin = (
            root
            / "tools"
            / "arm-none-eabi-gcc"
            / "14.2.1"
            / "bin"
        )
        gcc_bin.mkdir(parents=True)
        config = dict(
            self.config,
            toolchain_root=str(root),
            sdk_root=str(self.root / "sdk"),
        )
        env = build_flash.toolchain_env(config)
        self.assertEqual(env["RTT_EXEC_PATH"], str(gcc_bin))
        self.assertIn(str(gcc_bin), env["PATH"].split(os.pathsep))

    def test_toolchain_env_injects_build_paths(self) -> None:
        root = Path(self.config["toolchain_root"])
        (root / "arm-none-eabi" / "bin").mkdir(parents=True)
        (root / "ninja").mkdir()
        sdk = Path(self.config["sdk_root"])
        (sdk / "tools" / "build").mkdir(parents=True)
        venv = sdk / "tools" / "locks" / "default" / ".venv"
        (venv / ("Scripts" if os.name == "nt" else "bin")).mkdir(parents=True)

        env = build_flash.toolchain_env(self.config)

        self.assertEqual(env["RTT_CC"], "gcc")
        self.assertEqual(env["SIFLI_SDK"], str(sdk))
        self.assertEqual(env["SIFLI_SDK_PATH"], str(sdk))
        self.assertEqual(env["RTT_EXEC_PATH"], str(root / "arm-none-eabi" / "bin"))
        self.assertEqual(env["ENV_ROOT"], str(venv))
        self.assertTrue(
            env["PYTHONPATH"].startswith(str(sdk / "tools" / "build"))
        )
        path_parts = env["PATH"].split(os.pathsep)
        venv_bin = "Scripts" if os.name == "nt" else "bin"
        self.assertTrue(path_parts[0].endswith(venv_bin))
        self.assertIn(str(root / "ninja"), path_parts)

    def test_toolchain_env_applies_china_mirror(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SIFLI_SDK_MIRROR_CHINA": "1",
                "PATH": os.environ.get("PATH", ""),
            },
            clear=True,
        ):
            env = build_flash.toolchain_env(self.config)

        self.assertEqual(
            env["UV_DEFAULT_INDEX"],
            "https://mirrors.ustc.edu.cn/pypi/simple",
        )
        self.assertEqual(
            env["UV_PYTHON_DOWNLOADS_JSON_URL"],
            "https://uv.agentsmirror.com/metadata/python-downloads.json",
        )

    def test_toolchain_env_ignores_mirror_when_disabled(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SIFLI_SDK_MIRROR_CHINA": "0",
                "PATH": os.environ.get("PATH", ""),
            },
            clear=True,
        ):
            env = build_flash.toolchain_env(self.config)

        self.assertNotIn("UV_DEFAULT_INDEX", env)
        self.assertNotIn("UV_PYTHON_DOWNLOADS_JSON_URL", env)

    def test_toolchain_env_keeps_explicit_uv_index(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SIFLI_SDK_MIRROR_CHINA": "1",
                "UV_DEFAULT_INDEX": "https://example.invalid/simple",
                "PATH": os.environ.get("PATH", ""),
            },
            clear=True,
        ):
            env = build_flash.toolchain_env(self.config)

        self.assertEqual(env["UV_DEFAULT_INDEX"], "https://example.invalid/simple")

    def test_flash_options(self) -> None:
        self.assertEqual(
            build_flash._flash_options(
                self.config,
                verify=None,
                erase_all=None,
                after=None,
            ),
            (True, False, "soft_reset"),
        )
        self.assertEqual(
            build_flash._flash_options(
                self.config,
                verify=False,
                erase_all=True,
                after="no_reset",
            ),
            (False, True, "no_reset"),
        )


if __name__ == "__main__":
    unittest.main()
