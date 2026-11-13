# ESP32-S3 LVGL 移植 · 下一阶段执行计划

> 状态：待执行（本阶段只做调研，未实现）
> 调研真源：`docs/research/esp32-lvgl-port.md`
> 目标平台：一体化 ESP32-S3 触摸屏开发板
> 默认板：Waveshare ESP32-S3-Touch-AMOLED-1.8（V2，368x448，CO5300 QSPI，8 MB PSRAM，16 MB Flash，CST820）
> 技术基线：ESP-IDF v6.1 / LVGL 9.6.0 / `esp_lvgl_port` 2.9.0 / `esp_lcd_co5300` 2.2.0 / `esp_lcd_touch` 1.2.1
> 已定决策：ESP32 专用 LVGL 9.6 API；导出目录采用加法式 `chip-adapt/exports/esp32/<app>/`；不改 SiFli 的 9.4 基线

## 0. 一句话结论

**可以做。** 软件路线没有硬阻塞：LVGL 以源码组件编进 ESP32-S3 的 app 镜像，`esp_lvgl_port` 负责 LVGL 任务、tick、锁、display/touch 注册，现有 `void <app>_create(void)` + `lv_screen_active()` 契约可直接复用。

真正的不确定性在硬件：整板型号、面板初始化、触摸驱动兼容性与 QSPI 带宽实测。

## 1. 目标与非目标

### 1.1 目标

1. 在 ESP32-S3 整板上点亮 LVGL 9.6，显示与触摸都由 `esp_lvgl_port` 接管。
2. 把 `user/app/<app>` 导出为自包含的 ESP-IDF 工程，构建、烧录、串口日志可复现。
3. 复用现有应用契约：应用入口仍是 `void <app>_create(void)`，不写 `main`、不碰构建。
4. 本地 headless 与 ESP32 目标共用 LVGL 9.6 基线，减少双基线差异。
5. 为后续 `chip-adapt/esp32/` 导出器与上位机建立可测试的骨架。

### 1.2 非目标

- 不引入 Arduino、PlatformIO、Zephyr、MicroPython 路线。
- 不默认兼容 SiFli 的 LVGL 9.4；同一应用要双端导出时另做应用变体。
- 不把 ESP-IDF、`managed_components/`、`build/` 提交进 Git。
- 不输出 pass/fail、baseline、approval、acceptance；工具只给证据，验收标准由人在聊天里给。
- 不追求 390x450 精确分辨率；现成一体化板没有这个分辨率，先接受 368x448 或 410x502。

## 2. 硬件选择

### 2.1 默认：Waveshare ESP32-S3-Touch-AMOLED-1.8（V2）

| 项 | 值 |
| --- | --- |
| SoC | ESP32-S3R8，8 MB PSRAM，16 MB Flash |
| 屏幕 | 1.8" AMOLED，368x448，CO5300，QSPI |
| 触摸 | CST820（BSP 用 CST816S 驱动，带 CO5300 X 偏移处理） |
| 板厂 BSP | `waveshare/esp32_s3_touch_amoled_1_8` 2.0.3 |
| BSP 适配层 | `espressif/esp_lvgl_port` ^2 |
| BSP 显示驱动 | `espressif/esp_lcd_co5300` ^2.0.3 |
| BSP 触摸驱动 | `esp_lcd_touch_cst816s` / `esp_lcd_touch_ft5x06` |

选它的理由：分辨率比例最接近黄山派 390x450，CO5300 与黄山派同控制器家族，板厂 BSP 已经把 `esp_lvgl_port`、CO5300、触摸和 LVGL 串好。

注意：1.8 有 V1（SH8601/FT3168）和 V2（CO5300/CST820）；2026-05-30 起出货切 V2，买板看背面标签。

### 2.2 备选

