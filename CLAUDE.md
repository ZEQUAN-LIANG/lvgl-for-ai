# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

本文件给 AI 编码代理提供仓库级工作说明；用户文档与完整用法见根目录 `README.md`。

## 项目性质

- 工具根是 `console/`：真实 headless LVGL 宿主 + 虚拟 pointer/keypad/encoder + 虚拟时间，提供帧、timeline、diff、日志与回放，**不做 pass/fail 判定**。C engine 在 `engine/`。
- Python 3.9+，只用标准库；CLI 与测试一律 headless。
- 发布物是 Claude Code skill：release zip 解到 `%USERPROFILE%\.claude\skills\lvgl-verify-loop`，入口契约是根目录 `SKILL.md`。
- 旧 `workbench/` 已删除，不要恢复或 import。

## 每次会话先读

1. `CONTEXT.md` — 领域术语表。中文回复；技术术语与代码标识符保持原形；必须使用术语表术语，不得使用 `_Avoid_` 列出的同义词（例如「场景热更新」而非「热重载」、「垂直切片」而非「MVP」、不要单说「模拟器」）。
2. `docs/skill/SKILL.md`、`chip-adapt/docs/sifli.html` — skill 入口契约与 SiFli 导出边界；做 SiFli 相关改动前先读 `chip-adapt/sifli/README.md`。
3. 写或改用户应用时读 `user/app/GUIDE.md`，按版本查 `docs/skill/api-nav/<version>.md`；环境准备与首次运行见 `README.md`。

## 常用命令

所有命令从仓库根执行，统一使用 `python -I`。

```bash
# 跑 scenario（默认 --build、--record、headless）
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --json
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --idle

# 预编译构建（只需 GCC 与 dist/lvgl/<version>；--source 强制 CMake）
python -I console/entrypoints/cli.py --lvgl 9.6 --prebuilt --scenario user/scenarios/settings.json --json
python -I scripts/export_sdk.py --version 9.6 --json

# 安装其他 LVGL 版本（源码或版本包）
python -I scripts/install_version.py --list --json
python -I scripts/install_version.py --lvgl 9.4 --source auto

# 统一入口与发布产物（dist/release/）
python -I scripts/lvgl.py run --scenario user/scenarios/settings.json --json
python -I scripts/release.py --out dist/release --json          # 单包：解包目录 + zip + .sha256 + manifest
python -I scripts/release_all.py --out dist/release --json      # 默认两个包：full / full-sifli
python -I scripts/release_all.py --out dist/release --force-build --json

# 上传 Release 资产（token 只从环境变量读取）
#   set GITHUB_TOKEN=...   /   set GITEE_TOKEN=...
python -I scripts/upload_release.py --version 0.2.2 --replace --json
python -I scripts/upload_release.py --dry-run --json

# Gitee → GitHub 强制镜像（分支 + 标签）
python -I scripts/sync_github.py --dry-run
python -I scripts/sync_github.py

# 只读会话证据（不启动 engine / 网页）
python -I console/entrypoints/session_report.py --latest --log-tail 3
python -I console/entrypoints/session_report.py user/sessions/<id> --json
python -I console/entrypoints/session_report.py crop user/sessions/<id>/snapshots/000_x.png --region 0,0,320,240 --out /tmp/x.png
python -I console/entrypoints/session_report.py compare user/sessions/<a> user/sessions/<b> --json

# 网页端（固定 127.0.0.1:8765）
python -I console/entrypoints/serve.py
python -I console/entrypoints/serve.py --app coffee --open
python -I console/entrypoints/serve.py --manage --open
pythonw -I console/entrypoints/serve.pyw   # Windows 无控制台

# 重建 Windows 双击启动器（MinGW gcc + windres）
python -I scripts/launchers/build.py

# 新建应用骨架
python -I scripts/new_app.py myapp --dry-run

# 静态检查与格式化（ruff / clang-format / cppcheck / comments；细节见 console/README.md）
python -I scripts/lint.py check --json
python -I scripts/lint.py check --files console/web/routes.py
python -I scripts/lint.py format --files user/app/coffee/coffee_ui.c

# 一键回归：lint + 契约快照 + 全量测试 + 发布包冒烟
python -I scripts/verify.py --json

# 全量测试（单元 + 真实 engine 集成；需要六套 LVGL 源码）
python -I scripts/tests/run_tests.py

# 单个测试模块（tests 是包，用完整模块名）
python -I scripts/tests/run_tests.py scripts.tests.control.test_scenario

# 外部契约快照 / 版本边界 / API 导航校验
python -I scripts/contract_snapshot.py compare
python -I scripts/check_version_boundaries.py
python -I scripts/check_api_nav.py

# 准备源码（不随仓库提交）
python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .
python -I scripts/fetch_png.py --repo-root .

# SiFli 导出、构建与测试（入口见 chip-adapt/sifli/README.md）
python -I chip-adapt/sifli/export.py sift_watch --dry-run --force
python -I chip-adapt/sifli/host/cli.py build --app sift_watch --actor ai --json
python -I chip-adapt/sifli/run_tests.py
python -I chip-adapt/sifli/host/tests/run_tests.py
```

