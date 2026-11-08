"""Server-rendered HTML for session replay and the live controls.

Everything technical (manifest, checks, raw diffs, engine.log, build.log) is
rendered inside collapsed ``<details>`` blocks. The visible page only shows
the frames, snapshots, timeline, annotations and the optional read-only diff
overlay.

The evidence-to-view conversion lives in :mod:`replay_model`; this module only
turns that one model into markup.  Notes therefore have exactly one renderer
(:func:`_render_notes`): the browser replaces the rendered list with the same
markup after a save instead of rebuilding note fields itself.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from . import urls
from .replay_model import ReplayModel
from .wire import page_config

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATE_PATH = _TEMPLATE_DIR / "page.html"

# The app manager dialog owns one style block, one markup block and three
# script regions inside the page IIFE.  Each partial is substituted at its
# original position, so the inline script keeps the same scope and boot order;
# the rendered page keeps the same DOM, style and script as before the split.
_APP_MANAGER_PARTIALS = {
    "{{APP_MANAGER_STYLE}}": "app_manager.css",
    "{{APP_MANAGER_HTML}}": "app_manager.html",
    "{{APP_MANAGER_STATE_JS}}": "app_manager_state.js",
    "{{APP_MANAGER_ACTIONS_JS}}": "app_manager_actions.js",
    "{{APP_MANAGER_BINDINGS_JS}}": "app_manager_bindings.js",
}


def _partial(name: str) -> str:
    # ``read_text`` normalizes line endings; the placeholder line in page.html
    # owns the surrounding newlines, so strip the partial's file-ending one.
    return (_TEMPLATE_DIR / name).read_text(encoding="utf-8").rstrip("\n")


def _template() -> str:
    # Read per render: editing page.html or an app manager partial should not
    # require restarting web.py.
    markup = _TEMPLATE_PATH.read_text(encoding="utf-8")
    for placeholder, name in _APP_MANAGER_PARTIALS.items():
        markup = markup.replace(placeholder, _partial(name))
    return markup


def _text(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _attr(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def render_page(
    *,
    sessions: list[dict[str, Any]],
    selected_id: str | None,
    replay: ReplayModel | None,
    apps: list[dict[str, Any]] | None = None,
    selected_app: str | None = None,
    page_error: dict[str, str] | None = None,
) -> str:
    options = _render_options(sessions, selected_id)
    app_picker = _render_app_picker(apps or [], selected_app)
    error_html = ""
    if page_error is not None:
        error_html = (
            '<div class="notice" role="alert">'
            f"<strong>{_text(page_error.get('code', 'error'))}</strong> "
            f"{_text(page_error.get('message', ''))}</div>"
        )
    replay_html = _render_replay(
        replay if replay is not None else ReplayModel.empty()
    )
    model_json = _model_json(replay)
    return (
        _template()
        .replace("{{SESSION_OPTIONS}}", options)
        .replace("{{APP_PICKER}}", app_picker)
        .replace("{{PAGE_ERROR}}", error_html)
        .replace("{{REPLAY}}", replay_html)
        .replace("{{MODEL_JSON}}", model_json)
        .replace(
            "{{LIVE_WIRE_JSON}}",
            json.dumps(page_config(), separators=(",", ":")),
        )
    )


def _render_options(
    sessions: list[dict[str, Any]], selected_id: str | None
) -> str:
    if not sessions:
        return '<option value="">（无会话）</option>'
    options = []
    for session in sessions:
        session_id = session["id"]
        label = session_id if session.get("valid", False) else f"{session_id}（不可读）"
        app = session.get("app")
        if isinstance(app, str) and app:
            label = f"{label} · {app}"
        selected = " selected" if session_id == selected_id else ""
        options.append(
            f'<option value="{_attr(session_id)}"{selected}>{_text(label)}</option>'
        )
    return "".join(options)


def _render_app_picker(
    apps: list[dict[str, Any]], selected_app: str | None
) -> str:
    """Live app selector populated from scenarios that declare ``app``.

    The first scenario app is the default; there is no empty "default"
    option, because selecting an app is how the live preview starts.
    """
    if not apps:
        return ""
    known = {entry["app"] for entry in apps}
    current = selected_app or apps[0]["app"]
    extra = current if current not in known else None
    options = []
    for entry in apps:
        app = entry["app"]
        name = entry.get("name") or app
        label = name if name == app else f"{name}（{app}）"
        selected = " selected" if app == current else ""
        options.append(
            f'<option value="{_attr(app)}"{selected}>{_text(label)}</option>'
        )
    if extra is not None:
        options.append(
            f'<option value="{_attr(extra)}" selected>'
            f"{_text(extra)}（当前）</option>"
        )
    return (
        '<div class="app-picker">'
        '<label for="live-app">应用</label>'
        '<select id="live-app" aria-label="应用">'
        + "".join(options)
        + "</select>"
        "</div>"
    )


def _render_replay(model: ReplayModel) -> str:
    session_id = model.session_id
    manifest = model.manifest or {}
    frames = model.frames
    snapshots = model.snapshots
    timeline = model.timeline
    note_count = model.note_count
    frame_count = manifest.get("frame_count", 0)
    has_frames = bool(frames)

    first_frame = frames[0] if frames else None
    image_html = (
        f'<img id="frame-image" alt="第 {_attr(first_frame["frame_no"])} 帧" '
        f'src="{_attr(first_frame["url"])}">'
        if first_frame
        else ""
    )
    stage_class = "stage" if first_frame else "stage is-empty"
    empty_hidden = " hidden" if first_frame else ""
    empty_text = (
        "当前会话没有可显示的帧"
        if session_id
        else "没有可回放的会话"
    )
    empty_sub = (
        "启动测试或录制，或从顶部选择其他会话"
        if session_id
        else "点击上方「测试」进入测试，或用「录制」采集帧"
    )
    slider_max = max(1, len(frames))
    first_t_ms = first_frame["t_ms"] if first_frame else 0
    first_frame_no = first_frame["frame_no"] if first_frame else 0
    hud_frame = f"{first_frame_no:04d}" if first_frame else "----"
    position = f"1 / {frame_count}" if frames else f"0 / {frame_count}"
    ticks = "".join('<i aria-hidden="true"></i>' for _ in range(11))
    slider_disabled = "" if has_frames else " disabled"
    step_disabled = "" if has_frames else " disabled"

    return f"""
