"""Static checks for the Windows double-click launchers."""

from __future__ import annotations

import importlib.util
import struct
import unittest
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_ROOT.parent
LAUNCHERS_DIR = TOOL_ROOT / "tools" / "launchers"


def load_build():
    path = LAUNCHERS_DIR / "build.py"
    spec = importlib.util.spec_from_file_location("launcher_build", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LauncherConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build = load_build()
        cls.entries = {entry["name"]: entry for entry in cls.build.LAUNCHERS}

    def test_viewer_launcher_lives_at_the_repository_root(self) -> None:
        entry = self.entries["lvgl-ai-viewer"]
        self.assertEqual(entry["target"], r"core\web.pyw")
        self.assertEqual(entry["cwd"], ".")
        self.assertEqual(entry["args"], ())
        self.assertEqual(entry["python"], r"runtime\python\pythonw.exe")
        self.assertEqual(entry["output"], REPO_ROOT / "LVGL-AI-Viewer.exe")

    def test_host_launcher_lives_in_the_sifli_tools_directory(self) -> None:
        entry = self.entries["sifli-host"]
        self.assertEqual(entry["target"], r"..\host\server.py")
        self.assertEqual(entry["cwd"], r"..\host")
        self.assertEqual(entry["args"], ("--open",))
        self.assertEqual(
            entry["python"], r"..\..\..\runtime\python\pythonw.exe"
        )
        self.assertEqual(
            entry["output"], REPO_ROOT / "chip-adapt" / "sifli" / "tools" / "SiFli-Host.exe"
        )

    def test_launchers_do_not_embed_viewer_logic(self) -> None:
        source = (LAUNCHERS_DIR / "launcher.c").read_text(encoding="utf-8")
        for retired in ("http://", "--manage", "?manage=1", "cmd.exe", "netstat"):
            self.assertNotIn(retired, source)

    def test_viewer_defaults_to_no_build(self) -> None:
        source = (TOOL_ROOT / "web.pyw").read_text(encoding="utf-8")
        self.assertIn('"--no-build"', source)

    def test_build_uses_a_gui_subsystem_and_resource_files(self) -> None:
        source = (LAUNCHERS_DIR / "build.py").read_text(encoding="utf-8")
        self.assertIn('"-mwindows"', source)
        self.assertIn('"coff"', source)
        for entry in self.build.LAUNCHERS:
            self.assertTrue((LAUNCHERS_DIR / f"{entry['name']}.rc").is_file())


class IconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.icons = load_build().icons

    def _icon_bytes(self, name: str) -> bytes:
        path = LAUNCHERS_DIR / "icons" / f"{name}.ico"
        if not path.is_file():
            self.skipTest(f"{path} has not been generated")
        return path.read_bytes()

    def test_icons_cover_the_documented_sizes(self) -> None:
        for name in self.icons.ICON_NAMES:
            with self.subTest(icon=name):
                data = self._icon_bytes(name)
                reserved, kind, count = struct.unpack_from("<HHH", data, 0)
                self.assertEqual((reserved, kind), (0, 1))
                self.assertEqual(count, len(self.icons.SIZES))
                sizes = []
                for index in range(count):
                    entry = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
                    width, height, colors, entry_reserved, planes, bits, length, offset = entry
                    sizes.append(width or 256)
                    self.assertEqual(width, height)
                    self.assertEqual(colors, 0)
                    self.assertEqual(entry_reserved, 0)
                    self.assertEqual(planes, 1)
                    self.assertEqual(bits, 32)
                    self.assertLessEqual(offset + length, len(data))
                self.assertEqual(set(sizes), set(self.icons.SIZES))

    def test_the_two_icons_are_different(self) -> None:
        self.assertNotEqual(
            self._icon_bytes("lvgl-ai-viewer"), self._icon_bytes("sifli-host")
        )


if __name__ == "__main__":
    unittest.main()