- `--no-build` 复用 `build/lvgl_<token>/lvgl_engine.exe`，缺失时报 `EngineNotFound`；默认 `--build` 会重新配置/编译 `apps`。
- 录制只保存画面变化的帧：只在画面变化时写 PNG 与 timeline frame / diff 行；`frame_no` 保持连续。CLI 与网页录制都没有逐帧开关；无变化帧不进入磁盘、时间轴和 AI 摘要。
- `session_report.py` 与 CLI `--json` 共用 `session_index`；只给证据，不做判定。视觉输出必须显式给 `--out`，且不能写入会话证据目录。
- `release_all.py` 只产出两个 zip；`release.py` 才产出解包目录、`.sha256` 与 release manifest。两者在 engine 源码、`user/app`、宿主 SDK manifest 与 GCC 版本摘要未变时复用 `dist/release/lvgl_<token>/`；`--force-build` 强制重建。
- `upload_release.py` 只读 `GITHUB_TOKEN` / `GITEE_TOKEN`；`--replace` 删除同名旧资产，`--notes-file` 不传时保留线上 Release 正文。
- 环境变量：`LVGL_VERIFY_LOOP_LVGL_VERSION`（默认 9.6）、`LVGL_VERIFY_LOOP_LVGL_SRC`、`LVGL_VERIFY_LOOP_ZLIB_SRC`、`LVGL_VERIFY_LOOP_LIBPNG_SRC`、`LVGL_VERIFY_LOOP_SESSIONS_ROOT`、`LVGL_VERIFY_LOOP_BUILD_ROOT`、`LVGL_VERIFY_LOOP_MAX_FRAMES`、`LVGL_VERIFY_LOOP_MAX_LOG_BYTES`、`LVGL_VERIFY_LOOP_ENCODE_BUDGET_BYTES`、`LVGL_VERIFY_LOOP_DEMO`、`LVGL_VERIFY_LOOP_APPS_DIR`、`LVGL_VERIFY_LOOP_GCC`。
- 构建依赖：预编译模式只需 GCC 与 `dist/lvgl/<version>`；源码模式还需要 CMake 3.20+、Ninja，首次构建需要拉取 `engine/third_party/` 的 zlib/libpng 源码。
- 单元测试用 fake engine / session fixture；`*IntegrationTest` 会真实构建 engine，由同一次 `run_tests.py` 执行。`run_tests.py` 只跑全量；单个模块用 `python -I scripts/tests/run_tests.py scripts.tests.<domain>.<module>`。

## 架构

**一条会话 = 一个 engine 进程 = 一个 `Runtime` 实例。** `Runtime.start()` 负责构建（默认）、启动 engine、读取 `ready` 并维护递增 `seq`；`stop()` 发送 `quit`，录制会话等待后台编码 drain。上下文管理器可用。

**Python 控制层**（`console/`）：

