# LVGL AI Tools

真实 headless LVGL 运行时 + 取证 + 回放。工具只提供环境、输入和证据，不判定画面；验收标准由人在聊天里给出。

第三方许可声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与仓库根 `licenses/`。

本文件位于工具根 `core/`；下面列出的路径相对本目录，命令示例在**仓库根**执行。

## 目录

- `lvgl_ai/`：Python 控制层。`Runtime`（一个实例 = 一个 LVGL 进程 = 一次会话）、`Recording`（只读证据视图，annotations 可写）、`play_scenario`、`apps/`（应用管理 package：common / policy / registry / scaffold / trash / views）、错误类型、`web/`（HTTP/UI 适配）。
- `engine/`：C engine，负责协议、虚拟 indev、录帧、时间轴、窗口。
- `cli.py`：命令行入口。
- `web.py`：网页端入口。
- `tests/`：`python -I` 测试套件。
- `api-nav/`：每个 LVGL 版本一份 API 导航。
- `tools/fetch_lvgl.py`：下载官方 LVGL、校验版本并应用本地 patch。
- `tools/new_app.py`：生成应用变体的源文件与场景，并注册到 `user/app/app.c`。
- `tools/contract_snapshot.py`：记录/对比六类外部契约快照，用于重构行为冻结；用法见
  [CONTRACT_SNAPSHOT.md](CONTRACT_SNAPSHOT.md)。

## 环境准备

需要 Python 3.9+（仅标准库）、CMake 3.20+、Ninja、GCC（Windows 为 MinGW-w64）和 curl；
ccache 可选，git 仅在应用 `patches/` 时需要。

Windows 安装、PATH 配置、首次运行与常见错误见仓库根 [README.md](../README.md)。
本文件只保留工具用法。

## 准备 LVGL 源码

`lvgl-src/` 不随仓库提交，只保留 `lvgl-src/README.md` 说明。源码构建前先下载并安装对应版本：

```bash
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .
```

脚本按固定 tag 下载官方源码、校验版本宏、应用 `patches/<version>/` 下的 patch，再安装到
`lvgl-src/<version>/`；安装后写入 `.lvgl-ai-source.json` 记录 tag 与 patch。跳过 patch 用
`--no-patch`，自定义 patch 根用 `--patch-dir`。patch 的组织、生成与手动应用见
`patches/README.md`。

## 启动网页端

控制台入口：

```bash
python -I core/web.py
```

Windows 无控制台入口：

```text
双击 core/web.pyw
或：pythonw -I core/web.pyw
```

`web.pyw` 自动打开浏览器，并默认启用 `--exit-on-close`：最后一个网页关闭约 0.5 秒后停止服务并收尾 engine。不带参数启动（双击 `web.pyw` 或经 `open-web.vbs`）时，如果默认地址上已有服务在监听，它只打开页面并退出（暖启动），不会重复启动 server；带参数时保持普通启动路径。控制台入口需要显式加 `--exit-on-close` 才有相同行为。

仓库根的 `open-web.vbs` 是完全无黑框的启动入口：双击即可，只负责用 `pythonw` 启动 `core/web.pyw`；端口探测与打开的 URL 都在 Python 里。旧的 `open-web.cmd` 已移除。

默认固定端口 `8765`，地址：

```
http://127.0.0.1:8765/
```

- 页面包含回放（完整帧、关键画面、时间轴、框选标注）和 live（启动 / 停止独立 Runtime）。
- 顶部「应用」下拉从 `user/scenarios/*.json` 中声明了 `app` 的 scenario 生成；第一个应用是默认值，打开页面就会自动以测试模式预览它，选中其他应用立即切换，不需要再点「测试」，也不需要重启 `web.py`。选项里没有写死应用名。
- 技术细节（manifest、checks、原始 diff、engine.log、build.log）默认折叠在 `<details>` 中。
- 只读像素 diff 默认关闭；打开后按 `frame_diffs.ndjson`（以及可选的参考图 diff）覆盖显示 bbox，只作证据。
- 网页端只通过 `Runtime` / `Recording` 工作，没有第二套协议客户端；live 使用独立 Runtime 和独立 engine 进程。
- 测试模式每 33 ms 推进一次虚拟时间（约 30 fps），录制模式保持 100 ms；无输入时 timer、toast 和动画继续运行。录制/测试默认 `record_changed_only=True`，只保留画面发生变化的帧，HUD 时间使用虚拟时间 `t_ms`。
- 测试/录制预览走 raw 帧流：engine 写 `live.rgba`，页面通过 `GET /api/live/stream` 接到 canvas，不再轮询 PNG。`live.rgba` 是临时预览文件，停止时删除，不是证据。
- Windows 下 engine 与 cmake/ninja 子进程使用 `CREATE_NO_WINDOW`；从 `web.pyw` / `pythonw` 启动时不会弹出控制台黑框，切换应用也不会闪。
- 非 Windows、无浏览器环境不影响服务启动；`web.py` 默认不自动打开浏览器，需要时加 `--open`；`web.pyw` 会自动打开。
- 端口被占用或需要换地址时：`python -I core/web.py --host 127.0.0.1 --port 8766`。

