# LVGL AI Tools

真实 headless LVGL 运行时 + 取证 + 回放。工具只提供环境、输入和证据，不判定画面；验收标准由人在聊天里给出。

第三方许可声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与仓库根 `licenses/`。

本文件位于工具根 `core/`；下面列出的路径相对本目录，命令示例在**仓库根**执行。

## 目录

- `lvgl_ai/`：Python 控制层。`Runtime`（一个实例 = 一个 LVGL 进程 = 一次会话）、`Recording`（只读证据视图，annotations 可写）、`play_scenario`、`apps/`（应用管理 package：common / policy / registry / scaffold / trash / views）、错误类型、`web/`（HTTP/UI 适配）。
- `engine/`：C engine，负责协议、虚拟 indev、录帧、时间轴、窗口。
- `cli.py`：命令行入口。
- `session_report.py`：会话证据摘要入口，不启动 engine 或网页。
- `web.py`：网页端入口。
- `tests/`：`python -I` 测试套件。
- `api-nav/`：每个 LVGL 版本一份 API 导航。
- `tools/fetch_lvgl.py`：下载官方 LVGL、校验版本并应用本地 patch。
- `tools/fetch_png.py`：下载 pin 的 zlib / libpng 源码到 `third_party/`，供 engine 编码 PNG。
- `tools/new_app.py`：生成应用变体的源文件与场景，并注册到 `user/app/app.c`。
- `tools/export_sdk.py`：从 `lvgl-src/<version>` 导出宿主预编译 SDK 到 `sdk/<version>`。
- `tools/release.py`：生成可分发的 skill zip、`.sha256` 与 release manifest。
- `tools/lvgl.py`：统一入口，分发 `run` / `report` / `serve`。
- `tools/contract_snapshot.py`：记录/对比六类外部契约快照，用于重构行为冻结；用法见
  [CONTRACT_SNAPSHOT.md](CONTRACT_SNAPSHOT.md)。

## 环境准备

需要 Python 3.9+（仅标准库）、CMake 3.20+、Ninja、GCC（Windows 为 MinGW-w64）和 curl；
ccache 可选，git 用于拉取 `third_party/` 的 PNG 编码器源码以及应用 `patches/`。
只用预编译宿主 SDK 时，运行时只需要 Python 与 GCC；CMake、Ninja、LVGL 源码和
`third_party/` 都不是必需项。

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

## 准备 PNG 编码器源码

engine 用 libpng + zlib 编码录制帧与 snapshot，不再使用 LVGL 内置 lodepng 的编码器。
`third_party/` 不随仓库提交，源码构建前先执行：

```bash
python -I core/tools/fetch_png.py --repo-root .
```

脚本按固定 tag/commit 拉取 zlib 1.3.1 与 libpng 1.6.44，校验版本后安装到
`third_party/zlib/` 和 `third_party/libpng/`；CMake 静态编译这两个库。无法访问 GitHub 时，
可先手动准备好这两个目录，或设置 `LVGL_AI_ZLIB_SRC` / `LVGL_AI_LIBPNG_SRC` 指向已有源码。

## 预编译宿主 SDK

没有 LVGL 源码时，用预编译宿主 SDK 直接编译 `user/app`。SDK 包含五份静态库
（engine / adapter / LVGL / libpng / zlib）、公共头、`lv_conf.h` 和
`manifest.json`（`lvgl-ai-host-sdk-v1`，记录编译器版本、defines、include 顺序、
链接顺序与每份库的 sha256）：

```bash
# 从 lvgl-src/<version> 导出；默认输出 sdk/<version>
python -I core/tools/export_sdk.py --version 9.6
python -I core/tools/export_sdk.py --version 9.6 --json

# 重新导出已有 SDK
python -I core/tools/export_sdk.py --version 9.6 --force
```

SDK 是构建产物（`/sdk/` 不进 Git）。预编译构建只调用 GCC，不需要 CMake、Ninja、
LVGL 源码或 `third_party/`。构建前会校验 manifest 记录的编译器版本；版本不一致时
用 `LVGL_AI_GCC` 指向匹配的编译器，或重新导出 SDK。

## 构建方式选择

CLI 的选择规则：

- `lvgl-src/<version>` 存在且未显式指定时，走现有 CMake 源码构建。
- 源码缺失且 `sdk/<version>` 存在时，自动走预编译构建。
- `--prebuilt` 强制预编译；`--source` 强制源码构建。
- `--no-build` 始终只复用 `build/lvgl_<version>/lvgl_engine.exe`。

实际选择写入会话的 `build.log`（`# build mode: prebuilt` 或 CMake 阶段日志）。
预编译构建的对象缓存位于 `build/lvgl_<version>/.prebuilt/`，缓存键包含源文件、
头文件、SDK manifest 哈希与编译器版本；切换回源码构建时会删除预编译 engine，
避免 Ninja 误以为目标已是最新。

