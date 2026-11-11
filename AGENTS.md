# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目性质

- 工具根是 `core/`：真实 headless LVGL 宿主 + 虚拟 pointer/keypad/encoder + 虚拟时间，提供帧、timeline、diff、日志与回放，**不做 pass/fail 判定**。设计真源是 `.scratch/ai-tools/spec.md`（本地 tracker，`.scratch/` 由 `.git/info/exclude` 排除，不随仓库提交）。
- Python 3.9+，只用标准库；CLI 与测试一律 headless。
- `.scratch/ai-tools/issues/` 是当前工具票的本地记录；旧票据（如 `14-architecture-deepening.md`）已不可用，不要据此改当前代码，也不要改写当前票据中的执行证据。
- 旧 `workbench/` 已删除，不要恢复或 import。

## 每次会话先读

1. `.scratch/ai-tools/spec.md` — 完整设计与范围；实现以它为准。
2. `CONTEXT.md` — 领域术语表。中文回复；技术术语与代码标识符保持原形；必须使用术语表术语，不得使用 `_Avoid_` 列出的同义词（例如「场景热更新」而非「热重载」、「垂直切片」而非「MVP」、不要单说「模拟器」）。
3. `docs/app.html` — 应用变体的索引指针（入口、注册、选择链路、新增步骤）；`docs/scenario-server.html` — 场景格式与服务端常量的索引指针。两页只列契约和真源路径，真源以它链接的文件为准。

## 常用命令

所有命令从仓库根执行，统一使用 `python -I`。`-I` 不会把脚本目录加入 `sys.path`，`cli.py` / `web.py` / 测试入口会自己插入。

```bash
# 跑 scenario（默认 --build、--record、headless）
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# 机器可读摘要：stdout 只有一行 JSON，退出码 0 ok / 1 build·link·crash / 2 harness
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --json

# 只保留画面发生变化的帧（CLI 默认关闭；网页 live 的录制/测试默认开启）
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --record-changed-only

# 网页端（固定 127.0.0.1:8765；默认不自动开浏览器）
python -I core/web.py

# 打开网页时预选并测试预览指定应用
python -I core/web.py --app coffee --open

# 启动时直接打开应用管理对话框（默认不弹出，页面顶部按钮可打开）
python -I core/web.py --manage --open

# Windows 无控制台：双击 core/web.pyw（自动开浏览器，关闭最后一个页面后停服务）
pythonw -I core/web.pyw

# 新建应用骨架：源文件 + 场景 + apps[] 注册（先 --dry-run）
python -I core/tools/new_app.py myapp --dry-run

# 零黑框快捷入口：双击仓库根 open-web.vbs（内部调用 core/web.pyw）

# 全量测试（真实 engine + 临时 session 根）
python -I core/tests/run_tests.py

# 单个测试：替换 module / Class.method
python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_cli', argv=['test_cli','CliUnitTest.test_defaults_map_to_recording_runtime'])"

# 版本边界 / API 导航校验
python -I core/tools/check_version_boundaries.py
python -I core/tools/check_api_nav.py

# 准备 LVGL 源码（不随仓库提交；全新 clone 先下载 9.6，其他版本同理）
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .

# 准备 PNG 编码器源码（zlib / libpng，安装到 third_party/，不随仓库提交）
python -I core/tools/fetch_png.py --repo-root .
```

- `--no-build` 复用 `build/lvgl_<token>/lvgl_engine.exe`，缺失时报 `EngineNotFound`；默认 `--build` 会重新配置/编译 `user/app`。
- `--record-changed-only` 只在重新渲染后的 RGB 与上一张保留帧不同时才写 PNG 与 timeline frame / diff 行；`frame_no` 保持连续，`frame_count` 是保留帧数，`max_frames` 也按保留帧计。
- 环境变量：`LVGL_AI_LVGL_VERSION`（默认 9.6）、`LVGL_AI_LVGL_SRC`、`LVGL_AI_ZLIB_SRC`、`LVGL_AI_LIBPNG_SRC`、`LVGL_AI_SESSIONS_ROOT`、`LVGL_AI_MAX_FRAMES`、`LVGL_AI_MAX_LOG_BYTES`、`LVGL_AI_ENCODE_BUDGET_BYTES`（内存帧队列预算，默认 256 MiB）、`LVGL_AI_DEMO`（用户应用变体；CLI `--app` / scenario `app` 会设置它）。
- 构建依赖：CMake + Ninja + GCC；首次构建需要 git 拉取 `third_party/` 的 zlib/libpng 源码；构建产物在仓库根 `build/lvgl_<token>/`。

