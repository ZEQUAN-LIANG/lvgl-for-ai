# 黄山派串口与烧录上位机

`chip-adapt/sifli/host/` 是黄山派（SiFli SF32LB52x）的串口 + 烧录上位机，独立于 `console/`
的 LVGL 会话工具。Python 3.9+，只用标准库和已 vendor 的 pyserial。

## 形态

```
浏览器 (xterm.js) ── HTTP/SSE ──┐
CLI / AI ───────── HTTP JSON ───┼── broker（独占 COM）── pyserial ── 开发板
官方 sftool.exe ────────────────┘
```

- 一个 broker 独占串口；网页、CLI、AI 读同一份带序号的环形缓冲，各自用游标，互不抢字节。
- 人类和 AI/CLI 走同一个 `/api/flash` job，底层官方 `sftool.exe`；页面通过
  `/api/events` 和 `/api/jobs/<id>/stream` 显示进度与操作者（WEB/AI/CLI）。
- 网页是终端优先的 Tabby 风格：顶部只有「终端 / 活动」标签；烧录 dock 位于终端上方。
- 终端直接键盘输入，无发送栏；默认关闭本地回显（板端 finsh 已回显），标签栏「回显」
  可开；Enter 发 CR（RT-Thread finsh 用 CR 结束行，发 CRLF 会打印两次 `msh />`），
  Ctrl+L 清屏。
- `app` 不手填，从 project 路径推导；`/api/suggest` 自动填 project / build / port / baud。

## 快速开始

```powershell
# 检查/补齐依赖（pyserial、xterm.js、SDK uv lock 环境）
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/bootstrap.ps1

# 安装 SDK 工具链与 sftool（国内网络默认走 China mirror；已装可跳过）
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/install-toolchain.ps1

# 启动 broker + 网页（自动打开浏览器）
python -I chip-adapt/sifli/host/server.py --open

# 或双击无黑框入口（需要 pythonw.exe 或 pyw.exe 在 PATH）
chip-adapt/sifli/tools/SiFli-Host.exe
```

`SiFli-Host.exe` 由 `python -I scripts/launchers/build.py` 生成，启动器源码与图标在
`scripts/launchers/`。默认 `http://127.0.0.1:8766/`。依赖清单和手工恢复见
`ENVIRONMENT.md`；`bootstrap.ps1 -Check` 只检查、不安装。

构建链路是 `user/app/<app>/` → `export.py` → `chip-adapt/exports/<app>/project` →
`scons`。`build --app <app>` 会自动完成前两步；不会把源码复制进 SDK，工程通过
`SIFLI_SDK` 指向 `chip-adapt/vendor/sifli-sdk`。

CLI 会自动拉起 broker（`--no-autostart` 关闭）：

```bash
python -I chip-adapt/sifli/host/cli.py ports --json
python -I chip-adapt/sifli/host/cli.py open --port COM12 --json
python -I chip-adapt/sifli/host/cli.py tail
python -I chip-adapt/sifli/host/cli.py close --json
```

PowerShell 包装脚本：`scripts/install-toolchain.ps1 [-NoMirror]`、`scripts/suggest.ps1`、
`scripts/build-current.ps1`、`scripts/flash-current.ps1 [-Build] [-Port COM12]`。所有脚本支持 `Get-Help`；
`build-current.ps1` / `flash-current.ps1` 的 `-DryRun` 只打印命令，不构建/烧录；
退出码 0/1/2 透传。

## CLI / AI 接口

除 `serve` 外，子命令都接受 `--json`；一次调用的命令输出一个 JSON 对象，`tail --json`
和 `events --json` 每块/每条输出一行。`--actor cli|ai|web|system` 给活动流打标签，
AI 用 `--actor ai`。

| 命令 | 作用 |
| --- | --- |
| `serve [--open]` | 启动 broker / 网页 |
| `ports` | 枚举串口 |
| `suggest` | 上次/可用的 app、project、build、port、baud |
| `status` | broker 状态、游标、日志路径、sftool/uv/scons 环境 |
| `open --port COM12 [--baud 1000000]` | 打开串口；不传 `--port` 时只在唯一串口下自动选 |
| `close` | 手动关闭串口并停止自动重连 |
| `send "help" [--line-ending crlf] [--hex]` | 写串口 |
| `read --since N [--max N] [--timeout-ms N]` | 从游标读环形缓冲 |
| `tail [--since now]` | 跟随新数据；`--json` 每块输出一行 |
| `expect "nsh>" [--timeout-ms 5000] [--regex] [--ignore-case]` | 等待模式 |
| `reset [--pulse-ms 100]` | RTS 复位脉冲 |
| `build --app <app>` / `--project-dir <dir>` | 前者导出后构建；后者直接构建 |
| `flash --app <app>` / `--build-dir <dir>` | 前者构建后烧录；后者只烧录已有产物 |
| `flasher [--build] [--open]` | 打包 ZIP、交接串口并打开官方 Web Flasher |
| `events [--follow]` | 查看 AI/CLI/WEB/SYS 活动流 |
| `auto-reconnect on\|off` | 开关串口自动重连 |
| `logs` | 列出串口日志 |
| `shutdown` | 停止后台 broker |

