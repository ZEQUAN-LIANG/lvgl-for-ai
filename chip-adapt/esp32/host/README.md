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

## 测试

```bash
python -I chip-adapt/esp32/host/tests/run_tests.py
```

测试用 `FakeSerialBackend` 模拟页面、Wi-Fi、蓝牙和系统命令，不需要板子。
`CommandSession` 用一把锁串行化所有 `send`/`expect`，页面命令和无线命令不会互相串线。

## 边界

- 这是**原型**：网页/上位机已可跑；真实 Wi-Fi/BLE 驱动和 `esp_console` 命令要在 ESP-IDF
  固件壳里实现。构建/烧录先用 ESP-IDF 终端手动执行。
- `idf.py flash` 期间不要同时开 host，同一个 USB Serial/JTAG 口只能有一个 owner。
- 网页不直接用 Web Serial 打开 COM 口；浏览器、CLI、AI 都走同一个 host，避免抢口。
- Wi-Fi 密码通过串口发送，但 `SerialBroker` 的 TX 事件日志会标 `redacted: true`，不把密码
  写进 `events.ndjson`；串口 RX 日志仍保留设备输出。
- 只返回命令响应、串口日志和页面状态，不输出 pass/fail、baseline、approval、acceptance。
- 后续把 broker / SSE / job 抽到 `chip-adapt/host/`，SiFli 和 ESP32 只保留 board 后端。
