# ESP32-C6 Studio · 简单上位机

这是 `chip-adapt/esp32/` 的可运行上位机切片：一个本地 broker + 好看的网页 + CLI，
用串口做页面切换、Wi-Fi 配置、蓝牙配置和系统信息读取。它**复用**
`chip-adapt/sifli/host/` 的 `SerialBroker`（同一个 COM 口 owner、同一份环形缓冲和
`pyserial` vendor），没有第二套串口客户端。

## 网页功能

- **概览**：设备卡、当前页面、上一页/下一页、背光、Wi-Fi/蓝牙/内存/uptime 卡片、日志预览
- **页面**：页面列表（来自固件 `pages` 命令）、切换、刷新、背光
- **Wi-Fi**：状态（SSID/IP/RSSI/安全）、扫描网络、点击连接（密码弹窗）、手动 SSID、自动连接、断开
- **蓝牙**：启用/关闭、广播名称、允许发现、连接数、重新广播
- **串口**：端口/波特率、连接/断开、自动重连、行尾、原始命令、SSE 日志、清空/下载
- **系统**：芯片/Flash/内存/uptime/app/当前页面/串口状态、重置
- **烧录器**：独立页面 `/flash/`（不在主 UI 的 tab 里）；esptool 后端、固件计划、实时进度
- **性能监控**：独立页面 `/perf/`；Demo / Live 采集、发送周期、启动/停止、竖版/横版串口切换、实时预览

默认 `http://127.0.0.1:8767/`；`--fake` 模式用内存 backend 模拟固件，不需要板子。
页面列表和无线状态都来自串口命令，前端不写死。

## 快速开始

```bash
# 不需要板子：fake 串口，完整网页都能点
python -I chip-adapt/esp32/host/host.py serve --fake --open

# 真机：先选 COM 口，再打开网页
python -I chip-adapt/esp32/host/host.py serve --port COMx --baud 115200 --open
```

选 8767 是为了避开 `console` 的 8765 和 SiFli host 的 8766。

## 性能监控控制页

`http://127.0.0.1:8767/perf/` 是 `perf_monitor` 的专用控制页。它不直接打开 COM 口，
所有帧和布局命令都走同一个 `SerialBroker`，因此串口仍然只有一个 owner。

页面可以：

- 选择 **Demo** 或 **Live (Windows)**，设置 0.2–60 秒发送周期，启动/停止采集；
- 立即发送 `PERF PORTRAIT` / `PERF LANDSCAPE`，运行中也能切换，不停止采集；
- 实时显示最新一帧的 CPU / MEM / GPU / NET、线程柱和 seq，并在页面内切换竖/横预览。

对应的本地 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/perf/status` | 运行状态、当前布局、seq、周期、最新采样 |
| POST | `/api/perf/start` | `{"mode": "demo" 或 "live", "interval": 1.0, "layout": "portrait" 或 "landscape"}` |
| POST | `/api/perf/stop` | 停止采集线程 |
| POST | `/api/perf/layout` | `{"layout": "portrait" 或 "landscape"}`，发一帧布局命令 |

Live 采集复用 `perf_agent.py` 的 Windows 采集逻辑；单帧通常需要 3–4 秒，页面显示的
`period` 是实测帧间隔。`perf_agent.py` 仍可用于不开网页的 CLI 场景：

```bash
python -I chip-adapt/esp32/host/perf_agent.py --layout landscape --live --interval 1.0
```

## 固件侧协议

命令统一用 LF (`\n`) 结尾，回复行以 `@` 开头。SSID、密码、蓝牙名称在 `connect` / `name`
命令里做 URL 编码，避免空格和特殊字符切断命令行。

### 页面

| 输入 | 回复 |
| --- | --- |
| `pages` | `@PAGES home,status,about` |
| `page <name>` | `@OK PAGE <name>` / `@ERR PAGE unknown=<name>` |
| `page next` / `page prev` | `@OK PAGE <name>` |
| `state` | `@STATE page=<name>` |
| `ping` | `@PONG` |

### Wi-Fi

| 输入 | 回复 |
| --- | --- |
| `wifi status` | `@WIFI STATUS state=connected\|ssid=...\|ip=...\|rssi=-52\|security=WPA2\|auto=on` |
| `wifi scan` | `@WIFI SCAN ssid\|rssi\|security;ssid\|rssi\|security` |
| `wifi connect <urlencoded-ssid> [urlencoded-password]` | `@OK WIFI CONNECT ssid=...\|ip=...\|rssi=...` / `@ERR WIFI CONNECT reason=...` |
| `wifi disconnect` | `@OK WIFI DISCONNECT` |
| `wifi auto on\|off` | `@OK WIFI AUTO on\|off` |

### 蓝牙

| 输入 | 回复 |
| --- | --- |
| `bt status` | `@BT STATUS enabled=on\|name=...\|discoverable=on\|connected=0` |
| `bt on` / `bt off` | `@OK BT on\|off` |
| `bt name <urlencoded-name>` | `@OK BT NAME <name>` |
| `bt discoverable on\|off` | `@OK BT DISCOVERABLE on\|off` |

### 系统

| 输入 | 回复 |
| --- | --- |
| `sys info` | `@SYS INFO chip=ESP32-C6\|flash=4MB\|heap=183KB\|uptime=123s\|app=c6_demo\|page=home\|brightness=42` |
| `brightness <0-100>` | `@OK BRIGHTNESS <value>` |
| `sys reset` | `@OK SYS RESET` |

## CLI

先启动 `serve`，再用 CLI 走 HTTP（不会重复打开 COM 口）：

```bash
python -I chip-adapt/esp32/host/host.py pages --json
python -I chip-adapt/esp32/host/host.py page --name status --json
python -I chip-adapt/esp32/host/host.py page --next --json
python -I chip-adapt/esp32/host/host.py state --json
python -I chip-adapt/esp32/host/host.py send "ping" --json
python -I chip-adapt/esp32/host/host.py ports --json
python -I chip-adapt/esp32/host/host.py status --json
```

`send` 默认用 LF；如果调试别的行协议，用 `--line-ending none|lf|cr|crlf`。

## 烧录（esptool）

烧录后端是乐鑫官方 `esptool`，不是 SiFli 的 `sftool`。host 负责解析固件、释放串口、调用
esptool 并回传进度；ESP32 的 ROM bootloader 协议不在 Python 里重写。

烧录器是**独立网页** `http://127.0.0.1:8767/flash/`，不在设备控制页里。页面和 SiFli
host 的 `/flash/` 是同一份 `chip-adapt/host/flash_web/`，但后端不同：这里显示 `esptool`，
SiFli 那边显示 `sftool`。主页面左侧「烧录器」链接会新开该页。共享页的完整说明、API、
排障和实机记录见 [`../../host/README.md`](../../host/README.md)。