| 板型 | 取舍 |
| --- | --- |
| Waveshare ESP32-S3-Touch-AMOLED-2.06（410x502） | 竖屏比例更接近 390x450；但 BSP 2.0.0 源码仍用 SH8601 驱动，与产品页的 CO5300 不一致，买板后要确认驱动 IC |
| Waveshare ESP32-S3-Touch-AMOLED-1.75 / 2.16（466x466 / 480x480） | 有板厂 BSP，但用 `espressif/esp_lvgl_adapter`，不是 `esp_lvgl_port`；要统一到当前路线需改 BSP 或自己初始化 |
| Waveshare ESP32-S3-Touch-AMOLED-1.43（466x466 圆屏） | 圆表形态；无 BSP；FT3168/FT6146 混批，FT6146 兼容性未核实 |
| Espressif ESP32-S3-LCD-EV-Board（480x480 RGB） | 官方 `esp-bsp` 4.1.0，最稳；但 RGB 引脚多、要 PSRAM framebuffer，不是手表形态 |
| Guition JC3248W535（320x480 QSPI） | 性价比高；Espressif `esp_lcd_axs15231b` 2.1.1 官方驱动覆盖 LCD + 触摸，但无板级 BSP |

### 2.3 如果要精确 390x450

现成一体化板没有 390x450。只有两条路：

1. 定制 CO5300 QSPI 390x450 屏，自己接 DevKitC-1-N16R8 或自画板；面板初始化、gamma、亮度、TE 要按屏厂资料验证。
2. 接受 368x448 / 410x502，把应用布局按实际分辨率适配。

## 3. 阶段拆分

### M0 环境准备

任务：

- 用 EIM 安装 ESP-IDF v6.1（保守可退 v5.5.6）。
- 确认 `idf.py --version`、`idf.py set-target esp32s3` 可用。
- 跑通官方 `hello_world` 的 build / flash / monitor。

产出：

- 可用的 IDF 终端环境。
- `hello_world` 构建与串口日志。

证据：

- `idf.py --version` 输出。
- `build.log`、`flash.log`、串口启动日志。

### M1 最小点亮

任务：

- 基于 1.8 V2 板厂 BSP 或手写初始化：`lvgl_port_init` + panel + `lvgl_port_add_disp` + touch + `lvgl_port_add_touch`。
- 显示纯色/棋盘/渐变，确认颜色顺序、字节序、旋转、触摸坐标。
- 记录 QSPI 时钟、`lvgl_port_display_cfg_t` 的 buffer 配置、`idf.py size`。

产出：

- 最小 `app_main.c`。
- 屏幕点亮的串口日志与构建产物。

证据：

- `build.log`、串口日志。
- `idf.py size` / `idf.py size-components` 输出。
- 人工确认画面与触摸（必要时拍照或录屏，作为人类验收证据）。

### M2 应用适配

任务：

- 把 `sift_watch` 从 390x450 适配到目标分辨率（368x448 或 410x502）。
- 优先改布局参数，不做整体缩放；保持 `lv_canvas` 绘制路径。
- 本地 headless 用 LVGL 9.6 跑同一场景。

产出：

- 可编译的适配后应用源码。
- 本地 headless 会话。

证据：

- `python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch.json` 的 `manifest.json`：`status=ok`、`display=<目标宽高>`。
- `snapshots/` 与 `timeline.ndjson`。

### M3 导出器

任务：

- 新建 `chip-adapt/esp32/`：`export.py`、`layout.py`、`adapter.json`、`templates/`、`run_tests.py`。
- 生成自包含 ESP-IDF 工程到 `chip-adapt/exports/esp32/<app>/`。
- 按 LVGL 9.6 做 API 扫描；`assets.json` 的 `ezip` 模式给明确诊断，不生成会编译失败的工程。
- 复用 SiFli 的公共逻辑：源码读取/替换、注册表解析、错误类型。

产出：

- 导出器与模板。
- 契约测试（不依赖 ESP-IDF）。
- 导出 dry-run 结果。

证据：

