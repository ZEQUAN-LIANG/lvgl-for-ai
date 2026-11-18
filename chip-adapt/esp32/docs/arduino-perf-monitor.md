# ESP32-C6 · PERF TAPE Arduino 适配说明

本文记录 `perf_monitor` 在 Waveshare **ESP32-C6-LCD-1.47**（172×320，ST7789，
无触摸）上的临时 Arduino 适配。它是可烧录的 bring-up 固件，不是正式的 ESP-IDF
固件壳；正式壳仍按 `esp_lvgl_port` / `esp_console` 规划。

实机演示视频（无音频）：[`../../../docs/media/esp32-c6-perf-monitor.mp4`](../../../docs/media/esp32-c6-perf-monitor.mp4)。

生成与烧录入口：`chip-adapt/esp32/arduino/build.py`。

## 1. 硬件与引脚

| 项 | 值 |
| --- | --- |
| 屏幕 | 172×320，ST7789，无触摸 |
| SPI | SCLK=7，MOSI=6，MISO=5，CS=14，DC=15，RST=21 |
| 背光 | GPIO22，LEDC 1 kHz / 10 bit |
| 面板偏移 | `Offset_X=34`，`Offset_Y=0` |
| 方向 | ST7789 `MADCTL=0x00`，X 偏移 34；逻辑 172×320 |
| 板载 USB | USB Serial/JTAG（`CDCOnBoot=cdc`），COM13 示例 |

驱动来自微雪 demo 的 `Display_ST7789.cpp/.h`，构建脚本在 `export` 时从
`chip-adapt/vendor/esp32/demo/ESP32-C6-LCD-1.47-Demo.zip` 提取，不复制进 Git。

## 2. LVGL 9.6 配置

`arduino/templates/lv_conf.h` 的关键差异：

| 配置 | 值 | 原因 |
| --- | --- | --- |
| LVGL | 9.6.0 | 与 `user/app/perf_monitor` 的 API 门一致 |
| `LV_MEM_SIZE` | 96 KB | 对象 + 绘制层；C6 仍有约 127 KB 局部内存 |
| 颜色格式 | 显示端 `LV_COLOR_FORMAT_RGB565` | ST7789 16-bit |
| 渲染模式 | `LV_DISPLAY_RENDER_MODE_PARTIAL` | 不分配 110 KB 全屏缓冲 |
| 绘制缓冲 | `172 × 40 × 2 = 13,760 B` | 单缓冲，SPI 发送完再 `flush_ready` |
| `LV_DEF_REFR_PERIOD` | 33 ms | 屏幕刷新；数据 0.3 秒一帧 |
| `LV_USE_OS` | `LV_OS_NONE` | Arduino `loop()` 单线程 |
| 默认字体 | Montserrat 14 | 只是 LVGL 兜底；应用标签全部显式设字体 |
| `LV_USE_OBJ_NAME` | 0 | Arduino 适配层把 `app_obj_set_name()` 置空 |
| `LV_USE_DEMO_*` | 0 | 不链接 LVGL demo |

`perf_monitor.c` 的 canvas 仍是 RGB565；`s_cpu_fb`/`s_net_fb` 与 LVGL 绘制缓冲
互不影响。

## 3. 显示初始化与 flush

`perf_c6.ino` 做三件事：

```cpp
lv_display_t *disp = lv_display_create(172, 320);
lv_display_set_color_format(disp, LV_COLOR_FORMAT_RGB565);
lv_display_set_buffers(disp, s_draw_buf, NULL, sizeof(s_draw_buf),
                       LV_DISPLAY_RENDER_MODE_PARTIAL);
lv_display_set_flush_cb(disp, flush_cb);
```

`flush_cb` 分两步：

1. 若 `lv_display_get_rotation(disp) != 0`，用
   `lv_display_rotate_area()` 把逻辑区域映射到物理 172×320，再用
   `lv_draw_rotate()` 写入独立的 `s_rot_buf`；
