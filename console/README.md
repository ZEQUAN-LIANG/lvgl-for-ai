# LVGL Verify Loop Tools

真实 headless LVGL 宿主：构建并启动 C engine，注入 pointer / keypad / encoder 与虚拟时间，
录制帧、timeline、diff 和日志。工具只提供环境、输入和证据，不判定画面；验收标准由人在
聊天里给出。第三方许可全文见 `docs/licenses/`。

本文件位于工具根 `console/`；命令示例在**仓库根**执行。

## 目录

| 路径 | 内容 |
| --- | --- |
| `control/` | `Runtime`（一个实例 = 一个 engine 进程 = 一次会话）、`Recording`、构建、输入、证据 |
| `web/` | 网页检视台：`ReplayModel`、`LiveSession`、routes、wire |
| `appmgr/` | 应用管理：discovery、policy、scaffold、trash、views |
| `assets/` | 字体/图片转换；`vendor/` 内置 freetype-py 与 pypng |
| `entrypoints/` | `cli.py`、`serve.py`、`serve.pyw`、`assets_tool.py`、`session_report.py`、`feedback.py` |
| `paths.py` / `scenario.py` / `versions.py` / `digest.py` / `png_codec.py` | 共享模块 |

`console/` 是 `sys.path` 根，包内使用裸导入：`control`、`web`、`appmgr`、`assets`、
`scenario`、`paths`。`engine/` 是 C engine（`core/`、`render/`、`adapter/` 三个子目录）。

## 快速开始

```bash
# 首次：下载 LVGL 源码与 PNG 编码器源码
python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .
python -I scripts/fetch_png.py --repo-root .

# 跑场景（默认 --build --record，headless）
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --json

# 只读已有会话的证据
python -I console/entrypoints/session_report.py --latest --log-tail 3

# 网页端（固定 127.0.0.1:8765）
python -I console/entrypoints/serve.py --open
```

- 成功退出码 `0`，stdout 最后一行是会话目录；`manifest.json` 的 `status` 应为 `ok`。
- 网页端默认地址 `http://127.0.0.1:8765/`；端口冲突时加 `--port 8766`。
- Windows 无控制台入口：双击 `bin/LVGL-AI-Viewer.exe`，或 `pythonw -I console/entrypoints/serve.pyw`。

## 依赖与构建方式

- 预编译模式只需 GCC 与 `dist/lvgl/<version>`；不需要 CMake、Ninja、LVGL 源码。
- 源码模式需要 GCC、CMake 3.20+、Ninja，以及 `engine/lvgl/<version>` 与
  `engine/third_party/` 源码。
- `--no-build` 只复用 `build/lvgl_<version>/lvgl_engine.exe`，缺失时报 `EngineNotFound`。
- 构建选择顺序：`engine/lvgl/<version>` 存在时走源码构建；否则 `dist/lvgl/<version>`
  存在时走预编译；`--prebuilt` / `--source` 强制指定。

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --prebuilt --scenario user/scenarios/settings.json
python -I console/entrypoints/cli.py --lvgl 9.6 --source   --scenario user/scenarios/settings.json
python -I scripts/export_sdk.py --version 9.6 --json   # 导出到 dist/lvgl/9.6
```

Windows 建议 MSYS2 UCRT64 的 MinGW-w64 GCC 15.2.0（与 SDK manifest 一致）；CMake、Ninja
用同一环境安装。`python` 使用 python.org 版本，工具层只依赖标准库。

## 会话证据

`user/sessions/<id>/` 包含：

- `manifest.json`（`lvgl-verify-loop-session-v1`）：status / app / display / build / frame_count / artifacts
- `timeline.ndjson`、`frame_diffs.ndjson`：输入事件、虚拟时间、变化区域
- `frames/`、`snapshots/`：保留帧与命名快照（只保存画面变化的帧）
- `engine.log`、`build.log`、`annotations.json`、`whiteboards.json`
- `live.rgba` 只在 live 预览期间存在，不进入证据

AI 读取顺序：`session_index` 的 counts → annotations / whiteboards 索引 → 按需打开整帧或
局部图。保留策略：新会话创建后删除 `build_error` 会话，其余只留最新 10 条。

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `LVGL_VERIFY_LOOP_LVGL_VERSION` | 默认版本，未设置时用 `scripts/meta/versions.json` 的 default |
| `LVGL_VERIFY_LOOP_LVGL_SRC` | 覆盖 LVGL 源码目录 |
| `LVGL_VERIFY_LOOP_APPS_DIR` | 用户应用目录，默认 `user/app`；导出验证时可指向 `chip-adapt/exports/<app>/src/app` |
| `LVGL_VERIFY_LOOP_SESSIONS_ROOT` | 会话根，默认 `user/sessions` |
| `LVGL_VERIFY_LOOP_BUILD_ROOT` | 构建根，默认 `build`；把一次性构建（如测试）落到临时目录 |
| `LVGL_VERIFY_LOOP_DEMO` | 默认应用名 |
| `LVGL_VERIFY_LOOP_MAX_FRAMES` / `_MAX_LOG_BYTES` / `_ENCODE_BUDGET_BYTES` | 录制与日志上限 |
| `LVGL_VERIFY_LOOP_ZLIB_SRC` / `_LIBPNG_SRC` | 覆盖 PNG 编码器源码路径 |
| `LVGL_VERIFY_LOOP_GCC` | 预编译构建使用的 GCC |

## 维护命令

```bash
# 统一入口（run / report / serve / assets）
python -I scripts/lvgl.py run --scenario user/scenarios/settings.json --json
python -I scripts/lvgl.py assets doctor --json

# 静态检查与格式化（ruff / clang-format / cppcheck）
python -I scripts/lint.py check --json
python -I scripts/lint.py format --files user/app/coffee/coffee_ui.c

# 全量测试（单元 + 真实 engine 集成）
python -I scripts/tests/run_tests.py

# 应用骨架与版本安装
python -I scripts/new_app.py myapp --dry-run
python -I scripts/install_version.py --list --json

# 发布包（dist/release/）
python -I scripts/release.py --out dist/release --json
python -I scripts/release_all.py --out dist/release --json
```

`scripts/lint.py` 的 PostToolUse hook 由 `.claude/settings.json` 配置；git pre-commit 需
`git config core.hooksPath .githooks`，应急跳过用 `LVGL_VERIFY_LOOP_SKIP_LINT=1`。

## 常见错误

| 现象 | 处理 |
| --- | --- |
| `LVGL source not found` | 跑 `scripts/fetch_lvgl.py`，或设置 `LVGL_VERIFY_LOOP_LVGL_SRC` |
| `PNG encoder source not found` | 跑 `scripts/fetch_png.py`，或设置 zlib/libpng 源码变量 |
| `build tools not found on PATH` | 安装 GCC / CMake / Ninja，重开终端 |
| `engine binary not found` | 去掉 `--no-build` 先构建 |
| `cannot listen on 127.0.0.1:8765` | 换端口：`--port 8766` |
| `configure/build timed out after 600s` | 降低负载或杀毒扫描后重跑，已完成阶段会保留 |
