# 04：Recording 吸收帧/快照读模型（候选 05）

**What to build：** `Recording` 提供帧视图、快照视图和最新帧；web 的 live 状态与回放模型不再各自解析 frames 文件名和 timeline 行，只负责拼 URL。做完后，timeline schema 变化只改 `Recording` 一处，live 轮询仍走尾读。

**Blocked by：** None (can start immediately)

**Status:** open

**验收方式：**

- 方法/字段：`test_recording.py` 断言三个方法、字段集合、空帧 `None`、返回项无 `url`。
- 大 timeline：构造超过 256 KiB 的 timeline，`latest_frame()` 返回最后一帧的 `t_ms`。
- 去重：`git grep -n -E "frame_no = int\(|_timeline_by_file|_latest_frame_t_ms" -- core/lvgl_ai/web` → 0（相关逻辑只在 `Recording`）。
- 行为：`test_web_replay.py` 与 `test_web_live.py` 断言 JSON 形状与 URL 不变。
- 快照：先 `python -I core/tools/contract_snapshot.py compare --report <temp>/before.txt` → 预期退出 1，报告只列三个新增 `Recording` 成员；再 `record`；最后 `compare` → 退出 0。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：`before.txt` 的差异摘要与命令退出码写入票末「完成」。

- [ ] `Recording` 新增 `frame_views()`、`snapshot_views()`、`latest_frame()`；字段为 `file`、`frame_no`、`t_ms`，快照多 `label`，空帧返回 `None`（test_recording）。
- [ ] 返回项不含 URL；`Recording` 不 import web（代码审查）。
- [ ] 大 timeline 下 `latest_frame()` 正确；256 KiB 上限不变（测试 + 代码审查）。
- [ ] live/replay 不再解析文件名、`t_ms` 回退或 timeline 行（`git grep` 检查）；两者 HTTP 形状与 URL 不变（测试）。
- [ ] 快照更新只新增三个 `Recording` 成员（`before.txt` + `compare`）。
- [ ] `python -I core/tests/run_tests.py` 退出 0。