- `control/runtime.py`：`Runtime(app=...)` 选择用户应用变体；`pointer` / `key` / `encoder` / `tick` / `wait` / `input` / `snapshot` / `mark`；`wait(ms)`、`wait(frames=n)`、`wait_stable(...)`。`build_mode` 默认为 `auto`。
- `control/prebuilt.py`：宿主 SDK manifest 校验、编译器解析与 gcc 编译/链接命令构造；`control/build_plan.py` 按 `auto` / `source` / `prebuilt` 选择构建路径，预编译对象缓存与源码构建共用 `build/lvgl_<version>/`，切换模式时删除旧 engine。
- `control/recording.py`：`Recording` 只读视图，`open()` 不启动 engine；`annotations` 是唯一可写入口。
- `control/evidence.py`：`session_index` 是 CLI `--json` 与 `session_report.py` 共用的唯一索引入口。
- `console/entrypoints/session_report.py`：只读证据报告与视觉证据子命令（`crop` / `contact-sheet` / `pixel` / `compare`）。
- `scenario.py`：`play_scenario` 把 `lvgl-verify-loop-scenario-v1` 步骤翻译成 Runtime 调用；`click_at`、`drag`、`pointer`、`text` 只在控制层展开。
- `control/session.py`、`control/engine_link.py`、`control/build_plan.py`、`control/retention.py`、`control/engine_guard.py`：会话状态、engine 子进程与协议回执、构建计划、会话保留、非默认应用目录的构建锁与残留 engine。改这些行为先找对应模块，不要在 `Runtime` 里另起一套。
- `web/`：仅 HTTP/UI 适配；回放走 `Recording`（`ReplayModel`），live 走独立 `Runtime`（`LiveSession`）；测试与录制预览走 raw 帧流（`live.rgba` → `GET /api/live/stream` → canvas）。没有第二套协议客户端。
- `paths.py`：`CONSOLE_ROOT` = `console/`，`REPO_ROOT` = 仓库根；`APPS_DIR`、`SCENARIOS_DIR`、`SCRIPTS_DIR`、`API_NAV_DIR`、`ENGINE_DIR` 都在 `paths.py`。

**C engine**（`engine/`）：stdin/stdout 行协议，每条命令与回执带同一 `seq`；命令为 `ready`、`pointer`、`key`、`encoder`、`tick`、`wait`、`mark`、`snapshot`、`quit`。虚拟时间顺序是 `lv_tick_inc` → `lv_timer_handler` → `lv_refr_now` → 录制一帧。录制默认异步编码；首帧在 `ready` 前 drain，停止时 drain 后才写 timeline `end`。changed-only 在编码前按 RGB 严格比较上一张保留帧。`timeline.ndjson` 与 `frame_diffs.ndjson` 由 C engine 写；live 预览另写 `live.rgba`。

**多版本**：`engine/adapter/adapter_9x.c` / `engine/adapter/adapter_8x.c` 是唯一 include LVGL / lodepng 的文件；engine 其余部分只依赖 `engine/adapter/adapter.h`。PNG 编码在 `engine/render/png_writer.c`，只依赖 libpng/zlib。9.x 用 `lv_indev_create` / `lv_indev_set_read_cb`，8.x 用 `lv_indev_drv_*`。9.2+ 有对象名；9.1 与 8.x 的 `hit` 为空，只能看 `hit_class`。支持 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3；发布包 intro 应用按 9.4+ 门编写，9.1/8.x 走旧 harness。跨版本只比较事件语义与 session 文件集合，不比较像素。版本索引在 `scripts/meta/versions.json`（开发仓库与发布包同一位置），安装入口 `scripts/install_version.py`，场景可用 `"lvgl"` 字段选择版本（`--lvgl` 优先）。

**证据**：`user/sessions/<id>/` 包含 `manifest.json`（`lvgl-verify-loop-session-v1`，status 只有 `ok` / `build_error` / `link_error` / `crash` / `harness_error`）、`timeline.ndjson`、`frame_diffs.ndjson`、`frames/`、`snapshots/`、`engine.log`、`build.log`、`annotations.json`、`whiteboards.json`、`whiteboards/`。标注是单帧（`frame_no` + `regions`）或时间区间（`frame_start`..`frame_end` + `anchors[]`，每个锚点一帧的 `regions`）。每个 region 同时保存 bbox、原始局部图（`regions/<note>-aN-rM.png`）和带标注局部图（`...-annotated.png`）；每个锚点另有整帧原图与带标注整帧。白板有 `frame` / `range` / `global` 三种 scope，保存即生效；图片在 `whiteboards/`，文字在 `text` / `labels`。AI 读取顺序：`session_index` 里的 `annotations` / `whiteboards` 索引（`frame_images`、`annotated`、`regions`、`images`、`text`、`labels`）→ 先读文字和 bbox → 按需打开整帧或局部图。录制期间有临时 `.encode/`，正常停止后删除。`record=false` 不写 frames / timeline / frame_diffs，只写临时 `live.rgba`。默认上限 600 帧、日志 16 MB。

## 目录与产物

