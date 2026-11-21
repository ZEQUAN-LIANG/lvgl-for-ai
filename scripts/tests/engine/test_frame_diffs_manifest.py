from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from control import Recording, Runtime
from scripts.tests.support import read_png_rgb

BUTTON_CENTER = (112, 324)
WIDTH = 800
HEIGHT = 600
MANIFEST_FIELDS = (
    "schema",
    "id",
    "status",
    "mode",
    "input",
    "build",
    "lvgl",
    "lvgl_src",
    "adapter",
    "display",
    "tool_version",
    "record_changed_only",
    "frame_count",
    "truncated",
    "log_truncated",
    "checks",
    "error",
    "artifacts",
)
STATUSES = {"ok", "build_error", "link_error", "crash", "harness_error"}


def read_ndjson(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def expected_diff(
    previous: Path, current: Path, threshold: int = 10
) -> tuple[dict | None, int, float, float]:
    width, height, before = read_png_rgb(previous)
    other_width, other_height, after = read_png_rgb(current)
    if (width, height) != (other_width, other_height):
        raise AssertionError("frame sizes differ")
    min_x, min_y, max_x, max_y = width, height, -1, -1
    changed = 0
    max_delta = 0
    for index, (left, right) in enumerate(zip(before, after)):
        delta = max(
            abs(left[channel] - right[channel]) for channel in range(3)
        )
        if delta > max_delta:
            max_delta = delta
        if delta > threshold:
            changed += 1
            x = index % width
            y = index // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    bbox = None
    if changed:
        bbox = {
            "x": min_x,
            "y": min_y,
            "w": max_x - min_x + 1,
            "h": max_y - min_y + 1,
        }
    return bbox, changed, changed / (width * height), max_delta / 255.0


class FrameDiffManifestIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sessions_root = Path(self._tmp.name) / "sessions"

    def _runtime(self, **kwargs) -> Runtime:
        options = {
            "lvgl": "9.6",
            "app": "test_ui",
            "build": True,
            "record_changed_only": False,
            "sessions_root": self.sessions_root,
        }
        options.update(kwargs)
        return Runtime(**options)

    def test_manifest_has_all_fields_and_artifacts_match_disk(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        rt.tick(16)
        rt.pointer("down", *BUTTON_CENTER)
        rt.tick(16)
        rt.snapshot("evidence")

        live = rt.recording
        self.assertEqual(live.manifest["status"], "ok")
        self.assertEqual(live.timeline()[0]["type"], "frame")
        self.assertTrue((rt.session_dir / "frame_diffs.ndjson").is_file())

        rt.stop()
        recording = Recording.open(rt.session_dir)
        manifest = recording.manifest
        self.assertEqual(manifest["schema"], "lvgl-verify-loop-session-v1")
        self.assertIn(manifest["status"], STATUSES)
        self.assertEqual(manifest["status"], "ok")
        for field in MANIFEST_FIELDS:
            self.assertIn(field, manifest)
        self.assertIsNone(manifest["error"])
        self.assertEqual(manifest["id"], rt.session_id)
        self.assertEqual(manifest["mode"], "headless")
        self.assertEqual(manifest["input"], ["real", "virtual"])
        self.assertEqual(manifest["lvgl"], "9.6.0")
        self.assertEqual(manifest["adapter"], "9x")
        self.assertEqual(manifest["display"], {"width": 800, "height": 600})
        self.assertEqual(manifest["frame_count"], len(recording.frames))
        self.assertIs(manifest["truncated"], False)
        self.assertIs(manifest["log_truncated"], False)
        self.assertEqual(
            manifest["checks"],
            [
                {"cmd": "tick 16", "ok": True, "frame_no": 2},
                {"cmd": "pointer down 112 324", "ok": True, "frame_no": 2},
                {"cmd": "tick 16", "ok": True, "frame_no": 3},
                {"cmd": "snapshot evidence", "ok": True, "frame_no": 3},
                {"cmd": "quit", "ok": True, "frame_no": 3},
            ],
        )

        artifacts = manifest["artifacts"]
        for key in (
            "manifest",
            "build_log",
            "engine_log",
            "timeline",
            "frame_diffs",
            "frames",
            "snapshots",
        ):
            self.assertIn(key, artifacts)
        for value in artifacts.values():
            paths = value if isinstance(value, list) else [value]
            for relative in paths:
                self.assertTrue(
                    (recording.path / relative).is_file(),
                    f"artifact {relative} does not exist",
                )
        self.assertEqual(artifacts["frame_diffs"], "frame_diffs.ndjson")
        self.assertEqual(len(artifacts["frames"]), 3)
        self.assertEqual(
            artifacts["snapshots"], ["snapshots/001_evidence.png"]
        )

        rt.stop()
        final = Recording.open(rt.session_dir).manifest
        self.assertEqual(final["status"], "ok")
        self.assertEqual(final["frame_count"], 3)
        self.assertEqual(len(final["artifacts"]["frames"]), 3)

    def test_frame_diffs_skip_first_frame_and_match_the_pngs(self) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        self.assertTrue((rt.session_dir / "frame_diffs.ndjson").is_file())
        self.assertEqual(
            read_ndjson(rt.session_dir / "frame_diffs.ndjson"), []
        )

        rt.tick(16)
        rt.pointer("down", *BUTTON_CENTER)
        rt.wait(64)
        rt.stop()

        rows = read_ndjson(rt.session_dir / "frame_diffs.ndjson")
        frame_count = len(list((rt.session_dir / "frames").glob("*.png")))
        self.assertEqual(frame_count, 6)
        self.assertEqual(
            [row["schema"] for row in rows],
            ["lvgl-verify-loop-frame-diffs-v1"] * 5,
        )
        self.assertEqual([row["frame_no"] for row in rows], [2, 3, 4, 5, 6])
        self.assertEqual(
            [row["prev_frame_no"] for row in rows], [1, 2, 3, 4, 5]
        )
        self.assertEqual([row["t_ms"] for row in rows], [16, 32, 48, 64, 80])
        for row in rows:
            self.assertEqual(row["threshold"], 10)
            self.assertEqual((row["width"], row["height"]), (WIDTH, HEIGHT))

        unchanged = rows[0]
        self.assertEqual(unchanged["changed_px"], 0)
        self.assertIsNone(unchanged["bbox"])
        self.assertEqual(unchanged["changed_ratio"], 0.0)
        self.assertEqual(unchanged["max_delta"], 0.0)

        for row in rows:
            previous = (
                rt.session_dir / "frames" / f"{row['prev_frame_no']:06d}.png"
            )
            current = rt.session_dir / "frames" / f"{row['frame_no']:06d}.png"
            bbox, changed, ratio, max_delta = expected_diff(previous, current)
            self.assertEqual(row["bbox"], bbox)
            self.assertEqual(row["changed_px"], changed)
            self.assertAlmostEqual(row["changed_ratio"], ratio, places=9)
            self.assertAlmostEqual(row["max_delta"], max_delta, places=9)

        self.assertGreater(
            max(row["changed_px"] for row in rows),
            0,
            "the pressed-button transition must change pixels",
        )

    def test_diff_threshold_is_configurable(self) -> None:
        rt = self._runtime(diff_threshold=255)
        self.addCleanup(rt.stop)
        rt.start()
        rt.tick(16)
        rt.pointer("down", *BUTTON_CENTER)
        rt.wait(64)
        rt.stop()

        rows = read_ndjson(rt.session_dir / "frame_diffs.ndjson")
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row["threshold"], 255)
            self.assertEqual(row["changed_px"], 0)
            self.assertIsNone(row["bbox"])
            self.assertEqual(row["changed_ratio"], 0.0)
        self.assertGreater(max(row["max_delta"] for row in rows), 0.0)

    def test_invalid_diff_threshold_is_rejected(self) -> None:
        for value in (-1, 256, True, 10.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Runtime(
                        lvgl="9.6",
                        build=False,
                        sessions_root=self.sessions_root,
                        diff_threshold=value,
                    )

    def test_recording_open_replays_a_finished_session(self) -> None:
        rt = self._runtime()
        rt.start()
        rt.tick(16)
        rt.pointer("down", *BUTTON_CENTER)
        rt.tick(16)
        rt.mark("after_press")
        rt.snapshot("after_press")
        rt.stop()

        recording = Recording.open(rt.session_dir)
        self.assertEqual(recording.manifest["status"], "ok")
        self.assertEqual(len(recording.frames), 3)
        self.assertEqual(
            [row["type"] for row in recording.timeline()],
            ["frame", "frame", "input", "frame", "mark", "snapshot", "end"],
        )
        self.assertEqual(len(recording.frame_diffs()), 2)
        self.assertIn("[app] app_create", recording.log())
        self.assertEqual(recording.annotations["notes"], [])
        self.assertIn("# phase:", recording.build_log())

    def test_runtime_recording_annotations_are_written_to_the_session(
        self,
    ) -> None:
        rt = self._runtime()
        self.addCleanup(rt.stop)
        rt.start()
        rt.recording.annotations = {
            "schema": "lvgl-verify-loop-annotations-v1",
            "notes": [
                {
                    "id": "n1",
                    "frame_no": 1,
                    "t_ms": 0,
                    "regions": [{"x": 0, "y": 0, "w": 10, "h": 10}],
                    "tags": ["review"],
                    "text": "logo overlaps title",
                }
            ],
        }
        rt.stop()
        final = Recording.open(rt.session_dir)
        self.assertEqual(final.annotations["notes"][0]["id"], "n1")
        self.assertEqual(
            final.manifest["artifacts"]["annotations"], "annotations.json"
        )

    def test_reference_diffs_compare_every_frame_to_the_reference(
        self,
    ) -> None:
        baseline = self._runtime()
        baseline.start()
        baseline.wait(16)
        baseline.stop()
        reference = baseline.session_dir / "frames" / "000002.png"

        rt = self._runtime(reference=reference)
        rt.start()
        rt.tick(16)
        rt.pointer("down", *BUTTON_CENTER)
        rt.wait(64)
        rt.stop()

        rows = read_ndjson(rt.session_dir / "reference_diffs.ndjson")
        self.assertEqual([row["frame_no"] for row in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual(
            [row["schema"] for row in rows],
            ["lvgl-verify-loop-frame-diffs-v1"] * 6,
        )
        self.assertTrue(all(row["prev_frame_no"] is None for row in rows))
        self.assertEqual([row["changed_px"] for row in rows[:2]], [0, 0])
        for row in rows:
            current = rt.session_dir / "frames" / f"{row['frame_no']:06d}.png"
            bbox, changed, ratio, max_delta = expected_diff(reference, current)
            self.assertEqual(row["bbox"], bbox)
            self.assertEqual(row["changed_px"], changed)
            self.assertAlmostEqual(row["changed_ratio"], ratio, places=9)
            self.assertAlmostEqual(row["max_delta"], max_delta, places=9)
        self.assertGreater(max(row["changed_px"] for row in rows), 0)

        manifest = Recording.open(rt.session_dir).manifest
        self.assertEqual(
            manifest["artifacts"]["reference_diffs"], "reference_diffs.ndjson"
        )

    def test_relative_reference_path_is_anchored_to_caller_cwd(self) -> None:
        baseline = self._runtime()
        baseline.start()
        baseline.wait(16)
        baseline.stop()
        source = baseline.session_dir / "frames" / "000002.png"

        caller_dir = Path(self._tmp.name) / "caller"
        caller_dir.mkdir()
        shutil.copyfile(source, caller_dir / "ref.png")
        previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, previous_cwd)
        os.chdir(caller_dir)

        rt = self._runtime(build=False, reference="ref.png")
        rt.start()
        rt.tick(16)
        rt.stop()

        self.assertEqual(rt.reference, caller_dir / "ref.png")
        rows = read_ndjson(rt.session_dir / "reference_diffs.ndjson")
        self.assertEqual([row["changed_px"] for row in rows], [0, 0])

    def test_missing_reference_image_is_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            Runtime(
                lvgl="9.6",
                build=False,
                sessions_root=self.sessions_root,
                reference=Path(self._tmp.name) / "missing.png",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
