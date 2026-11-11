# 07：应用管理台 live 路径收口（候选 06）

**What to build：** 应用管理台的 live 路径折叠 6 个 1:1 转发方法，live 错误在 HTTP dispatch 统一映射；`live.start()` 移出 `_apps_lock`，构建期间 `/api/apps` 仍能立即返回。做完后，最长 600 秒的构建不再卡住应用列表，live 路径的错误映射只有一个入口。

**Blocked by：** 06：场景索引单源

**Status:** open

**验收方式：**

- 慢启动：fake Runtime 的 `start()` 阻塞在 `threading.Event`；后台线程请求 `/api/live/start`；等待状态变为 `STARTING`；用 1 秒客户端超时请求 `/api/apps` → 200 且返回应用列表；释放事件，等待 start 完成。
- 错误映射：让 live 方法抛 `LiveError`，断言 HTTP 状态码与 JSON 错误码与现状一致。
- 转发方法：代码审查 `WebApp` 上不存在 6 个 1:1 live 转发方法。
- 状态：现有 `STARTING` 状态测试通过（`test_web_live.py`）。
- 契约/全量：`python -I core/tools/contract_snapshot.py compare` 与 `python -I core/tests/run_tests.py` → 退出 0。
- 记录：慢启动测试名、请求返回与命令退出码写入票末「完成」。

- [ ] `WebApp` 上 6 个 live 转发方法删除；`LiveError` 与 `HttpError` 在 HTTP dispatch 并列映射（代码审查 + 错误映射测试）。
- [ ] HTTP 路由、状态码与 JSON 形状不变（现有 live HTTP 测试）。
- [ ] `start_live` 只在 `_apps_lock` 内读取场景 display；`LiveSession.start()` 在锁外执行（代码审查 + 慢启动测试）。
- [ ] 慢启动测试通过：live 启动仍在进行时，`/api/apps` 在 1 秒客户端超时内返回 200 与应用列表。
- [ ] `LiveSession` 的 `STARTING` / `RUNNING` / `IDLE` 语义不变（现有状态测试）。
- [ ] 全量测试与契约比较通过。