- `console/`：Python 控制层。`control/`、`web/`、`appmgr/`、`assets/` 四个域包，`entrypoints/` 放 `cli.py`、`serve.py`、`serve.pyw`、`assets_tool.py`、`session_report.py`、`feedback.py`；`paths.py`、`scenario.py`、`versions.py`、`digest.py`、`png_codec.py` 是共享模块。`console/README.md` 是工具用法。
- `engine/`：C engine 源码。`core/`（main、protocol、session、timeline、window）、`render/`（capture、frame_*、json、png_writer）、`adapter/`（adapter_*、`lv_conf.h`），以及 vendored FreeType 头/库。
- `scripts/`：维护与版本脚本。`scripts/launchers/` 是 Windows 双击启动器、图标生成器与构建脚本。`scripts/release_tools_README.md` 是发布包内 `scripts/README.md` 的替代版本。`scripts/upload_release.py` 只给维护者用，不进发布包。
- `user/app/`：用户只写 `user/app/**/*.c` 与 `user/scenarios/`；应用资源头放在各自的 `user/app/<name>/`，没有公共资源目录。应用目录默认不需要任何 JSON——目录名即应用名，入口按 `void <name>_create(void)` 推导；只有入口名偏离约定时才在该目录写 `app.json`。跨应用约束（当前只有 `default`）在根级 `user/app/app.json`。写应用先看 `user/app/GUIDE.md`。`.trash/` 是管理台回收站，不参与构建。
- `user/scenarios/`：场景 JSON；工具层不写死应用名，应用列表来自 `user/app/` 的目录发现和 `user/scenarios/*.json` 的 `app` 字段。
- `docs/`：`skill/SKILL.md` 与 `skill/api-nav/`（每版本 API 导航）、`licenses/`（第三方许可）、`assets/docs.css`；SiFli 能力索引在 `chip-adapt/docs/sifli.html`。
- `chip-adapt/sifli/`：SiFli 导出适配层。`chip-adapt/README.md` 是区域路由，`chip-adapt/sifli/README.md` 是适配层入口；`chip-adapt/vendor/` 是外部下载物（只读，清单见其 README）；`chip-adapt/exports/` 是导出生成物。`chip-adapt/sifli/export.py` 把 `user/app` 按 LVGL 9.4 基线导出到 `chip-adapt/exports/<app>/`；共享源码仍以 `user/app` 为唯一真源。
- `chip-adapt/sifli/host/`：黄山派串口 + 烧录上位机，用法见其 README；双击入口是 `chip-adapt/sifli/launcher/SiFli-Host.exe`。
- `chip-adapt/esp32/host/`：ESP32-C6 串口/Wi-Fi/蓝牙上位机与烧录入口，用法见其 README；PERF TAPE 面板在 `host/perf/perf_gui.py`，双击入口是 `chip-adapt/esp32/launcher/PerfTape.exe`（等价于 `python -I chip-adapt/esp32/host/launch.py`）。
- `engine/lvgl/<version>/`：LVGL 源码，不进 Git；用 `fetch_lvgl.py` 下载。要改 LVGL 时把 unified diff 放进 `engine/lvgl/patches/<version>/`，由 `fetch_lvgl.py` 应用；不要直接修改已安装的源码树。
- `dist/lvgl/<version>/`：预编译宿主 SDK（静态库、公共头、`lv_conf.h`、`lvgl-verify-loop-host-sdk-v1` manifest），由 `scripts/export_sdk.py` 生成；不进 Git。
- `scripts/meta/`：包元数据；`versions.json` 是版本索引（`lvgl-verify-loop-versions-v2`），发布包还含 `VERSION.json`。
- `dist/release/`：`release_all.py` 生成两个 zip（`full` / `full-sifli`）；`release.py` 额外生成解包目录 `lvgl-verify-loop/`、`.sha256` 与 release manifest。解包目录根只有 `SKILL.md` 一个文件，另有 `api-nav/` 目录；其余在 `console/`、`engine/`、`user/app/`、`user/scenarios/`、`scripts/`、`dist/lvgl/`、`build/`、`bin/`、`docs/`、`scripts/meta/`、`docs/licenses/` 下；不进 Git。发布包只带 `user/app/intro/` 一个应用（默认介绍页与模板），不带 Python runtime、`smoke/` 或维护脚本。多版本包的公共 SDK 库与头文件在 `dist/lvgl/common/`。
- `bin/lvgl.cmd`：统一入口包装脚本，调用 `scripts/lvgl.py` 的 `run` / `report` / `serve` / `assets`；`bin/LVGL-AI-Viewer.exe` 是双击启动器；`docs/skill/SKILL.md` 是发布包根 `SKILL.md` 的源。
- `user/sessions/`：会话产物；每次新建会话后删除 `build_error` 会话，并只保留最新的 10 条。

