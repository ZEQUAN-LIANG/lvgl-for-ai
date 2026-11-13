# LVGL AI Tools

真实 headless LVGL 运行时 + 虚拟输入/虚拟时间 + 帧、timeline、diff、日志取证 + 回放。工具只提供环境、输入和证据，不判定画面；验收标准由人在聊天里给出。

一条会话 = 一个 engine 进程 = 一个 `Runtime` 实例。Python 控制层驱动真实 LVGL，按固定虚拟时间步进，录制完整 PNG、timeline、逐帧 diff 与引擎日志；AI 与人类共用同一份会话证据。

## 仓库包含 / 不包含

**包含**

- `core/`：Python 控制层、C engine、测试、工具与 API 导航。
- `user/`：应用变体（`user/app/`）与场景（`user/scenarios/`）；每个应用自己持有资源头。
- `docs/`：两份契约索引指针页（应用变体、场景/服务端常量）；SiFli 导出边界索引在 `chip-adapt/docs/sifli.html`。
- `chip-adapt/`：SiFli 导出适配层与上位机；入口、下载物和生成物分区见 `chip-adapt/README.md`。
- `licenses/`：LVGL、lodepng、zlib 与 libpng 的完整许可文本。
- `LVGL-AI-Viewer.exe`、`chip-adapt/sifli/tools/SiFli-Host.exe`：Windows 双击启动器；源码、图标与构建脚本在 `core/tools/launchers/`。
- `lvgl-src/README.md`、`third_party/README.md`、`patches/README.md`：源码与 patch 目录的使用说明。

**不包含**（需要在本机生成或下载）

- `lvgl-src/<version>/`：LVGL 源码树，用 `core/tools/fetch_lvgl.py` 下载。
- `third_party/zlib/`、`third_party/libpng/`：zlib / libpng 源码树，用 `core/tools/fetch_png.py` 下载。
- `build/`：engine 构建产物。
- `chip-adapt/vendor/`：SiFli SDK 与外部工具下载物，按 `chip-adapt/vendor/README.md` 恢复。
- `chip-adapt/exports/`：导出生成的 SDK 工程副本。
- `sessions/`：运行时生成的会话证据。
- `sdk/<version>/`：预编译宿主 SDK，由 `core/tools/export_sdk.py` 生成。
- `dist/`：发布 zip、sha256 与 release manifest，由 `core/tools/release.py` 生成。
- `.scratch/tmp/`：下载缓存与临时目录（由下载脚本按需创建）。
- 预编译 engine、Python 第三方依赖（项目只使用标准库，**不需要 `pip install`**）；双击启动器 exe 是随仓库提供的例外。

公开仓库是单提交发布快照，完整开发历史不公开。

## 环境要求

| 依赖 | 要求 | 本次验证版本 | 说明 |
| --- | --- | --- | --- |
| Python | ≥ 3.9 | 3.14.7 | 只用标准库；命令统一使用 `python -I` |
| CMake | ≥ 3.20 | 4.3.1 | 必须能在 PATH 中找到 `cmake` |
| Ninja | 任意近版 | 1.13.2 | CMake 固定使用 `-G Ninja` |
| GCC | MinGW-w64 64 位 | 15.2.0 (x86_64-ucrt-posix-seh) | 必须能在 PATH 中找到 `gcc`；不支持 MSVC `cl.exe` |
| curl | 任意近版 | 8.1.2 | 仅下载 LVGL 时使用；Windows 10 与 Git for Windows 通常自带 |
| ccache | 可选 | 4.13.2 | 检测到会自动启用 |
| git | 可选 | 2.41.0 | 仅在 `patches/<version>/` 有 patch 时需要 |
| 磁盘 | 约 1 GB 可用 | — | LVGL 9.6 归档约 107 MB，解压约 200 MB，另加构建产物 |

### Windows：推荐 MSYS2 UCRT64