- `python -I chip-adapt/esp32/run_tests.py`。
- `python -I chip-adapt/esp32/export.py <app> --dry-run --force` 的文件清单与 `export.json`。

### M4 上位机

任务：

- 新建 `chip-adapt/esp32/host/`（或把现有 SiFli host 抽象成多后端，二选一在下阶段定）。
- `build` 调 `idf.py build`，`flash` 调 `idf.py -p COMx -b 921600 flash`，`monitor` 复用现有 broker 读串口。
- 从环境继承 `IDF_PATH` / `IDF_TOOLS_PATH` / `PATH`，不硬编码 `C:\Espressif`。
- 只返回证据，不做 pass/fail 判定。

产出：

- host CLI / HTTP / 网页入口。
- fake `idf.py` 与 fake serial 测试。

证据：

- `python -I chip-adapt/esp32/host/tests/run_tests.py`。
- `build.log`、`flash.log`、串口日志。

### M5 真机验证

任务：

- 构建、烧录、串口监视。
- 记录资源占用与刷新表现。
- 用会话证据与串口日志交付，不写自动判定。

证据：

- `idf.py build` 成功输出。
- `idf.py size` 的 flash/RAM 占用。
- 串口日志与人工验收记录。

## 4. 仓库落点

```text
chip-adapt/
  esp32/                         # 自研适配层，进 Git
    export.py
    layout.py
    adapter.json
    templates/
    run_tests.py
    host/                        # 下阶段再定是否新建
  exports/
    esp32/<app>/                 # 生成物，不进 Git
      CMakeLists.txt
      sdkconfig.defaults
      sdkconfig.defaults.esp32s3
      partitions.csv
      main/
        CMakeLists.txt
        idf_component.yml
        app_main.c
        app/
          app.c
          lvgl_ai_esp.h
          assets.h / assets.c
          <app>/                 # 应用源码副本
      export.json
      README.md
  vendor/                        # 只读外部物；ESP-IDF 走 EIM 系统级安装
```

外部依赖：

- ESP-IDF：EIM 系统级安装，`IDF_PATH` / `IDF_TOOLS_PATH` 由环境提供。
- 组件：`managed_components/` 由 Component Manager 生成，不手改、不提交。

## 5. 关键契约

### 5.1 `app_main.c`

```c
#include "esp_lvgl_port.h"
#include "lvgl.h"

extern void app_create(void);

void app_main(void)
{
    const lvgl_port_cfg_t port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&port_cfg));

    /* 板级初始化：panel IO、panel、reset/init、背光、touch */
    /* lvgl_port_add_disp(...); lvgl_port_add_touch(...); */

    lvgl_port_lock(0);
    app_create();
    lvgl_port_unlock();
}
```

要点：

- `lvgl_port_init()` 内部会创建 `taskLVGL` 并调用 `lv_init()`，应用不要再调 `lv_init()`。
- `lv_timer_handler()` 由 `taskLVGL` 自动驱动，应用不要再写 `while (1)` 主循环。
- 所有 LVGL 调用都要在 `lvgl_port_lock(0)` / `lvgl_port_unlock()` 内。

### 5.2 `app/app.c`

```c
#include "lvgl_ai_esp.h"
#include "<app>/assets.h"

extern void <app>_create(void);

void app_create(void)
{
    app_assets_init();   /* 仅当生成资源层时存在 */
    <app>_create();
}
```

### 5.3 `lvgl_ai_esp.h`

用 `ESP_PLATFORM` 区分目标构建与本地 headless：

```c
#ifndef LVGL_AI_ESP_H
#define LVGL_AI_ESP_H

#if defined(ESP_PLATFORM)
#  include "lvgl.h"
#  include "esp_lvgl_port.h"
#else
#  include "sim_esp.h"
#endif

#endif
```

本地桩只用于验证，不代表真实显示/触摸行为。

## 6. 验证命令

