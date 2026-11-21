from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

from paths import ensure_import_paths

ensure_import_paths()

from flash_control import (  # noqa: E402
    Esptool,
    FlashController,
    FlashError,
    _Progress,
    build_flash_command,
    parse_flash_args_text,
    preferred_flash_port,
)
from flasher_web import PlanStore, asset_path  # noqa: E402
from host import HostHandler, HostServer, HostState  # noqa: E402
from jobs import Job  # noqa: E402


def write_build(root: Path) -> Path:
    build = root / "build"
    (build / "bootloader").mkdir(parents=True)
    (build / "partition_table").mkdir()
    (build / "bootloader" / "bootloader.bin").write_bytes(b"B" * 64)
    (build / "partition_table" / "partition-table.bin").write_bytes(b"P" * 64)
    (build / "app.bin").write_bytes(b"A" * 64)
    (build / "flash_args").write_text(
        "--flash_mode dio --flash_freq 80m --flash_size 4MB "
        "0x0 bootloader/bootloader.bin "
        "0x8000 partition_table/partition-table.bin "
        "0x10000 app.bin\n",
        encoding="utf-8",
    )
    return build


def make_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def wait_job(job: Job, timeout: float = 10.0) -> Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.status in ("ok", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job.status}")


class FlashPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"
        self.controller = FlashController(
            HOST_DIR,
            {"flash_cache_dir": str(self.cache)},
            broker=None,
            fake=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parse_flash_args(self) -> None:
        parsed = parse_flash_args_text(
            "--flash_mode=dio --flash_freq 80m --flash_size 4MB "
            "0x0 'my app.bin' 0x8000 partition-table.bin"
        )
        self.assertEqual(parsed["flash_mode"], "dio")
        self.assertEqual(parsed["flash_freq"], "80m")
        self.assertEqual(parsed["flash_size"], "4MB")
        self.assertEqual(
            parsed["pairs"],
            [("0x0", "my app.bin"), ("0x8000", "partition-table.bin")],
        )

    def test_flasher_args_json_directory(self) -> None:
        build = self.root / "json-build"
        (build / "bootloader").mkdir(parents=True)
        (build / "bootloader" / "bootloader.bin").write_bytes(b"B" * 32)
        (build / "app.bin").write_bytes(b"A" * 32)
        (build / "flasher_args.json").write_text(
            json.dumps(
                {
                    "flash_files": {
                        "0x0": "bootloader/bootloader.bin",
                        "0x10000": "app.bin",
                    },
                    "flash_settings": {
                        "flash_mode": "dio",
                        "flash_freq": "80m",
                        "flash_size": "4MB",
                    },
                }
            ),
            encoding="utf-8",
        )
        preview = self.controller.plan({"path": str(build)})
        self.assertEqual(preview["notes"], "ESP-IDF flasher_args.json")
        self.assertEqual(
            [(item["address"], item["name"]) for item in preview["entries"]],
            [("0x0", "bootloader.bin"), ("0x10000", "app.bin")],
        )

    def test_directory_plan(self) -> None:
        build = write_build(self.root)
        preview = self.controller.plan({"path": str(build)})
        self.assertEqual(preview["source"], "idf")
        self.assertEqual(
            [(item["name"], item["address"]) for item in preview["entries"]],
            [
                ("bootloader.bin", "0x0"),
                ("partition-table.bin", "0x8000"),
                ("app.bin", "0x10000"),
            ],
        )
        full = self.controller.get_plan(preview["plan_id"])
        self.assertTrue(Path(full["work_dir"]).is_dir())

    def test_zip_flash_args_plan(self) -> None:
        build = write_build(self.root)
        archive = make_zip(
            self.root / "build.zip",
            {
                "build/flash_args": (build / "flash_args").read_bytes(),
                "build/bootloader/bootloader.bin": b"B" * 64,
                "build/partition_table/partition-table.bin": b"P" * 64,
                "build/app.bin": b"A" * 64,
            },
        )
        preview = self.controller.plan({"path": str(archive)})
        self.assertEqual(preview["source"], "idf")
        self.assertEqual(len(preview["entries"]), 3)
        full = self.controller.get_plan(preview["plan_id"])
        for entry in full["entries"]:
            self.assertTrue((Path(full["work_dir"]) / entry["path"]).is_file())

    def test_zip_flasher_args_json(self) -> None:
        archive = make_zip(
            self.root / "json.zip",
            {
                "build/flasher_args.json": json.dumps(
                    {
                        "flash_files": {
                            "0x0": "bootloader.bin",
                            "0x10000": "app.bin",
                        },
                        "flash_settings": {"flash_mode": "dio"},
                    }
                ).encode("utf-8"),
                "build/bootloader.bin": b"B" * 32,
                "build/app.bin": b"A" * 32,
            },
        )
        preview = self.controller.plan({"path": str(archive)})
        self.assertIn("flasher_args.json", preview["notes"])
        self.assertEqual(len(preview["entries"]), 2)

    def test_waveshare_zip(self) -> None:
        archive = make_zip(
            self.root / "demo.zip",
            {"Firmware/ESP32-C6-LCD-1.47-Test.bin": b"F" * 128},
        )
        preview = self.controller.plan({"path": str(archive)})
        self.assertEqual(
            preview["entries"],
            [
                {
                    "name": "ESP32-C6-LCD-1.47-Test.bin",
                    "address": "0x0",
                    "size": 128,
                }
            ],
        )

    def test_single_bin_defaults_to_zero(self) -> None:
        image = self.root / "app.bin"
        image.write_bytes(b"A" * 32)
        preview = self.controller.plan({"path": str(image)})
        self.assertEqual(preview["entries"][0]["address"], "0x0")

    def test_ambiguous_zip(self) -> None:
        archive = make_zip(
            self.root / "multi.zip",
            {"a.bin": b"A", "b.bin": b"B"},
        )
        with self.assertRaises(FlashError) as context:
            self.controller.plan({"path": str(archive)})
        self.assertEqual(context.exception.code, "ambiguous_images")

    def test_zip_slip_is_rejected(self) -> None:
        archive = make_zip(
            self.root / "slip.zip",
            {"../evil.bin": b"E"},
        )
        with self.assertRaises(FlashError) as context:
            self.controller.plan({"path": str(archive)})
        self.assertEqual(context.exception.code, "bad_zip")


class FlashUploadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.controller = FlashController(
            HOST_DIR,
            {
                "flash_cache_dir": str(self.root / "cache"),
                "flash_max_upload_bytes": 16,
            },
            broker=None,
            fake=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sanitizes_name(self) -> None:
        result = self.controller.save_upload("..\\..\\evil.bin", b"1234")
        uploaded = self.controller.uploads_root / result["token"] / "evil.bin"
        self.assertTrue(uploaded.is_file())
        self.assertEqual(result["size"], 4)
        self.assertEqual(len(result["sha256"]), 64)

    def test_rejects_large_upload(self) -> None:
        with self.assertRaises(FlashError) as context:
            self.controller.save_upload("big.bin", b"x" * 17)
        self.assertEqual(context.exception.code, "upload_too_large")


class FlashCommandTest(unittest.TestCase):
    def plan(self) -> dict:
        return {
            "entries": [{"address": "0x0", "path": "app.bin"}],
            "flash_mode": "dio",
            "flash_freq": "80m",
            "flash_size": "4MB",
        }

    def test_esptool_4_command(self) -> None:
        esptool = Esptool(("esptool",), "esptool", (4, 8, 1))
        command = build_flash_command(
            esptool,
            "COM7",
            460800,
            self.plan(),
            {"erase_all": True, "verify": True},
        )
        self.assertIn("write_flash", command)
        self.assertIn("--verify", command)
        self.assertIn("--erase-all", command)
        self.assertIn("--flash_mode", command)
        self.assertEqual(command[-2:], ["0x0", "app.bin"])

    def test_esptool_5_command(self) -> None:
        esptool = Esptool(("esptool",), "esptool", (5, 6, 0))
        command = build_flash_command(
            esptool,
            "COM7",
            921600,
            self.plan(),
            {"erase_all": False, "verify": True, "after": "hard_reset"},
        )
        self.assertIn("write-flash", command)
        self.assertNotIn("--verify", command)
        self.assertIn("--flash-mode", command)
        self.assertNotIn("--flash_mode", command)
        self.assertEqual(command[command.index("--after") + 1], "hard-reset")

    def test_progress_formats(self) -> None:
        legacy = _Progress(1)
        self.assertEqual(legacy.percent_for("Writing at 0x0000... (50 %)"), 50)
        modern = _Progress(1)
        self.assertEqual(
            modern.percent_for("Writing at 0x0000 ━━ 12.3% 256/1024"), 12
        )
        modern.percent_for("Hash of data verified.")
        self.assertEqual(modern.percent_for("unrelated 99% line"), None)


class FakeFlashJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.controller = FlashController(
            HOST_DIR,
            {
                "flash_cache_dir": str(self.root / "cache"),
                "flash_fake_delay": 0.005,
            },
            broker=None,
            fake=True,
        )
        image = self.root / "app.bin"
        image.write_bytes(b"A" * 32)
        self.plan = self.controller.get_plan(
            self.controller.plan({"path": str(image)})["plan_id"]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fake_flash_reaches_100(self) -> None:
        job = Job("flash", "flash")
        self.controller.start(
            job,
            self.plan,
            {"port": "COM99", "reconnect": False},
        )
        wait_job(job)
        self.assertEqual(job.status, "ok")
        self.assertEqual(job.percent, 100)
        self.assertTrue((job.result or {}).get("fake"))

    def test_cancel(self) -> None:
        job = Job("flash", "flash")
        self.controller.start(
            job,
            self.plan,
            {"port": "COM99", "reconnect": False},
        )
        time.sleep(0.01)
        job.cancel()
        wait_job(job)
        self.assertEqual(job.status, "cancelled")


def request_json(
    method: str,
    url: str,
    payload: dict | None = None,
    raw: bytes | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    data = None
    if raw is not None:
        data = raw
        headers["Content-Type"] = "application/octet-stream"
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class FlashHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = HostState(
            fake=True,
            config={
                "log_dir": str(root / "logs"),
                "flash_cache_dir": str(root / "cache"),
                "flash_fake_delay": 0.005,
            },
        )
        self.server = HostServer(("127.0.0.1", 0), HostHandler, self.state)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.state.broker.close()
        self.tmp.cleanup()

    def test_upload_plan_flash(self) -> None:
        status, uploaded = request_json(
            "POST",
            f"{self.base}/api/flash/upload?name=app.bin",
            raw=b"A" * 64,
        )
        self.assertEqual(status, 200)
        self.assertTrue(uploaded["ok"])
        status, preview = request_json(
            "POST",
            f"{self.base}/api/flash/plan",
            {"token": uploaded["token"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(preview["entries"][0]["address"], "0x0")
        status, started = request_json(
            "POST",
            f"{self.base}/api/flash",
            {
                "plan_id": preview["plan_id"],
                "port": "COM99",
                "reconnect": False,
            },
        )
        self.assertEqual(status, 202)
        job_id = started["job_id"]
        deadline = time.time() + 10
        job: dict = {}
        while time.time() < deadline:
            _, payload = request_json(
                "GET", f"{self.base}/api/jobs/{job_id}?since=0"
            )
            job = payload.get("job") or {}
            if job.get("status") in ("ok", "failed", "cancelled"):
                break
            time.sleep(0.02)
        self.assertEqual(job.get("status"), "ok")
        self.assertEqual(job.get("percent"), 100)

    def test_env_reports_fake(self) -> None:
        status, payload = request_json("GET", f"{self.base}/api/flash/env")
        self.assertEqual(status, 200)
        env = payload["env"]
        self.assertTrue(env["fake"])
        self.assertEqual(env["default_baud"], 460800)
        self.assertEqual(env["backend"]["kind"], "esptool")
        self.assertEqual(env["backend"]["name"], "esptool")
        self.assertEqual(env["sources"], ["upload", "path", "build_dir"])
        self.assertIn("hard_reset", env["options"]["after"])
        self.assertIn("usb_reset", env["options"]["before"])
        self.assertEqual(env["defaults"]["port"], "COM99")

    def test_start_alias(self) -> None:
        status, uploaded = request_json(
            "POST",
            f"{self.base}/api/flash/upload?name=alias.bin",
            raw=b"A" * 32,
        )
        self.assertEqual(status, 200)
        _, preview = request_json(
            "POST",
            f"{self.base}/api/flash/plan",
            {"token": uploaded["token"]},
        )
        status, started = request_json(
            "POST",
            f"{self.base}/api/flash/start",
            {
                "plan_id": preview["plan_id"],
                "port": "COM99",
                "reconnect": False,
            },
        )
        self.assertEqual(status, 202)
        job_id = started["job_id"]
        deadline = time.time() + 10
        job: dict = {}
        while time.time() < deadline:
            _, payload = request_json(
                "GET", f"{self.base}/api/jobs/{job_id}?since=0"
            )
            job = payload.get("job") or {}
            if job.get("status") in ("ok", "failed", "cancelled"):
                break
            time.sleep(0.02)
        self.assertEqual(job.get("status"), "ok")

    def test_flasher_page_and_assets(self) -> None:
        with urllib.request.urlopen(f"{self.base}/flash/") as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("烧录器", html)
            self.assertIn("/flash/flasher.js", html)
        with urllib.request.urlopen(
            f"{self.base}/flash/flasher.js"
        ) as response:
            script = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("/api/flash/env", script)


class PortPreferenceTest(unittest.TestCase):
    def test_prefers_esp_usb_serial(self) -> None:
        ports = [
            {
                "port": "COM1",
                "description": "通信端口",
                "hwid": "ACPI\\PNP0501",
            },
            {
                "port": "COM13",
                "description": "USB 串行设备",
                "hwid": "USB VID:PID=303A:1001",
            },
        ]
        with mock.patch("broker.ports", return_value=ports):
            self.assertEqual(preferred_flash_port(), "COM13")

    def test_returns_empty_when_unsure(self) -> None:
        with mock.patch(
            "broker.ports",
            return_value=[{"port": "COM1", "description": "通信端口"}],
        ):
            self.assertEqual(preferred_flash_port(), "")


class SharedFlasherAssetsTest(unittest.TestCase):
    def test_asset_lookup(self) -> None:
        self.assertIsNotNone(asset_path("index.html"))
        self.assertIsNotNone(asset_path("flasher.js"))
        self.assertIsNone(asset_path("../host.py"))
        self.assertIsNone(asset_path("..\\host.py"))
        self.assertIsNone(asset_path("missing.css"))

    def test_plan_store_roundtrip(self) -> None:
        store = PlanStore(ttl_s=10, limit=2)
        plan_id = store.put({"entries": [{"name": "app.bin"}]})
        stored = store.get(plan_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["plan_id"], plan_id)
        self.assertEqual(stored["entries"][0]["name"], "app.bin")
        self.assertIsNone(store.get("missing"))


if __name__ == "__main__":
    unittest.main()