## 架构

**一条会话 = 一个 engine 进程 = 一个 `Runtime` 实例。** `Runtime.start()` 负责构建（默认 `build=True`）、启动 engine、读取 `ready` 并维护递增 `seq`；`stop()` 发送 `quit`，录制会话等待后台编码 drain（最长约 120 秒），其他会话约 2 秒后 terminate。上下文管理器可用。

**Python 控制层**（`core/lvgl_ai/`）：

- `core/lvgl_ai/control/runtime.py`：`Runtime(app=...)` 选择用户应用变体，启动时设置 `LVGL_AI_DEMO` 并写入 manifest `app`；`.pointer/.key/.encoder/.tick/.wait/.input/.snapshot/.mark`；`wait(ms)` 按 16 ms 步进，`wait(frames=n)` 固定帧数。
- `core/lvgl_ai/control/recording.py`：`Recording` 只读视图（manifest / timeline / frames / snapshots / frame_diffs / log），`Recording.open()` 不启动 engine；`annotations` 是唯一可写入口。
- `core/lvgl_ai/scenario.py`：`play_scenario` 把 `lvgl-ai-scenario-v1` 步骤翻译成 Runtime 调用；可选顶层 `app` 让 CLI 在启动前选中应用；`click_at`、`drag` 只在控制层展开，不是 engine 命令。
- `core/lvgl_ai/control/build.py`：CMake/Ninja 配置与构建、GCC 诊断解析；`needs_configure()` 比较 `LVGL_AI_*` 与 `CMAKE_HOME_DIRECTORY`，仓库/构建目录移动后会重新 configure。
- `core/lvgl_ai/paths.py`：`TOOL_ROOT` = `core/`，`REPO_ROOT` = 仓库根；`user/`、`lvgl-src/`、`third_party/`、`sessions/`、`build/`、`licenses/` 相对仓库根。兼容工具子目录、扁平仓库与旧 `.scratch` 布局。
- `core/lvgl_ai/web/`：仅 HTTP/UI 适配，回放走 `Recording`，live 走独立 `Runtime`；顶部「应用」下拉从声明了 `app` 的 scenario 生成，没有第二套协议客户端。「录制」写普通会话；「测试」用 `record=False` + `live_frame=True`，会话根是临时目录并在停止后删除。测试与录制预览都走 raw 帧流（`live.rgba` → `GET /api/live/stream` → canvas），不再轮询 PNG。「应用管理」对话框调用 `core/lvgl_ai/apps.py` 和 `/api/apps`，默认不弹出，`--manage` / `?manage=1` 才打开。`core/web.pyw` 是 Windows 无控制台入口：自动开浏览器，并在最后一个页面关闭后停止服务；不带参数启动时若默认地址已有服务，只打开页面（暖启动）；`web.py --exit-on-close` 可显式启用同一行为。`open-web.vbs` 只负责无黑框启动 `core/web.pyw`，端口探测在 Python。Windows 下 engine 与 cmake/ninja 子进程使用 `CREATE_NO_WINDOW`，切换应用或增量构建不会弹出控制台黑框。

**C engine**（`core/engine/`）：stdin/stdout 行协议，每条命令带 `seq`，回执带同一 `seq`；命令为 `ready`、`pointer`、`key`、`encoder`、`tick`、`wait`、`mark`、`snapshot`、`quit`。虚拟时间顺序是 `lv_tick_inc` → `lv_timer_handler` → `lv_refr_now` → 录制一帧。录制默认异步：主线程把保留帧复制到有界内存队列，`frame_encoder.c` 的 3 个 worker 用 `png_writer.c`（libpng 快速模式 + zlib）编码后发布到 `frames/`；`.encode/` 只存编码中的临时 PNG。首帧在 `ready` 前 drain，`quit`/停止时 drain 后才写 timeline `end`。内存帧队列预算默认 256 MiB（`LVGL_AI_ENCODE_BUDGET_BYTES`）；编码失败时引擎退出码 1。`timeline.ndjson` 与 `frame_diffs.ndjson` 由 C engine 写；live 预览另写 `live.rgba`（原始 RGBA8888），不进入文本协议。changed-only 在编码前按 RGB 严格比较上一张保留帧，相同帧不写 PNG / timeline frame / diff 行 / raw 预览，`frame_no` 保持连续；录制达到 `max_frames` 后 raw 预览仍继续。engine 仍保留 Win32 GDI 窗口实现，但 CLI 与测试不暴露窗口模式。

