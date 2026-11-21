from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control import Recording, Runtime
from scenario import play_scenario
import paths

SETTINGS_SCENARIO = paths.REPO_ROOT / "user" / "scenarios" / "settings.json"
VERSIONS = ("9.6", "9.5", "9.4", "9.1", "8.4", "8.3")
# app.c compiles the directory-discovery registry for 9.4+ only, so the
# versions below it cannot select an app and show an empty screen instead.
DISCOVERY_VERSIONS = ("9.6", "9.5", "9.4")
EXPECTED_LVGL = {
    "9.6": "9.6.0",
    "9.5": "9.5.0",
    "9.4": "9.4.0",
    "9.1": "9.1.0",
    "8.4": "8.4.0",
    "8.3": "8.3.11",
}
EXPECTED_ADAPTER = {
    version: "8x" if version.startswith("8.") else "9x" for version in VERSIONS
}

# 8.3/8.4 spell the button class "lv_btn" and 9.1 "btn"; the matrix compares
# the canonical 9.4+ "lv_button".
CLASS_ALIASES = {"btn": "lv_button", "lv_btn": "lv_button", "obj": "lv_obj"}


def input_rows(recording: Recording) -> list[dict]:
    return [row for row in recording.timeline() if row["type"] == "input"]


def timeline_row_types(recording: Recording) -> list[str]:
    return [row["type"] for row in recording.timeline()]


def artifact_paths(session_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(session_dir).as_posix()
        for path in session_dir.rglob("*")
        if path.is_file()
    )


def without_hit(rows: list[dict]) -> list[dict]:
    return [
        {
            key: value
            for key, value in row.items()
            if key not in ("hit", "hit_class")
        }
        for row in rows
    ]


def canonical_classes(rows: list[dict]) -> list[str]:
    return [
        CLASS_ALIASES.get(row["hit_class"], row["hit_class"]) for row in rows
    ]


class VersionPathRulesTest(unittest.TestCase):
    def test_build_dirs_are_per_version_and_patched_trees_are_separate(
        self,
    ) -> None:
        self.assertEqual(
            paths.build_dir_for("9.6"), paths.BUILD_ROOT / "lvgl_9_6"
        )
        self.assertEqual(
            paths.build_dir_for("9.6-patched"),
            paths.BUILD_ROOT / "lvgl_9_6_patched",
        )
        self.assertEqual(
            paths.build_dir_for("9.5-src"), paths.BUILD_ROOT / "lvgl_9_5_src"
        )
        self.assertEqual(
            paths.build_dir_for("8.4"), paths.BUILD_ROOT / "lvgl_8_4"
        )
        self.assertEqual(
            paths.build_dir_for("8.4-patched"),
            paths.BUILD_ROOT / "lvgl_8_4_patched",
        )
        self.assertEqual(
            paths.build_dir_for("8.3"), paths.BUILD_ROOT / "lvgl_8_3"
        )
        with mock.patch.dict(os.environ, {"LVGL_VERIFY_LOOP_LVGL_SRC": ""}):
            self.assertEqual(
                paths.lvgl_src_for("9.6-patched"),
                paths.LVGL_SRC_ROOT / "9.6-patched",
            )
            self.assertEqual(
                paths.lvgl_src_for("8.4-patched"),
                paths.LVGL_SRC_ROOT / "8.4-patched",
            )

    def test_build_root_override_relocates_every_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertEqual(
                paths.build_dir_for("9.6", build_root=root),
                root / "lvgl_9_6",
            )
            self.assertEqual(
                paths.build_dir_for("9.6", paths.APPS_DIR, build_root=root),
                root / "lvgl_9_6",
            )
            exported = paths.build_dir_for(
                "9.6", root / "elsewhere" / "src" / "app", build_root=root
            )
            self.assertEqual(exported.parent, root)

    def test_build_root_from_env_reads_the_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ, {"LVGL_VERIFY_LOOP_BUILD_ROOT": tmp}
            ):
                self.assertEqual(
                    paths.build_root_from_env(), Path(tmp).resolve()
                )
        with mock.patch.dict(os.environ, {"LVGL_VERIFY_LOOP_BUILD_ROOT": ""}):
            self.assertEqual(paths.build_root_from_env(), paths.BUILD_ROOT)


class MultiVersionMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls._env = mock.patch.dict(os.environ, {"LVGL_VERIFY_LOOP_LVGL_SRC": ""})
        cls._env.start()
        cls.addClassCleanup(cls._env.stop)

        cls.runs: dict[str, tuple[Runtime, Recording]] = {}
        for version in VERSIONS:
            root = Path(cls._tmp.name) / version / "sessions"
            # play_scenario only plays steps: the app comes from Runtime, so
            # the scenario's own "app" field is only honoured by the CLI.
            # Below 9.4 app.c ignores the selection and shows an empty screen.
            kwargs = {"app": "test_ui"} if version in DISCOVERY_VERSIONS else {}
            rt = Runtime(
                lvgl=version,
                build=True,
                sessions_root=root,
                **kwargs,
            )
            rt.start()
            try:
                play_scenario(rt, SETTINGS_SCENARIO)
            finally:
                rt.stop()
            cls.runs[version] = (rt, Recording.open(rt.session_dir))

    def test_ready_and_manifest_report_the_built_version_and_source(
        self,
    ) -> None:
        for version, (rt, recording) in self.runs.items():
            with self.subTest(version=version):
                expected_version = EXPECTED_LVGL[version]
                expected_src = paths.lvgl_src_for(version)
                self.assertEqual(rt.ready["lvgl"], expected_version)
                self.assertEqual(Path(rt.ready["lvgl_src"]), expected_src)
                self.assertEqual(recording.manifest["lvgl"], expected_version)
                self.assertEqual(
                    Path(recording.manifest["lvgl_src"]), expected_src
                )
                self.assertEqual(
                    recording.manifest["adapter"], EXPECTED_ADAPTER[version]
                )
                self.assertEqual(rt.build_dir, paths.build_dir_for(version))
                self.assertTrue(rt.engine_path.is_file())

    def test_versions_build_and_run_the_same_scenario(self) -> None:
        baseline = input_rows(self.runs["9.6"][1])
        baseline_types = timeline_row_types(self.runs["9.6"][1])
        baseline_artifacts = artifact_paths(self.runs["9.6"][0].session_dir)

        # settings.json selects test_ui, so the 9.4+ builds hit its button at
        # (112,324) five times; the trailing three inputs reach the screen.
        self.assertEqual(
            [row["hit"] for row in baseline],
            [
                "test_ui_button",
                "test_ui_button",
                "test_ui_button",
                "test_ui_button",
                "test_ui_button",
                "test_ui",
                "test_ui",
                "test_ui",
            ],
        )
        self.assertTrue(all(row["hit_class"] for row in baseline))

        # 9.4, 9.5 and 9.6 all have the discovery registry, so they run the
        # scenario identically; only 9.1 and 8.x fall back to an empty screen.
        for version in ("9.6", "9.5", "9.4"):
            with self.subTest(version=version):
                rt, recording = self.runs[version]
                rows = input_rows(recording)
                self.assertEqual(rows, baseline)
                self.assertEqual(timeline_row_types(recording), baseline_types)
                self.assertEqual(
                    artifact_paths(rt.session_dir), baseline_artifacts
                )

        # 9.1 and 8.x predate the registry: app.c's else branch leaves the
        # screen empty, so every input hits the screen itself (or nothing)
        # and no button is ever pressed.
        for version in ("9.1", "8.4", "8.3"):
            with self.subTest(version=version, empty=True):
                rows = input_rows(self.runs[version][1])
                self.assertEqual([row["hit"] for row in rows], [""] * 8)
                self.assertTrue(
                    all(row["hit_class"] in ("obj", "lv_obj", "label", "screen")
                        or row["hit_class"] == ""
                        for row in rows),
                    [row["hit_class"] for row in rows],
                )
        self.assertEqual(
            input_rows(self.runs["8.4"][1]), input_rows(self.runs["8.3"][1])
        )

    def test_reference_png_decodes_on_every_version(self) -> None:
        # 9.x lodepng returns a draw buffer and 8.x raw RGBA; a broken decode
        # would crash or diff against an identical run.
        for version in VERSIONS:
            with (
                self.subTest(version=version),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                baseline = Runtime(
                    lvgl=version,
                    build=True,
                    record_changed_only=False,
                    sessions_root=root / "baseline",
                )
                baseline.start()
                baseline.wait(16)
                baseline.stop()
                reference = baseline.session_dir / "frames" / "000002.png"
                self.assertTrue(reference.is_file())

                rt = Runtime(
                    lvgl=version,
                    build=True,
                    record_changed_only=False,
                    sessions_root=root / "reference",
                    reference=reference,
                )
                rt.start()
                try:
                    rt.wait(16)
                finally:
                    rt.stop()
                rows = Recording.open(rt.session_dir).reference_diffs()
                self.assertIsNotNone(rows)
                assert rows is not None
                self.assertEqual(
                    [row["changed_px"] for row in rows[:2]], [0, 0]
                )

    def test_lvgl_version_env_selects_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("9.5", "8.3"):
                with (
                    self.subTest(version=version),
                    mock.patch.dict(
                        os.environ,
                        {
                            "LVGL_VERIFY_LOOP_LVGL_VERSION": version,
                            "LVGL_VERIFY_LOOP_LVGL_SRC": "",
                        },
                    ),
                ):
                    rt = Runtime(
                        build=True,
                        sessions_root=Path(tmp) / version / "sessions",
                    )
                    rt.start()
                    try:
                        self.assertEqual(rt.lvgl, version)
                        self.assertEqual(
                            rt.build_dir, paths.build_dir_for(version)
                        )
                        self.assertEqual(
                            rt.ready["lvgl"], EXPECTED_LVGL[version]
                        )
                        self.assertEqual(
                            rt.ready["adapter"], EXPECTED_ADAPTER[version]
                        )
                    finally:
                        rt.stop()

    def test_lvgl_src_override_is_reported_by_the_engine(self) -> None:
        cases = (("9.5-override", "9.4"), ("8.3-override", "8.4"))
        with tempfile.TemporaryDirectory() as tmp:
            for label, tree in cases:
                override = (paths.LVGL_SRC_ROOT / tree).resolve()
                expected_version = EXPECTED_LVGL[tree]
                adapter = EXPECTED_ADAPTER[tree]
                with (
                    self.subTest(label=label),
                    mock.patch.dict(
                        os.environ, {"LVGL_VERIFY_LOOP_LVGL_SRC": str(override)}
                    ),
                ):
                    rt = Runtime(
                        lvgl=label,
                        build=True,
                        sessions_root=Path(tmp) / label / "sessions",
                    )
                    rt.start()
                    try:
                        self.assertEqual(rt._store.lvgl_src, override)
                        self.assertEqual(
                            rt.build_dir, paths.build_dir_for(label)
                        )
                        self.assertEqual(rt.ready["lvgl"], expected_version)
                        self.assertEqual(Path(rt.ready["lvgl_src"]), override)
                        self.assertEqual(rt.ready["adapter"], adapter)
                    finally:
                        rt.stop()
                    manifest = Recording.open(rt.session_dir).manifest
                    self.assertEqual(manifest["lvgl"], expected_version)
                    self.assertEqual(Path(manifest["lvgl_src"]), override)
                    self.assertEqual(manifest["adapter"], adapter)


class EightXInputSemanticsTest(unittest.TestCase):
    def test_8x_keypad_and_encoder_are_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("8.4", "8.3"):
                with self.subTest(version=version):
                    rt = Runtime(
                        lvgl=version,
                        build=True,
                        sessions_root=Path(tmp) / version / "sessions",
                    )
                    rt.start()
                    try:
                        self.assertIs(
                            rt.key("press", "ENTER")["delivered"], True
                        )
                        self.assertIs(
                            rt.key("release", "ENTER")["delivered"], True
                        )
                        self.assertIs(rt.encoder("turn", 1)["delivered"], True)
                        self.assertIs(
                            rt.encoder("turn", -1)["delivered"], True
                        )
                    finally:
                        rt.stop()
                    log_text = (rt.session_dir / "engine.log").read_text(
                        encoding="utf-8"
                    )
                    # 8.x has no discovery registry and therefore no widgets,
                    # so activation cannot be observed through an app. What
                    # this pins is the adapter: the virtual keypad and encoder
                    # events reached LVGL and were reported as delivered.
                    self.assertIn("[app] app=none (LVGL < 9.4)", log_text)
                    rows = input_rows(Recording.open(rt.session_dir))
                    self.assertEqual(
                        [(row["device"], row["delivered"]) for row in rows],
                        [
                            ("key", True),
                            ("key", True),
                            ("encoder", True),
                            ("encoder", True),
                        ],
                    )

    def test_keypad_enter_activates_the_focused_button(self) -> None:
        # The counterpart to the case above: from 9.4 on there is an app to
        # focus, so ENTER must reach LVGL and fire the button's callback.
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime(
                lvgl="9.4",
                build=True,
                sessions_root=Path(tmp) / "sessions",
                app="test_ui",
            )
            rt.start()
            try:
                self.assertIs(rt.key("press", "ENTER")["delivered"], True)
                self.assertIs(rt.key("release", "ENTER")["delivered"], True)
            finally:
                rt.stop()
            log_text = (rt.session_dir / "engine.log").read_text(
                encoding="utf-8"
            )
            self.assertIn("[app] focus group created", log_text)
            self.assertIn("[app] test_ui_button clicked", log_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
