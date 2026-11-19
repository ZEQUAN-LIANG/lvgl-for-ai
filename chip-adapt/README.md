# chip-adapt

SiFli 黄山派（SF32LB52x）与 ESP32-C6 的适配层与 PC 侧上位机。它和 `console/` 的
LVGL headless 宿主分开：`console/` 负责预览/取证，本目录负责把 `user/app` 导出成
目标工程（SiFli 已实现；ESP32-C6 已打通 Arduino bring-up、host 控制页和真机烧录，
正式 ESP-IDF 导出器仍规划中），并提供串口、构建和烧录入口。

## 先看三个区

| 区域 | 路径 | 进 Git | 能否手改 | 谁生成/安装 |
| --- | --- | --- | --- | --- |
| 自研 | `chip-adapt/sifli/`（除 host 的 vendor/cache/logs） | 是 | 是 | 人 / AI |
| 自研 | `chip-adapt/esp32/` | 是 | 是 | 人 / AI |
| 自研 | `chip-adapt/host/`（共享烧录页与计划缓存） | 是 | 是 | 人 / AI |
| 外部大件 | `chip-adapt/vendor/` | 否（仅 README） | 否 | 按 `vendor/README.md` 下载 |
| 上位机运行时依赖 | `chip-adapt/sifli/host/vendor/`、`host/web/vendor/` | 否 | 否 | `bootstrap.ps1` |
| 生成物 | `chip-adapt/exports/`、`host/.cache/`、`host/logs/` | 否 | 否 | `export.py`（SiFli）/ `arduino/build.py`（ESP32）/ host 运行 |
| 双击启动器 | `bin/LVGL-AI-Viewer.exe`、`chip-adapt/sifli/tools/SiFli-Host.exe` | 否（构建生成） | 否 | `scripts/launchers/build.py` |
| 系统级工具 | `%USERPROFILE%\.sifli` 或 `SIFLI_SDK_TOOLS_PATH` | 否 | 否 | SDK `install.ps1` |

- `chip-adapt/docs/sifli.html`：SDK 图形能力知识索引，不是操作手册。
- `chip-adapt/sifli/`：SiFli 自研代码，唯一可直接改 SiFli 导出逻辑的区域。
- `chip-adapt/esp32/`：ESP32-C6 板级适配、host 控制页、桌面 GUI 与 Arduino bring-up；
  见 `esp32/README.md`，演示视频 `../docs/media/esp32-c6-perf-monitor.mp4`。
- `chip-adapt/host/`：独立烧录页、esptool/sftool 双后端契约、排障与实机记录，见
  `host/README.md`。
- `chip-adapt/vendor/`：SDK 与可选外部资源；**只读**，升级按清单重下。
- `chip-adapt/exports/`：导出副本；**只能由导出脚本生成**（SiFli `export.py`、ESP32 `arduino/build.py`），手改会丢。

## 任务路由

