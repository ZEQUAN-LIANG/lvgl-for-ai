
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from lvgl_ai.web import create_server
from support import write_png_rgb

SESSION_ID = "20260102-030405-abcd"
FRAME_COLORS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (0, 255, 255),
    (255, 0, 255),
]


def frame_name(number: int) -> str:
    return f"frames/{number:06d}.png"


def make_web_session(
    root: str | Path,
    *,
    session_id: str = SESSION_ID,
    frame_count: int = 3,
    with_snapshots: bool = True,
    with_annotations: bool = False,
    with_reference_diffs: bool = False,
    status: str = "ok",
    app: str | None = None,
) -> Path:
    session = Path(root) / session_id
    frames_dir = session / "frames"
    frames_dir.mkdir(parents=True)
    for number in range(1, frame_count + 1):
        color = FRAME_COLORS[(number - 1) % len(FRAME_COLORS)]
        write_png_rgb(
            session / frame_name(number), 2, 2, [color, color, color, color]
        )

    timeline: list[dict] = []
    for number in range(1, frame_count + 1):
        timeline.append(
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "frame",
                "frame_no": number,
                "t_ms": (number - 1) * 16,
                "file": frame_name(number),
            }
        )
    if frame_count >= 2:
        timeline.append(
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "input",
                "seq": 1,
                "frame_no": 1,
                "t_ms": 0,
                "device": "pointer",
                "action": "down",
                "x": 1,
                "y": 1,
                "hit": "demo_button",
                "hit_class": "lv_button",
            }
        )
        timeline.append(
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "mark",
                "frame_no": 2,
                "t_ms": 16,
                "id": "after_click",
            }
        )
    snapshots: list[str] = []
    if with_snapshots and frame_count >= 1:
        snapshot_rel = "snapshots/001_after_click.png"
        (session / "snapshots").mkdir()
        write_png_rgb(
            session / snapshot_rel, 2, 2, [(9, 9, 9), (9, 9, 9), (9, 9, 9), (9, 9, 9)]
        )
        snapshots.append(snapshot_rel)
        timeline.append(
            {
                "schema": "lvgl-ai-timeline-v1",
                "type": "snapshot",
                "frame_no": min(2, frame_count),
                "t_ms": min(16, (frame_count - 1) * 16),
                "label": "after_click",
                "file": snapshot_rel,
            }
        )
    timeline.append(
        {
            "schema": "lvgl-ai-timeline-v1",
            "type": "end",
            "frame_count": frame_count,
            "t_ms": max(0, (frame_count - 1) * 16),
            "truncated": False,
        }
    )
    (session / "timeline.ndjson").write_text(
        "".join(json.dumps(row) + "\n" for row in timeline), encoding="utf-8"
    )

    diff_rows = []
    for number in range(2, frame_count + 1):
        diff_rows.append(
            {
                "schema": "lvgl-ai-frame-diffs-v1",
                "frame_no": number,
                "prev_frame_no": number - 1,
                "t_ms": (number - 1) * 16,
                "width": 2,
                "height": 2,
                "threshold": 10,
                "bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
                "changed_px": 1,
                "changed_ratio": 0.25,
                "max_delta": 0.2,
            }
        )
    (session / "frame_diffs.ndjson").write_text(
        "".join(json.dumps(row) + "\n" for row in diff_rows), encoding="utf-8"
    )
    if with_reference_diffs:
        reference_rows = [
            {
                "schema": "lvgl-ai-frame-diffs-v1",
                "frame_no": number,
                "prev_frame_no": None,
                "t_ms": (number - 1) * 16,
                "width": 2,
                "height": 2,
                "threshold": 10,
                "bbox": {"x": 1, "y": 1, "w": 1, "h": 1},
                "changed_px": 1,
                "changed_ratio": 0.25,
                "max_delta": 0.1,
            }
            for number in range(1, frame_count + 1)
        ]
        (session / "reference_diffs.ndjson").write_text(
            "".join(json.dumps(row) + "\n" for row in reference_rows),
            encoding="utf-8",
        )
    if with_annotations:
        (session / "annotations.json").write_text(
            json.dumps(
                {
                    "schema": "lvgl-ai-annotations-v1",
                    "notes": [
                        {
                            "id": "seed-note",
                            "frame_no": 1,
                            "t_ms": 0,
                            "regions": [{"x": 0, "y": 0, "w": 1, "h": 1}],
                            "tags": ["seed"],
                            "text": "existing note",
                            "author": "human",
                            "source": "web",
                            "feedback_anchor": {"kind": "t_ms", "t_ms": 0},
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    (session / "engine.log").write_text(
        "[app] app_create\n[app] marker line\n", encoding="utf-8"
    )
    (session / "build.log").write_text("# phase: build\nbuilt\n", encoding="utf-8")

    artifacts: dict = {
        "manifest": "manifest.json",
        "build_log": "build.log",
        "engine_log": "engine.log",
        "timeline": "timeline.ndjson",
        "frame_diffs": "frame_diffs.ndjson",
        "frames": [frame_name(number) for number in range(1, frame_count + 1)],
    }
    if snapshots:
        artifacts["snapshots"] = snapshots
    if with_annotations:
        artifacts["annotations"] = "annotations.json"
    if with_reference_diffs:
        artifacts["reference_diffs"] = "reference_diffs.ndjson"
    manifest = {
        "schema": "lvgl-ai-session-v1",
        "id": session_id,
        "status": status,
        "app": app,
        "scenario": None,
        "source_digest": None,
        "mode": "headless",
        "input": ["real", "virtual"],
        "build": {"status": "ok", "log": "build.log"},
        "lvgl": "9.6.0",
        "lvgl_src": "I:/lvgl-src/9.6",
        "adapter": "9x",
        "tool_version": "0.1.0",
        "frame_count": frame_count,
        "truncated": False,
        "log_truncated": False,
        "checks": [],
        "error": None,
        "artifacts": artifacts,
    }
    (session / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return session


class WebHarness:

    def __init__(
        self,
        sessions_root,
        *,
        runtime_factory=None,
        lvgl=None,
        scenarios_dir=None,
        repo_root=None,
        page_clock=None,
    ):
        self.server = create_server(
            sessions_root=sessions_root,
            scenarios_dir=scenarios_dir,
            repo_root=repo_root,
            runtime_factory=runtime_factory,
            lvgl=lvgl,
            host="127.0.0.1",
            port=0,
            page_clock=page_clock,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="web-test", daemon=True
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def request(
        self,
        method: str,
        path: str,
        *,
        payload=None,
        raw: bytes | None = None,
        headers: dict | None = None,
        timeout: float = 30.0,
    ):
        data = raw
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method
        )
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def json(self, method: str, path: str, **kwargs):
        status, headers, body = self.request(method, path, **kwargs)
        return status, headers, json.loads(body.decode("utf-8"))

    def html(self, path: str = "/"):
        status, headers, body = self.request("GET", path)
        return status, headers, body.decode("utf-8")

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