```bash
python -I core/cli.py --lvgl 9.6 --prebuilt --scenario user/scenarios/settings.json --json
python -I core/cli.py --lvgl 9.6 --source   --scenario user/scenarios/settings.json --json
```

## 统一入口

`core/tools/lvgl.py` 把 `run` / `report` / `serve` 映射到现有入口；包内
`bin/lvgl.cmd` 只是包装脚本，不掺协议或构建逻辑：

```bash
python -I core/tools/lvgl.py run --scenario user/scenarios/settings.json --json
python -I core/tools/lvgl.py report --latest --log-tail 5
python -I core/tools/lvgl.py serve
```

## 发布包

`core/tools/release.py` 产出可分发 skill zip、`.sha256` 和 release manifest：

```bash
# 默认 9.6；缺少 SDK 时自动导出；产物在 release/
python -I core/tools/release.py --out release --json
```

`release/` 目录同时保留解包后的 skill 目录 `release/lvgl-ai-new/`（含 `SKILL.md`、
`CONTEXT.md`、`core/`、`user/`、`sdk/`、`bin/`、`VERSION.json`），以及同名 zip、
`.sha256` 和 release manifest；可以直接在 `release/lvgl-ai-new/` 里运行，不必先解压。
包内包含 `core/`、`user/`、`sdk/<version>/`、预编译 engine、`bin/lvgl.cmd`、
`SKILL.md`、`CONTEXT.md`、`VERSION.json` 与 `licenses/`。LVGL 源码、`third_party/`、
`sessions/`、测试目录、`chip-adapt/vendor`、`chip-adapt/exports`、构建中间物和开发机
绝对路径不会进包（二进制里的 `__FILE__` 与调试信息也会被检查）；打包前会在暂存目录
从无关工作目录运行 `--no-build`、预编译构建、统一入口和网页端 smoke。`--skip-smoke`
只用于开发调试。

## 启动网页端

控制台入口：

```bash
python -I core/web.py
```

Windows 无控制台入口：

```text
双击仓库根的 LVGL-AI-Viewer.exe
或：双击 core/web.pyw
或：pythonw -I core/web.pyw
```

`web.pyw` 自动打开浏览器，并默认启用 `--exit-on-close`：最后一个网页关闭约 0.5 秒后停止服务并收尾 engine。不带参数启动（双击 `web.pyw`、`LVGL-AI-Viewer.exe` 或经 `pythonw`）时，如果默认地址上已有服务在监听，它只打开页面并退出（暖启动），不会重复启动 server；带参数时保持普通启动路径。控制台入口需要显式加 `--exit-on-close` 才有相同行为。

仓库根的 `LVGL-AI-Viewer.exe` 是带图标的完全无黑框启动入口：双击即可，只负责在 PATH 中找到 `pythonw.exe`（找不到时回退 `pyw.exe`）并启动 `core/web.pyw`；端口探测与打开的 URL 都在 Python 里。启动器源码、图标与构建脚本在 `core/tools/launchers/`，用 `python -I core/tools/launchers/build.py` 重新生成（需要 MinGW gcc 与 windres）。旧的 `.vbs` / `.cmd` 入口已移除。

默认固定端口 `8765`，地址：

```
http://127.0.0.1:8765/
```

- 页面包含回放（完整帧、关键画面、时间轴、框选标注）和 live（启动 / 停止独立 Runtime）。
- 顶部「应用」下拉从 `user/scenarios/*.json` 中声明了 `app` 的 scenario 生成；第一个应用是默认值，打开页面就会自动以测试模式预览它，选中其他应用立即切换，不需要再点「测试」，也不需要重启 `web.py`。选项里没有写死应用名。live 分辨率跟随该应用对应场景的 `display`；同一应用有多个场景时取文件名字典序第一个，画布按帧头自适应。
- 技术细节（manifest、checks、原始 diff、engine.log、build.log）默认折叠在 `<details>` 中。
- 只读像素 diff 默认关闭；打开后按 `frame_diffs.ndjson`（以及可选的参考图 diff）覆盖显示 bbox，只作证据。
- 网页端只通过 `Runtime` / `Recording` 工作，没有第二套协议客户端；live 使用独立 Runtime 和独立 engine 进程。
- 测试与录制均每 33 ms 推进一次虚拟时间（约 30 fps）；PNG 编码由 engine 的 3 个后台 worker 完成，不阻塞 tick。无输入时 timer、toast 和动画继续运行。录制固定只保留画面发生变化的帧（没有逐帧开关），HUD 时间使用虚拟时间 `t_ms`。
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
源码构建，不能依赖预编译 engine。需要非默认分辨率时，在生成的场景顶层加
`"display": {"width": 640, "height": 480}`；尺寸在 engine 启动时传入，改尺寸不需要
重新编译 engine。

