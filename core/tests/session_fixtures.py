"""Finished-session fixtures shared by the evidence tests.

The builders write ``sessions/<id>/`` directly; no engine and no web server is
started. ``make_summary_session`` is the shape the report/CLI tests read;
``make_recording_session`` is the smaller shape ``Recording`` tests need.
"""

from __future__ import annotations

import json
from pathlib import Path

from support import write_png_rgb

SESSION_NAME = "20260102-030405-abcd"
FRAME_1 = "frames/000001.png"
FRAME_2 = "frames/000002.png"
SNAPSHOT = "snapshots/001_after_click.png"

DEFAULT_ENGINE_LOG = (
    "[app] apps=coffee,settings\n"
    "[app] app_create\n"
    "[app] app=settings\n"
    "[app] app=coffee\n"
)
RECORDING_ENGINE_LOG = "[app] app_create\n[app] hello\n"


def make_session(
    root: Path,
    *,
    name: str = SESSION_NAME,
    status: str = "ok",
    app: str = "coffee",
    display: dict | None = None,
    manifest_schema: str = "lvgl-ai-session-v1",
    artifacts: dict | None = None,
    record_changed_only: bool = True,
    with_timeline: bool = True,
    with_frame_diffs: bool = True,
    with_frames: bool = True,
    with_snapshot: bool = False,
    with_annotations: bool = False,
    with_engine_log: bool = True,
    with_build_log: bool = False,
    frames: int = 2,
    frame_count: int | None = None,
    engine_log: str | None = None,
    error: dict | None = None,
    timeline: str = "summary",
) -> Path:
    """Write one finished session and return its directory."""
    session = root / name
    (session / "frames").mkdir(parents=True)
    if with_frames:
        write_png_rgb(session / FRAME_1, 2, 2, [(255, 0, 0)] * 4)
        if frames >= 2:
            write_png_rgb(session / FRAME_2, 2, 2, [(0, 255, 0)] * 4)
    if with_snapshot:
        (session / "snapshots").mkdir()
        write_png_rgb(session / SNAPSHOT, 1, 1, [(0, 0, 255)])

    if frame_count is None:
        frame_count = frames if with_timeline else 0

    if with_timeline:
        rows = _timeline_rows(
            timeline, frames, with_snapshot, frame_count
        )
        (session / "timeline.ndjson").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    if with_frame_diffs:
        diff = {
            "schema": "lvgl-ai-frame-diffs-v1",
            "frame_no": 2,
            "prev_frame_no": 1,
            "t_ms": 32,
            "width": 2,
            "height": 2,
            "threshold": 10,
            "bbox": (
                {"x": 0, "y": 0, "w": 1, "h": 1}
                if timeline == "minimal"
                else {"x": 0, "y": 0, "w": 2, "h": 2}
            ),
            "changed_px": 1 if timeline == "minimal" else 9,
            "changed_ratio": 0.25,
            "max_delta": 0.2,
        }
        (session / "frame_diffs.ndjson").write_text(
            json.dumps(diff) + "\n", encoding="utf-8"
        )

    if with_annotations:
        (session / "annotations.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-annotations-v1",
                    "notes": [
                        {
                            "id": "n1",
                            "frame_no": 1,
                            "t_ms": 0,
                            "regions": [{"x": 1, "y": 2, "w": 3, "h": 4}],
                            "tags": ["layout"],
                            "text": "button is too low",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if with_engine_log:
        (session / "engine.log").write_text(
            DEFAULT_ENGINE_LOG if engine_log is None else engine_log,
            encoding="utf-8",
        )
    if with_build_log:
        (session / "build.log").write_text(
            "# phase: build\nok\n", encoding="utf-8"
        )

    if artifacts is None:
        artifacts = {"manifest": "manifest.json"}
        if with_build_log:
            artifacts["build_log"] = "build.log"
        if with_engine_log:
            artifacts["engine_log"] = "engine.log"
        if with_timeline:
            artifacts["timeline"] = "timeline.ndjson"
        if with_frame_diffs:
            artifacts["frame_diffs"] = "frame_diffs.ndjson"
        if with_frames:
            artifacts["frames"] = [FRAME_1] + (
                [FRAME_2] if frames >= 2 else []
            )
        if with_snapshot:
            artifacts["snapshots"] = [SNAPSHOT]

    manifest = {
        "schema": manifest_schema,
        "id": name,
        "status": status,
        "app": app,
        "record_changed_only": record_changed_only,
        "mode": "headless",
        "input": ["real", "virtual"],
        "build": {"status": "ok", "log": "build.log"},
        "lvgl": "9.6.0",
        "lvgl_src": "I:/lvgl-src/9.6",
        "adapter": "9x",
        "display": display,
        "tool_version": "0.1.0",
        "frame_count": frame_count,
        "truncated": False,
        "log_truncated": False,
        "checks": [],
        "error": error,
        "artifacts": artifacts,
    }
    (session / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return session


def make_summary_session(root: Path, **overrides) -> Path:
    """Session shaped like the report/CLI tests: timeline, frames, snapshot."""
    options = dict(
        timeline="summary",
        with_snapshot=True,
        with_annotations=False,
        with_build_log=False,
        frames=2,
    )
    options.update(overrides)
    return make_session(root, **options)


def make_recording_session(root: Path, **overrides) -> Path:
    """Minimal session shaped like the ``Recording`` tests."""
    options = dict(
        timeline="minimal",
        with_snapshot=False,
        with_annotations=True,
        with_build_log=True,
        frames=1,
        engine_log=RECORDING_ENGINE_LOG,
    )
    options.update(overrides)
    return make_session(root, **options)


def _timeline_rows(
    kind: str, frames: int, with_snapshot: bool, frame_count: int
) -> list[dict]:
    if kind == "minimal":
        return [
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "frame",
                "frame_no": 1,
                "t_ms": 0,
                "file": FRAME_1,
            },
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "end",
                "frame_count": frame_count,
                "t_ms": 0,
                "truncated": False,
            },
        ]
    if kind != "summary":
        raise ValueError(f"unknown timeline fixture kind: {kind!r}")
    rows = [
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "frame",
            "frame_no": 1,
            "t_ms": 0,
            "file": FRAME_1,
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "input",
            "seq": 1,
            "source": "scenario",
            "frame_no": 1,
            "t_ms": 0,
            "device": "pointer",
            "action": "down",
            "x": 112,
            "y": 324,
            "hit": "btn",
            "hit_class": "lv_button",
        },
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "mark",
            "frame_no": 1,
            "t_ms": 16,
            "id": "start",
        },
    ]
    if with_snapshot:
        rows.append(
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "snapshot",
                "frame_no": 1,
                "t_ms": 16,
                "label": "after_click",
                "file": SNAPSHOT,
            }
        )
    if frames >= 2:
        rows.extend(
            [
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "frame",
                    "frame_no": 2,
                    "t_ms": 32,
                    "file": FRAME_2,
                },
                {
                    "schema": "lvgl-ai-timeline-v1",
                    "type": "input",
                    "seq": 2,
                    "source": "scenario",
                    "frame_no": 2,
                    "t_ms": 32,
                    "device": "key",
                    "action": "press",
                    "key": "ENTER",
                    "delivered": True,
                },
            ]
        )
    rows.append(
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "end",
            "frame_count": frame_count,
            "t_ms": 32,
            "truncated": False,
        }
    )
    return rows