| 我要… | 从这里开始 | 关键命令/文件 |
| --- | --- | --- |
| 导出应用到 SDK 工程 | `sifli/README.md` | `python -I chip-adapt/sifli/export.py <app> --dry-run`（默认增量） |
| 构建 / 烧录 / 看串口 | `sifli/host/README.md` | `python -I chip-adapt/sifli/host/server.py --open` |
| 直接点开上位机 / 重建启动器 | `sifli/tools/` | 双击 `SiFli-Host.exe`；`python -I scripts/launchers/build.py` |
| 改导出规则或模板 | `sifli/export.py`、`sifli/asset_plan.py`、`sifli/templates/` | `python -I chip-adapt/sifli/run_tests.py` |
| 改 SiFli 上位机 | `sifli/host/` | `python -I chip-adapt/sifli/host/tests/run_tests.py` |
| ESP32-C6 页面 / Wi-Fi / 蓝牙 / 串口 | `esp32/host/README.md` | `python -I chip-adapt/esp32/host/host.py serve --fake --open` |
| 烧录器（独立网页，两个后端） | `host/README.md` | ESP32 `:8767/flash/`（esptool）；SiFli `:8766/flash/`（sftool） |
| ESP32-C6 现状与后续 | `esp32/README.md` | perf_monitor 已真机验证；host + `/perf/` + GUI；正式 ESP-IDF 导出器/壳待补 |
| ESP32-C6 Arduino 演示固件 | `esp32/arduino/README.md` | `python -I chip-adapt/esp32/arduino/build.py all --port COMx`；原理见 `esp32/docs/arduino-perf-monitor.md` |
| 下载/升级 SDK、工具链、sftool | `vendor/README.md` | `host/scripts/install-toolchain.ps1`（国内网络默认镜像）；不在仓库内改 SDK |
| 查 SDK 图形能力 | `docs/sifli.html` | 以链接的 SDK v2.5.1 真源为准 |
| 改应用 | `../user/app/GUIDE.md` | 只改 `user/app/`，不改 `exports/` |

## 下载与工具落点

完整来源、版本、落点和校验见 [`vendor/README.md`](vendor/README.md)。这里只记结论：

- SDK 源码：`chip-adapt/vendor/sifli-sdk/`（commit `f4042d7e`，`version.txt` = `v2.5.1`）。
- SDK 自带工具：留在 `vendor/sifli-sdk/tools/`（`png2ezip/ezip.exe`、`sdk.py`、`uart_download/`、`locks/`）。
- ARM 工具链与 sftool：官方 `install.ps1` 安装到 `%USERPROFILE%\.sifli\tools\`，不进仓库。国内网络用 `sifli/host/scripts/install-toolchain.ps1`（默认 `SIFLI_SDK_MIRROR_CHINA=1`，走 downloads.sifli.com 与 USTC PyPI），细节见 `vendor/README.md`。
- Web Flasher 静态资源：可选，`vendor/sifli-wiki/source/_static/sftool/`。
- pyserial / xterm.js：`bootstrap.ps1` 安装到 `sifli/host/vendor/` 和 `sifli/host/web/vendor/`。

## 修改规则

| 任务 | 改哪里 | 必须同步 | 禁止 |
| --- | --- | --- | --- |
| 改导出逻辑 | `sifli/export.py`、`sifli/asset_plan.py` | 适配器测试、`sifli/README.md` | 改 `vendor/`、`exports/` |
| 改导出模板 | `sifli/templates/` | 测试、导出 dry-run | 在导出副本里手改 |
| 改上位机 | `sifli/host/` | host 测试、host README/API 表 | 另起协议客户端 |
| 改共享烧录页 | `host/flash_web/`、`host/flasher_web.py` | 两边 host 的 env/plan 测试、两份 README | 在页面写死某个芯片或工具 |
| 改启动器或图标 | `scripts/launchers/` | 重建 exe、`scripts/tests/tools/test_launchers.py` | 手改 exe/ico；启动器掺端口/URL/协议 |
| 升级 SDK | `vendor/README.md` + 重下 | 路径、链接、API 复核 | 直接改 SDK 源码 |
| 新增/修改应用 | `user/app/<app>/` | 场景、`assets.json`、`app.json` | 改 `exports/<app>/` |
| 改文档 | 本节列出的各 README | 链接校验 | 复制官方 skill 内容 |

路径只从 `sifli/layout.py` 取：不要在新代码里硬编码导出目录或 SDK 目录。

> SiFli 与 ESP32 的导出/构建默认都是增量的：只更新变化的源码，复用 SDK/Arduino
> 构建缓存；`--force` 仅用于清理后重导。ESP32-C6 已跑通 `perf_monitor` 真机链路：
> Arduino bring-up、host 的 **UART + BLE 双链路**（BLE 优先、UART 回退）、烧录、
> `/perf/` 控制页、tkinter GUI 和横竖版切换；视频见
> `../docs/media/esp32-c6-perf-monitor.mp4`。正式 ESP-IDF 导出器和固件壳尚未实现，
> 见 `esp32/README.md`。

## 从 user/app 到 SDK 编译

导出**不会把源码复制进 SDK**。它生成自包含工程，构建时通过 `SIFLI_SDK` 指向
`chip-adapt/vendor/sifli-sdk`；不要把导出目录复制到 SDK 里。

```text
user/app/<app>/                       # 唯一源码真源
  └─ export.py ──> chip-adapt/exports/<app>/project
                       ├─ scons --board=sf32lb52-lchspi-ulp -j8
                       └─ build_sf32lb52-lchspi-ulp_hcpu/