`web.py` 支持 `--sessions-root`（默认 `LVGL_AI_SESSIONS_ROOT` 或仓库根的 `sessions/`）、`--lvgl`（live 使用，默认 `LVGL_AI_LVGL_VERSION` 或 `9.6`）、`--app NAME`（打开页面时预选并测试预览该应用）、`--manage`（打开页面时显示应用管理对话框）、`--open`（自动开浏览器）、`--exit-on-close`（最后一个网页关闭后退出）。`--app` 只影响打开的页面 URL（`?app=NAME`），有 live 会话运行时当前会话优先。

## 新建应用

```bash
# 先看计划，不写文件
python -I core/tools/new_app.py myapp --dry-run

# 生成 user/app/myapp/、user/scenarios/myapp.json，并注册到 app.c
python -I core/tools/new_app.py myapp

# 构建并跑场景
python -I core/cli.py --scenario user/scenarios/myapp.json

# 构建并在网页里直接预览
python -I core/web.py --app myapp --open
```

完整教程见 `user/app/GUIDE.md`。脚手架只生成骨架，界面仍由人/AI 写 C；新代码必须
源码构建，不能依赖预编译 engine。

## 应用管理台

网页端顶部的「应用管理」按钮打开管理对话框；需要启动时直接打开时，用
`python -I core/web.py --manage --open`。双击仓库根 `open-web.vbs` 仍打开普通页面。
管理台可以：

- 选择/预览/测试/录制应用（复用顶部现有控件）；
- 新建应用，显示源文件、场景和注册表路径；
- 查看应用目录树、`user/app/app.c` 注册和场景文件；
- 删除应用到 `user/.trash/apps/<trash-id>/`，从回收站恢复，或再次确认后永久删除；
- 查看上次操作和最近修改时间。

删除会同时移除 `user/app/app.c` 的 include 与 `apps[]` 行，并移走所有顶层 `app`
匹配的场景。`coffee`、`xiaohongshu`、`spectrum` 等内置应用受保护，不能删除。
`user/.trash/` 不参与构建。

管理接口只接受本机页面发起的 JSON POST（`Content-Type: application/json` 与
`X-LVGL-AI-Request: 1`），live 启动/运行中拒绝修改应用。

## 命令行

```bash
# scenario 顶层声明 "app" 时，CLI 自动把应用传给 engine
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/xiaohongshu.json

# 已有 build/ 产物时跳过重新构建
python -I core/cli.py --no-build --lvgl 9.6 --scenario user/scenarios/settings.json

# 没有 scenario 时用 --app；--idle 保持会话直到 Ctrl+C（headless）
python -I core/cli.py --lvgl 9.6 --app coffee --idle

# 机器可读摘要（含 app）
python -I core/cli.py --scenario user/scenarios/settings.json --json
```

`--app NAME` 选择用户应用变体，启动时写入 `LVGL_AI_DEMO`；`--scenario` 的 `app` 优先于
继承的环境变量，显式 `--app` 再覆盖 scenario。scenario 的 `app` 字段匹配
`[A-Za-z0-9_-]+`，工具不维护应用清单。

`--record-changed-only` 只保存相对上一张保留帧发生 RGB 变化的帧；默认关闭，网页 live 默认开启。开启后 `frame_count` 是保留帧数，静态画面不消耗 `max_frames` 预算；live 预览也遵循同一变化门控。

`--build/--no-build` 默认 `--build`；`--no-build` 复用仓库根
`build/lvgl_<version>/lvgl_engine`，不重新编译 `user/app`。产物不存在时抛
`EngineNotFound`；改过 C 代码后仍要用源码构建。

退出码：`0` 会话正常结束；`1` build / link / crash；`2` harness、scenario、协议或环境错误。`--json` 在 stdout 输出一行 `session_id` / `manifest_path` / `app` / `error`。

## Python

```python
from lvgl_ai import Recording, Runtime, play_scenario

with Runtime(lvgl="9.6", app="coffee") as rt:   # app 省略时用 LVGL_AI_DEMO / 用户代码默认值
    play_scenario(rt, "user/scenarios/coffee.json")
    print(rt.recording.timeline())

recording = Recording.open("sessions/<id>")
print(recording.manifest["app"], recording.manifest["frame_count"])
```

`Recording.annotations` 是唯一可写入口；写入使用临时文件加替换。

## 会话产物

`sessions/<id>/`：

- `manifest.json`（`lvgl-ai-session-v1`）：status / app / record_changed_only / mode / input / build / lvgl / frame_count / checks / error / artifacts
- `frames/`、`snapshots/`：保留帧与命名快照的完整 PNG；changed-only 时静态帧不落盘，`frame_count` 是保留帧数
- `timeline.ndjson`、`frame_diffs.ndjson`、`engine.log`、`build.log`
- `annotations.json`（`lvgl-ai-annotations-v1`）：`notes` 数组，每条含 `id` / `frame_no` / `t_ms` / `regions` / `tags` / `text`
- `live.rgba`：仅 live 预览期间存在，原始 RGBA8888，停止时删除；不列入 manifest artifacts

保留策略：每次新建会话后，`build_error` 会话一律删除，其余只保留最新的 10 条；没有 `manifest.json` 的目录不会动。

## 版本

`LVGL_AI_LVGL_VERSION` 选择 `lvgl-src/<version>`，支持 `9.6` / `9.5` / `9.4` / `9.1` / `8.4` / `8.3`；`LVGL_AI_LVGL_SRC` 可覆盖源码路径。跨版本比较事件语义，不比较像素。

## 测试

```bash
python -I core/tests/run_tests.py

# 外部契约对比（重构前后都应零差异）
python -I core/tools/contract_snapshot.py compare
```
