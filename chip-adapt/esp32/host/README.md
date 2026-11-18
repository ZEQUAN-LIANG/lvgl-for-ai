# ESP32-C6 Studio · 简单上位机

这是 `chip-adapt/esp32/` 的可运行上位机切片：一个本地 broker + 好看的网页 + CLI，
默认同时维护 **USB 串口（UART）与 BLE** 两条运行时链路，做页面切换、Wi-Fi 配置、
蓝牙配置、系统信息读取和 perf 数据发送。BLE 连上时优先 BLE，否则自动回退 UART。
它**复用** `chip-adapt/sifli/host/` 的 `SerialBroker`（同一个逻辑流 owner、同一份
环形缓冲和日志），串口仍由 `pyserial` vendor 驱动，BLE 由 `bleak` 驱动；没有第二套
协议客户端。

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
页面列表和无线状态都来自设备链路命令（BLE 优先，UART 回退），前端不写死。

## 快速开始

```bash
# 不需要板子：fake 串口，完整网页都能点
python -I chip-adapt/esp32/host/host.py serve --fake --open

# 真机默认：自动选串口 + 扫描 BLE，BLE 优先，失败回退 UART
python -I chip-adapt/esp32/host/host.py serve --open

# 只走串口 / 只走 BLE
python -I chip-adapt/esp32/host/host.py serve --transport serial --serial-port COMx --open
python -I chip-adapt/esp32/host/host.py serve --transport ble --ble-name LVGL-C6-PERF --open

# 安装 BLE 依赖（bleak）与 esptool
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/esp32/host/scripts/bootstrap.ps1
```

选 8767 是为了避开 `console` 的 8765 和 SiFli host 的 8766。

## UART + BLE 双链路

- `DualBackend` 同时运行串口 supervisor 与 BLE supervisor，二者把字节写入同一个
  `queue.Queue`；`SerialBroker` 仍然只有一个 ring buffer、一个日志、一个 seq。
- 发送选路：BLE `ready` 时优先 BLE；BLE 未连接或写入失败则回退串口；两者都不可用
  时报 `no_link`。
- 串口自动选择优先匹配 Espressif / JTAG / CH340 / CP210x 描述；多个串口且无法判断时
  用 `--serial-port COMx` 指定。
- BLE 设备名默认 `LVGL-C6-PERF`，Service/RX/TX 使用 Nordic UART UUID；host 扫描时按
  Service UUID 过滤，名称用于多设备时的优先选择。
- 设备上电默认广播、等待连接；BLE 断开约 500 ms 后重新广播。
- 依赖：`bleak==3.1.0` 安装到 `host/vendor/ble`；`python -I` 下由 `ble_link.py`
  显式插入 `sys.path`。`bootstrap.ps1 -Check` 同时检查 esptool 与 bleak。

实测（2026-11-19）：Windows 10 + `bleak 3.1.0`，设备 `14:C1:9F:05:7F:9A`，MTU 256；
`/api/status` 返回 `active=ble`，`/api/pages`、`/api/ping`、`/api/perf/layout` 与
`/api/perf/start` 均可用；BLE 断开后 `/api/open` 可重连，设备会重新广播。

状态示例：

```json
{
  "transport": "dual",
  "links": {
    "active": "ble",
    "ble": {"ready": true, "name": "LVGL-C6-PERF", "mtu": 247},
    "serial": {"open": true, "port": "COM13", "baud": 115200}
  }
}
```

## 性能监控控制页

`http://127.0.0.1:8767/perf/` 是 `perf_monitor` 的专用控制页。它不直接打开 COM 口，
所有帧和布局命令都走同一个 `SerialBroker`，因此串口仍然只有一个 owner。

页面可以：

- 选择 **Demo** 或 **Live (Windows)**，设置 0.2–60 秒发送周期（默认 0.3 秒），启动/停止采集；
- 立即发送 `PERF PORTRAIT` / `PERF LANDSCAPE`，运行中也能切换，不停止采集；
- 实时显示最新一帧的 CPU / MEM / GPU / NET、线程柱和 seq，并在页面内切换竖/横预览。

