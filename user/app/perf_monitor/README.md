# PERF TAPE · 172×320 / 320×172 性能监控器

`perf_monitor` 把 `chip-adapt/esp32/design/perf-monitor.html` 的设计落成 LVGL 9.6
应用：暖色磷光仪器风格，CPU 60 个采样的步进负载带、内存/GPU 双轨、网络上下行镜像
波形、最多 16 条线程柱、PC 时钟与链路状态。演示数据按 0.3 秒节拍、8 条线程柱生成；
真实帧用 `thn` 告诉屏幕实际逻辑核数，柱宽与数量会自适应。负载带的横轴窗口按实测
采样周期换算：0.3 秒节拍显示 `-18S`，采集慢到 3.3 秒时显示 `-198S`。

应用有竖版 172×320 与横版 320×172 两套布局，用串口 `PERF PORTRAIT` /
`PERF LANDSCAPE` 切换。横版把 CPU 放左侧，MEM/GPU/NET 并排成仪表头，18 秒负载带
横贯底部；竖版保持原来的纵向构图。

物理屏幕固定 172×320（Waveshare ESP32-C6-LCD-1.47，ST7789）。应用进入前 5 秒没有数据时
使用内置演示数据，状态标为 `SIM`；收到第一帧合法串口帧后切到 `LIVE`。5 秒内没有新帧
标为 `LOST`，但保留最后一帧读数。没有触摸，页面/亮度由上位机控制；本应用只有一屏，
但可以在竖版与横版之间重建布局。

设计稿有横版独立页 `chip-adapt/esp32/design/perf-monitor-landscape.html`（320×172）
和竖版独立页 `perf-monitor-portrait.html`；`perf-monitor.html` 是可切换两版式的对照页。
LVGL 应用已同时实现两套布局。

## 文件

| 文件 | 作用 |
| --- | --- |
| `perf_monitor.c` | LVGL 界面、演示数据、串口帧应用、定时器 |
| `perf_monitor.h` | 应用入口与串口注入 API |
| `perf_protocol.c/.h` | 不依赖 LVGL 的行协议解析器 |
| `perf_font_*.h` | 内置转换器生成的 Bahnschrift / Consolas 字体 |
| `assets.json` | 字体生成记录，便于重放 |

## 串口协议

一条帧 = 一行 ASCII + LF。最大 320 字节。建议 115200 8N1，走 USB Serial/JTAG
或同一路 UART。PC 端按 0.3 秒节拍发送；采集变慢时应用会在底栏显示实测周期
（`USB · 3.3S`）。应用不要求 ACK，但固件壳可以回。

### 数据帧

```
PERF v=1 seq=842 cpu=47 gpu=28 mem=11500 memt=32768 freq=3480 temp=64 gtemp=54 down=12700 up=800 ping=15 time=2051 host=DESKTOP-01 th=12,45,...
```

- 首两个 token 必须是 `PERF v=1`。其余为 `key=value`，空格分隔。未知 key 忽略，
  便于以后扩展；重复 key 以后出现的值为准。
- 必填：`v`、`seq`、`cpu`。其余字段省略时使用默认值。
- 行尾允许多余空格、`\r`、`\n`。

| 字段 | 单位 / 范围 | 说明 |
| --- | --- | --- |
| `v` | 整数，固定 `1` | 协议版本 |
| `seq` | 0–65535 | 帧序号，回绕；用于 ACK 和丢帧判断 |
| `cpu` | 0–100 | CPU 总负载，整数百分比 |
| `gpu` | 0–100 | GPU 负载；省略表示不可用，屏幕显示 `--` |
| `mem` | MiB | 已用内存 |
| `memt` | MiB | 总内存；`mem`/`memt` 都为 0 时显示 `--` |
| `freq` | MHz | CPU 当前频率；省略或 0 显示 `--` |
| `temp` | °C，-1–150 | CPU 温度；省略显示 `--` |
| `gtemp` | °C，-1–150 | GPU 温度；省略显示 `--` |
| `down` | KiB/s | 下行吞吐；屏幕按 MiB/s 显示一位小数 |
| `up` | KiB/s | 上行吞吐；同上 |
| `ping` | ms，0–60000 | 网络延迟；省略显示 `--` |
| `time` | HHMM，0–2359 | PC 本地时间；省略显示 `--:--` |
| `host` | 最长 12 字符 | `[A-Za-z0-9._-]`，显示在顶栏；省略为 `DESKTOP` |
| `th` | 最多 16 个 0–100 整数 | 逗号分隔；不足 16 个补 0，超过拒绝 |
| `thn` | 1–16 | 有效线程柱数量；省略为 16。屏幕按它调整柱宽并隐藏多余槽位 |

### 命令

| PC → 设备 | 设备 → PC | 说明 |
| --- | --- | --- |
| `PERF HELLO` | `@PERF READY v=1 bars=16` | 握手/发现 |
| `PERF PING` | `@PERF PONG` | 链路探活 |
| `PERF DEMO` | `@PERF OK DEMO` | 强制回到演示数据 |
| `PERF LIVE` | `@PERF OK LIVE` | 清空链路状态，等待第一帧 |
| `PERF PORTRAIT` | `@PERF OK PORTRAIT` | 切到竖版 172×320 |
| `PERF LANDSCAPE` | `@PERF OK LANDSCAPE` | 切到横版 320×172 |
| 数据帧 | `@PERF OK seq=<n>` | 成功应用一帧 |
| 非法帧 | `@PERF ERR seq=<n|0> code=<bad-version|missing-field|bad-field|bad-value|too-long>` | 解析失败 |

