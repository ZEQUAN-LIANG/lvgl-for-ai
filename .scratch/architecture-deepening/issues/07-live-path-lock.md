# 07：应用管理台 live 路径收口（候选 06）

**What to build：** 应用管理台的 live 路径折叠 6 个 1:1 转发方法，live 错误在 HTTP dispatch 统一映射；`live.start()` 移出 `_apps_lock`，构建期间 `/api/apps` 仍能立即返回。做完后，最长 600 秒的构建不再卡住应用列表，live 路径的错误映射只有一个入口。

**Blocked by：** 06：场景索引单源

**Status:** done

**验收方式：**

- 慢启动：fake Runtime 的 `start()` 阻塞在 `threading.Event`；后台线程请求 `/api/live/start`；等待状态变为 `STARTING`；用 1 秒客户端超时请求 `/api/apps` → 200 且返回应用列表；释放事件，等待 start 完成。
- 错误映射：让 live 方法抛 `LiveError`，断言 HTTP 状态码与 JSON 错误码与现状一致。
- 转发方法：代码审查 `WebApp` 上不存在 6 个 1:1 live 转发方法。
- 状态：现有 `STARTING` 状态测试通过（`test_web_live.py`）。
- 契约/全量：`python -I core/tools/contract_snapshot.py compare` 与 `python -I core/tests/run_tests.py` → 退出 0。
- 记录：慢启动测试名、请求返回与命令退出码写入票末「完成」。

- [x] `WebApp` 上 6 个 live 转发方法删除；`LiveError` 与 `HttpError` 在 HTTP dispatch 并列映射（代码审查 + 错误映射测试）。
- [x] HTTP 路由、状态码与 JSON 形状不变（现有 live HTTP 测试）。
- [x] `start_live` 只在 `_apps_lock` 内读取场景 display；`LiveSession.start()` 在锁外执行（代码审查 + 慢启动测试）。
- [x] 慢启动测试通过：live 启动仍在进行时，`/api/apps` 在 1 秒客户端超时内返回 200 与应用列表。
- [x] `LiveSession` 的 `STARTING` / `RUNNING` / `IDLE` 语义不变（现有状态测试）。
- [ ] 全量测试与契约比较通过。契约比较已通过；全量测试按主代理约束未在 worktree 运行（缺 `lvgl-src/`、`third_party/`，真实 engine 不可用），由主代理合并后执行。

## 完成

- 改动文件：
  - `core/lvgl_ai/web/webapp.py`：删除 `WebApp` 的 `live_status`、`open_live_stream`、`start_live`、`stop_live`、`live_pointer`、`live_key` 六个 live 转发方法，以及 `_live_call` 和实例级 `_live_http_error`；`_live_http_error` 改为模块级 helper，由 `_WebHandler._dispatch` 在 `except HttpError` 之后并列 `except LiveError` 映射，状态码来自既有 `LIVE_ERROR_STATUS`，JSON 仍为 `{"error": {"code", "message", "detail"}}`。HTTP 路由直接调用 `self.app.live.status/stop/pointer/key/start`，`/api/live/stream` 调 `self.app.live.open_stream()`，`WebApp.shutdown()` 调 `self.live.stop()` 并 catch `LiveError`。`start` 路由新增 `_WebHandler._start_live`：先 `validate_live_kind`（保持未知 mode 优先于坏 app 的顺序），再 `_input_app`，然后 `WebApp.scenario_display(app)` 在 `_apps_lock` 内只读取场景 display，最后在锁外调用 `LiveSession.start()`；`_scenario_display_locked` 改名为公开的 `scenario_display` 并在内部取锁。
  - `core/tests/test_web_live.py`：`LiveHttpTest` 新增 `test_apps_stay_available_while_live_start_is_building` 与 `test_live_errors_keep_http_status_and_json_shape`；`_quiet_stop` 改调 `app.live.stop()`；新增 `shutil` 与 `APP_C` 夹具。
  - `core/tests/test_web_transport.py`：`LiveStreamHttpTest._quiet_stop` 改调 `app.live.stop()`。
- 红态（先写测试）：`LiveHttpTest.test_apps_stay_available_while_live_start_is_building` → `TimeoutError: timed out`（`/api/apps` 等待被 `start_live` 持有的 `_apps_lock`，1 秒客户端超时）；`LiveHttpTest.test_live_errors_keep_http_status_and_json_shape` → `AssertionError: 500 != 409`，payload `{'error': {'code': 'internal_error', ...}}`（`LiveError` 落入 generic 500）。命令退出 1，Ran 2 tests，FAILED (failures=1, errors=1)。
- 绿态：上述两条 → 退出 0，Ran 2 tests，OK。
- 慢启动证据：`BlockingRuntime.start()` 阻塞在 `threading.Event`；后台线程 POST `/api/live/start`；主线程等 `runtime.start_entered` 并确认 `harness.server.app.live.is_starting()` 为真（未轮询 `/api/live`）；`GET /api/apps`（`timeout=1.0`）返回 200，`apps` 包含 `coffee`、含 `trash`；`finally` 释放 `start_release` 后后台 POST 返回 200 且 `running=True`，测试 join 后台线程并 quiet stop。
- 错误映射测试：对 `live.status`、`live.stop`、`live.pointer`、`live.key`、`live.start` 注入 `LiveError`，断言 HTTP 状态与 error.code 与现状一致：`live_not_running` 409、`live_starting` 409、`live_stop_error` 500、`invalid_input` 400、`live_input_error` 500、`live_running` 409；并断言 JSON 顶层只有 `error`，`error` 只有 `code`/`message`/`detail`，detail 原样透传。
- 代码审查：`grep` 确认 `WebApp` 不存在 `def live_status/open_live_stream/start_live/stop_live/live_pointer/live_key`、`_live_call`、`_scenario_display_locked`；live HTTP 路由直接调用 `self.app.live.*`；`shutdown()` 与测试 cleanup 不再调用 `stop_live`。
- 行为锚点：`test_web_live.{LiveSessionTest,PageTrackingTest,LiveHttpTest}` → 退出 0，Ran 44 tests，OK（含 STARTING 状态测试 `test_state_transitions_are_observable`、`test_status_blocks_while_start_holds_the_live_lock`）。`test_web_apps` → 退出 0，Ran 10 tests，OK（含 `test_mutation_is_refused_while_live_is_running`）。`test_web_transport` → 退出 0，Ran 8 tests，OK。`test_contract_snapshot` → 退出 0，Ran 14 tests，OK。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0，`differences: 0`；未改 `contract_snapshot.json`（快照不记录 `WebApp` 成员）。
- 全量测试：按主代理约束未在 worktree 运行（`lvgl-src/`、`third_party/` 缺失），留给主代理合并后执行。
- 风险/边界：`LiveSession.start()` 仍全程持有 `LiveSession._lock`，因此构建期间 `GET /api/live` 状态轮询仍阻塞，这是票面明确保留的现有行为；`_reject_app_mutation_while_live` 仍经 `live.is_active()` 等待该锁，应用变更保护不变。`/api/live/stream` 仅在发送响应头前抛出的 `LiveError` 由 dispatch 映射，发送后的异常继续静默结束流。校验顺序（未知 mode 优先于坏 app）由 `_WebHandler._start_live` 保留。
