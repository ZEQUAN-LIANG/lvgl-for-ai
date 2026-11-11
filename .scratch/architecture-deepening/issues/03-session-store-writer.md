# 03：SessionStore 成为会话状态唯一写者（候选 02）

**What to build：** 会话选项、manifest、日志、pid 身份和落盘帧计数由 `SessionStore` 拥有；`Runtime` 的会话型属性改为只读转发；`EngineLink` 写 pid 时带上 session 身份。做完后，改一个会话字段只改一个写入点，排障时 pid 能指向具体会话。

**Blocked by：** None (can start immediately)

**Status:** open

**验收方式：**

- 单一写者：代码审查 `Runtime.__init__` 只把会话选项传给 `SessionStore`，同名属性是 property；`Runtime` 不再给这些名字赋第二份值。
- pid：测试启动 fake engine 后读取 `.engine.pid` JSON，断言 `session_id` 与 `app` 非空且等于 Runtime 的值。
- 帧计数：一次 changed-only 会话分别断言 `runtime.frame_count`（引擎预约帧）与 manifest `frame_count`（落盘 PNG 数）；manifest 必须等于 `len(frames)`。
- ready/mode：fake engine 返回 ready mode 后，断言 `runtime.mode` 与 manifest `mode` 都等于该值。
- 公开面：`python -I core/tools/contract_snapshot.py compare` → 退出 0，无差异。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：测试名、断言值与命令退出码写入票末「完成」。

- [ ] 会话选项只由 `SessionStore` 保存；`Runtime` 的 `app`、`build`、`record`、`live_frame`、`record_changed_only`、`mode`、`lvgl_src`、`sessions_root`、`max_log_bytes`、`session_retention`、`ready` 从 store 读取（代码审查 + 行为测试）。
- [ ] `mode` 与 `ready` 在 ready 回执后写回 store；测试断言 runtime 与 manifest 一致。
- [ ] `Runtime` 公开构造签名与属性名不变；`contract_snapshot.py compare` 无差异。
- [ ] `.engine.pid` 的 `session_id`/`app` 非空且正确（pid 测试）。
- [ ] 预约帧与落盘帧分别有测试断言，manifest `frame_count` 等于 `len(frames)`。
- [ ] 测试覆盖选项组合、pid、mode、live 回退帧计数；`python -I core/tests/run_tests.py` 退出 0。
