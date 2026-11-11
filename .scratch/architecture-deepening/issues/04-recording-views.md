# 04：Recording 吸收帧/快照读模型（候选 05）

**What to build：** `Recording` 提供帧视图、快照视图和最新帧；web 的 live 状态与回放模型不再各自解析 frames 文件名和 timeline 行，只负责拼 URL。做完后，timeline schema 变化只改 `Recording` 一处，live 轮询仍走尾读。

**Blocked by：** None (can start immediately)

**Status:** done

**验收方式：**

- 方法/字段：`test_recording.py` 断言三个方法、字段集合、空帧 `None`、返回项无 `url`。
- 大 timeline：构造超过 256 KiB 的 timeline，`latest_frame()` 返回最后一帧的 `t_ms`。
- 去重：`git grep -n -E "frame_no = int\(|_timeline_by_file|_latest_frame_t_ms" -- core/lvgl_ai/web` → 0（相关逻辑只在 `Recording`）。
- 行为：`test_web_replay.py` 与 `test_web_live.py` 断言 JSON 形状与 URL 不变。
- 快照：先 `python -I core/tools/contract_snapshot.py compare --report <temp>/before.txt` → 预期退出 1，报告只列三个新增 `Recording` 成员；再 `record`；最后 `compare` → 退出 0。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：`before.txt` 的差异摘要与命令退出码写入票末「完成」。

- [x] `Recording` 新增 `frame_views()`、`snapshot_views()`、`latest_frame()`；字段为 `file`、`frame_no`、`t_ms`，快照多 `label`，空帧返回 `None`（test_recording）。
- [x] 返回项不含 URL；`Recording` 不 import web（代码审查）。
- [x] 大 timeline 下 `latest_frame()` 正确；256 KiB 上限不变（测试 + 代码审查）。
- [x] live/replay 不再解析文件名、`t_ms` 回退或 timeline 行（`git grep` 检查）；两者 HTTP 形状与 URL 不变（测试）。
- [x] 快照更新只新增三个 `Recording` 成员（`before.txt` + `compare`）。
- [ ] `python -I core/tests/run_tests.py` 退出 0。（按实施指令不在本 worktree 跑真实 engine 全量测试；本票 fake/unit 面已通过，见下。）

**完成：**

- 实现：`Recording.frame_views(timeline=None)`、`snapshot_views(timeline=None)`、`latest_frame()`；字段 `file` / `frame_no` / `t_ms`（快照加 `label`），条目不含 URL，`Recording` 不 import web。timeline 尾读（256 KiB，`_TIMELINE_TAIL_BYTES`）随 `_latest_frame_t_ms` 移入 `Recording`；`frame_views()` 读完整 timeline，可选 `timeline` 参数供 replay 复用已解析行，缺失/损坏时回退文件名与 `t_ms=0`。
- live/replay：`live_session._status_for` 改用 `Recording.latest_frame()`，URL 仍由 `frame_url` 拼；`replay_model.frames/snapshots` 改用 `frame_views(self.timeline)` / `snapshot_views(self.timeline)`，只补 `url`。删除 `_timeline_by_file`、`_frame_entries`、`_snapshot_entries`、`_frame_no_from_name`、`_latest_frame_t_ms`；HTTP JSON 形状与 URL 不变。
- 去重检查：`git grep -n -E "frame_no = int\(|_timeline_by_file|_latest_frame_t_ms" -- core/lvgl_ai/web` → 0 命中。
- 测试（红→绿）：
  - 红：新增 `RecordingViewsTest` 7 例首次运行全部 `AttributeError`（7 errors，退出 1）。
  - 绿：`test_recording`、`test_replay_model`、`test_web_replay`、`test_web_live.LiveSessionTest`、`test_web_live.LiveHttpTest` 共 110 例 OK，退出 0。
  - `timeline_reads`：`test_one_timeline_read_feeds_frames_snapshots_and_timeline`、`test_prime_reads_every_page_section_once` OK；`_CountingRecording.timeline_reads == 1` 未改测试。
  - 大 timeline：`test_latest_frame_reads_the_tail_of_a_large_timeline`（>256 KiB，末帧 `t_ms=43210`）、`test_frame_views_read_the_full_timeline` OK。
  - 关联回归：`test_web_transport`、`test_web_annotations`、`test_web_apps`、`test_contract_snapshot` 共 57 例 OK。
- 契约快照：
  - 改动前基线：`python -I core/tools/contract_snapshot.py compare` → `differences: 0`，退出 0。
  - `compare --report <temp>/before-04.txt` → 退出 1，`differences: 3`，仅新增 `sections.python.lvgl_ai.members.Recording.members.frame_views` / `latest_frame` / `snapshot_views`。
  - `record` → 退出 0；复查 `compare` → `differences: 0`，退出 0。
- 限制：按实施指令不在本 worktree 跑真实 engine 全量测试（集成类需要构建 LVGL 并写 `build/`、`sessions/`），该门禁留给集成分支；本票 fake/unit 面已全部通过。