## 硬约束

- 工具不输出 pass/fail、baseline、approval、acceptance；人类在聊天里给验收标准。
- 没有对象树、`inspect`、属性读取、`set`、`param`；精确状态只能由用户 C 代码 `printf` 到 `engine.log`。
- 用户入口固定为 `app_create(void)`；`user/app/**/*.c` 递归收集并全部编译。应用由 `user/app/<name>/` 目录自动发现：目录内声明了 `void <name>_create(void)` 即为应用，入口名偏离约定时在该目录放 `app.json` 声明 `entry`；构建生成 `user/app/app_registry.inc`，没有需要登记应用名的中心表。
- 工具层不写死应用名；应用列表来自 `user/app/` 下的目录发现和 `user/scenarios/*.json` 的 `app` 字段。
- 跨应用的唯一性约束只在根级 `user/app/app.json` 声明（当前只有 `default`）；加删应用永远不需要改它。
- 管理台只保护根级 `app.json` 指定的 `default` 应用；没有 `PROTECTED_APPS` / `PROTECTED_SCENARIOS` 静态名单，添加或删除应用不需要改 `console/appmgr/policy.py`。
- 不静默自动重建旧 engine；`--no-build` 遇到旧 engine 时直接报错并提示用 `--build` 重建。
- 不改已安装的 `engine/lvgl/<version>/`；要改 LVGL 就把 unified diff 放进 `engine/lvgl/patches/<version>/`，由 `fetch_lvgl.py` 应用。
- 不引入第二套协议客户端；CLI、网页与 `session_report.py` 都走 `Runtime` / `Recording` / `session_index`。
- 发布包布局是 `<package>/lvgl-verify-loop/`；开发仓库与发布包使用同一套目录名，路径由 `paths.py` 解析。发布包包含 `console/`，但不含 `engine/lvgl/`、`engine/third_party/`、测试与维护脚本。
- 发布包不自带 Python：宿主机必须提供 Python 3.9+ 并在 PATH 上。改 `user/app/**/*.c` 后重新编译需要 GCC（MinGW-w64 64 位，版本与 `dist/lvgl/*/manifest.json` 一致，当前 15.2.0）；从 LVGL 源码构建需要 CMake 3.20+、Ninja 和 GCC。
- Windows 双击启动器只负责拉起 `pythonw` / `pyw`；端口、URL、HTTP 与串口逻辑留在 Python。

## 工作规则

- 中文回复；使用 `CONTEXT.md` 术语。
- 改完 `.py` / `.c` / `.h` 后跑 `python -I scripts/lint.py check --files <改过的路径>`；项目级 PostToolUse hook 已配置为 check-only，不会自动改文件。
- **不写注释**：`comments` 检查禁止源码里的注释与 docstring（C 的 `//`、`/* */`，Python 的 `#` 与三种 docstring）。工具指令类注释例外：shebang、`# noqa:`、`# type:`、`# pragma:`、`// cppcheck-suppress`；需要说明设计时写进 `console/README.md` 或 `docs/`，不写进源码。
- 不要直接跑 `ruff format .` 或 `clang-format -i -r`；统一走 `lint.py format`，它按规则跳过生成文件、vendored 与构建目录。生成文件识别以 `Generated by` / `Generated from` / `do not edit` 标记为准。
- cppcheck 默认只查 `engine/`；`user/app` 单文件 cppcheck 约 84–90 秒，只在专项审计时用 `--cppcheck-user-app`。MISRA 默认关闭。
- `scripts/lint.py` 与根目录 `pyproject.toml` / `.clang-format` 不进入发布包；`release.py` 的 allowlist 已登记。
- 发布/上传 token 只从环境变量读取（`GITHUB_TOKEN` / `GITEE_TOKEN`），不写入脚本、文档或仓库。
- 日常“导出 → 构建 → 烧录”用本仓库 host（`chip-adapt/sifli/host/cli.py build|flash`）；官方 SiFli-Skills 只在通用 SDK 工程、手动 sftool、代码审查等场景参考。SDK/工具链/sftool 安装见 `chip-adapt/vendor/README.md`。