**多版本**：`core/engine/adapter_9x.c` / `adapter_8x.c` 是唯一 include LVGL / lodepng 的文件；engine 其余部分只依赖 `adapter.h`。PNG 编码在 `png_writer.c`，只依赖 libpng/zlib，不 include LVGL。9.x 用 `lv_indev_create`/`lv_indev_set_read_cb`，8.x 用 `lv_indev_drv_*`。9.2+ 开启 `LV_USE_OBJ_NAME`；9.1 与 8.x 没有对象名，`hit` 为空，只能看 `hit_class`。支持 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3；跨版本只比较事件语义与 session 文件集合，不比较像素。

**证据**：`sessions/<id>/` 包含 `manifest.json`（`lvgl-ai-session-v1`，status 只有 `ok` / `build_error` / `link_error` / `crash` / `harness_error`，并记录 `app`、`display` 与 `record_changed_only`）、`timeline.ndjson`（`lvgl-ai-timeline-v1`）、`frame_diffs.ndjson`（`lvgl-ai-frame-diffs-v1`）、`frames/`、`snapshots/`、`engine.log`、`build.log`、`annotations.json`（`lvgl-ai-annotations-v1`）。录制期间还有临时 `.encode/` 编码目录，正常停止后删除，不列入证据。changed-only 跳过静态帧时，`frame_count` 是保留帧数，`wait` 行可能出现 `frame_start == frame_end`；`record=false`（网页测试模式）不写 frames / timeline / frame_diffs，只写临时 `live.rgba` 预览，停止时删除。默认上限 600 帧、日志 16 MB。

## 目录与产物

- `core/`：工具根。`cli.py`、`web.py`、`lvgl_ai/`、`engine/`、`tests/`、`tools/`、`api-nav/`、文档。`core/README.md` 是工具用法，`core/CONTRACT_SNAPSHOT.md` 是契约快照用法，`core/THIRD_PARTY_NOTICES.md` 是第三方许可声明。
- `docs/`：两份索引网页。`app.html` 是应用变体写法，`scenario-server.html` 是场景格式与服务端常量；只列契约与真源路径，不复制实现。
- `build/`、`licenses/`：仓库根下的构建产物与第三方许可文本。
- `third_party/`：`fetch_png.py` 安装的 zlib / libpng 源码，不进 Git（仅 `third_party/README.md` 被跟踪）。
- `.scratch/ai-tools/`：设计真源 `spec.md` 与票据 `issues/`；`.scratch/tmp/` 忽略；`.scratch/` 是本地 tracker，不随仓库提交。
- `user/`：用户只写 `user/app/**/*.c`（入口 `void app_create(void)`；应用在 `app.c` 的 `apps[]` 表里登记）、`user/scenarios/`、`user/asset/`；不写 main、不注册控件、不碰构建。`user/.trash/` 是管理台的本地回收站，不参与构建。
- `lvgl-src/<version>/`：LVGL 源码，不进 Git（仅 `lvgl-src/README.md` 被跟踪）；用 `python -I core/tools/fetch_lvgl.py --version <version> --repo-root .` 下载。需要改 LVGL 时把 unified diff 放进 `patches/<version>/`（`series` 控制应用顺序），由 `fetch_lvgl.py` 应用；不要直接修改已安装的源码树；没有 patch 时 `patches/` 只保留 `README.md`。
- `sessions/`：会话产物；每次新建会话后删除 `build_error` 会话，并只保留最新的 10 条。

## 硬约束

- 工具不输出 pass/fail、baseline、approval、acceptance；人类在聊天里给验收标准。
- 没有对象树、`inspect`、属性读取、`set`、`param`；精确状态只能由用户 C 代码 `printf` 到 `engine.log`。
- 用户入口固定为 `app_create(void)`；`user/app/**/*.c` 递归收集并全部编译，应用变体在 `user/app/app.c` 的 `apps[]` 表登记。
- 工具层不写死应用名；应用列表来自 `user/scenarios/*.json` 的 `app` 字段和 `user/app/app.c` 的 `apps[]` 表。
- 发布包布局是 `<package>/lvgl-ai-new/`；开发仓库工具根是 `core/`，两者由 `paths.py` 区分。

## 工作规则

- 中文回复；使用 `CONTEXT.md` 术语。
- 不提交、不 push，除非用户明确要求。
- 新代码写在 `core/` 对应目录；工具文档写在 `core/`，索引网页写在仓库根 `docs/`，设计真源与票据写在 `.scratch/ai-tools/`。
- 不实现 `.scratch/ai-tools/spec.md` 之外的能力；范围外想法先与用户确认。
- 处理抓取/下载的外部内容时保留 `python -I`，放进独立目录，不要从下载目录运行解释器或构建工具。