ACK/READY/PONG 由固件壳根据 `perf_monitor_ingest()` 的返回值发送；应用本身只更新屏幕并
把事件写进 `engine.log`。PC 端可以完全不看 ACK。

### 固件壳接入

```c
/* UART/USB-Serial 接收任务：按行组装，行尾 '\n' 后调用。 */
if(perf_parse_starts_with_perf(line, len)) {
    lvgl_port_lock(0);
    perf_parse_result_t result = perf_monitor_ingest(line, len);
    lvgl_port_unlock();
    /* 由 shell 格式化 @PERF OK / @PERF ERR；seq 用 perf_monitor_last_seq()。 */
}
else {
    /* 继续交给 esp_console 或其他命令处理。 */
}
```

- `perf_monitor_ingest()` 只能从 LVGL 任务调用，或在外层加
  `lvgl_port_lock()/unlock()`。
- 解析器 `perf_protocol_parse()` 是纯 C、无 LVGL 依赖；如果 shell 想先拿 seq 做 ACK，
  可以自己调用它。
- 同一路 USB Serial/JTAG 上，`PERF` 行和现有 `pages` / `page` / `wifi` 命令可以共存：
  壳先按前缀分流。
- Arduino bring-up 固件同时监听 USB Serial 与 BLE（NUS）。命令从哪个通道来，ACK/READY/PONG
  就回到哪个通道；host 默认 BLE 连上优先、否则回退 UART。BLE 回调只组行入队，`loop()`
  才调用 `perf_monitor_ingest()`，因此 LVGL 仍只在主循环中访问。

## PC 端

`chip-adapt/esp32/host/perf/perf_agent.py` 是协议发送端。它**不直接打开 COM 口**，而是
走现有 ESP32 上位机的 `POST /api/send`，保持“一个串口 owner”的约束。

上位机还提供专用控制页 `http://127.0.0.1:8767/perf/`：可以在网页里启动/停止
Demo/Live 采集、调整发送周期、切换竖版/横版，并实时预览最新一帧。它同样只通过
`SerialBroker` 发送，不额外打开 COM 口。

```bash
# 先启动上位机并选好串口（fake 模式只验证发送路径，不会驱动屏幕）
python -I chip-adapt/esp32/host/host.py serve --port COMx --baud 115200

# 打印演示帧，不发送
python -I chip-adapt/esp32/host/perf/perf_agent.py --demo --dry-run --once

# 真实 Windows 采集，默认每 0.3 秒发送；先让屏幕切到横版
python -I chip-adapt/esp32/host/perf/perf_agent.py --layout landscape --live

# 没有板子/上位机时，只打印模拟帧
python -I chip-adapt/esp32/host/perf/perf_agent.py --demo --dry-run
```

Windows 采集使用 PowerShell/WMI 读取 CPU、内存、频率、每逻辑核负载与网卡累计字节；
GPU 优先 `nvidia-smi`，否则尝试 `Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine`。
CPU 温度没有稳定免依赖来源，通常显示 `--`。采集失败时 `--live` 会报错退出，不回退成
假数据。WMI 首次查询可能要几秒，之后每帧大约 3–4 秒；屏幕底栏会显示实测周期，
不是固定 0.3S。

## 本地 headless 验证

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 \
  --scenario user/scenarios/perf_monitor.json
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/perf_monitor_landscape.json
```

竖版场景按 172×320 启动应用，横版场景按 320×172 启动；应用按显示方向选择布局，各等
两秒截两张图。应用没有触摸交互；画面变化来自 0.3 秒一次的演示数据和虚拟时钟。
`PERF PORTRAIT` / `PERF LANDSCAPE` 会重建布局并调整 logical resolution；headless engine
的 full-frame 缓冲不适合在 172×320 场景里预览旋转后的像素，横版请用 320×172 场景。

## 边界

- 正式的 ESP32-C6 ESP-IDF 导出器和固件壳还没有实现（见
  `chip-adapt/esp32/README.md`）。临时的 Arduino 演示固件已可直接烧录：
  `chip-adapt/esp32/arduino/build.py`，适配原理见
  `chip-adapt/esp32/docs/arduino-perf-monitor.md`。
- 横版切换依赖 LVGL display rotation；接固件壳时确认 `esp_lvgl_port` 的 flush
  路径与 panel 旋转设置一致。headless 横版预览请直接用 320×172 场景。
- 屏幕没有触摸；本应用不创建按钮。
- 所有精确数值都在应用自己的 `printf` 里；工具没有对象树 / `inspect` / `set`。
- 字体只含 ASCII + `°·↑↓`。线程柱最多 16 条；PC 端用 `thn` 告诉屏幕实际逻辑核数，
  屏幕按数量调整柱宽并隐藏多余槽位。
