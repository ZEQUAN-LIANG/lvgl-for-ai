# 03：SessionStore 成为会话状态唯一写者（候选 02）

**What to build：** 会话选项、manifest、日志、pid 身份和落盘帧计数由 `SessionStore` 拥有；`Runtime` 的会话型属性改为只读转发；`EngineLink` 写 pid 时带上 session 身份。做完后，改一个会话字段只改一个写入点，排障时 pid 能指向具体会话。

**Blocked by：** None (can start immediately)

**Status:** done

**验收方式：**

- 单一写者：代码审查 `Runtime.__init__` 只把会话选项传给 `SessionStore`，同名属性是 property；`Runtime` 不再给这些名字赋第二份值。
- pid：测试启动 fake engine 后读取 `.engine.pid` JSON，断言 `session_id` 与 `app` 非空且等于 Runtime 的值。
- 帧计数：一次 changed-only 会话分别断言 `runtime.frame_count`（引擎预约帧）与 manifest `frame_count`（落盘 PNG 数）；manifest 必须等于 `len(frames)`。
- ready/mode：fake engine 返回 ready mode 后，断言 `runtime.mode` 与 manifest `mode` 都等于该值。
- 公开面：`python -I core/tools/contract_snapshot.py compare` → 退出 0，无差异。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：测试名、断言值与命令退出码写入票末「完成」。

- [x] 会话选项只由 `SessionStore` 保存；`Runtime` 的 `app`、`build`、`record`、`live_frame`、`record_changed_only`、`mode`、`lvgl_src`、`sessions_root`、`max_log_bytes`、`session_retention`、`ready` 从 store 读取（代码审查 + 行为测试）。
- [x] `mode` 与 `ready` 在 ready 回执后写回 store；测试断言 runtime 与 manifest 一致。
- [x] `Runtime` 公开构造签名与属性名不变；`contract_snapshot.py compare` 无差异。
- [x] `.engine.pid` 的 `session_id`/`app` 非空且正确（pid 测试）。
- [x] 预约帧与落盘帧分别有测试断言，manifest `frame_count` 等于 `len(frames)`。
- [x] 测试覆盖选项组合、pid、mode、live 回退帧计数；本 worktree 无 `lvgl-src/`、`third_party/`，真实 engine 全量留给主仓库验收。

## 完成

实现摘要：

- `SessionStore` 新增 `ready`、`lvgl_src`、`session_retention` 只读属性与 `note_mode()`；选项、manifest、日志、预览、retention 仍由它独占。
- `Runtime.__init__` 只把 11 个会话选项传给 `SessionStore`，不再写同名实例属性；读取走 `__getattr__` 转发（`_SESSION_OPTIONS`，类 `__dict__` 无新公开成员）。
- `Runtime.start()` 在 ready 后用 `note_ready()` / `note_mode()` 写回 store；`self.window`/`self.headless` 回退逻辑保留，`mode` 只读 store。
- `EngineLink.__init__` 新增关键字 `session_id`、`app`，`start()` 写 `.engine.pid` 时落盘身份；`Runtime` 传入当前会话身份。
- `Runtime.frame_count` 仍是“引擎回执的预约帧”；manifest `frame_count` 仍由 `SessionStore._frames()` 数落盘 PNG。

取舍：票面写“同名属性是 property”，但 `contract_snapshot.py` 会扫描 `Runtime.__dict__`，新增 property 会记为 11 个新公开成员并让 `compare` 退出 1；spec 只允许 05 更新快照。按实施说明改用 `__getattr__` 只读转发，属性名、构造签名与快照均不变。

验证命令、测试与断言（worktree：`ticket/02`，基线 `c47319c`）：