对应的本地 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/perf/status` | 运行状态、当前布局、seq、周期、最新采样 |
| POST | `/api/perf/start` | `{"mode": "demo" 或 "live", "interval": 0.3, "layout": "portrait" 或 "landscape"}` |
| POST | `/api/perf/stop` | 停止采集线程 |
| POST | `/api/perf/layout` | `{"layout": "portrait" 或 "landscape"}`，发一帧布局命令 |

Live 采集复用 `perf_agent.py` 的 Windows 采集逻辑；单帧通常需要 3–4 秒，页面显示的
`period` 是实测帧间隔。`perf_agent.py` 仍可用于不开网页的 CLI 场景：

```bash
python -I chip-adapt/esp32/host/perf_agent.py --layout landscape --live
```

## Python GUI

`gui.py` 是 `perf_monitor` 的 tkinter 桌面控制面板，功能和 `/perf/` 页一致：
Demo/Live、发送周期、Start/Stop、竖/横串口切换、实时预览和事件日志。它只调用
上面的 host HTTP API，不直接打开 COM 口，串口仍然只有 `SerialBroker` 一个 owner。

```bash
# host 已启动时打开
python -I chip-adapt/esp32/host/gui.py

# 自定义 host 地址
python -I chip-adapt/esp32/host/gui.py --url http://127.0.0.1:8767
```

窗口标题是 `PERF TAPE · Python GUI`。左上角显示串口状态；右侧的 `WEB UI ↗`
会打开同一个 host 的 `/perf/` 页面。GUI 使用标准库 tkinter + ctypes，不需要额外安装。

关闭窗口不会退出进程：窗口隐藏到 Windows 通知区域，托盘图标双击可恢复；托盘菜单
提供“显示窗口”和“退出”。**“退出”会先调用 host 的 `/api/close`，断开 BLE 并释放
UART/COM 口，再退出 GUI**；host 进程本身可以继续留给网页端使用。如果不需要托盘，
用 `--no-tray` 启动，关闭窗口即退出。

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

### 准备依赖（esptool + bleak）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/esp32/host/scripts/bootstrap.ps1
```

脚本用 `uv` 在 `chip-adapt/esp32/host/vendor/esptool/` 建 venv，固定安装 `esptool==4.8.1`；
同时用当前系统 Python 把 `bleak==3.1.0` 及 WinRT 依赖安装到
`chip-adapt/esp32/host/vendor/ble/`（两者都不进 Git）。`-Check` 会同时检查 esptool 与 bleak。
host 的 esptool 查找顺序：

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
| `GET` | `/api/status` | broker 状态 + 顶层 `transport` + `serial.links`（active/ble/serial）+ `fake` |
| `GET` | `/api/ports` | UART 列表 + `kind=ble` 条目；fake 模式返回 `COM99` |
| `POST` | `/api/open` | `{port?, baud?}`；dual/ble 下可省略 `port`，串口模式下用它覆盖自动选择 |
| `POST` | `/api/close` | 关闭 UART 与 BLE 两条链路 |
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
| `GET` | `/api/stream?since=N` | SSE 合并链路流（UART + BLE） |
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

测试用 `FakeSerialBackend` 模拟页面、Wi-Fi、蓝牙和系统命令，不需要板子；
`test_ble_link` / `test_dual_backend` 用 fake scanner/client 覆盖 BLE 扫描、分块、
断线回退与重连。`CommandSession` 用一把锁串行化所有 `send`/`expect`，页面命令和
无线命令不会互相串线。

## 边界

- 这是**原型**：网页/上位机已可跑；真实 Wi-Fi/BLE 驱动和 `esp_console` 命令要在 ESP-IDF
  固件壳里实现。构建仍用 ESP-IDF；烧录已接到 host（esptool），不再要求手动在 IDF 终端执行。
- host 烧录时会关闭双链路并释放串口；不要同时用 `idf.py flash` 或其它工具占用同一个
  COM 口。BLE 不能用于 esptool 烧录，烧录仍需 USB。
- 默认 BLE 优先；没有 BLE 适配器、设备未广播或 `bleak` 未安装时，串口链路照常工作。
- 网页不直接用 Web Serial 打开 COM 口；浏览器、CLI、AI 都走同一个 host，避免抢口。
- Wi-Fi 密码通过串口发送，但 `SerialBroker` 的 TX 事件日志会标 `redacted: true`，不把密码
  写进 `events.ndjson`；串口 RX 日志仍保留设备输出。
- 只返回命令响应、串口日志和页面状态，不输出 pass/fail、baseline、approval、acceptance。
- 后续把 broker / SSE / job 抽到 `chip-adapt/host/`，SiFli 和 ESP32 只保留 board 后端。