### 准备 esptool

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/esp32/host/scripts/bootstrap.ps1
```

脚本用 `uv` 在 `chip-adapt/esp32/host/vendor/esptool/` 建 venv，固定安装 `esptool==4.8.1`
（不进 Git）。host 的查找顺序：

1. `ESPTOOL_BIN` 或 `serve --esptool PATH`；
2. 上面的 vendor venv（优先 `python -m esptool`，避免控制台启动器留下孤儿进程）；
3. PATH 上的 `esptool` / `esptool.py`；
4. `IDF_PYTHON_ENV_PATH` 或 `~/.espressif/python_env/*` 里的 Python；
5. 当前解释器 `python -m esptool`。

同时支持 esptool 4.x 与 5.x：命令名、`--verify`、`--after` 与 `--flash_mode` 的写法按主版本
自动切换；5.x 始终校验，网页会禁用“校验”勾选。

### 网页流程

1. 打开 `http://127.0.0.1:8767/flash/`（主页面「烧录器」链接）。选择 `.bin` / `.zip`
   （上传到 host），或填写本机路径；ESP-IDF build 目录会读取
   `flash_args` / `flasher_args.json`，Waveshare demo zip 会自动取
   `Firmware/*.bin @ 0x0`。ZIP 只解压被引用的 BIN，不展开整个 260 MB 目录。
2. 确认计划表里的文件/地址，选择端口与烧录波特率（默认 460800）。页面会自动
   优先选 USB JTAG / USB 串行 / CH340 / CP210x 端口；没有把握时显示「选择串口」，
   不会默认拿 COM1 开烧。
3. 开始烧录：host 先释放串口，esptool 独占 COM 口；完成后按需重连
   （`no_reset` 时不重连，避免打开没有固件输出的串口）。
4. 取消/失败会结束 esptool 进程树；设备可能停在 bootloader，需复位后重试。

页面右侧「后端」卡显示当前工具、版本、路径和芯片；这是 `esptool` 后端与 SiFli
`sftool` 后端的对照展示。

`--fake` 模式不调用 esptool，用模拟进度，便于无板演示和测试。

### CLI

```bash
python -I chip-adapt/esp32/host/host.py flash --file fw.bin --plan-only
python -I chip-adapt/esp32/host/host.py flash --zip chip-adapt/vendor/esp32/demo/ESP32-C6-LCD-1.47-Demo.zip --port COMx
python -I chip-adapt/esp32/host/host.py flash --build-dir path/to/build --port COMx --json
```

`--address` 只对单个 `.bin` 生效，默认 `0x0`；`--erase-all`、`--no-verify`、
`--after hard_reset|soft_reset|no_reset`、`--before default_reset|usb_reset`、
`--no-reconnect` 与网页选项对应。

如果 esptool 连不上 C6 的 USB Serial/JTAG，先用 `--before usb_reset` 重试；仍失败时按住
BOOT 再上电进入下载模式。

### 真机记录（2026-11-18）

- 设备：ESP32-C6FH4，USB JTAG/serial 在 `COM13`；`esptool flash_id` 报 **8 MB Flash**
  （官方文档写 4 MB，按实际批次确认）。
- 固件：微雪 demo `Firmware/ESP32-C6-LCD-1.47-Test.bin`，4 MB @ `0x0`。
- 网页 `/flash/` 自动选中 `COM13`，烧录 14.7 s，进度 100%；esptool 输出
  `Hash of data verified` 与 `-- verify OK (digest matched)`。
- 烧录时串口已打开的场景会先释放、结束后 `serial reconnected`；串口读取确认 demo
  正在跑 BLE/Wi-Fi/RAM 测试。
- SiFli 的 sftool 后端未做真机烧录：当前机器只检测到 ESP32 板卡，没有 SiFli CH340
  串口。

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/status` | broker 状态 + `fake` 标记 |
| `GET` | `/api/ports` | 串口列表；fake 模式返回 `COM99` |
| `POST` | `/api/open` | `{port, baud}` |
| `POST` | `/api/close` | 关闭串口 |
| `POST` | `/api/serial/auto_reconnect` | `{enabled}` |
| `GET` | `/api/pages` | 发送 `pages` + `state` |
| `POST` | `/api/page` | `{name}` |
| `POST` | `/api/page/next` | `page next` |
| `POST` | `/api/page/prev` | `page prev` |
| `GET` | `/api/ui/state` | 发送 `state` |
| `POST` | `/api/ping` | 发送 `ping` |
| `POST` | `/api/send` | `{data, line_ending}`，调试用 |
| `GET` | `/api/sys` | 发送 `sys info` |
| `GET` | `/api/wifi` | 发送 `wifi status` |
| `POST` | `/api/wifi/scan` | 发送 `wifi scan` |
| `POST` | `/api/wifi/connect` | `{ssid, password}` |
| `POST` | `/api/wifi/disconnect` | `wifi disconnect` |
| `POST` | `/api/wifi/auto` | `{enabled}` |
| `GET` | `/api/bt` | 发送 `bt status` |
| `POST` | `/api/bt/enable` | `{enabled}` |
| `POST` | `/api/bt/name` | `{name}` |
| `POST` | `/api/bt/discoverable` | `{enabled}` |
| `POST` | `/api/brightness` | `{value}` |
| `POST` | `/api/system/reset` | `sys reset` |
| `GET` | `/api/stream?since=N` | SSE 串口流 |
| `GET` | `/flash/`、`/flash/<asset>` | 独立烧录页（共享 `chip-adapt/host/flash_web/`） |
| `GET` | `/api/flash/env` | 后端元数据、能力、默认波特率和建议固件 |
| `POST` | `/api/flash/upload?name=...` | 原始文件字节上传，返回 `token` |
| `POST` | `/api/flash/plan` | `{token\|path\|files\|build_dir, address?}` → `plan_id` + entries |
| `POST` | `/api/flash/start` | `{plan_id, port?, baud?, erase_all?, verify?, after?, before?, reconnect?}` → 202 `job_id` |
| `POST` | `/api/flash` | 旧入口，参数同 `/api/flash/start` |
| `GET` | `/api/jobs`、`/api/jobs/<id>` | 任务列表 / 快照（`since` 增量） |
| `GET` | `/api/jobs/<id>/stream?since=N` | SSE 任务进度，终态发 `event: done` |
| `POST` | `/api/jobs/<id>/cancel` | 取消烧录任务 |

## 测试

```bash
python -I chip-adapt/esp32/host/tests/run_tests.py
```

测试用 `FakeSerialBackend` 模拟页面、Wi-Fi、蓝牙和系统命令，不需要板子。
`CommandSession` 用一把锁串行化所有 `send`/`expect`，页面命令和无线命令不会互相串线。

## 边界

- 这是**原型**：网页/上位机已可跑；真实 Wi-Fi/BLE 驱动和 `esp_console` 命令要在 ESP-IDF
  固件壳里实现。构建仍用 ESP-IDF；烧录已接到 host（esptool），不再要求手动在 IDF 终端执行。
- host 烧录时会释放串口；不要同时用 `idf.py flash` 或其它工具占用同一个 COM 口。
- 网页不直接用 Web Serial 打开 COM 口；浏览器、CLI、AI 都走同一个 host，避免抢口。
- Wi-Fi 密码通过串口发送，但 `SerialBroker` 的 TX 事件日志会标 `redacted: true`，不把密码
  写进 `events.ndjson`；串口 RX 日志仍保留设备输出。
- 只返回命令响应、串口日志和页面状态，不输出 pass/fail、baseline、approval、acceptance。
- 后续把 broker / SSE / job 抽到 `chip-adapt/host/`，SiFli 和 ESP32 只保留 board 后端。