AI 典型调用：

```bash
python -I chip-adapt/sifli/host/cli.py flash --build-dir <build_dir> \
  --port COM12 --actor ai --json
```

AI 烧录不需要人工确认；不传 `--port` 时只有唯一候选口才自动选，多个口必须显式指定。

游标语义：`read --since N` 返回 `{text, data_b64, next, first_seq, next_seq, truncated}`，
下次用 `next` 继续；多个读者从同一 `since` 读到同一段数据。环形缓冲默认 2 MiB，
`truncated=true` 表示 `since` 太旧，数据已从 `first_seq` 开始。

## 网页终端与烧录 dock

- PROJECT / BUILD 打开页面时由 `/api/suggest` 填好；project 为
  `chip-adapt/exports/<app>/project` 时推导出 `app=<app>`。
- **构建**：project 是导出副本时先跑 `export.py <app> --force --json`，再 `scons`；
  否则直接构建该 project。
- **仅烧录 / 构建并烧录**：创建 `/api/flash` job；读取 build 里的 `sftool_param.json`，
  生成与 SDK 相同的 `sftool ... write_flash --verify` 命令。
- **进度**：dock 进度条和百分比、页面顶部全局进度条，终端写 `[build]` / `[flash]` 行；
  失败时 stderr 也进对应的 `[build]` / `[flash]` 行。AI/CLI 触发的同一 job 同样显示。
- **活动**：AI/CLI/WEB 的 open/expect/reset/build/flash 以及 AI/CLI 的 send 事件按时间
  显示；WEB 键盘输入只在终端，不重复进活动流。
- 烧录结束后 build 目录回填到 BUILD。

## 活动与自动重连

- 自动重连默认开：意外断线、flash job 烧录后都会重试（页面发起的 job 固定
  `reconnect=true`，CLI `--no-reconnect` 关闭）；页面重连后从原游标继续读取。
- 页面顶部「自动重连」开关对应 `POST /api/serial/auto_reconnect`；手动「断开」清除
  wanted 状态并停止重连。
- 重试从 0.8 s 起指数退避到 5 s；页面状态栏显示「重连中…」。
- 旧 `/tools/sftool/` 官方页仍保留路由，但主 UI 无入口；手动使用官方页时先用
  `POST /api/flasher/prepare` 准备 ZIP，再 `POST /api/serial/handoff` 交接
  （`cli.py flasher` 会一次完成），交接期间 broker 不抢串口。

## 构建环境

`build` 的命令选择顺序：

1. `config.json` 的 `build_command`；
2. PATH 里的 `scons` → `scons --board=<board> -j8`；
3. SDK uv lock → `uv run --project <sdk>/tools/locks/default scons --board=<board> -j8`；
4. 官方 `export.ps1`（source 后跑 `scons`）。

host 为 scons 注入 `RTT_CC=gcc`、`SIFLI_SDK`/`SIFLI_SDK_PATH`、`PYTHONPATH`、
`RTT_EXEC_PATH`、`CONAN_HOME`、`PKGS_ROOT` 等；工具链优先从
`%USERPROFILE%\.sifli\tools\arm-none-eabi-gcc\<version>\bin` 或
`SIFLI_SDK_TOOLS_PATH` 发现。通用 scons/export.ps1 用法见官方 `sifli-build-win`
skill；本仓库不重复教学。

- 依赖安装：`scripts/bootstrap.ps1`；细节见 `ENVIRONMENT.md` 和
  `chip-adapt/vendor/README.md`。
- `sftool` 查找顺序：`SFTOOL_BIN` → `host/config.json` 的 `sftool` →
  `%USERPROFILE%\.sifli\tools\sftool\<version>` → `<toolchain_root>/tools/sftool` → PATH。
- 导出 `user/app`：`python -I chip-adapt/sifli/export.py <app> --force --json`，产物在
  `chip-adapt/exports/<app>/`。
- 模板保留 `templates/src/SConscript` 的 `src/main.c` 编译修复；`Kconfig.proj` 只保留
  `CUSTOM_MEM_MAP`，image cache 符号由 SDK 的 `middleware/lvgl/Kconfig_mem` 提供，避免重复定义。

## 配置