```

推荐用本仓库上位机完成“导出 → 构建 → 烧录”，它会自动重新导出并注入 uv lock 与
`~/.sifli` 工具链环境：

```bash
# 导出并构建（--app 会先跑 export.py）
python -I chip-adapt/sifli/host/cli.py build --app sift_watch --actor ai --json

# 构建并烧录；不传 --port 时只有唯一串口才自动选
python -I chip-adapt/sifli/host/cli.py flash --app sift_watch --port COM12 --actor ai --json
```

等价的纯 SCons 手动方式（先让官方 `export.ps1` 或 host 注入环境）：

```bash
cd chip-adapt/exports/sift_watch/project
scons --board=sf32lb52-lchspi-ulp -j8
```

要在 VS Code/IDE 里打开工程，打开 `chip-adapt/exports/<app>/project`，不要改
`vendor/sifli-sdk` 里的示例。

## 官方 SiFli-Skills：什么时候用

本仓库已经有内部上位机 `host/`，日常“导出 → 构建 → 烧录”**不需要**再引入官方
skill；host 已经封装了 export、uv lock、工具链、sftool、进度和 AI/CLI 共用 job。

只有在这些场景才参考官方 skill：

| 场景 | 官方 skill |
| --- | --- |
| 与本仓库导出无关的通用 SDK 工程、手动 scons | `sifli-build-win` |
| 需要 sftool 原始命令、读回、排障 | `sftool` |
| 代码审查/风格 | `sifli-code-review` |
| VS Code/CodeKit MCP 环境 | `sifli-sdk-codekit`（仅该环境） |
| crash dump / MUSB / 新料号 | `sifli-crash-dump-triage`、`musb-reg-dump-analyzer`、`sf32lb57-add-part-number` |

官方 `sifli-build-win` / `sftool` skill **不覆盖安装**；SDK、工具链、sftool 安装仍按
`vendor/README.md`。

## 验证入口

```bash
# 适配器测试（export / assets / layout）
python -I chip-adapt/sifli/run_tests.py

# 上位机测试（fake serial，不需要板子）
python -I chip-adapt/sifli/host/tests/run_tests.py

# 重建两个双击启动器（MinGW gcc + windres）
python -I scripts/launchers/build.py

# headless 验证导出副本（先安装 9.4 源码与 PNG 依赖）
LVGL_VERIFY_LOOP_USER_APP_DIR="$PWD/chip-adapt/exports/sift_watch/src/app" \
  python -I console/entrypoints/cli.py --lvgl 9.4 --scenario user/scenarios/sift_watch.json
```

## 不做什么

- 不把 SDK、工具链、sftool、官方 skills 提交进 Git。
- 不让启动器探测端口、拼 URL 或直接碰串口；它只负责拉起 `pythonw` / `pyw`。
- 不手改 `vendor/` 或 `exports/`。
- 不为多芯片做统一板级抽象；只共享烧录前端/HTTP 契约（`host/`），SiFli 导出在
  `exports/<app>`，ESP32 规划在 `exports/esp32/<app>`，各自保留 board 后端与 profile。
- 不引入第二套协议客户端；网页、CLI、AI 共用 host 的 broker 和 job。