## 应用管理台

网页端顶部的「应用管理」按钮打开管理对话框；需要启动时直接打开时，用
`python -I core/web.py --manage --open`。双击仓库根 `LVGL-AI-Viewer.exe` 仍打开普通页面。
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

scenario 顶层可选 `"display": {"width": W, "height": H}`（`1..4096`）；CLI 把宽高传给
engine，不写时使用默认 800×600。显式 `--app` 只覆盖应用，不覆盖场景的 `display`。

录制固定只保存相对上一张保留帧发生 RGB 变化的帧（CLI 与网页 live 一致，没有逐帧开关）。`frame_count` 是保留帧数，静态画面不消耗 `max_frames` 预算，人类与 AI 都不必读重复帧；live 预览也遵循同一变化门控。

录制默认使用 3 个后台 worker 编码 PNG：主线程把保留帧复制到有界内存队列，worker 用 libpng 快速模式编码后发布到 `frames/`；`.encode/` 只保存编码中的临时 PNG。`start()` 返回时首帧 PNG 已落盘；网页 live 的录制与测试都以 33 ms（约 30fps）推进，运行中 `frames/` 可能滞后于 `timeline.ndjson` 的 frame 行，`stop()` 会等待全部编码完成再写 `end` 行。内存队列默认最多 256 MiB，可用 `LVGL_AI_ENCODE_BUDGET_BYTES` 覆盖；超过预算时主线程等待编码，队列为空时允许单个超预算帧。

`--build/--no-build` 默认 `--build`；`--no-build` 复用仓库根
`build/lvgl_<version>/lvgl_engine`，不重新编译 `user/app`。产物不存在时抛
`EngineNotFound`；改过 C 代码后仍要用源码构建。

退出码：`0` 会话正常结束；`1` build / link / crash；`2` harness、scenario、协议或环境错误。`--json` 在 stdout 输出一行 JSON，始终包含 `session_id` / `manifest_path` / `app` / `error`；会话证据可读时再带上 `session_dir`、`status`、`display`、`frame_count`、`requested_app`、`effective_app`、`snapshots`、`marks`、`log_tail`，字段语义与 `summarize_session` 一致。摘要读取失败（崩溃会话、文件不齐）时只保留可得字段，不改变退出码；诊断只走 stderr。

## 会话报告

不启动 engine、不启动网页，读取已有会话的证据：

```bash
# 最新会话的人类可读摘要
python -I core/session_report.py

# 指定会话，stdout 只有一行 JSON
python -I core/session_report.py sessions/<id> --json

# 显式指定最新会话，并且只看最后 5 行 engine.log
python -I core/session_report.py --latest --log-tail 5
```

会话根默认 `sessions/`，可用 `LVGL_AI_SESSIONS_ROOT` 覆盖；无参数或 `--latest` 取最新会话。摘要包含 status、mode、display、帧数与帧绝对路径、requested / effective app、快照、marks、inputs、帧差异和日志尾部。

摘要字段以 `core/lvgl_ai/control/evidence.py` 的 `SUMMARY_FIELDS` 为准；`frames` 是帧 PNG 的绝对路径，供视觉证据命令使用，CLI `--json` 只增加 `CLI_EVIDENCE_FIELDS` 中的较短字段集。`recorded` 与 `Recording.open()` 使用同一规则：manifest 描述录制（`frame_count > 0` 或 artifacts 含 `timeline` / `frame_diffs`）时必须同时存在 `timeline.ndjson` 与 `frame_diffs.ndjson`，缺失按损坏证据报错；`record=False` 或 crash 会话没有这些文件时返回空列表并标记 `recorded: false`，只有 `manifest.json` 或 `engine.log` 缺失才算错误。未知会话或损坏文件退出码 `2`，错误只走 stderr。

`crop`、`contact-sheet` 与 `compare --out` 的输出路径必须显式给出，且不能落在任一源会话的证据目录内：写入 `sessions/<id>/` 的新 PNG 会被 `Recording.frames` / `Recording.snapshots` 当成证据。`pixel` 只读不写。`compare` 的会话输入按摘要顺序取最后一张快照；没有快照时取文件名排序的最后一帧，规则同时写在 `--help` 与票 09。

Python 侧的稳定入口是 `lvgl_ai.summarize_session(session, log_tail_lines=20)`，接受会话目录或 `manifest.json`。

## 等待画面稳定

