from __future__ import annotations

import paths

import importlib.util
import ntpath
import struct
import unittest
from pathlib import Path

CONSOLE_ROOT = paths.CONSOLE_ROOT
REPO_ROOT = CONSOLE_ROOT.parent
LAUNCHERS_DIR = paths.SCRIPTS_DIR / "launchers"


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

    def test_viewer_launcher_lives_in_bin(self) -> None:
        entry = self.entries["lvgl-verify-loop-viewer"]
        self.assertEqual(entry["target"], r"..\console\entrypoints\serve.pyw")
        self.assertEqual(entry["cwd"], r"..")
        self.assertEqual(entry["args"], ())
        self.assertNotIn("python", entry)
        self.assertEqual(
            entry["output"], REPO_ROOT / "bin" / "LVGL-AI-Viewer.exe"
        )

    def test_host_launcher_lives_in_the_sifli_launcher_directory(self) -> None:
        entry = self.entries["sifli-host"]
        self.assertEqual(entry["target"], r"..\host\server.py")
        self.assertEqual(entry["cwd"], r"..\host")
        self.assertEqual(entry["args"], ("--open",))
        self.assertNotIn("python", entry)
        self.assertEqual(
            entry["output"],
            REPO_ROOT / "chip-adapt" / "sifli" / "launcher" / "SiFli-Host.exe",
        )

    def test_perf_tape_launcher_lives_in_the_esp32_launcher_directory(
        self,
    ) -> None:
        entry = self.entries["perf-tape"]
        self.assertEqual(entry["target"], r"..\host\launch.py")
        self.assertEqual(entry["cwd"], r"..\host")
        self.assertEqual(entry["args"], ())
        self.assertNotIn("python", entry)
        self.assertEqual(
            entry["output"],
            REPO_ROOT / "chip-adapt" / "esp32" / "launcher" / "PerfTape.exe",
        )

    def test_every_launcher_target_and_cwd_resolve(self) -> None:
        """The C launcher joins them onto the exe dir; they must exist there.

        Every launcher sits one level below the tool it starts, so the
        relative paths are easy to get wrong -- an entry that resolves to
        a missing file makes the built exe fail on double-click with a
        "target not found" dialog.
        """

        for entry in self.build.LAUNCHERS:
            with self.subTest(launcher=entry["name"]):
                exe_dir = entry["output"].parent
                target = Path(
                    ntpath.normpath(ntpath.join(exe_dir, entry["target"]))
                )
                cwd = Path(
                    ntpath.normpath(ntpath.join(exe_dir, entry["cwd"]))
                )
                self.assertTrue(
                    target.is_file(), f"launcher target missing: {target}"
                )
                self.assertTrue(
                    cwd.is_dir(), f"launcher cwd missing: {cwd}"
                )

    def test_launchers_use_python_from_path(self) -> None:
        source = (LAUNCHERS_DIR / "launcher.c").read_text(encoding="utf-8")
        self.assertIn('find_in_path(L"pythonw.exe"', source)
        self.assertIn('find_in_path(L"pyw.exe"', source)
        for retired in (
            "LAUNCHER_PYTHON",
            "console\\python",
            "package runtime",
        ):
            self.assertNotIn(retired, source)

    def test_launchers_do_not_embed_viewer_logic(self) -> None:
        source = (LAUNCHERS_DIR / "launcher.c").read_text(encoding="utf-8")
        for retired in (
            "http://",
            "--manage",
            "?manage=1",
            "cmd.exe",
            "netstat",
        ):
            self.assertNotIn(retired, source)

    def test_viewer_defaults_to_no_build(self) -> None:
        source = paths.entrypoint_path("serve.pyw").read_text(encoding="utf-8")
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
                    entry = struct.unpack_from(
                        "<BBBBHHII", data, 6 + 16 * index
                    )
                    (
                        width,
                        height,
                        colors,
                        entry_reserved,
                        planes,
                        bits,
                        length,
                        offset,
                    ) = entry
                    sizes.append(width or 256)
                    self.assertEqual(width, height)
                    self.assertEqual(colors, 0)
                    self.assertEqual(entry_reserved, 0)
                    self.assertEqual(planes, 1)
                    self.assertEqual(bits, 32)
                    self.assertLessEqual(offset + length, len(data))
                self.assertEqual(set(sizes), set(self.icons.SIZES))

    def test_the_icons_are_all_different(self) -> None:
        blobs = {}
        for name in self.icons.ICON_NAMES:
            data = self._icon_bytes(name)
            for other, blob in blobs.items():
                self.assertNotEqual(
                    data, blob, f"{name} and {other} share one icon"
                )
            blobs[name] = data


if __name__ == "__main__":
    unittest.main()
