# ESP32-C6 Arduino bring-up adapter

这是 `perf_monitor` 的**临时 Arduino 演示固件**生成器：把 `user/app/perf_monitor`
复制进一个自包含 sketch，带上 LVGL 9.6 和微雪 ST7789 驱动，用 `arduino-cli`
编译，再通过现有 ESP32 host 烧录。

固件同时支持 **USB 串口（UART）与 BLE** 两条控制通道：

- 设备上电默认广播 `LVGL-C6-PERF`，等待 BLE 连接；同时保留 USB 串口控制。
- BLE 使用 Nordic UART Service（NUS）UUID，行协议与串口相同。
- host 默认同时维护两条链路：BLE 连上时优先用 BLE，否则自动回退 UART。

正式的 ESP-IDF 导出器/固件壳仍未实现；这一层只用于把屏幕、LVGL 旋转、双通道控制
和横竖切换先跑通。详细原理与排障见
[`../docs/arduino-perf-monitor.md`](../docs/arduino-perf-monitor.md)。

## 前置

- Arduino CLI，已安装 `esp32:esp32` core 3.3.x
- `engine/lvgl/9.6/` 源码（`python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .`）
- `chip-adapt/vendor/esp32/demo/ESP32-C6-LCD-1.47-Demo.zip`（只取 ST7789 驱动）
- 烧录时先启动 host：`python -I chip-adapt/esp32/host/host.py serve --port COMx`
- Windows 下 `arduino-cli` 默认在 `C:\Program Files\Arduino CLI\`，也可设置
  `ARDUINO_CLI` 或用 `--arduino-cli`

## 命令

```bash
# 只生成 chip-adapt/exports/esp32/perf_monitor_arduino/（默认增量）
python -I chip-adapt/esp32/arduino/build.py export

# 生成 + 编译；默认复用 build/ 缓存，只重编改动文件
python -I chip-adapt/esp32/arduino/build.py build

# host 正在运行、串口已打开：通过 host 释放 COM 后烧录
python -I chip-adapt/esp32/arduino/build.py flash --port COM13

# 一步完成
python -I chip-adapt/esp32/arduino/build.py all --port COM13
```

常用参数：

- `--out DIR`：改变输出目录；默认 `chip-adapt/exports/esp32/perf_monitor_arduino/`
- `--dry-run`：只打印将写入的文件/将执行的命令
- `--json`：单行 JSON，便于 AI/CI 读取
- `--no-export`：`build` 时复用已有 sketch
- `--force`：清理 `perf_c6/`、`libraries/lvgl/`、`build/` 后全量重导/重编；默认不使用
- `--host-url`：host 地址，默认 `http://127.0.0.1:8767`
- `--fqbn`：默认 `esp32:esp32:esp32c6:CDCOnBoot=cdc,PartitionScheme=huge_app`

## 输出

```text
chip-adapt/exports/esp32/perf_monitor_arduino/
  perf_c6/                 # Arduino sketch，目录名必须与 .ino 同名
    perf_c6.ino
    ble_uart.h/.cpp        # NUS GATT + BLE 行队列
    lv_conf.h
    app.h                  # 把 app_obj_set_name/scrollable 适配到裸 LVGL
    perf_monitor.c/.h
    perf_protocol.c/.h
    perf_font_*.h          # 从 user/app 复制，include 路径已改写
    Display_ST7789.cpp/.h  # 从 vendor demo zip 提取
  libraries/lvgl/          # LVGL 9.6 精简副本（Arduino library 布局）
  build/                   # arduino-cli 输出，含 .merged.bin
```

## BLE 通道

| 项 | 值 |
| --- | --- |
| 设备名 | `LVGL-C6-PERF` |
| Service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX（host→设备，write） | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX（设备→host，notify） | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |
| MTU | 设备首选 256；按 `peer MTU - 3` 分块 |
| 行协议 | 与串口相同，`\n` 结尾，最长 320 字节 |

BLE 回调只把完整行放入 FreeRTOS 队列，`loop()` 才调用 `perf_monitor_ingest()`，
因此 LVGL 仍然只在 Arduino 主循环里被访问。USB 串口继续解析同一套行协议，作为
host 的回退通道。

`perf_c6/lv_conf.h` 使用 16 bpp、96 KB LVGL heap、partial render；`perf_c6.ino`
负责 172×320 ST7789 初始化、LVGL tick、USB Serial 行组装、软件旋转 flush 和
`SHOT` 灰度快照。源码内容未变时不会重写文件，`arduino-cli` 的 `build/` 缓存也保留，
所以默认路径是增量的。

## 边界

- 不改 `user/app`，不改 `engine/lvgl/<version>/`；所有生成物在 `exports/`。
- 不直接打开 COM；烧录沿用 host 的 flash job，串口仍只有一个 owner。
- Arduino 只用于 bring-up；正式 ESP-IDF 固件壳/导出器仍需另做。
