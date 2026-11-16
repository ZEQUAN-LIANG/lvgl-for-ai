# ESP32-C6 适配区

目标板：微雪 **ESP32-C6-LCD-1.47（无触摸，172×320，ST7789，4 MB Flash，无 PSRAM）**。
软件基线：ESP-IDF 5.5.x / LVGL 9.6 / `esp_lvgl_port` 2.9。

## 当前状态

| 区域 | 状态 | 说明 |
| --- | --- | --- |
| `host/` | 可运行原型 | 复用 SiFli host 的 `SerialBroker`；页面 + Wi-Fi + 蓝牙 + 串口 + 系统网页，CLI + fake backend |
| LVGL demo | 可运行 | `user/app/c6_demo/`，3 页，172×320，headless 场景 `user/scenarios/c6_demo.json` |
| Wi-Fi / 蓝牙配置 UI | 已实现 | 网页扫描/连接/开关/改名/可发现；串口协议见 `host/README.md` |
| 导出器 | 未实现 | 导出器与模板待补；见下方“固件侧待做” |
| ESP-IDF 固件壳 | 未实现 | 需要 `app_main.c` + ST7789 + `esp_lvgl_port` + `esp_console` 胶水 |
| 真机烧录 | 未验证 | 本机尚未安装 `idf.py` |

## 快速入口

```bash
# LVGL demo（headless，不需要板子）
python -I console/entrypoints/cli.py --lvgl 9.6 \
  --scenario user/scenarios/c6_demo.json --json

# 上位机（fake 串口，不需要板子）
python -I chip-adapt/esp32/host/host.py serve --fake --open
python -I chip-adapt/esp32/host/tests/run_tests.py

# 上位机（真机）
python -I chip-adapt/esp32/host/host.py serve --port COMx --baud 115200 --open
```

网页默认 `http://127.0.0.1:8767/`；页面列表来自固件，不在前端写死。

## 功能取舍

这一轮先做“能演示、能验证”的闭包：

- **保留**：页面切换、背光、Wi-Fi 扫描/连接/状态/自动连接、蓝牙开关/广播名/可发现/
  连接数、串口端口/波特率/自动重连/行尾/日志、系统信息/重置。
- **暂不做**：OTA、静态 IP/DNS、BLE 配对/绑定管理、设备端 Wi-Fi/蓝牙设置页。
  这些会显著增加固件状态机和内存占用；C6 只有 512 KB SRAM、无 PSRAM，Wi-Fi + BLE +
  LVGL 同时开要先用 `idf.py size` 和实测 heap 评估。
- **真实驱动**：网页和 host 协议已就绪；Wi-Fi 用 `esp_wifi`，蓝牙用 NimBLE
  (`esp_nimble`) 在 ESP-IDF 固件壳里实现，下一阶段做。

## 固件侧待做

1. 安装 ESP-IDF 5.5.x，跑通 `hello_world` 和 `esptool.py --chip esp32c6 flash_id`。
2. 新建 `chip-adapt/esp32/templates/` 与 `export.py`：ST7789 + `esp_lvgl_port` 的
   `app_main.c`，以及 `sdkconfig.defaults` / `partitions.csv` / `main/CMakeLists.txt`。
3. 加 `esp_console` 的 USB Serial/JTAG REPL，注册 `pages` / `page` / `state` / `ping`，
   调用 `user/app/c6_demo` 暴露的 `c6_demo_page_*` API。
4. 真机验证：网页按钮 -> 串口命令 -> 屏幕切页，保留串口日志与屏幕照片/录屏。
5. 再把 host 的 `idf.py build` / `flash` 后端接进来；烧录前 broker 释放 COM 口。

## 边界

- 不在 `chip-adapt/esp32/` 里再写一套串口客户端；host 复用 SiFli 的 broker。
- 网页不直接用 Web Serial 抢 COM 口；CLI、网页、AI 都走同一个 host。
- 不输出 pass/fail、baseline、approval、acceptance；只保留日志、响应和截图证据。
- 导出物放 `chip-adapt/exports/esp32/<app>/`，不进 Git。