安装 [MSYS2](https://www.msys2.org/) 后，在 **MSYS2 UCRT64** 终端执行：

```bash
pacman -Syu
# 终端重启后
pacman -S --needed \
  mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-cmake \
  mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-curl \
  mingw-w64-ucrt-x86_64-ccache
```

把 `C:\msys64\ucrt64\bin` 加入 Windows `PATH`，并放在会遮蔽它的路径之前。然后在 Git Bash / PowerShell / cmd 中验证：

```bash
python --version
cmake --version
ninja --version
gcc --version
curl --version

# Git Bash
which -a cmake ninja gcc
# PowerShell / cmd
where.exe cmake
where.exe ninja
where.exe gcc
```

注意：

- `python` 建议使用 [python.org](https://www.python.org/) 安装的版本；若打开的是 Microsoft Store，请关闭 App Execution Alias，或改用 `py -3`。
- 必须使用 MinGW-w64 GCC；MSVC 不在支持路径内。
- winget 也可安装部分工具（如 `Kitware.CMake`、`Ninja-build.Ninja`），但 GCC 仍建议通过 MSYS2 获取；本仓库未在 winget 路线上复测。

## 首次运行

```bash
git clone https://gitee.com/liang-zequan/lvgl-for-ai.git lvgl-for-agent
cd lvgl-for-agent

# 1. 检查环境
python --version
cmake --version
ninja --version
gcc --version

# 2. 下载并安装 LVGL 9.6 源码
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .

# 3. 下载 PNG 编码器源码（zlib / libpng，安装到 third_party/）
python -I core/tools/fetch_png.py --repo-root .

# 4. 跑一个场景（首次会构建 engine）
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# 5. 或启动网页端
python -I core/web.py --open
```

国内网络访问 `codeload.github.com` 不稳定时，第 2 步改用 Gitee 镜像：

```bash
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root . --source gitee
```

说明：

- `fetch_lvgl.py` 成功后会输出 `installed LVGL 9.6.0 -> .../lvgl-src/9.6`，并写入 `.lvgl-ai-source.json`。
- `fetch_png.py` 会把 zlib 1.3.1 与 libpng 1.6.44 安装到 `third_party/zlib/`、`third_party/libpng/`；构建前若缺失会直接报错并提示重跑该命令。
- 首次构建会编译整个 LVGL，通常需要数分钟；工具对 configure / build 每个阶段设置 600 秒硬超时。
- CLI 成功退出码为 `0`，stdout 最后一行是会话目录；会话 `manifest.json` 的 `status` 应为 `ok`。
- 网页端默认地址 `http://127.0.0.1:8765/`；端口冲突时用 `--port 0` 或 `--port 8766`，Ctrl+C 停止。
- Windows 无控制台启动可双击仓库根的 `LVGL-AI-Viewer.exe`（需要 `pythonw.exe` 或 `pyw.exe` 在 PATH 中；用 `python -I core/tools/launchers/build.py` 重新生成）。

## 常用命令

```bash
# 机器可读摘要：stdout 只有一行 JSON，退出码 0 ok / 1 build·link·crash / 2 harness
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --json

# 只保留画面发生变化的帧
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json --record-changed-only

# 复用已有 engine，跳过构建
python -I core/cli.py --no-build --lvgl 9.6 --scenario user/scenarios/settings.json

# 预编译构建：只需要 GCC 和 sdk/9.6，不需要 CMake/Ninja/LVGL 源码
python -I core/cli.py --lvgl 9.6 --prebuilt --scenario user/scenarios/settings.json --json
python -I core/cli.py --lvgl 9.6 --source --scenario user/scenarios/settings.json --json

# 导出宿主预编译 SDK（默认 sdk/<version>）
python -I core/tools/export_sdk.py --version 9.6

# 统一入口（包内 bin/lvgl.cmd 调用同一实现）
python -I core/tools/lvgl.py run --scenario user/scenarios/settings.json --json
python -I core/tools/lvgl.py report --latest --log-tail 5
python -I core/tools/lvgl.py serve

# 生成发布 zip、sha256 与 release manifest（默认 dist/）
python -I core/tools/release.py --out dist --json

# 网页端（固定 127.0.0.1:8765）
python -I core/web.py
python -I core/web.py --app coffee --open
python -I core/web.py --manage --open

# 新建应用骨架（先 --dry-run）
python -I core/tools/new_app.py myapp --dry-run
```

构建方式自动选择：`lvgl-src/<version>` 存在时走 CMake 源码构建；源码缺失且
`sdk/<version>` 存在时走预编译构建；`--prebuilt` / `--source` 可显式覆盖。实际选择
写在会话 `build.log`。`sdk/`、`dist/` 都是构建产物，不进入 Git。

其他已支持的 LVGL 版本：9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3。用 `--lvgl <version>` 选择，并用 `fetch_lvgl.py --version <version>` 下载对应源码。

## 常见错误

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `LVGL source not found: ...` | 没有下载对应版本的 LVGL 源码 | 运行 `python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .`，或设置 `LVGL_AI_LVGL_SRC` |
| `PNG encoder source not found: ...` | 没有下载 zlib / libpng 源码 | 运行 `python -I core/tools/fetch_png.py --repo-root .`，或设置 `LVGL_AI_ZLIB_SRC` / `LVGL_AI_LIBPNG_SRC` |
| `build tools not found on PATH: cmake, ninja, gcc` | 工具缺失，或 PATH 未生效 | 按上面的 MSYS2 步骤安装，重开终端，用 `which -a` / `where.exe` 检查 |
| `CMake 3.20 or higher is required` | CMake 版本过低 | 升级 CMake |
| `engine binary not found: ...` | 使用了 `--no-build`，但 `build/` 中没有 engine | 去掉 `--no-build` 先构建 |
| `configure timed out after 600s` / `build timed out after 600s` | 单阶段超过 600 秒 | 关闭负载或杀毒扫描后重跑；已完成的阶段会保留，可增量构建 |
| `all download URLs failed:` | 网络、DNS 或代理问题 | 加 `--source gitee`；检查 `curl` 与代理环境变量 |
| `version header mismatch:` | 镜像 tag 漂移 | 删除 `.scratch/tmp/archives` 后重下，或加 `--force` |
| `[web] cannot listen on 127.0.0.1:8765:` | 端口被占用 | 用 `--port 0` 或换一个端口 |
| `cannot read scenario ...` | 场景路径写错 | 检查 `user/scenarios/` 下的文件名 |
| `python` 打开 Microsoft Store | Store 别名 | 使用 python.org 版本、`py -3`，或关闭 App Execution Alias |
| `git is required to apply LVGL patches` | 有 patch 但未安装 git | 安装 Git，或加 `--no-patch`（当前仓库默认没有 patch） |

## 目录说明

| 路径 | 内容 |
| --- | --- |
| `core/` | 工具根：`lvgl_ai/` Python 控制层、`engine/` C engine、`cli.py`、`web.py`、`tests/`、`tools/`、`api-nav/` |
| `user/app/` | 应用变体源码；`app.c` 的 `apps[]` 是注册表 |
| `user/scenarios/` | 场景 JSON |
| `lvgl-src/` | 只跟踪 README；各版本源码按需下载 |
| `third_party/` | zlib / libpng 源码（按需下载，Git 忽略） |
| `build/` | engine 构建产物（Git 忽略） |
| `sdk/` | 预编译宿主 SDK（Git 忽略；由 `export_sdk.py` 生成） |
| `dist/` | 发布 zip、sha256 与 release manifest（Git 忽略） |
| `bin/` | `lvgl.cmd` 统一入口包装脚本 |
| `sessions/` | 会话证据（Git 忽略） |
| `docs/` | 应用变体与场景/服务端常量的索引指针页；SiFli 能力索引见 `chip-adapt/docs/sifli.html` |
| `licenses/` | 第三方许可全文 |
| `patches/` | LVGL patch 组织说明与可选 patch |
| `SKILL.md` | 可分发 skill 的入口契约与 agent 工作流 |

## 会话证据

`sessions/<id>/` 包含：

- `manifest.json`（`lvgl-ai-session-v1`，`status` 为 `ok` / `build_error` / `link_error` / `crash` / `harness_error`）
- `timeline.ndjson`、`frame_diffs.ndjson`
- `frames/`（完整 PNG）、`snapshots/`
- `engine.log`、`build.log`
- `annotations.json`（可选）

`--record-changed-only` 只保留画面变化的帧；`frame_no` 保持连续，`frame_count` 是保留帧数。默认上限 600 帧、日志 16 MB。

## 测试

```bash
# 全量测试（需要六套 LVGL 源码：9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3）
python -I core/tests/run_tests.py

# 只准备当前版本时，不要跑全量；可先跑 CLI / 网页的冒烟命令
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json
```

其他版本的源码下载：

```bash
python -I core/tools/fetch_lvgl.py --version 9.5 --repo-root .
```

## 文档

- `core/README.md`：工具用法（网页端、CLI、Python API、会话产物、测试）。
- `docs/app.html`：应用变体写法索引。
- `docs/scenario-server.html`：场景格式与服务端常量索引。
- `chip-adapt/README.md`：SiFli 适配层入口（分区、任务路由、修改规则）。
- `chip-adapt/vendor/README.md`：外部下载物清单（SDK、工具链、sftool、校验）。
- `chip-adapt/docs/sifli.html`：SiFli SDK 图形能力与导出边界索引。
- `CONTEXT.md`：领域术语表。
- `CLAUDE.md`：AI 编码代理的仓库工作说明；`AGENTS.md` 指向它。

## 许可

- 本项目自身源码：MIT，见根目录 `LICENSE`（`Copyright (c) 2026 zequan.liang`）。
- LVGL：MIT；lodepng、zlib：zlib 许可；libpng：PNG Reference Library License v2。完整文本见 `licenses/`，声明见 `core/THIRD_PARTY_NOTICES.md`。