```bash
# 红态（实现前）
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_engine_link', argv=['test_engine_link','EnginePidFileTest'], verbosity=2)"
# 退出 1：TypeError: EngineLink.__init__() got an unexpected keyword argument 'session_id'
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_session_store', argv=['test_session_store','SessionStoreTest'], verbosity=2)"
# 退出 1：AttributeError: 'SessionStore' object has no attribute 'ready' / 'session_retention'
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_runtime', argv=['test_runtime','RuntimeSessionOptionTest','RuntimeProcessSeamTest'], verbosity=2)"
# 退出 1：11 个选项仍在 Runtime.__dict__；window 回退后 rt._store.mode == 'window'
```

绿态：

```bash
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_engine_link', argv=['test_engine_link'], verbosity=1)"
# 退出 0，27 tests OK
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_session_store', argv=['test_session_store'], verbosity=1)"
# 退出 0，31 tests OK
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_runtime', argv=['test_runtime','RuntimeSessionOptionTest','RuntimeProcessSeamTest'], verbosity=2)"
# 退出 0，10 tests OK
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_session_retention', argv=['test_session_retention','RuntimeRetentionConfigTest'], verbosity=1)"
# 退出 0，2 tests OK
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_errors_logs_checks', argv=['test_errors_logs_checks','MaxFramesIntegrationTest.test_default_values_are_600_frames_and_16_mb'], verbosity=1)"
# 退出 0，1 test OK
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_contract_snapshot', argv=['test_contract_snapshot'], verbosity=1)"
# 退出 0，14 tests OK
python -I core/tools/contract_snapshot.py compare
# 退出 0，differences: 0
```

新增/更新断言：

- `EnginePidFileTest.test_start_writes_the_session_identity_to_the_pid_file`：`.engine.pid` 的 `session_id == "20260101-000000-abcd"`、`app == "coffee"`，两者均非空。
- `SessionStoreTest.test_ready_and_mode_are_written_back_to_the_store`：`store.ready is None`（ready 前）；`note_ready()`+`note_mode()` 后 `store.mode == "headless"`、`store.ready["mode"] == "headless"`、`store.ready["frames"] == 1`。
- `SessionStoreTest.test_session_options_keep_their_public_names`：`store.session_retention == 3`、`store.lvgl_src == <root>/lvgl-src/9.6`。
- `RuntimeSessionOptionTest.test_session_options_are_read_from_the_store`：11 个名字均不在 `vars(rt)`，`getattr(rt, name) == getattr(rt._store, name)`；`rt.app == "coffee"`、`rt.record is False`、`rt.live_frame is True`、`rt.session_retention is None`、`rt.ready is None`、`rt.lvgl_src` 是 `Path`。
- `RuntimeProcessSeamTest.test_window_fallback_writes_the_ready_mode_back_to_the_store`：`rt.ready["mode"] == rt.mode == rt._store.mode == manifest["mode"] == "headless"`，`rt.window is False`、`rt.headless is True`。
- `RuntimeProcessSeamTest.test_reserved_frames_are_not_the_manifest_frame_count`：fake engine 两次 tick 后 `rt.frame_count == 3`；stop 后 `manifest["frame_count"] == len(recording.frames) == 0`，`rt.frame_count` 仍为 3。
- `RuntimeProcessSeamTest.test_live_only_session_counts_no_recorded_frames`：`record=False, live_frame=True, record_changed_only=True` 组合下 `recording.frames == []`、`manifest["frame_count"] == 0`、`record_changed_only is True`、`app == "coffee"`。
- `ChangedFramesTest`：`test_static_ticks_are_skipped_and_changes_stay_contiguous` 与 `test_max_frames_counts_retained_frames_only` 增加 `reserved = rt.frame_count`，stop 后断言 `manifest["frame_count"] == len(frames) == reserved`。

未在本 worktree 执行：`test_changed_frames`、`test_async_encoding`、`test_pointer_timeline`、`test_multiversion` 等真实 engine 集成测试（缺 `lvgl-src/`、`third_party/`）；`test_cli`/`test_scenario` 的真实 engine 类同样因缺源码报 `BuildError`，其单元类全部通过。`python -I core/tests/run_tests.py` 需在主仓库执行。