```bash
# M0：环境
idf.py --version

# M1：目标与构建
idf.py set-target esp32s3
idf.py build
idf.py -p COMx -b 921600 flash monitor
idf.py size
idf.py size-components

# M2：本地 headless
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch.json

# M3：导出器（下阶段新建后）
python -I chip-adapt/esp32/run_tests.py
python -I chip-adapt/esp32/export.py sift_watch --dry-run --force
LVGL_AI_USER_APP_DIR="$PWD/chip-adapt/exports/esp32/sift_watch/main/app" \
  python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch.json

# M4：上位机（下阶段新建后）
python -I chip-adapt/esp32/host/tests/run_tests.py
python -I chip-adapt/esp32/host/cli.py build --app sift_watch --actor ai --json
```

## 7. 风险与待确认

| 项 | 状态 | 处理 |
| --- | --- | --- |
| 最终板型/版本 | 待确认 | 默认 1.8 V2；买板确认背面标签是 V2 |
| 2.06 的 BSP 驱动不一致 | 已发现 | BSP 2.0.0 源码用 SH8601，产品页写 CO5300；若选 2.06，面板初始化改用 `esp_lcd_co5300` |
| QSPI 能否稳定跑 80 MHz | 未核实 | 先按 40 MHz 跑通，再逐步升频；以实测为准 |
| 390x450@60 fps | 未核实 | 只有带宽估算；先接受局部刷新/较低帧率 |
| FT6146 触摸兼容性 | 未核实 | 要用 FT6146 时先做 I2C 读点验证，必要时自写驱动 |
| 资源 schema | 待定 | 现有 `assets.json` 的 `ezip|raw` 是 SiFli 语义；ESP32 先支持 `c_array`/`raw`，`ezip` 给诊断 |
| IDF 安装方式 | 待定 | 推荐 EIM 系统级；不把 IDF 放进仓库 |
| 上位机结构 | 待定 | 新建 `chip-adapt/esp32/host/` 还是抽象 SiFli host，下阶段决策 |
| 双目标导出 | 已定 | ESP32 专用 9.6；SiFli 9.4 另做应用变体 |

## 8. 不做什么

- 不把 `managed_components/`、`build/`、`sdkconfig` 提交进 Git。
- 不硬编码 `IDF_PATH`、COM 口、板级引脚到 Python 工具层。
- 不引入第二套协议客户端；网页、CLI、AI 共用同一套 Runtime / Recording / broker。
- 不在工具里输出 pass/fail、baseline、approval、acceptance。
- 不默认兼容 SiFli 9.4；需要双端时另做变体。
- 不在未确认板型前批量生成导出工程或写死引脚。

## 9. 执行顺序

1. 确认整板型号与版本（默认 1.8 V2）。
2. EIM 安装 ESP-IDF v6.1，跑通 `hello_world`。
3. 1.8 V2 最小点亮：LVGL + panel + touch，验证颜色/旋转/触摸。
4. 记录 `idf.py size` 与 QSPI/刷新实测。
5. 把 `sift_watch` 适配到实际分辨率。
6. 写 `chip-adapt/esp32/` 导出器与契约测试。
7. 写 host 的 build / flash / monitor。
8. 真机验证并保留构建、烧录、串口日志与会话证据。

## 10. 交接提示

- 版本与链接以 `docs/research/esp32-lvgl-port.md` 为准；本文件只保留执行计划。
- 1.8 V2 的板厂 BSP 2.0.3 已经把 `esp_lvgl_port`、`esp_lcd_co5300`、触摸和 LVGL 串好，是首板最低风险路径。
- 2.06 的 BSP 不要把「BSP 版本号」当成「面板驱动正确」；先确认驱动 IC。
- 1.75 / 2.16 的 BSP 用 `espressif/esp_lvgl_adapter`，不是 `esp_lvgl_port`；要统一路线需改 BSP 或自己初始化。
- 本阶段只调研，未实现；上表所有「待确认」项都需要先定硬件再动代码。