2. 用 `LCD_SetCursor()` + `SPI.writeBytes()` 发送旋转后的物理区域。

关键点：**LVGL 9.6 的 `lv_display_set_rotation()` 只交换 logical resolution，
不会自己旋转像素**。第一版固件把 320×172 的逻辑区域直接写到 172×320 面板，
横版因此越界/花屏（“跑飞”）。修复后横竖都正确。

当前 `lv_conf.h` 里 `LV_DRAW_TRANSFORM_USE_MATRIX=0`，旋转由 flush 软件完成，
与 LVGL 官方 rotation 文档的 partial-mode 示例一致。若以后改用矩阵旋转，需要
同时开启 `LV_USE_MATRIX` / `LV_DRAW_TRANSFORM_USE_MATRIX` 并
`lv_display_set_matrix_rotation(disp, true)`，不要两套同时启用。

## 4. 内存与尺寸

最近一次 `arduino-cli compile`（core 3.3.10，C6）：

```text
Sketch uses 714044 bytes (22%) of program storage space.
Global variables use 200188 bytes (61%) of dynamic memory,
leaving 127492 bytes for local variables.
```

其中约：

- LVGL heap：96 KB
- `s_draw_buf`：13.7 KB
- `s_rot_buf`：16.5 KB
- `s_shadow`（`SHOT` 调试快照）：27.5 KB
- 应用静态 canvas：约 27 KB

C6 无 PSRAM，以上全部在 SRAM；如果以后加 Wi-Fi/蓝牙或更多 canvas，需要重新用
`idf.py size` / 实际 heap 评估。

## 5. USB Serial 与协议

`perf_c6.ino` 的 `loop()` 按行组装 USB Serial 输入：

- 最长 `PERF_PROTOCOL_MAX_LINE = 320` 字节；
- `\r` 忽略，`\n` 触发；
- 以 `PERF` 开头的行交给 `perf_monitor_ingest()`；
- `SHOT` 是调试命令，输出 4 bpp 灰度快照；
- 其他行忽略。

因此 host 的 `/perf/` 页面、`perf_agent.py --layout landscape` 和数据帧都能直接
驱动本固件。应用启动先进入 `SIM` 演示；收到 `PERF DEMO`/`PERF LIVE` 和第一帧
后切换状态。

### 5.1 UART + BLE 双通道

固件同时监听 USB Serial 与 BLE，回复发回命令来源通道：

- BLE 使用 Nordic UART Service：Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`，
  RX `6E400002-...`，TX `6E400003-...`；设备名 `LVGL-C6-PERF`。
- 上电后开始广播；连接后停止广播；断开约 500 ms 后重新广播。
- BLE `onWrite` 只把字节拼成完整行放入 FreeRTOS 队列，`loop()` 才调用
  `perf_monitor_ingest()`；BLE 任务不直接访问 LVGL。
- 设备按 `peer MTU - 3` 分块 notify；host 写入也按 MTU 分块，两侧都按 `\n` 组行。
- `PERF HELLO` 回复 `@PERF READY v=1 bars=16 mtu=<n>`；数据帧回复
  `@PERF OK seq=<n>`；`PERF PING` 回复 `@PERF PONG`。
- host 默认同时维护 UART 与 BLE：BLE 连上时优先 BLE，BLE 断开或未连接时自动
  回退 UART；USB 串口仍可作为控制通道和日志通道。
- BLE 依赖（`bleak`）由 `host/scripts/bootstrap.ps1` 安装到
  `host/vendor/ble`；host 用 `python -I` 运行时通过显式 `sys.path` 注入。

实机记录（2026-11-19）：板卡广播 `LVGL-C6-PERF`，Windows `bleak` 连接后 MTU 256，
`PERF HELLO` 收到 `@PERF READY v=1 bars=16 mtu=256`；`/perf/` Demo 帧逐帧收到
`@PERF OK seq=N`；启动日志 `heap after ble=157604`，`Global variables` 204796 B
（62%），仍有约 122 KB 静态余量。

排障：

| 现象 | 优先检查 |
| --- | --- |
| host 显示 `active=none` | PC 蓝牙是否开启；设备是否在广播；`ble_name` 是否匹配 |
| BLE 连上但命令超时 | 设备是否已订阅 TX；MTU 是否为 23；串口是否被其他程序占用 |
| BLE 断开后不恢复 | 看 `links.ble.last_error`；设备是否重新广播；Windows 蓝牙缓存 |
| 想强制走 UART | `serve --transport serial --serial-port COMx` 或 `--no-ble` |

## 6. 横竖切换

应用侧命令：

| 命令 | 行为 |
| --- | --- |
| `PERF PORTRAIT` | `lv_display_set_rotation(0)`，重建 172×320 布局 |
| `PERF LANDSCAPE` | `lv_display_set_rotation(90)`，重建 320×172 布局 |

屏幕物理仍是 172×320，横版时把板子转 90° 看。旋转本身在 `flush_cb` 完成，
应用只改 logical resolution 和布局。

## 7. SHOT 自检

没有相机时可用 `SHOT` 验证“实际送给屏幕的像素”：

```text
SHOT BEGIN 172 320 4
<430 行十六进制，每字节两个 4-bit 像素>
SHOT END
```

按物理 172×320 行优先排列。`chip-adapt/exports/esp32/perf_monitor_arduino/evidence/`
里有本次抓取的竖版和横版证据。横版物理图需要再旋转 90° 阅读。

## 8. 构建与烧录

```bash
# 生成（默认增量：只更新变化的文件）
python -I chip-adapt/esp32/arduino/build.py export