`Runtime.wait_stable(max_ms, stable_frames)` 以 16 ms 步进调用引擎 `wait`，累计连续 `changed=false` 的次数，达到 `stable_frames` 或 `max_ms` 上限后返回 `waited_ms` / `stable_frames` / `stable`；返回值是证据，不是 pass/fail。它只依据 `wait` 回执的 `changed` 布尔字段，与变化帧门控的保留帧数无关，因此保留帧数为 0 不会被当成稳定。

`changed` 表示该次 `wait` 期间至少有一次 display flush。9.x 与 8.x 的实现边界相同：`core/engine/adapter_9x.c` 和 `core/engine/adapter_8x.c` 都在 flush callback 里设置同一个 `refresh_painted` flag，`core/engine/session.c` 把 flag 汇总进 `wait` / `wait frames` 回执；`tick`、`pointer` 等其它回执不带该字段。支持的 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3 都具备该信号，不需要版本降级。缺 `changed` 字段的旧 engine 会在第一次轮询时报错并提示 `--build` 重建，不会无限等待。

## Python

```python
from lvgl_ai import Recording, Runtime, play_scenario

with Runtime(lvgl="9.6", app="coffee") as rt:   # app 省略时用 LVGL_AI_DEMO / 用户代码默认值
    play_scenario(rt, "user/scenarios/coffee.json")
    print(rt.recording.timeline())

recording = Recording.open("sessions/<id>")
print(recording.manifest["app"], recording.manifest["frame_count"])
```

旧 import 路径 `lvgl_ai.core`、`lvgl_ai.region`、`lvgl_ai.web.server`、`lvgl_ai.web.stream`、`lvgl_ai.web.page`、`lvgl_ai.web.region_images` 已移除；控制层请改用 `lvgl_ai` 顶层导出或 `lvgl_ai.control`，web 请改用 `lvgl_ai.web` 包内模块。

嵌入方可以用 `Runtime(lvgl="9.6", width=640, height=480)` 指定显示尺寸；宽高必须成对且
为 `1..4096`，省略时使用 engine 默认 800×600。实际尺寸以 engine 的 `ready.display` 为准。

`Recording.annotations` 是唯一可写入口；写入使用临时文件加替换。

## 会话产物

`sessions/<id>/`：

- `manifest.json`（`lvgl-ai-session-v1`）：status / app / display / record_changed_only / mode / input / build / lvgl / frame_count / checks / error / artifacts
- `error.detail`：build / link 失败包含 `log_tail`（最后 40 行、最多 8 KB）和 `command`；crash 包含 `exit_code` 与 `log_tail`
- `frames/`、`snapshots/`：保留帧与命名快照的完整 PNG；changed-only 时静态帧不落盘，`frame_count` 是保留帧数
- `timeline.ndjson`、`frame_diffs.ndjson`、`engine.log`、`build.log`
- `annotations.json`（`lvgl-ai-annotations-v1`）：`notes` 数组，每条含 `id` / `frame_no` / `t_ms` / `regions` / `tags` / `text`
- `live.rgba`：仅 live 预览期间存在，原始 RGBA8888，停止时删除；不列入 manifest artifacts
- `.encode/`：编码中的临时 PNG 目录；正常停止后删除，不列入证据

保留策略：每次新建会话后，`build_error` 会话一律删除，其余只保留最新的 10 条；没有 `manifest.json` 的目录不会动。

## 版本

`LVGL_AI_LVGL_VERSION` 选择 `lvgl-src/<version>`，支持 `9.6` / `9.5` / `9.4` / `9.1` / `8.4` / `8.3`；`LVGL_AI_LVGL_SRC` 可覆盖源码路径。`LVGL_AI_USER_APP_DIR` 可指向导出的应用目录（例如 `chip-adapt/exports/<app>/src/app`），用于运行时验证；非默认目录的构建输出在 `build/lvgl_<token>_export_<label>_<hash>`，与 `user/app` 的 `build/lvgl_<token>` 隔离。构建前会获取该目录的跨进程锁，并等待或终止 PID 文件记录的残留 engine。跨版本比较事件语义，不比较像素。

## 测试

```bash
python -I core/tests/run_tests.py

# 外部契约对比（重构前后都应零差异）
python -I core/tools/contract_snapshot.py compare
```

测试套件同时包含单元测试和真实 engine 的集成测试：`*IntegrationTest` 类会按仓库既有方式构建 LVGL（当前主要是 9.6，多版本测试覆盖全部支持版本），由同一次 `run_tests.py` 执行；它们不是 skip 或未执行断言。预编译与 release 集成测试在 `sdk/9.6` 缺失时会自动调用 `tools/export_sdk.py`，因此同样需要 `lvgl-src/9.6` 与 GCC。单元测试使用 fake engine / 纯函数，不构建 LVGL。