<section class="panel replay-panel" id="replay" data-session-id="{_attr(session_id)}" data-frame-count="{_attr(frame_count)}" data-has-frames="{1 if has_frames else 0}" data-live-state="stopped">
  <div class="panel-head">
    <div class="panel-title">
      <span class="eyebrow">RECORD / REPLAY · 录制与回放</span>
      <h2>检视台</h2>
      <span class="session-tag">{_text(session_id or "未选择会话")}</span>
    </div>
    <div class="readout" aria-label="会话统计">
      <div class="readout-item"><span class="readout-label">帧数</span><span class="readout-value" id="frame-total">{_text(frame_count)}</span></div>
      <div class="readout-item"><span class="readout-label">关键画面</span><span class="readout-value" id="snapshot-total">{_text(len(snapshots))}</span></div>
      <div class="readout-item"><span class="readout-label">标注</span><span class="readout-value" id="annotation-total">{_text(note_count)}</span></div>
    </div>
  </div>
  <div class="viewer">
    <div class="viewer-main">
      <div class="stage-shell">
        <div class="stage-bezel">
          <div class="{stage_class}" id="stage" tabindex="0">
            {image_html}
            <canvas id="live-canvas" aria-label="live 实时预览" hidden></canvas>
            <div class="stage-empty" id="stage-empty"{empty_hidden}>
              <span class="stage-empty-mark" aria-hidden="true">▣</span>
              <span id="stage-empty-text">{_text(empty_text)}</span>
              <span class="stage-empty-sub" id="stage-empty-sub">{_text(empty_sub)}</span>
            </div>
            <div class="overlay-layer" id="annotation-layer">
              <div id="selection-box" class="selection-box" hidden></div>
            </div>
            <div class="overlay-layer" id="diff-layer" hidden></div>
          </div>
        </div>
        <div class="stage-hud">
          <div class="hud-frame">
            <span class="hud-label" id="hud-label">FRAME</span>
            <span class="hud-number" id="hud-frame-no">{_text(hud_frame)}</span>
            <span class="hud-sep">/</span>
            <span class="hud-total" id="hud-frame-total">{_text(frame_count)}</span>
          </div>
          <div class="hud-time" id="hud-time">t = {_text(first_t_ms)} ms</div>
        </div>
      </div>
      <div class="transport replay-only">
        <button id="frame-prev" type="button" class="transport-btn" title="上一帧" aria-label="上一帧"{step_disabled}>◂</button>
        <div class="transport-range">
          <input id="frame-slider" type="range" min="1" max="{slider_max}" value="1" aria-label="帧位置"{slider_disabled}>
          <div class="ticks" aria-hidden="true">{ticks}</div>
        </div>
        <button id="frame-next" type="button" class="transport-btn" title="下一帧" aria-label="下一帧"{step_disabled}>▸</button>
        <span id="frame-position" class="transport-readout">{_text(position)}</span>
        <span id="frame-time" class="transport-time muted">t={_text(first_t_ms)} ms</span>
      </div>
    </div>
    <aside class="viewer-side">
      <section class="side-block replay-only">
        <div class="side-head"><span class="index">01</span><h3>诊断覆盖</h3></div>
        <label class="toggle"><input type="checkbox" id="diff-toggle"> 显示只读像素 diff（仅证据，不判定）</label>
        <p id="diff-note" class="hint">diff 默认关闭。</p>
      </section>
      <section class="side-block replay-only">
        <div class="side-head"><span class="index">02</span><h3>关键画面</h3></div>
        <div id="snapshots" class="snapshots">
          {_render_snapshots(snapshots)}
        </div>
        <button id="snapshot-back" type="button" class="ghost-btn" hidden>← 回到帧序列</button>
      </section>
      <section class="side-block annotation-block">
        <div class="side-head"><span class="index">03</span><h3>标注</h3></div>
        <p class="hint annotation-locked">测试/录制中不能标注；停止后即可框选。</p>
        <div id="annotation-form">
          <p class="hint" id="annotation-hint">在画面上拖动框选区域，可多次框选；保存后会自动截出区域 PNG（regions/），AI 可直接读取 annotations.json 里的 image 路径。</p>
          <div id="pending-regions" class="pending" hidden></div>
          <label class="field">标签 <input id="annotation-tags" type="text" placeholder="layout, color"></label>
          <label class="field">说明 <textarea id="annotation-text" rows="3" placeholder="描述问题或期望"></textarea></label>
          <div class="row">
            <button id="annotation-save" type="button" class="primary-btn" disabled>保存标注</button>
            <button id="annotation-clear" type="button" class="ghost-btn">清除框选</button>
          </div>
          <p id="annotation-status" role="status" class="hint"></p>
        </div>
        <ul id="annotation-list" class="notes">{_render_notes(model.note_views(), model.annotations_error)}</ul>
      </section>
      <section class="side-block live-note">
        <p class="hint">测试/录制中：在画面上点击、拖动或使用方向键与运行时交互。运行期间不能标注；停止录制后打开回放会话即可框选标注。</p>
      </section>
      <section class="side-block empty-note">
        <p class="hint">当前没有可回放的帧。点击上方「测试」或「录制」开始，或从顶部选择其他会话。</p>
      </section>
    </aside>
  </div>
  <section class="timeline-block replay-only">
    <div class="side-head"><span class="index">04</span><h3>时间线</h3><span class="side-note">点击帧行跳转</span></div>
    <div class="table-wrap">
      <table id="timeline">
        <thead><tr><th>类型</th><th>帧</th><th>时间</th><th>详情</th></tr></thead>
        <tbody>{_render_timeline(timeline)}</tbody>
      </table>
    </div>
  </section>