复制 `config.json.example` 为 `config.json`（已忽略）。常用键：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `host` | `127.0.0.1` | 监听地址 |
| `port` | `8766` | 网页/API 端口 |
| `default_baud` | `1000000` | 串口默认波特率 |
| `board` | `sf32lb52-lchspi-ulp` | 构建板名 |
| `app` / `project_dir` | 空 | 默认应用 / 工程 |
| `build_command` | `[]` | 覆盖默认 scons 命令 |
| `build_timeout_sec` / `flash_timeout_sec` | `1800` / `300` | 构建 / 烧录超时 |
| `flash_baud` | `1000000` | sftool 下载波特率 |
| `flash_verify` / `flash_erase_all` | `true` / `false` | 烧录校验 / 全片擦除 |
| `flash_after` | `soft_reset` | 烧录后动作 |
| `ring_buffer_bytes` / `max_read_bytes` | 2 MiB / 256 KiB | 环形缓冲 / 单次读取上限 |
| `auto_reconnect` | `true` | 串口意外断开后自动重连 |
| `reconnect_interval_s` / `reconnect_max_delay_s` | `0.8` / `5.0` | 重连退避 |

环境变量：`SIFLI_HOST_URL`（CLI 连接地址）、`SIFLI_HOST_BIND`、`SIFLI_HOST_PORT`、
`SIFLI_HOST_BAUD`、`SIFLI_HOST_SFTOOL`、`SIFLI_HOST_SDK`、`SIFLI_HOST_PROJECT_DIR`。

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/ports` | 串口列表 |
| GET | `/api/status` | broker + 环境 |
| GET | `/api/suggest` | app/project/build/port/baud 建议 |
| POST | `/api/open` | `{port, baud}` |
| POST | `/api/close` | 手动关闭（停止自动重连） |
| POST | `/api/send` | `{data, encoding, line_ending}` |
| GET | `/api/read?since=&max=&timeout_ms=` | 读环形缓冲 |
| POST | `/api/expect` | `{pattern, since, timeout_ms, regex, ignore_case}` |
| POST | `/api/reset` | `{pulse_ms}` |
| GET | `/api/stream?since=` | SSE 串口流 |
| GET | `/api/events?since=&limit=` | 活动快照 |
| GET | `/api/events/stream?since=` | SSE 活动流 |
| POST | `/api/serial/auto_reconnect` | `{enabled}` |
| POST | `/api/serial/handoff` | 释放串口给官方页 |
| POST | `/api/build` | 创建构建 job |
| POST | `/api/flash` | 创建烧录 job（人类/AI 共用） |
| GET | `/api/jobs/<id>?since=` | job 快照 |
| GET | `/api/jobs/<id>/stream?since=` | SSE job 流 |
| POST | `/api/jobs/<id>/cancel` | 取消 job |
| POST | `/api/flasher/prepare` | `{build_dir}` → ZIP + 官方页 URL |
| GET | `/api/logs` | 串口日志列表 |
| POST | `/api/shutdown` | 停止 broker |
| GET | `/`、`/vendor/*`、`/tools/sftool/*`、`/firmware/*` | 页面、vendor 资源、官方页、固件 ZIP |

## 目录

```
host/
  server.py           HTTP 路由 + 静态页 + API
  http_layer.py       JSON/SSE/静态文件/错误状态映射
  cli.py              CLI（--json、自动拉起 broker）
  runner.py           build/flash job 编排（释放串口、重连、记录状态）
  broker.py           串口所有权、游标、自动重连
  ring_buffer.py      带序号的接收环形缓冲
  serial_log.py       串口日志目录与 NDJSON 事件
  jobs.py             构建/烧录 job
  events.py           AI/CLI/WEB 活动事件总线
  state.py            上次构建/打开记录与自动填充
  build_flash.py      export.py / scons / sftool / Web Flasher ZIP
  serial_backend.py   pyserial 封装（vendor/pyserial）
  config.py           路径与默认配置
  timeutil.py         统一 ISO 时间戳
  scripts/            bootstrap.ps1、install-toolchain.ps1、build-current.ps1、flash-current.ps1、suggest.ps1
  web/                xterm 终端、烧录 dock、活动流；web/vendor/xterm/
  vendor/serial/      pyserial 3.5（BSD-3-Clause）
  tests/              单元测试
  logs/               串口日志（运行时）
  .cache/             状态与固件 ZIP 缓存（运行时）
```

## 测试

```bash
python -I chip-adapt/sifli/host/tests/run_tests.py
```

测试使用 fake serial backend，不需要开发板，也不会打开真实 COM 口；覆盖环形缓冲、
串口日志、HTTP 辅助层、job 编排、CLI 子命令表与路由表。

## 已知边界

- Windows 是主目标；RTS 复位、路径和 `sftool.exe` 按黄山派布置。
- 主烧录走官方 `sftool`，不依赖浏览器 Web Serial；官方 `/tools/sftool/` 页仅作手工备选。
- `sftool` 无可靠的芯片 ID 查询，host 不做芯片校验；多个候选口时必须显式 `--port`。
- 打开串口时 RTS/DTR 置低；端口被外部串口助手占用时报 `port_busy` 并进入重连退避。
- `sftool-gui`、`Impeller`、`Sifli_Trace` 是 GUI-only，未集成。
- 不做 XMODEM/YMODEM 文件传输、宏、多串口同时打开。