# 编译（默认增量：复用 build/ 缓存）
python -I chip-adapt/esp32/arduino/build.py build

# host 已运行并占用 COM13 时，走 host 释放串口 -> esptool -> 重连
python -I chip-adapt/esp32/arduino/build.py flash --port COM13

# 或一步完成
python -I chip-adapt/esp32/arduino/build.py all --port COM13
```

默认是增量构建：导出只改写内容变化的源码，`build/` 缓存会保留，`arduino-cli` 只重编
改动的文件。只有显式加 `--force` 才会清理 `perf_c6/`、`libraries/lvgl/` 和 `build/`，
做一次全量编译。

输出：

```text
chip-adapt/exports/esp32/perf_monitor_arduino/
  perf_c6/          # sketch；目录名必须与 .ino 同名
  libraries/lvgl/   # LVGL 9.6 Arduino library
  build/perf_c6.ino.merged.bin
```

## 9. 常见问题

| 现象 | 优先检查 |
| --- | --- |
| 横版花屏/内容超出屏幕 | `flush_cb` 是否调用 `lv_display_rotate_area` + `lv_draw_rotate`；不能直接把 320 宽逻辑区发给 172 宽面板 |
| 颜色整体偏蓝/偏红 | RGB565 字节序；先确认 ST7789 期望高字节在前，必要时改 `RGB565_SWAPPED` 或手动 swap |
| 白屏/黑屏但有串口日志 | 背光 GPIO22、SPI 引脚、`LCD_Init()`、`0x36` 方向/偏移 |
| 烧录 `port busy` | 不要直接抢 COM；用 host 的 `flash` job 释放串口 |
| 启动反复重启 | 看 USB Serial 启动日志；检查分区（`huge_app`）、堆和栈 |
| 页面能连但屏幕不动 | host 是否在发 `PERF v=1`；应用是否收到第一帧；`PERF LIVE` 状态 |

## 10. 边界

- 这是 Arduino bring-up，不包含正式 ESP-IDF export/template、`esp_lvgl_port`、
  `esp_console` 和 OTA。
- 不把 LVGL 或微雪驱动复制进 `user/app`；生成物在 `chip-adapt/exports/`，不进 Git。
- 不直接打开 COM；烧录统一走 host 的 flash job。
- 应用源码仍以 `user/app/perf_monitor/` 为唯一真源；构建脚本只复制并改写
  Arduino 的 `<lvgl.h>` include 路径。