</section>
"""


def _render_snapshots(snapshots: list[dict[str, Any]]) -> str:
    if not snapshots:
        return '<p class="hint">本次会话没有关键画面。</p>'
    buttons = []
    for number, snapshot in enumerate(snapshots, start=1):
        buttons.append(
            '<button class="snapshot" type="button" '
            f'data-snapshot-url="{_attr(snapshot["url"])}" '
            f'data-snapshot-label="{_attr(snapshot["label"])}">'
            '<span class="snapshot-thumb">'
            f'<img src="{_attr(snapshot["url"])}" alt="" loading="lazy">'
            "</span>"
            f'<span class="snapshot-num">{number:02d}</span>'
            f'<span class="snapshot-label">{_text(snapshot["label"])}</span>'
            "</button>"
        )
    return "".join(buttons)


def _render_notes(
    views: list[dict[str, Any]],
    error: Exception | None,
) -> str:
    """The only note renderer: field/label/region/URL rules live in the model."""
    parts = []
    if error:
        parts.append(
            f'<li class="empty">标注文件不可读：{_text(error)}</li>'
        )
    if not views:
        parts.append('<li class="empty">暂无标注。</li>')
        return "".join(parts)
    for view in views:
        tags = (
            f'<span class="tags">{_text(view["tags"])}</span>'
            if view["tags"]
            else ""
        )
        regions = (
            f'<code class="note-regions">{_text(view["region_text"])}</code>'
            if view["region_text"]
            else ""
        )
        crops = ""
        if view["crops"]:
            links = [
                f'<a href="{_attr(crop["url"])}" target="_blank" rel="noopener">'
                f'<img class="note-crop" src="{_attr(crop["url"])}" '
                f'alt="{_attr(crop["alt"])}"></a>'
                for crop in view["crops"]
            ]
            crops = '<div class="note-crops">' + "".join(links) + "</div>"
        text = f"<p>{_text(view['text'])}</p>" if view["text"] else ""
        frame_attr = (
            f' data-note-frame="{_text(view["frame_no"])}"'
            if view["has_frame"]
            else ""
        )
        parts.append(
            f'<li data-note-id="{_attr(view["id"])}"{frame_attr}>'
            f'<span class="note-meta">{_text(view["meta"])}</span> '
            f"{tags}{text}{regions}{crops}</li>"
        )
    return "".join(parts)


def _render_timeline(timeline: list[dict[str, Any]]) -> str:
    if not timeline:
        return '<tr><td colspan="4" class="hint">时间轴为空。</td></tr>'
    rows = []
    for row in timeline:
        t_ms = row.get("t_ms", row.get("t_ms_start", ""))
        kind = str(row.get("type") or "")
        frame_attr = ""
        if _is_int(row.get("frame_no")):
            frame_attr = (
                f' data-frame-no="{_text(row.get("frame_no"))}"'
                ' class="timeline-row is-jump"'
            )
        elif kind:
            frame_attr = ' class="timeline-row"'
        rows.append(
            f"<tr{frame_attr}>"
            f'<td><span class="kind kind-{_attr(kind)}">{_text(kind)}</span></td>'
            f"<td>{_text(row.get('frame_no', ''))}</td>"
            f"<td>{_text(t_ms)}</td>"
            f"<td>{_text(_timeline_detail(row))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _timeline_detail(row: dict[str, Any]) -> str:
    kind = row.get("type")
    if kind == "frame":
        return str(row.get("file", ""))
    if kind == "input":
        parts = [str(row.get("device", "")), str(row.get("action", ""))]
        if "x" in row and "y" in row:
            parts.append(f"x={row.get('x')} y={row.get('y')}")
        if row.get("key"):
            parts.append(f"key={row.get('key')}")
        if "diff" in row:
            parts.append(f"diff={row.get('diff')}")
        if "hit" in row:
            parts.append(f"hit={row.get('hit') or ''}")
        if row.get("hit_class"):
            parts.append(f"hit_class={row.get('hit_class')}")
        if row.get("source"):
            parts.append(f"source={row.get('source')}")
        return " ".join(part for part in parts if part)
    if kind == "wait":
        return (
            f"{row.get('t_ms_start')} → {row.get('t_ms_end')} ms，"
            f"帧 {row.get('frame_start')} → {row.get('frame_end')}"
        )
    if kind == "mark":
        return f"id={row.get('id')}"
    if kind == "snapshot":
        return f"label={row.get('label')} file={row.get('file')}"
    if kind == "end":
        return (
            f"frame_count={row.get('frame_count')} "
            f"truncated={row.get('truncated')}"
        )
    return ""


def _model_json(replay: ReplayModel | None) -> str:
    frames = replay.frames if replay else []
    manifest = replay.manifest if replay else {}
    frame_diffs = replay.frame_diffs if replay else []
    reference_diffs = (replay.reference_diffs or []) if replay else []
    note_count = replay.note_count if replay else 0

    def by_frame(rows: list[dict[str, Any]]) -> dict[str, Any]:
        table: dict[str, Any] = {}
        for row in rows:
            frame_no = row.get("frame_no")
            if _is_int(frame_no):
                table[str(frame_no)] = row
        return table

    model = {
        "sessionId": replay.session_id if replay else None,
        "frameCount": manifest.get("frame_count", 0) if replay else 0,
        "frames": frames,
        "diffs": by_frame(frame_diffs),
        "refDiffs": by_frame(reference_diffs),
        "notesCount": note_count,
        "annotationsUrl": (
            urls.annotations_url(replay.session_id)
            if replay and replay.session_id
            else None
        ),
    }
    return json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
