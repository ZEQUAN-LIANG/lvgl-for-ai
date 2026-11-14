# ESP32-S3 上把 LVGL 编译进固件：官方路线调研

> 调研日期：2026-11-13
> 目标平台：**ESP32-S3**（用户已确定）。
> 范围：ESP-IDF + LVGL 9.x + `esp_lvgl_port`；不涉及 Arduino、PlatformIO、Zephyr、MicroPython。
> 方法：只取 Espressif、LVGL 官方文档、GitHub 仓库与 ESP Component Registry 页面；Waveshare 板型取其官方文档/产品页与官方 BSP 仓库。版本号以抓取当日页面为准；无法从一手来源核实的，明确标注「未核实」。
> 已定决策：ESP32 导出按 **LVGL 9.6 专用 API**，不把 SiFli 9.4 兼容作为默认约束；硬件形态为**一体化 ESP32-S3 触摸屏开发板**（具体型号待定）。
> 当前阶段：用户只要求调研，未授权实现导出器/上位机；具体整板型号确认后再进入落地。

本文使用 `CONTEXT.md` 的术语：应用变体、真源、运行时、会话、导出。「芯片支持」指 SoC caps 与 ESP-IDF 驱动能力；「官方 BSP 支持」指 `esp-bsp` 仓库中已维护的板级组件。两者不是一回事，文中分开写。

---

## 1. 结论摘要

### 1.1 推荐路线

把 `user/app/<app>` 导出为自包含的 ESP-IDF 工程，LVGL 以**源码组件**编进 app 镜像：

```text
user/app/<app>/                       # 唯一源码真源
  └─ chip-adapt/esp32/export.py ──> chip-adapt/exports/esp32/<app>/
                                       ├─ idf.py set-target esp32s3
                                       ├─ idf.py build
                                       └─ idf.py -p COMx flash monitor
```

技术栈基线：

| 层 | 选择 | 说明 |
| --- | --- | --- |
| SoC | **ESP32-S3** | 双核 LX7，240 MHz，支持 SPI/QSPI、LCD_CAM 的 I80/RGB、PSRAM |
| SDK | ESP-IDF v6.1（当前 stable） | 保守可退到 v5.5.6 |
| 构建 | CMake + Ninja，由 `idf.py` 驱动 | 组件模型 |
| LVGL | `lvgl/lvgl` 9.6.0 | 与本地 headless 运行时的 9.6 一致 |
| 移植层 | `espressif/esp_lvgl_port` 2.9.0 | 任务、tick、锁、display/touch 注册 |
| 显示 | `esp_lcd` + 面板驱动组件 | SPI/QSPI 屏；RGB/I80 走 LCD_CAM |
| 触摸 | `espressif/esp_lcd_touch` 1.2.1 + 控制器组件 | I2C 触摸 |
| 依赖管理 | `idf_component.yml` + Component Manager | 依赖下载到 `managed_components/` |

### 1.2 默认推荐板型

**如果买现成集成屏板：Waveshare ESP32-S3-Touch-AMOLED-1.8（V2）。**

- 368x448 AMOLED，**CO5300 QSPI**，8 MB PSRAM，16 MB Flash，CST820 触摸。
- 屏幕控制器和黄山派同为 CO5300 家族，最接近“390x450 手表 UI”的形态。
- Waveshare 有官方 BSP 组件 `esp32_s3_touch_amoled_1_8` 2.0.3，依赖 `espressif/esp_lcd_co5300`、`esp_lcd_touch_cst816s`/`ft5x06`、`espressif/esp_lvgl_port`、`lvgl/lvgl`。
- 注意：Waveshare BSP 是**板厂官方**，不是 Espressif `esp-bsp` 官方；两者不要混写。

**如果必须精确 390x450：定制一体化板（屏 + 连接器/FPC + 驱动在同一 PCB），不是 DevKitC-1 裸板 + 外接屏。**

- 选 CO5300 QSPI 390x450 模组，做定制载板；PSRAM 8 MB 起步，16 MB 更稳。
- 需要屏厂初始化序列、QSPI 最高时钟、背光/TE、触摸 I2C 地址；CO5300 驱动组件已有，但模组参数要按屏厂资料验证。
- DevKitC-1 只作为芯片能力/引脚调试参考，不作为交付形态。

**如果限定 Espressif 官方 BSP：ESP32-S3-LCD-EV-Board（480x480 RGB，16 MB PSRAM）** 是最接近大屏 UI 的官方板；**M5Dial（240x240 圆形）** 是形态最接近手表的官方 BSP 板。两者都不是 390x450。

### 1.3 版本基线（2026-11-13 核实）

| 项 | 版本 | 核实来源与备注 |
| --- | --- | --- |
| ESP-IDF 当前 stable | **v6.1** | 文档 stable 指向 v6.1；GitHub release `v6.1` 发布于 2026-08-27 |
| ESP-IDF 最新 bugfix 发布 | **v5.5.6** | 2026-10-16 发布；属于 v5.5 维护线，不是当前 stable 文档线 |
| LVGL | **9.6.0** | GitHub release `v9.6.0` 发布于 2026-09-16 |
| `lvgl/lvgl` 组件 | **9.6.0\~1** | Component Registry；`~1` 是 Registry 的 downstream revision |
| `espressif/esp_lvgl_port` | **2.9.0** | Registry 页面；`idf >=5.2`，`lvgl/lvgl >=8,<10` |
| `espressif/esp_lvgl_adapter` | **0.7.8** | Registry 页面；另一条 LVGL 适配层，要求 IDF >=5.5.5；Waveshare 1.75/2.16 BSP 用 ~0.6 |
| `espressif/esp_lcd_touch` | **1.2.1** | Registry 页面 |
| `espressif/esp_lcd_co5300` | **2.2.0** | Registry 页面；要求 ESP-IDF >= 5.4 |
| `espressif/esp_lcd_jd9365` | **2.0.2** | Registry 页面；MIPI-DSI，要求 ESP-IDF >= 5.3 |
| `espressif/esp_lcd_gc9a01` | **2.0.4** | Registry 页面；SPI |
| `espressif/esp_lcd_ili9341` | **2.1.0** | Registry 页面；SPI |
| `espressif/esp_lcd_touch_ft5x06` | **1.1.1** | Registry 页面 |
| `espressif/esp-bsp` | 无统一版本号 | 各 BSP 组件独立版本；master README 声明支持 ESP-IDF 5.2–6.1 |

一个需要纠正的名称：Component Registry 里**没有** `espressif/lvgl`（抓取返回 404）。LVGL 的官方组件是 **`lvgl/lvgl`**，由 LVGL 组织发布。

关于「LVGL 9.x 的官方 ESP 移植是否已稳定」：LVGL 官方集成文档把 `esp_lvgl_port` 作为推荐路径，组件 README 明确写 “fully compatible with LVGL version 9”，LVGL 9.6 也已在 Registry 发布。可以认为 **LVGL 9 的 ESP-IDF 主路径已经稳定**；但 PPA draw unit 被 LVGL 官方标为 experimental（而且 S3 没有 PPA），LVGL 9.6 + ESP-IDF 6.1 是较新的组合，首板仍要留实测时间。

### 1.4 ESP32-S3 能力一句话

- 显示接口：SPI/QSPI、LCD_CAM 的 **I80（8/16 位）** 和 **RGB（8/16/24 位）**；**没有 MIPI-DSI**。
- PSRAM：支持 Quad/Octal SPI PSRAM，DevKitC-1 档位为 0 / 2 / 8 / 16 MB。
- 2D 加速：**没有 PPA，也没有 DMA2D**；LCD_CAM 是显示/摄像头控制器，不是 2D 加速器。LVGL 走软件绘制。
- DMA：SPI2/SPI3 有 SPI DMA；LCD_CAM 的 RGB/I80 走 GDMA/EDMA；PSRAM 与 flash 共用 MSPI 总线。
- LVGL 基线：ESP32 导出按 **9.6 专用 API**；不默认兼容 SiFli 9.4。需要双端导出时另做应用变体。

### 1.5 最大风险

1. **390x450 + SPI 的带宽不够**：40 MHz SPI 理论 5 MB/s，全屏 60 fps 需要 21.1 MB/s；必须用 QSPI、RGB 或 I80，或者接受局部刷新/低帧率。
2. **390x450 CO5300 模组没有官方 BSP**：驱动组件有，但具体初始化序列、gamma、亮度、TE、QSPI 最高时钟要按屏厂资料验证。
3. **S3 没有 PPA**：黄山派上靠 EPIC 做的旋转/缩放，在 S3 上退回软件绘制；大图旋转会明显掉帧。
4. **触摸 FT6146 未核实**：Espressif 官方只有 `esp_lcd_touch_ft5x06` 1.1.1，页面只写 FT5x06；FT6146 能否直接复用未核实。
5. **双目标 LVGL 基线已定**：ESP32 导出按 LVGL 9.6 专用 API；同一应用若要导出 SiFli（9.4），需要单独的应用变体或另行保持 9.4，不把 9.4 兼容当作 ESP32 导出器的默认要求。

---

## 2. ESP-IDF 构建体系与「LVGL 如何进固件」

### 2.1 项目与组件模型

ESP-IDF 项目是一个或多个 **component** 的集合，加上一个特殊的 `main` component、`sdkconfig`、顶层 `CMakeLists.txt` 和分区表。构建系统在 `IDF_PATH/components`、项目 `components/`、`managed_components/` 等目录里查找组件，每个组件用自己的 `CMakeLists.txt` 调 `idf_component_register()` 注册源文件和依赖。

最小项目：

```cmake
cmake_minimum_required(VERSION 3.22)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(<app>)
```

最小组件：

```cmake
idf_component_register(
    SRCS "foo.c" "bar.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_lcd
)
```

`main` 是特殊组件：它自动依赖构建中的所有组件，所以应用代码放在 `main/` 时通常不需要显式写 `REQUIRES`。`idf_component_register()` 还支持 `EMBED_FILES` / `EMBED_TXTFILES` 把二进制或文本文件嵌进 `.rodata`，以及 `REQUIRED_IDF_TARGETS` 限定目标芯片。

关键事实：

- 一个项目只有一个 `sdkconfig`；`idf.py set-target` 会清空 build 目录并重建 `sdkconfig`。
- 顶层 `CMakeLists.txt` 必须先 `cmake_minimum_required(VERSION 3.22)`，再 `include($ENV{IDF_PATH}/tools/cmake/project.cmake)`，最后 `project(...)`。
- 源文件编译成组件静态库，最终链接进 app 镜像。LVGL 也是这个路径，不是预编译库。
- 构建系统会在编译命令里定义 `ESP_PLATFORM`，可用于区分 ESP-IDF 构建和本地 headless 构建。

来源：[ESP-IDF Build System](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/build-system.html)

### 2.2 `idf_component.yml` 与 Component Manager

`idf_component.yml` 放在组件根目录，描述组件元数据和依赖。项目通过 `main/idf_component.yml` 声明第三方依赖，Component Manager 在构建时下载到 `managed_components/<namespace>__<name>/`，并生成 `dependencies.lock`。`dependencies.lock` 由工具自动生成/更新，不应手改。

版本格式：

```text
major.minor.patch~revision-prerelease+build
```

其中 `~revision` 是 downstream revision，用于「主要依赖上游包，只改下游打包/代码」的情况。因此 `lvgl/lvgl` 的 `9.6.0~1` 表示上游 LVGL 9.6.0 的第 1 个 Registry revision，不是另一个 LVGL 版本。

依赖示例（S3 + CO5300 QSPI）：

```yaml
dependencies:
  idf: ">=5.4"
  lvgl/lvgl: "~9.6.0"
  espressif/esp_lvgl_port: "^2.9.0"
  espressif/esp_lcd_touch: "^1.2.1"
  espressif/esp_lcd_co5300: "^2.2.0"
  espressif/esp_lcd_touch_cst816s: "^1.1.1~1"
```

如果是 ST7789/GC9A01/ILI9341，把 CO5300/CST816S 换成对应组件；ST7789 和 SSD1306 是 ESP-IDF 内置驱动，不需要额外组件。

也可以在命令行添加：

```bash
idf.py add-dependency "espressif/esp_lvgl_port^2.9.0"
```

来源：[IDF Component Manager manifest](https://docs.espressif.com/projects/idf-component-manager/en/latest/reference/manifest_file.html)、[Versioning](https://docs.espressif.com/projects/idf-component-manager/en/latest/reference/versioning.html)、[Build System](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/build-system.html)

### 2.3 `sdkconfig` 与 `sdkconfig.defaults`

- `sdkconfig` 是当前配置值，由 `idf.py menuconfig` 生成/修改，不要手改。
- `sdkconfig.defaults` 是用户默认值，格式和 `sdkconfig` 一样，每行 `CONFIG_NAME=value`。
- `sdkconfig.defaults.<chip>` 只对指定目标生效，例如 `sdkconfig.defaults.esp32s3`；**前提是同时存在 `sdkconfig.defaults`**，后者可以是空文件。
- `idf.py save-defconfig` 可以把当前 menuconfig 中与默认值不同的项导出成 `sdkconfig.defaults`。

对导出器的含义：模板只生成 `sdkconfig.defaults` / `sdkconfig.defaults.esp32s3`，不生成 `sdkconfig`；`sdkconfig` 让首次构建在现场生成。

来源：[Configuration File Structure](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/kconfig/configuration_structure.html)

### 2.4 Windows 安装与 shell 环境

当前 v6.1 文档的官方 Windows 安装方式是 **EIM（ESP-IDF Installation Manager）**：

- GUI 或 CLI：`winget install Espressif.EIM` / `winget install Espressif.EIM-CLI`
- 非交互安装：`eim install`
- 交互式选择版本：`eim wizard`，或 `eim install -i v5.4.2`
- 安装完成后，用 EIM 的 `Open IDF Terminal`，或桌面上的 `IDF_vX.Y.Z_Powershell` 快捷方式打开已激活环境；之后所有 `idf.py` 命令都在这个终端里跑。

前置要求：Git、Python 3.10+；ESP-IDF 和项目路径不能含空格，也不建议含非 ASCII 字符。

底层工具安装器是 `tools/idf_tools.py`：`install` 负责下载/解压工具，`export` 负责输出需要设置的环境变量；工具默认装在 `IDF_TOOLS_PATH`，未设置时是 `%USERPROFILE%\.espressif`。EIM 和旧的 `export.bat` 都会调用它；日常用 EIM 终端即可，不需要手工执行 `idf_tools.py`。

旧版 v5.5 文档使用的是 ESP-IDF Tools Installer，并通过 `export.bat` 设置 `PATH`、`IDF_PATH` 等环境变量。v6.1 的 Windows 安装页只描述 EIM，未出现 `install.bat` / `export.bat` 的说明；如果网上教程还在讲 `install.bat`，那是更旧的流程，不能作为 v6.1 的安装依据。

来源：[Windows Setup v6.1](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html)、[Start a Project on Windows](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-start-project.html)、[Windows Setup v5.5](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/get-started/windows-setup.html)、[Downloadable IDF Tools](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/idf-tools.html)

### 2.5 `idf.py build|flash|monitor`

`idf.py` 是 CMake、Ninja、esptool 的前端：

```bash
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py -p COMx -b 921600 flash
idf.py -p COMx monitor
```

- 未指定目标时默认 `esp32`；建议在 `sdkconfig.defaults` 里写 `CONFIG_IDF_TARGET="esp32s3"`，或用 `idf.py set-target esp32s3`。
- `idf.py flash` 会自动先构建；`-p` 指定串口，`-b` 指定烧录波特率。
- `idf.py monitor` 启动 IDF Monitor；退出是 `Ctrl+]`，菜单是 `Ctrl+T`。
- `idf.py size` / `idf.py size-components` 可以看 flash/RAM 占用，适合做资源预算。
- `idf.py merge-bin` 可以生成单个合并镜像，便于量产/转交。

来源：[IDF Frontend - idf.py](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/idf-py.html)

### 2.6 LVGL 组件如何编译进 app 镜像

LVGL 通过 Component Registry 的 `lvgl/lvgl` 组件进入项目。它的 `env_support/cmake/esp.cmake` 做了这些事：

```cmake
file(GLOB_RECURSE SOURCES ${LVGL_ROOT_DIR}/src/*.c ${LVGL_ROOT_DIR}/src/*.cpp)
idf_component_register(
    SRCS ${SOURCES} ...
    INCLUDE_DIRS ${LVGL_ROOT_DIR} ${LVGL_ROOT_DIR}/src ...
    PRIV_REQUIRES esp_timer log)
target_compile_definitions(${COMPONENT_LIB} PUBLIC "-DLV_CONF_INCLUDE_SIMPLE")
```

也就是说：

- LVGL 的**全部源码**被 glob 进来，编译成组件静态库，再链接进 app 镜像；不是 `.a` 预编译库。
- `LV_CONF_INCLUDE_SIMPLE` 是 PUBLIC 定义，所有依赖 LVGL 的组件都会看到。
- 如果 IDF 里有 `esp_driver_ppa`（5.3+），LVGL 会把它加入私有依赖，供 `LV_USE_PPA` 使用；S3 没有 PPA，这段不会带来加速。
- 如果启用 `LV_USE_FS_FATFS`，构建会要求 `main/CMakeLists.txt` 里显式依赖 `fatfs`。

Component Manager 下载的组件源码在 `managed_components/lvgl__lvgl/`，和项目源码一起参与编译。导出目录是自包含的：只要 `idf_component.yml` 和网络/缓存可用，`idf.py build` 会自行拉取 LVGL。

来源：[lvgl/lvgl esp.cmake](https://github.com/lvgl/lvgl/blob/master/env_support/cmake/esp.cmake)、[lvgl/lvgl idf_component.yml](https://github.com/lvgl/lvgl/blob/master/idf_component.yml)

### 2.7 `lv_conf.h` 与 Kconfig

这是 ESP-IDF 集成里最容易搞混的一点：

- LVGL 的 `Kconfig` 里 `config LV_CONF_SKIP` **默认是 y**，含义是「不包含 `lv_conf.h`，配置来自 Kconfig 树和内置默认值」。
- `lv_conf_internal.h` 在 `!LV_CONF_SKIP` 时才去找 `lv_conf.h`；`LV_CONF_INCLUDE_SIMPLE` 让它 `#include "lv_conf.h"`。
- ESP-IDF 构建默认走 Kconfig：`CONFIG_LV_*` 由 `lv_conf_kconfig.h` 映射成 `LV_*`。所以**默认不需要也不应该**在导出工程里放 `lv_conf.h`。
- 如果确实要手写 `lv_conf.h`，需要 `CONFIG_LV_CONF_SKIP=n`，并把 `lv_conf.h` 放到 include 路径上；此时 `LV_CONF_INCLUDE_SIMPLE` 已经由 `esp.cmake` 定义。
- 常用配置项在 menuconfig 的 `Component config -> LVGL configuration` 下；写进 `sdkconfig.defaults` 的典型项见 6.4。

来源：[LVGL v9.6.0 Kconfig](https://github.com/lvgl/lvgl/blob/v9.6.0/Kconfig)、[lv_conf_internal.h](https://github.com/lvgl/lvgl/blob/v9.6.0/include/lvgl/config/lv_conf_internal.h)、[LVGL ESP32 集成文档](https://lvgl.io/docs/open/integration/chip_vendors/espressif/add_lvgl_to_esp32_idf_project)

### 2.8 ESP-IDF 版本与 ESP32-S3 支持范围

事实：

- ESP-IDF 当前 stable 是 **v6.1**；抓取当日最新 bugfix 是 **v5.5.6**。两条线都支持 ESP32-S3。
- `esp_lvgl_port` 2.9.0 的组件清单要求 **`idf >=5.2`**。
- `esp-bsp` master 的兼容表覆盖 **ESP-IDF 5.2–6.1**，4.x 不支持。
- `esp_lcd_co5300` 2.2.0 要求 **ESP-IDF >= 5.4**；`esp_lcd_jd9365` 2.0.2 要求 >= 5.3。
- LVGL 9.6.0 组件没有显式 IDF 下限，但实际组合要以 `esp_lvgl_port` 和面板驱动的约束为准。

推荐组合：

| 场景 | ESP-IDF | LVGL | esp_lvgl_port | 面板/触摸组件 |
| --- | --- | --- | --- | --- |
| 首选（新项目） | v6.1 | 9.6.0 | 2.9.0 | `esp_lcd_co5300` 2.2.0 + `esp_lcd_touch_cst816s` 1.1.1 或 `esp_lcd_touch_ft5x06` 1.1.1 |
| 保守（已验证生态） | v5.5.6 | 9.6.0 | 2.9.0 | 同上 |
| 最低组合（仅 ST7789/GC9A01/ILI9341） | v5.2 | 9.6.0 | 2.9.0 | 内置 ST7789，或 GC9A01 2.0.4 / ILI9341 2.1.0 |
| 使用 CO5300 QSPI | >=5.4 | 9.6.0 | 2.9.0 | `esp_lcd_co5300` 2.2.0 |

说明：

- LVGL 集成页写 `esp_lvgl_port` 支持 IDF 4.4+，但当前组件 2.9.0 的 `idf_component.yml` 写 `idf >=5.2`；以组件清单为准，**不要低于 5.2**。
- `esp_lvgl_port` 2.7.1 的 changelog 有 “Fixed PPA rotation for IDF6”，2.8.0 支持按 `SOC_*` 选择 RGB/MIPI-DSI，2.9.0 修复 DPI 回调；这说明它有 IDF 6 适配，但首次在 v6.1 上构建仍要留排错时间。
- IDF 6.x 引入了 `IDF_BUILD_V2` 这条构建分支；`esp_lvgl_port` 有 `CMakeLists_v2.txt` 适配。第三方 BSP/驱动未必都适配，选板时要确认。

来源：[ESP-IDF Releases](https://github.com/espressif/esp-idf/releases)、[esp_lvgl_port idf_component.yml](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/idf_component.yml)、[esp-bsp README](https://github.com/espressif/esp-bsp/blob/master/README.md)、[esp_lcd_co5300 Registry](https://components.espressif.com/components/espressif/esp_lcd_co5300)、[esp_lvgl_port Changelog](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/CHANGELOG.md)

---

## 3. LVGL + `esp_lvgl_port` 集成结构

### 3.1 `esp_lvgl_port` 解决什么

`espressif/esp_lvgl_port` 是 Espressif 维护的 LVGL 移植层，源码在 `esp-bsp` 仓库的 `components/esp_lvgl_port/`，Registry 版本 2.9.0。它负责：

- 初始化 LVGL，创建 LVGL 任务和 tick 定时器；
- 添加/移除 display（基于 `esp_lcd`）；
- 添加/移除 touch（基于 `esp_lcd_touch`）；
- 添加/移除按键、编码器、USB HID 鼠标/键盘；
- 屏幕旋转（软件旋转，P4 可用 PPA；S3 只能软件）；
- 电源管理（stop/resume、任务休眠）；
- 线程安全的 `lvgl_port_lock/unlock`。

它支持 LVGL 8 和 LVGL 9：CMake 根据 LVGL 版本选择 `src/lvgl8/` 或 `src/lvgl9/`，LVGL 8 用 `esp_lvgl_port_compatibility.h` 做类型兼容。LVGL 官方文档明确推荐它作为 ESP32 上连接输入/输出设备的方式。

来源：[esp_lvgl_port README](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/README.md)、[Registry 页面](https://components.espressif.com/components/espressif/esp_lvgl_port)

### 3.2 源码结构与版本选择

```text
components/esp_lvgl_port/
  CMakeLists.txt            # 根据 LVGL 版本选 lvgl8/lvgl9，按依赖裁剪功能
  idf_component.yml         # idf >=5.2, lvgl/lvgl >=8,<10
  Kconfig                   # 只有 CONFIG_LVGL_PORT_ENABLE_PPA
  include/
    esp_lvgl_port.h
    esp_lvgl_port_disp.h
    esp_lvgl_port_touch.h
    esp_lvgl_port_button.h
    esp_lvgl_port_knob.h
    esp_lvgl_port_usbhid.h
    esp_lvgl_port_compatibility.h
  src/
    lvgl9/*.c
    lvgl8/*.c
    common/ppa/lcd_ppa.c
```

版本选择逻辑在 `CMakeLists.txt`：从 build components 里判断 `lvgl` 是本地组件还是 `lvgl__lvgl` 托管组件，再取版本；`<9.0.0` 用 `lvgl8/`，否则用 `lvgl9/`。所以 `esp_lvgl_port` 2.9.0 可以同时服务 LVGL 8 和 9，但 LVGL 9 是当前主路径。

来源：[esp_lvgl_port CMakeLists.txt](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/CMakeLists.txt)

### 3.3 主要 API

| API | 作用 |
| --- | --- |
| `lvgl_port_init(const lvgl_port_cfg_t *cfg)` | 初始化 LVGL、创建任务、tick 定时器、互斥锁、事件组 |
| `lvgl_port_add_disp(const lvgl_port_display_cfg_t *cfg)` | 添加 SPI/I2C/I80 等通用 display |
| `lvgl_port_add_disp_rgb(...)` | 添加 RGB display |
| `lvgl_port_add_disp_dsi(...)` | 添加 MIPI-DSI display（S3 不支持） |
| `lvgl_port_add_touch(const lvgl_port_touch_cfg_t *cfg)` | 添加触摸输入 |
| `lvgl_port_lock(timeout_ms)` / `lvgl_port_unlock()` | 取/放 LVGL 递归互斥锁；`0` 表示无限等待 |
| `lvgl_port_stop()` / `lvgl_port_resume()` | 停止/恢复 LVGL timer，配合 light-sleep |
| `lvgl_port_task_wake(event, param)` | 从 ISR 或其它任务唤醒 LVGL 任务 |
| `lvgl_port_flush_ready(disp)` | 在 port 之外手动通知 flush 完成 |

`lvgl_port_cfg_t` 默认值（`ESP_LVGL_PORT_INIT_CONFIG()`）：

```c
{
    .task_priority = 4,
    .task_stack = 7168,
    .task_affinity = -1,
    .task_max_sleep_ms = 500,
    .task_stack_caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_DEFAULT,
    .timer_period_ms = 5,
}
```

来源：[esp_lvgl_port.h](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/include/esp_lvgl_port.h)

### 3.4 初始化顺序

`lvgl_port_init()` 的实际行为（源码）：

1. 创建 timer mutex、LVGL recursive mutex、event group。
2. 创建 `taskLVGL` 任务（默认优先级 4，栈 7168，可绑核）。
3. 等待任务通知，确认 `lv_init()` 已完成。
4. 任务里调用 `lv_init()`，创建 `esp_timer` 周期定时器，每 `timer_period_ms` 调 `lv_tick_inc()`。
5. 任务循环等待事件或超时，拿锁后调用 `lv_timer_handler()`；有触摸/编码器事件时先读 `lv_indev`。

所以应用侧的顺序是：

```c
void app_main(void)
{
    const lvgl_port_cfg_t cfg = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&cfg));

    /* 1. 初始化总线：SPI / I2C / RGB / I80 */
    /* 2. 创建 panel IO 和 panel driver，reset/init，开背光 */
    /* 3. 添加 display */
    lv_display_t *disp = lvgl_port_add_disp(&disp_cfg);

    /* 4. 创建 touch driver，添加触摸 */
    lv_indev_t *touch = lvgl_port_add_touch(&touch_cfg);

    /* 5. 应用 UI 必须在锁内创建 */
    lvgl_port_lock(0);
    app_create();
    lvgl_port_unlock();
}
```

注意：`app_create()` 内部用 `lv_screen_active()` 取屏幕，这点和 SiFli 导出的入口一致；区别只是 SiFli 由 `littlevgl2rtt_init()` 完成显示/触摸注册，ESP32 由 `lvgl_port_init()` + `lvgl_port_add_disp()` + `lvgl_port_add_touch()` 完成。

### 3.5 主循环与 SiFli `main.c` 的对应

SiFli 模板 `src/main.c`：

```c
littlevgl2rtt_init("lcd");
app_create();
while (1) {
    rt_uint32_t ms = lv_task_handler();
    rt_thread_mdelay(ms);
}
```

ESP32 对应关系：

| SiFli | ESP32 |
| --- | --- |
| `littlevgl2rtt_init("lcd")` | `lvgl_port_init()` + `lvgl_port_add_disp()` + `lvgl_port_add_touch()` |
| `app_create()` | `app_create()`（锁内） |
| `while (1) { lv_task_handler(); delay; }` | `esp_lvgl_port` 的 `taskLVGL` 后台任务自动跑 `lv_timer_handler()` |
| `lv_task_handler()` 返回延时 | `lv_timer_handler()` 返回值决定任务等待时长，空闲时睡到 `task_max_sleep_ms` |

因此 ESP32 的 `app_main()` 不应该再写 `while (1) lv_timer_handler()`；那会和 `esp_lvgl_port` 的任务重复驱动 LVGL。应用只需要在锁内操作 UI。

### 3.6 flush 与触摸回调路径

**Display flush**（`esp_lvgl_port_disp.c`）：

```c
static void lvgl_port_flush_callback(lv_display_t *drv, const lv_area_t *area, uint8_t *color_map)
{
    ...
    esp_lcd_panel_draw_bitmap(disp_ctx->panel_handle,
                              offsetx1, offsety1, offsetx2 + 1, offsety2 + 1,
                              color_map);
}
```

- 对 SPI/QSPI/I80 面板：`lvgl_port_add_disp()` 给 panel IO 注册 `on_color_trans_done` 回调，回调里 `lv_disp_flush_ready()`；所以 `lvgl_port_flush_callback` 本身不在 SPI 上同步等待。
- 对 RGB 面板：注册 `on_vsync`（或 bounce buffer 的 `on_bounce_frame_finish` / `on_frame_buf_complete`）回调。
- 对 MIPI-DSI：注册 `on_color_trans_done` 或 `on_frame_buf_complete`（`avoid_tearing` 时）；S3 没有 DSI，这条不适用。
- `direct_mode` / `full_refresh` 只对 RGB/DSI 有意义，flush 时整屏 `esp_lcd_panel_draw_bitmap()`。

**Touch**（`esp_lvgl_port_touch.c`）：

```c
esp_lcd_touch_read_data(touch_ctx->handle);
esp_lcd_touch_get_data(touch_ctx->handle, touch_data, &touch_cnt,
                       CONFIG_ESP_LCD_TOUCH_MAX_POINTS);
```

- 有中断引脚时，touch 驱动注册中断回调，回调里 `lvgl_port_task_wake(LVGL_PORT_EVENT_TOUCH, ...)`，LVGL 任务随后读点；`lv_indev` 设为 `LV_INDEV_MODE_EVENT`。
- 无中断引脚时走轮询，由 LVGL 任务周期读取。
- 触摸坐标和屏幕分辨率不一致时，用 `lvgl_port_touch_cfg_t.scale.x/y` 缩放。

### 3.7 锁与线程模型

- `lvgl_port_lock()` 是**递归互斥锁**，`timeout_ms=0` 表示无限等待。
- 所有 LVGL 调用都必须在锁内；`lvgl_port_add_disp()` / `lvgl_port_add_touch()` 内部会自己加锁，但应用创建 UI、改控件、读状态时必须显式 `lvgl_port_lock(0) ... lvgl_port_unlock()`。
- 只有一个 LVGL 任务在跑 `lv_timer_handler()`；不要在应用里再起第二个 LVGL 任务。
- 触摸中断只做唤醒，不在 ISR 里碰 LVGL。

来源：[esp_lvgl_port.c](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/src/lvgl9/esp_lvgl_port.c)、[esp_lvgl_port_disp.c](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/src/lvgl9/esp_lvgl_port_disp.c)、[esp_lvgl_port_touch.c](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/src/lvgl9/esp_lvgl_port_touch.c)

---

## 4. ESP32-S3 的显示接口、DMA 与 PSRAM

### 4.1 显示接口能力

ESP32-S3 的 `esp_lcd` 支持以下路径：

| 接口 | 驱动入口 | S3 支持 | 说明 |
| --- | --- | --- | --- |
| SPI | `esp_lcd_new_panel_io_spi()` | 是 | GPSPI（SPI2/SPI3），支持 SPI/QSPI/Octal SPI 模式 |
| I80（8080） | `esp_lcd_new_i80_bus()` + `esp_lcd_new_panel_io_i80()` | 是 | LCD_CAM；`bus_width` 只支持 8 或 16 |
| RGB | `esp_lcd_new_rgb_panel()` | 是 | LCD_CAM；`data_width` 8/16/24 |
| I2C | `esp_lcd_new_panel_io_i2c()` | 是 | 小 OLED，不适合 390x450 |
| MIPI-DSI | `esp_lcd_new_dsi_bus()` | **否** | S3 SoC caps 没有 `SOC_MIPI_DSI_SUPPORTED` |

SPI 的关键点：

- `esp_lcd_panel_io_spi_config_t::flags` 里有 `quad_mode` 和 `octal_mode`，分别对应 4 线和 8 线；CO5300 的 QSPI 宏就是 `quad_mode = true`。
- `lcd_cmd_bits` / `lcd_param_bits` 是面板相关：ST7789 常见 8/8；CO5300 QSPI 是 32/8。
- `pclk_hz` 是 SPI 时钟；ESP-IDF 频率枚举提供 `SPI_MASTER_FREQ_40M` 和 `SPI_MASTER_FREQ_80M`，实际可用时钟受屏、FPC、PCB 限制。Waveshare 1.28 的官方文档标称其 SPI 可到 80 MHz。
- `max_transfer_sz` 要至少覆盖一次传输的像素字节数；`trans_queue_depth` 影响可排队事务数。

I80 的关键点：

- `esp_lcd_i80_bus_config_t` 的 `bus_width` 只支持 8 或 16；`max_transfer_bytes`、`dma_burst_size` 要按一次刷新的字节数配置。
- `esp_lcd_panel_io_i80_config_t` 的 `pclk_hz` 越高刷新越快，但可能因 DMA 带宽不足或面板不支持而花屏。

RGB 的关键点：

- `esp_lcd_rgb_panel_config_t` 支持 `data_width` 8/16/24、`fb_in_psram`、`num_fbs`、`no_fb`、`bounce_buffer_size_px`、`timings`。
- S3 的 RGB 信号走 GPIO matrix；高像素时钟 + PSRAM framebuffer 时，EDMA 和 CPU 共享 PSRAM 带宽，可能花屏/撕裂。

来源：[S3 LCD 总览](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/index.html)、[SPI LCD](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/lcd/spi_lcd.html)、[I80 LCD（S3）](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/i80_lcd.html)、[RGB LCD（S3）](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html)

### 4.2 DMA 通道与数据路径

S3 的 SoC caps 标记了 `SOC_GDMA_SUPPORTED`、`SOC_AHB_GDMA_SUPPORTED`、`SOC_PSRAM_DMA_CAPABLE`。实际数据路径：

| 路径 | DMA | 要点 |
| --- | --- | --- |
| SPI2/SPI3 → LCD | SPI DMA | `spi_bus_initialize(..., SPI_DMA_CH_AUTO)`；S3 支持 `SPI_TRANS_DMA_USE_PSRAM` 直接从 PSRAM 收发 |
| LCD_CAM I80 → LCD | GDMA | `esp_lcd_new_i80_bus()` 配置 `max_transfer_bytes`、`dma_burst_size` |
| LCD_CAM RGB → LCD | GDMA/EDMA | `esp_lcd_new_rgb_panel()` 配置 `dma_burst_size`、`bounce_buffer_size_px`、`fb_in_psram` |
| PSRAM | MSPI | PSRAM 与 flash 共用总线；SPI/RGB DMA 和 CPU 都会争用带宽 |

两个重要的 S3 专属细节：

- `SPI_TRANS_DMA_USE_PSRAM` 允许 GPSPI DMA 直接读写 PSRAM，省掉一次内部拷贝；但官方文档明确说它和 MSPI 总线共享带宽，GPSPI 传输带宽应小于 PSRAM 带宽，否则可能丢数据。
- 具体 GDMA 通道数和仲裁规则以 **ESP32-S3 Technical Reference Manual** 为准；SoC caps 只告诉你“有 GDMA”，不告诉你每个外设能同时占用多少通道。不要把“有 DMA”误解成“可以无限并行”。

来源：[S3 SPI Master](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/spi_master.html)、[S3 I80 LCD](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/i80_lcd.html)、[S3 RGB LCD](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html)、[S3 SoC caps](https://github.com/espressif/esp-idf/blob/master/components/soc/esp32s3/include/soc/soc_caps.h)

### 4.3 PSRAM 配置（Quad / Octal、容量档位）

S3 的 PSRAM Kconfig 在 `components/esp_psram/esp32s3/Kconfig.spiram`：

- **模式**：`choice SPIRAM_MODE`，默认 `SPIRAM_MODE_QUAD`，可选 `SPIRAM_MODE_OCT`。
- **类型**：`SPIRAM_TYPE_AUTO`（默认）、`ESPPSRAM16`、`ESPPSRAM32`、`ESPPSRAM64`；`ESPPSRAM16/32` 只允许 Quad。
- **速度**：`SPIRAM_SPEED_40M`（默认）、`SPIRAM_SPEED_80M`、`SPIRAM_SPEED_120M`。
  - 120 MHz Quad 是稳定项；120 MHz Octal 是 experimental，温度变化约 20°C 就可能随机崩溃，不建议量产使用。
- **使用方式**：`SPIRAM_USE_MEMMAP`、`SPIRAM_USE_CAPS_ALLOC`、`SPIRAM_USE_MALLOC`；默认是 `SPIRAM_USE_MALLOC`（`malloc()` 也能拿到 PSRAM）。
- **其他**：`SPIRAM_MALLOC_ALWAYSINTERNAL`、`SPIRAM_MALLOC_RESERVE_INTERNAL`、`SPIRAM_FETCH_INSTRUCTIONS`、`SPIRAM_RODATA`、`SPIRAM_ECC_ENABLE`（仅 Octal）。

ESP32-S3-DevKitC-1 官方订购档位（v1.1 用户指南）：

| 型号 | 模组 | Flash | PSRAM | 备注 |
| --- | --- | --- | --- | --- |
| `ESP32-S3-DevKitC-1-N32R16V` | WROOM-2-N32R16V | 32 MB | 16 MB | 1.8 V SPI；GPIO35–37 不可外接 |
| `ESP32-S3-DevKitC-1-N16R8` | WROOM-1 | 16 MB | 8 MB | 3.3 V SPI |
| `ESP32-S3-DevKitC-1U-N16R8` | WROOM-1U | 16 MB | 8 MB | 外置天线 |
| `ESP32-S3-DevKitC-1-N8`（EOL） | WROOM-1-N8 | 8 MB | 无 | 不适合 390x450 |
| `ESP32-S3-DevKitC-1-N8R2`（EOL） | WROOM-1-N8R2 | 8 MB | 2 MB | 只适合小屏/轻量 UI |

Waveshare 板型的 PSRAM 档位更杂：1.28 是 **2 MB**，1.69/2.1/1.8 AMOLED/1.43 AMOLED/3.5 等多为 **8 MB**；具体见 5.2 表。

ESP-IDF 的 S3 External RAM 文档还说明：S3 可以映射最多 **32 MB 虚拟地址空间**给外部 PSRAM；具体板子能装多少，取决于模组和 PCB。上面 DevKitC-1 的 16 MB 是官方板的最高档，不是芯片上限。

实践建议：

- 390x450 + LVGL 9.6：**至少 8 MB PSRAM**；2 MB 只适合 240x240 级别。
- 8 MB 档通常是 Octal（`CONFIG_SPIRAM_MODE_OCT`），2 MB 档通常是 Quad（`CONFIG_SPIRAM_MODE_QUAD`）；最终以模组型号为准。
- 速度先用 **80 MHz**；不要为了省事开 120 MHz Octal（experimental）。
- `CONFIG_SPIRAM_USE_MALLOC` 会让 `malloc()` 也可能拿到 PSRAM，方便但不适合所有 DMA 缓冲；LVGL 的 PSRAM buffer 用 `heap_caps_malloc(MALLOC_CAP_SPIRAM)` 更可控。
- PSRAM 和 flash 共用 MSPI 总线；Wi-Fi、文件系统、RGB framebuffer、LVGL 同时跑会争带宽。

来源：[S3 PSRAM Kconfig](https://github.com/espressif/esp-idf/blob/master/components/esp_psram/esp32s3/Kconfig.spiram)、[S3 External RAM](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/external-ram.html)、[ESP32-S3-DevKitC-1 v1.1](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)

### 4.4 390x450 的带宽与缓冲约束

390x450、RGB565 的一帧：

```text
390 * 450 = 175,500 pixels
175,500 * 2 bytes = 351,000 bytes/frame
351,000 * 60 = 21,060,000 B/s ≈ 21.1 MB/s
```

不同接口的理论上限（**只算像素字节，不含命令、空档、DMA 开销**）：

| 接口 | 示例时钟 | 理论带宽 | 390x450 全屏理论上限 |
| --- | --- | --- | --- |
| SPI（1 线数据） | 40 MHz | 5 MB/s | ≈14.2 fps |
| SPI（1 线数据） | 80 MHz | 10 MB/s | ≈28.5 fps |
| QSPI（4 线） | 40 MHz | 20 MB/s | ≈57.0 fps |
| QSPI（4 线） | 80 MHz | 40 MB/s | ≈114 fps |
| I80（8 位） | 20 MHz | 20 MB/s | ≈57.0 fps |
| I80（16 位） | 20 MHz | 40 MB/s | ≈114 fps |
| RGB（16 位） | 16 MHz | 32 MB/s | ≈91 fps |

结论：

- **普通 SPI 不适合 390x450 全屏 60 fps**：40 MHz 只有 5 MB/s，80 MHz 也只有 10 MB/s；只能靠局部刷新，或接受 15–30 fps。
- **QSPI 是 S3 上 390x450 的现实选择**：40 MHz 理论约 57 fps，80 MHz 约 114 fps；CO5300 的 QSPI 宏默认 40 MHz，能否跑 80 MHz 要按屏/PCB 实测。
- **I80 16 位/RGB 带宽更高**，但引脚多、时序复杂；RGB 还要一整屏 framebuffer 在 PSRAM，EDMA 与 CPU 争带宽。
- 以上都是理论上限，实际要扣掉命令、空档、DMA 建立、PSRAM 争用、LVGL 绘制时间；**不能当作实测帧率承诺**。

缓冲尺寸参考（RGB565）：

| 缓冲 | 像素 | 字节 |
| --- | --- | --- |
| 全屏 390x450 | 175,500 | 351,000 |
| 全屏双缓冲 | 351,000 | 702,000 |
| 1/10 屏幕（约 45 行） | 17,550 | 35,100 |
| 40 行局部 buffer | 15,600 | 31,200 |
| 40 行双缓冲 | 31,200 | 62,400 |
| 20 行 trans buffer（PSRAM canvas 用） | 7,800 | 15,600 |

小屏对照：

- 240x280 @60 fps = 240×280×2×60 ≈ 8.06 MB/s；80 MHz SPI 理论 10 MB/s，所以小屏 SPI 可以接近 60 fps。
- 368x448 @60 fps ≈ 19.8 MB/s；QSPI 40 MHz 理论 20 MB/s，**刚好卡在边界**，实际很难稳定；80 MHz 才有余量。
- 480x480 @60 fps ≈ 27.6 MB/s；RGB 16 位 16 MHz 理论 32 MB/s，但 PSRAM/blanking 会吃掉余量。

来源：[S3 SPI Master](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/spi_master.html)、[S3 I80 LCD](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/i80_lcd.html)、[S3 RGB LCD](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html)、[CO5300 QSPI 宏](https://github.com/espressif/esp-iot-solution/blob/master/components/display/lcd/esp_lcd_co5300/include/esp_lcd_co5300.h)

### 4.5 ESP32-S3 的 2D 加速与 LVGL 软件绘制

**S3 没有 PPA，也没有 DMA2D。**

- S3 SoC caps 没有 `SOC_PPA_SUPPORTED`；LVGL 官方 PPA 文档只列 ESP32-P4 系列。
- LVGL DMA2D 文档说它用于 “chips like the ESP32-P4”；S3 不在其中。
- LCD_CAM 是显示/摄像头控制器，不是 2D 图形加速器；它不替 LVGL 做圆角、阴影、混合、旋转。

因此 S3 上的 LVGL 走 **软件绘制（SW draw）**。可做的优化：

- `CONFIG_LV_USE_DRAW_SW=y`（默认）；不要开 `CONFIG_LV_USE_PPA`。
- `CONFIG_LV_DEF_REFR_PERIOD=16`（约 60 Hz 目标）或 `10`；按实际 UI 调。
- `CONFIG_LV_ATTRIBUTE_FAST_MEM_USE_IRAM=y`：把常用 LVGL 函数放 IRAM。
- `CONFIG_COMPILER_OPTIMIZATION_PERF=y`、`CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y`。
- `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y`；flash 频率按模组支持选 80 MHz（或 120 MHz，若模组支持）。
- `CONFIG_LV_DRAW_BUF_ALIGN`：SPI DMA 至少 4 字节对齐；PSRAM/RGB 场景建议 64 字节（按 cache line）。
- `CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y`：RGB/PSRAM 场景常用。
- 不要依赖 SIMD 汇编：`esp_lvgl_port` 的 S3 SIMD 汇编只在 **LVGL 9.1.0 <= version < 9.2.0** 时编译；LVGL 9.6 不走这段。LVGL 的 NEON/Helium 选项也不适用于 Xtensa S3。
- 旋转/缩放：能预旋转就预旋转（导出期处理图片），不要在运行时对全屏大图做软件旋转。

来源：[S3 SoC caps](https://github.com/espressif/esp-idf/blob/master/components/soc/esp32s3/include/soc/soc_caps.h)、[LVGL PPA 文档](https://lvgl.io/docs/open/integration/chip_vendors/espressif/hardware_accelerator_ppa)、[LVGL DMA2D 文档](https://lvgl.io/docs/open/integration/chip_vendors/espressif/hardware_accelerator_dma2d)、[esp_lvgl_port CMakeLists](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/CMakeLists.txt)

### 4.6 缓冲区/PSRAM 配置建议

`lvgl_port_display_cfg_t` 的关键字段：

| 字段 | 含义 | S3 建议 |
| --- | --- | --- |
| `buffer_size` | LVGL 绘制缓冲区大小，单位像素 | SPI 屏用 40–80 行；RGB/DSI 用全屏 |
| `double_buffer` | 是否分配两块 buffer | SPI 屏建议开；全屏 PSRAM 双缓冲吃 702 KB |
| `buff_dma` | buffer 放 DMA 可用内存 | SPI 屏建议 true；仅 RGB565 |
| `buff_spiram` | buffer 放 PSRAM | 内部 SRAM 不够时用；性能低于 SRAM |
| `trans_size` | 额外 SRAM 搬运缓冲区 | PSRAM canvas 模式必配 |
| `direct_mode` | 整屏 buffer，绝对坐标 | 仅 RGB；要求 `buffer_size == hres*vres` |
| `full_refresh` | 每帧整屏重绘 | 仅 RGB 有意义 |
| `swap_bytes` | 发送前交换 RGB565 字节 | 屏端字节序不对时用 |
| `sw_rotate` | 软件旋转 | S3 只能软件；大图慎用 |
| `rounder_cb` | 对齐绘制区域 | 某些面板/总线要求 x/宽度对齐 |
| `color_format` | `LV_COLOR_FORMAT_RGB565` 等 | 与 panel `bits_per_pixel` 匹配 |

两种典型配置：

**A. 内部 SRAM 局部 buffer（SPI/QSPI 屏首选）**

```c
const lvgl_port_display_cfg_t disp_cfg = {
    .io_handle = io,
    .panel_handle = panel,
    .buffer_size = 390 * 40,      /* 40 行，约 31.2 KB */
    .double_buffer = true,        /* 约 62.4 KB */
    .hres = 390,
    .vres = 450,
    .color_format = LV_COLOR_FORMAT_RGB565,
    .flags = {
        .buff_dma = true,
        .buff_spiram = false,
        .swap_bytes = false,
    },
};
```

**B. PSRAM canvas + SRAM trans buffer（内部 SRAM 紧张时）**

```c
const lvgl_port_display_cfg_t disp_cfg = {
    .io_handle = io,
    .panel_handle = panel,
    .buffer_size = 390 * 450,     /* 全屏 351 KB，放 PSRAM */
    .double_buffer = false,
    .trans_size = 390 * 20,       /* 20 行 SRAM DMA 搬运，约 15.6 KB */
    .hres = 390,
    .vres = 450,
    .color_format = LV_COLOR_FORMAT_RGB565,
    .flags = {
        .buff_dma = false,
        .buff_spiram = true,
        .swap_bytes = false,
    },
};
```

官方性能文档的结论：

- buffer 大小是影响帧率最大的因素；`<10%` 屏幕会严重掉帧，`>25%` 收益很小。
- 内部 SRAM 的 buffer 明显快于 PSRAM；PSRAM buffer 会差一些。
- 推荐 `CONFIG_COMPILER_OPTIMIZATION_PERF=y`、`CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y`、`CONFIG_ESPTOOLPY_FLASHMODE_QIO=y`、`CONFIG_LV_ATTRIBUTE_FAST_MEM_USE_IRAM=y`、`CONFIG_LV_DEF_REFR_PERIOD=10`。
- 双核芯片可以把 LVGL 任务绑到另一个核（`task_affinity` 或 `CONFIG_ESP_MAIN_TASK_AFFINITY_CPU1`）。

来源：[esp_lvgl_port performance.md](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/docs/performance.md)、[esp_lvgl_port_disp.h](https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/include/esp_lvgl_port_disp.h)、[S3 SPI Master](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/spi_master.html)

---

## 5. ESP32-S3 板型矩阵与推荐

### 5.1 官方 Espressif 板型

| 板型 | 模组/内存 | 屏幕 | 接口 | 控制器 | 触摸 | 官方 BSP |
| --- | --- | --- | --- | --- | --- | --- |
| ESP32-S3-DevKitC-1-N32R16V | WROOM-2，32 MB flash + 16 MB PSRAM，1.8 V | 外接 | SPI/QSPI/I80/RGB | 自选 | 自选 | 无屏；用通用组件 |
| ESP32-S3-DevKitC-1-N16R8 | WROOM-1，16 MB flash + 8 MB PSRAM，3.3 V | 外接 | SPI/QSPI/I80/RGB | 自选 | 自选 | 无屏；用通用组件 |
| ESP32-S3-LCD-EV-Board | S3，16 MB flash + 16 MB PSRAM | 480x480 或 800x480 | RGB | GC9503CV / ST7262E43 | FT5x06 / GT1151 | `esp32_s3_lcd_ev_board` 4.1.0 |
| ESP32-S3-BOX-3 | S3-WROOM-1，16 MB flash + 16 MB Octal PSRAM | 320x240 | SPI | ILI9341（BSP 亦列 ST7789） | GT911 / TT21100 | `esp-box-3` 3.2.1 |
| M5Dial | S3FN8，8 MB flash，**无 PSRAM** | 240x240 圆形 | SPI | GC9A01 | FT3267（BSP 用 FT5x06） | `m5dial` 3.1.0 |
| M5Stack CoreS3 | S3，16 MB flash + 8 MB Quad PSRAM | 320x240 | SPI | ILI9342C/E | FT5x06 | `m5stack_core_s3` 4.1.0 |

说明：

- DevKitC-1 的 N8 / N8R2 是 EOL 型号；如果只做芯片/引脚调试，选 N16R8 或 N32R16V，交付形态仍用一体化整板。
- WROOM-2（N32R16V）和八线 PSRAM 模组的 **GPIO35–37 不可外接**；N32R16V 是 1.8 V SPI 电压（V 后缀），外设电平要匹配。N16R8 是 WROOM-1，3.3 V SPI；最终以模组 datasheet 为准。
- ESP32-S3-LCD-EV-Board 的主板支持 I2C/SPI/8080/RGB 子板；480x480 子板是 GC9503CV + FT5x06，800x480 子板是 ST7262E43 + GT1151。
- ESP32-S3-BOX-3 是 16 MB flash + 16 MB Octal PSRAM（Espressif 硬件概览）；M5Dial 是 8 MB flash、**没有 PSRAM**（M5Stack 规格表），只适合 240x240 级别的圆形 UI。
- DevKitC-1 两行是芯片能力/引脚调试参考，不是用户要的交付形态；一体化整板见 5.2。

来源：[DevKitC-1 v1.1](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)、[S3-LCD-EV 用户指南](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-lcd-ev-board/user_guide.html)、[esp-bsp README](https://github.com/espressif/esp-bsp/blob/master/README.md)

### 5.2 一体化 ESP32-S3 触摸屏开发板候选（总表）

下表把 Espressif 官方 esp-bsp 板、Waveshare、LilyGO、M5Stack 和常见国产模组放在一起对比。`BSP` 列区分 **Espressif esp-bsp 官方**、**板厂 BSP**、**无 BSP**；`LVGL 9` 列区分「BSP 已带」「需自行接 `esp_lvgl_port`」「未核实」。所有板型都要求一体化（屏 + 触摸 + 主控在一块 PCB 上），不列裸 DevKitC-1。

| 类别 | 板型 | SoC | 屏幕（控制器 / 分辨率 / 接口） | 触摸 | PSRAM / Flash | BSP | LVGL 9 可用性 | 与 390x450 的关系 / 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 官方 esp-bsp | ESP32-S3-BOX-3 | S3-WROOM-1 | ILI9341 320x240 SPI | GT911 / TT21100 | 16 MB Octal / 16 MB Quad flash | `esp-box-3` 3.2.1 | 是（BSP 用 `esp_lvgl_port`） | 非手表形态；官方支持最稳 |
| 官方 esp-bsp | ESP32-S3-LCD-EV-Board | S3 | GC9503CV 480x480 RGB / ST7262E43 800x480 RGB | FT5x06 / GT1151 | 16 MB / 16 MB | `esp32_s3_lcd_ev_board` 4.1.0 | 是 | 方形大屏，接近 390x450；RGB 引脚多 |
| 官方 esp-bsp | M5Dial | S3FN8 | GC9A01 240x240 SPI | FT3267（BSP 用 FT5x06） | **无 PSRAM** / 8 MB | `m5dial` 3.1.0 | 是 | 圆形手表形态；分辨率低、无 PSRAM |
| 官方 esp-bsp | M5Stack CoreS3 | S3 | ILI9342C/E 320x240 SPI | FT5x06 | 8 MB Quad / 16 MB | `m5stack_core_s3` 4.1.0 | 是 | 方形小屏；非手表 |
| 板厂 | Waveshare ESP32-S3-Touch-LCD-1.28 | S3R2 | GC9A01A 240x240 SPI | CST816S | 2 MB / 16 MB | 无 BSP 组件（厂商示例） | 可接 `esp_lvgl_port`；GC9A01/CST816S 有 Espressif 组件 | 圆形小表；2 MB PSRAM 限制 |
| 板厂 | Waveshare ESP32-S3-Touch-LCD-1.69 | S3R8 | ST7789V2 240x280 SPI | CST816T（BSP 用 `esp_lcd_touch_cst816s`） | 8 MB / 16 MB | Waveshare BSP 2.0.0 | 是（BSP 用 `esp_lvgl_port`） | 小竖屏；引脚资料完整 |
| 板厂 | Waveshare ESP32-S3-Touch-LCD-2.1 | S3R8 | ST7701 480x480 RGB | CST820 | 8 MB / 16 MB | 无 BSP 组件（厂商示例） | 可接；ST7701/CST820 驱动需核实 | 圆形大屏，接近 390x450；RGB 引脚多 |
| 板厂 | Waveshare ESP32-S3-Touch-LCD-2.8 | S3R8 | ST7789 240x320 SPI | CST3530（V2）/ CST328（V1） | 8 MB / 16 MB | 无 BSP 组件（厂商示例） | ST7789 内置；触摸驱动需核实 | 小竖屏；非手表 |
| 板厂 | Waveshare ESP32-S3-Touch-LCD-2.8C | S3R8 | ST7701 480x480 RGB | GT911 | 8 MB / 16 MB | 无 BSP 组件（厂商示例） | GT911 有 Espressif 组件；ST7701 需核实 | 方形大屏，接近 390x450；RGB |
| 板厂 | Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 | S3R8 | CO5300 368x448 QSPI | CST820（BSP 用 `esp_lcd_touch_cst816s`） | 8 MB / 16 MB | Waveshare BSP 2.0.3 | 是（BSP 用 `esp_lvgl_port`） | **最接近 390x450**；默认推荐 |
| 板厂 | Waveshare ESP32-S3-Touch-AMOLED-1.43 | S3R8 | CO5300 / SH8601 466x466 QSPI | FT3168（部分批次 FT6146） | 8 MB / 16 MB | 无 BSP 组件（厂商示例） | FT3168 可走 `esp_lcd_touch_ft5x06`（需实测）；FT6146 未核实 | 圆形表；适合验证 FT6146 |
| 板厂 | Waveshare ESP32-S3-Touch-AMOLED-1.75 | S3R8 | CO5300 466x466 QSPI | CST9217 | 8 MB / 16 MB | Waveshare BSP 3.0.1（**用 `esp_lvgl_adapter`，不是 `esp_lvgl_port`**；IDF >=5.5.5） | 是，但适配层是 `espressif/esp_lvgl_adapter` ~0.6 | 圆形表；要统一到 `esp_lvgl_port` 需改 BSP |
| 板厂 | Waveshare ESP32-S3-Touch-AMOLED-2.06 | S3R8 | CO5300 410x502 QSPI | FT3168（BSP 用 `esp_lcd_touch_ft5x06`） | 8 MB / 32 MB | Waveshare BSP 2.0.0，但源码仍用 `waveshare/esp_lcd_sh8601`；与当前 CO5300 屏不符，需核实或自接 `esp_lcd_co5300` | 是（BSP 用 `esp_lvgl_port`，面板驱动待核实） | 竖向大表，接近 390x450 比例 |
| 板厂 | Waveshare ESP32-S3-Touch-AMOLED-2.16 | S3R8 | CO5300 480x480 QSPI | CST9220（BSP 用 CST9217 驱动） | 8 MB / 16 MB | Waveshare BSP 2.0.1（**用 `esp_lvgl_adapter`**；IDF >=5.5.5） | 是，但适配层是 `esp_lvgl_adapter` ~0.6 | 方形大表；要 `esp_lvgl_port` 需改 BSP |
| 板厂 | Waveshare ESP32-S3-Touch-LCD-3.5 | S3R8 | ST7796 320x480 SPI | FT6336 | 8 MB / 16 MB | 无 BSP 组件（厂商示例） | ST7796 有 Espressif 组件；FT6336 需核实 | 3.5" 竖屏；非手表 |
| 板厂 | LilyGO T-Display-S3-Touch | S3R8 | ST7789 170x320 SPI | CST328 / CST816（按实物） | 8 MB OPI / 16 MB | 无 esp-bsp；厂商示例 | Arduino 示例已用 LVGL 9；ESP-IDF 需另行集成 | 窄屏；非手表 |
| 板厂 | LilyGO T-Display-S3 AMOLED（1.91"） | S3R8 | RM67162 240x536 QSPI | CST816（仅触摸版） | 8 MB OPI / 16 MB | 无 esp-bsp；厂商示例 | 厂商 Arduino 示例已用 LVGL 9；ESP-IDF 需另行集成 | 窄长屏；非手表 |
| 板厂 | LilyGO T4-S3 | S3R8 | RM690B0 450x600 QSPI | CST226SE | 8 MB OPI / 16 MB | 无 esp-bsp；厂商示例 | 厂商 Arduino 示例已用 LVGL 9；ESP-IDF 需另行集成 | 大矩形；非手表 |
| 国产模组 | Guition JC3248W535 | S3-WROOM-1 / S3R8 | AXS15231B 320x480 QSPI | AXS15231B（同芯片，I2C；地址按 schematic 确认） | 8 MB PSRAM / 16 MB | 无 esp-bsp；Espressif `esp_lcd_axs15231b` 2.1.1 官方驱动 | 可接 `esp_lvgl_port`；官方驱动覆盖 LCD + 触摸 | 3.5" 竖屏；性价比高，非手表 |

说明：

- **官方 BSP** 指 Espressif `esp-bsp`；**板厂 BSP** 指 Waveshare/LilyGO 自己的组件或示例。两者的 issue、升级、维护责任不同。
- Waveshare BSP 的 IDF 下限：1.8/1.69/2.06 为 `>=5.3`，1.75/2.16 为 `>=5.5`（其 `esp_lvgl_adapter` 依赖要求 `>=5.5.5`）；都声明 `lvgl/lvgl >=8,<10`，所以 LVGL 9 可用。
- Waveshare 1.43/2.1/2.8/2.8C/3.5/1.28 在 `waveshare-esp32-components` 的 `bsp/` 目录中**未见对应组件**；不是“绝对不能做”，而是需要自己接 `esp_lcd` + `esp_lvgl_port`，或使用厂商示例包。
- M5Dial 是圆形手表形态，但 **S3FN8 + 8 MB flash，无 PSRAM**；它适合 240x240 的轻量 UI，不适合 390x450 的大 buffer。
- JC3248W535 的板级规格（16 MB flash / 8 MB PSRAM / 320x480）来自 Guition 官方产品页；AXS15231B 的 LCD+触摸驱动是 Espressif 官方组件，但 **这块板本身不在 esp-bsp**，板级初始化/引脚/PSRAM 模式要按 Guition schematic 接。
- LilyGO T-Display-S3-Touch 的触摸控制器有 CST328/CST816 两种，厂商示例用宏切换；买板/写驱动前必须确认实物型号。

来源：[ESP-BOX-3 硬件概览](https://github.com/espressif/esp-box/blob/master/docs/hardware_overview/esp32_s3_box_3/hardware_overview_for_box_3.md)、[M5Dial 规格](https://docs.m5stack.com/en/core/M5Dial)、[M5Stack CoreS3 规格](https://docs.m5stack.com/en/core/CoreS3)、[Waveshare 产品页（板型总表）](https://www.waveshare.com/esp32-s3-touch-lcd-2.1.htm)、[AMOLED-1.8 文档](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8)、[AMOLED-1.43 文档](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.43)、[AMOLED-1.75 文档](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75)、[AMOLED-2.06 文档](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.06)、[Touch-LCD-1.69 文档](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.69)、[Touch-LCD-1.28 文档](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.28)、[Touch-LCD-2.8 文档](https://docs.waveshare.com/ESP32-S3-Touch-LCD-2.8)、[Touch-LCD-2.8C 文档](https://docs.waveshare.com/ESP32-S3-Touch-LCD-2.8C)、[Waveshare BSP 仓库](https://github.com/waveshareteam/waveshare-esp32-components)、[LilyGO T-Display-S3](https://github.com/Xinyuan-LilyGO/T-Display-S3)、[LilyGO AMOLED Series](https://github.com/Xinyuan-LilyGO/LilyGo-AMOLED-Series)、[Guition JC3248W535](https://www.guition.com/esp32-display-module/3-5-inch-esp32s3-display-module)、[Espressif AXS15231B 组件](https://components.espressif.com/components/espressif/esp_lcd_axs15231b)

### 5.3 官方 esp-bsp 支持情况

- `esp-bsp` 官方支持列表里**没有 Waveshare、LilyGO、Guition 板型**。它们的 BSP/示例由各自板厂维护。
- `esp-bsp` 官方 S3 带屏板型：ESP32-S3-BOX-3（320x240 SPI，16 MB PSRAM）、ESP32-S3-LCD-EV-Board（480x480/800x480 RGB，16 MB PSRAM）、M5Dial（240x240 圆形，**无 PSRAM**）、M5Stack CoreS3（320x240 SPI，8 MB Quad PSRAM）。
- Waveshare 板厂 BSP 仓库当前有：1.8（2.0.3，`esp_lvgl_port`）、1.69（2.0.0，`esp_lvgl_port`）、2.06（2.0.0，`esp_lvgl_port`，但面板驱动仍用 SH8601）、1.75（3.0.1，**`esp_lvgl_adapter`**）、2.16（2.0.1，**`esp_lvgl_adapter`**）；1.28/1.43/2.1/2.8/2.8C/3.5 未见对应组件。`esp_lvgl_adapter` 是另一个 Espressif 组件，不是 `esp_lvgl_port`。
- Guition JC3248W535 没有板级 BSP，但 Espressif 有 `esp_lcd_axs15231b` 2.1.1 官方驱动，覆盖 LCD + 触摸，QSPI 可用。
- LilyGO 的 AMOLED 系列示例已用 LVGL 9（Arduino），ESP-IDF 示例在单独的 `LilyGo-Display-IDF` 仓库；没有 esp-bsp 板级组件。
- 没有 Espressif 官方 BSP 覆盖 390x450 CO5300 屏；这块屏的板级支持要定制或依赖板厂。

### 5.4 推荐 2–3 块整板

**首选：Waveshare ESP32-S3-Touch-AMOLED-1.8（V2）。**

- 368x448、CO5300 QSPI、8 MB PSRAM、16 MB Flash、CST820；屏幕比例和黄山派 390x450 最接近。
- Waveshare BSP 2.0.3 已把 `esp_lvgl_port`、`esp_lcd_co5300`、`esp_lcd_touch_cst816s`、`lvgl/lvgl` 串好，接 `esp_lvgl_port` 的成本最低。
- 取舍：368x448 不是精确 390x450；V1 是 SH8601/FT3168，买板要确认 V2。

**第二推荐：Waveshare ESP32-S3-Touch-AMOLED-2.06。**

- 410x502、CO5300 QSPI、8 MB PSRAM、32 MB Flash、FT3168；比例接近 390x450 的竖屏，比 368x448 更接近目标分辨率。
- Waveshare BSP 2.0.0 使用 `esp_lvgl_port`，IDF >=5.3；FT3168 走 `esp_lcd_touch_ft5x06`。**但 BSP 源码当前仍用 `waveshare/esp_lcd_sh8601` 和 SH8601 初始化序列，而产品页写的是 CO5300**；买板后先确认驱动 IC，若是 CO5300，面板初始化改用 `esp_lcd_co5300`，或等 Waveshare 更新 BSP。
- 取舍：410x502 不是精确 390x450；BSP 是板厂组件，不是 Espressif esp-bsp；面板驱动版本要核实。

**圆屏备选（注意适配层不同）：Waveshare 1.75 / 2.16 / 1.43。**

- 1.75（466x466，CO5300，CST9217）BSP 3.0.1 和 2.16（480x480，CO5300，CST9220）BSP 2.0.1 都使用 **`espressif/esp_lvgl_adapter`**，不是 `esp_lvgl_port`；如果项目统一用 `esp_lvgl_port`，需要改 BSP 或自己初始化。
- 1.43（466x466，CO5300/SH8601，FT3168/FT6146）没有 BSP 组件，需要手动接 `esp_lcd` + `esp_lvgl_port`；FT6146 兼容性未核实。
- 如果圆屏是硬性要求，先决定用 `esp_lvgl_adapter` 还是自己接 `esp_lvgl_port`，再选 1.75/2.16/1.43。

**官方支持最稳：ESP32-S3-LCD-EV-Board。**

- 480x480 RGB（GC9503CV + FT5x06）或 800x480 RGB（ST7262E43 + GT1151），16 MB PSRAM，`esp-bsp` 4.1.0。
- 好处是官方 BSP、显示/触摸/示例齐全；代价是 RGB 需要更多 GPIO 和 PSRAM framebuffer，板子是 4 英寸级，不是手表形态。
- 如果只要“方形表盘 + 官方 BSP”，它是最稳的验证平台。

**性价比备选：Guition JC3248W535。**

- 320x480、AXS15231B QSPI、8 MB PSRAM、16 MB Flash；Espressif `esp_lcd_axs15231b` 2.1.1 官方驱动同时覆盖 LCD + 触摸，QSPI 接线少，国内易买。
- 取舍：3.5" 竖屏，不是手表形态；没有 esp-bsp 板级 BSP，需要自己接 `esp_lvgl_port` 和板级初始化。

**不建议作为 390x450 替代：**

- M5Dial（240x240、无 PSRAM）适合验证圆形交互，不适合大 buffer。
- Waveshare 1.28（2 MB PSRAM）、1.69（240x280）、2.8（240x320）、BOX-3/CoreS3（320x240）只适合小屏验证。
- LilyGO T-Display-S3-Touch（170x320）和 T-Display-S3 AMOLED（240x536）适合窄屏实验，不是手表比例。

### 5.5 引脚与外设注意

- **避开模组内部占用**：ESP32-S3-WROOM-1/2 的 SPI flash 引脚不引出；八线 PSRAM/Flash 模组的 **GPIO35–37** 不可用（DevKitC-1 v1.1 文档明确写）。
- **避开 strapping/USB**：GPIO0、GPIO3、GPIO45、GPIO46 是 strapping 相关；GPIO19/GPIO20 是 USB D-/D+。做 SPI 屏时尽量避开。
- **电平**：WROOM-2（N32R16V）是 1.8 V SPI 电压，外接 3.3 V 屏/触摸要确认电平转换；N16R8 是 3.3 V。
- **背光**：`esp_lcd` 不管背光；需要 GPIO/PWM 或面板命令（CO5300 有亮度命令）。
- **触摸中断**：有 INT 引脚就接到 GPIO，`esp_lvgl_port` 会走事件模式；没有就轮询。

---

## 6. 从 user/app 导出的映射（ESP32-S3）

### 6.1 三区结构

SiFli 适配层的三区是：自研 `chip-adapt/sifli/`、外部 `chip-adapt/vendor/`、生成物 `chip-adapt/exports/`。ESP32-S3 版本建议如下：

| 区域 | SiFli 现状 | ESP32-S3 建议 | 进 Git | 说明 |
| --- | --- | --- | --- | --- |
| 自研适配层 | `chip-adapt/sifli/` | `chip-adapt/esp32/` | 是 | `export.py`、`layout.py`、`adapter.json`、`templates/`、`host/`、测试 |
| 外部 SDK | `chip-adapt/vendor/sifli-sdk/` | EIM 安装的 ESP-IDF（`IDF_PATH`）或可选 `chip-adapt/vendor/esp-idf/` | 否 | 推荐 EIM 系统级安装，和 SiFli 的 `%USERPROFILE%\.sifli` 类似 |
| 托管组件 | 无 | 导出工程里的 `managed_components/` | 否 | Component Manager 生成，不手改 |
| 生成物 | `chip-adapt/exports/<app>/` | `chip-adapt/exports/esp32/<app>/` | 否 | 只能由 `export.py` 生成 |
| 双击启动器 | `chip-adapt/sifli/tools/SiFli-Host.exe` | 可选 `chip-adapt/esp32/tools/` | 是 | 仍然只负责拉起 `pythonw`，不碰串口/URL |

关于 `exports` 布局：现有 SiFli 是单芯片扁平布局 `exports/<app>/`，且 `chip-adapt/README.md` 明确写「不为多芯片做抽象」。加入 ESP32-S3 后有两个选择：

1. **加法式（推荐）**：SiFli 继续用 `exports/<app>/`，ESP32-S3 用 `exports/esp32/<app>/`，互不影响。
2. **重构式**：统一成 `exports/<chip>/<app>/`，需要改 SiFli 的 `layout.py`、文档、测试和已有导出路径，风险大。

建议先走加法式，等两条路线都稳定后再考虑统一。

### 6.2 共享源码与目标专属生成层

**共享源码（唯一真源）**：

```text
user/app/
  app.h
  lvgl_compat.h
  <app>/
    assets.json
    assets/*.png
    *.c / *.h
```

- 应用入口仍是 `void <app>_create(void)`；内部用 `lv_screen_active()` 取屏幕。
- 应用代码只写 LVGL API 和 `#include "assets.h"`；不写平台分支。
- ESP32-S3 导出按 **9.6 专用 API**：导出器按 9.6 扫描与生成，不默认要求共享源码兼容 SiFli 9.4。同一应用若要双端导出，需要单独的应用变体，或由应用作者自行保持 9.4 子集。

**目标专属生成层（ESP32-S3）**：

```text
chip-adapt/exports/esp32/<app>/
  CMakeLists.txt              # 顶层，include project.cmake
  sdkconfig.defaults          # 公共默认值
  sdkconfig.defaults.esp32s3  # S3 专属默认值
  partitions.csv              # 自定义分区表（app 大小、资源分区）
  main/
    CMakeLists.txt            # idf_component_register + 图片生成
    idf_component.yml         # 版本锁定
    app_main.c                # ESP-IDF 入口：port init + app_create
    app/
      app.c                   # void app_create(void)
      lvgl_ai_esp.h           # 目标/本地切换头
      assets.h / assets.c     # 资源层
      <app>/                  # 应用源码原样副本
    assets/                   # 可选：PNG 或生成的 C array
  export.json                 # 资源、版本、缓存、生成结果
  README.md
```

**明确不属于共享源码的东西**：

- `app_main.c`、`CMakeLists.txt`、`idf_component.yml`、`sdkconfig.defaults*`、`partitions.csv`；
- 面板/触摸初始化、背光、QSPI/SPI/RGB 时序、引脚；
- 资源转换脚本和生成的 C array；
- `dependencies.lock`、`managed_components/`、`build/`。

### 6.3 `sdkconfig.defaults`（S3）

起点模板（按板型改）：

```ini
CONFIG_IDF_TARGET="esp32s3"

# Flash：按模组容量改
CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y
CONFIG_ESPTOOLPY_FLASHMODE_QIO=y
CONFIG_ESPTOOLPY_FLASHFREQ_80M=y

# CPU / 编译
CONFIG_COMPILER_OPTIMIZATION_PERF=y
CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y
CONFIG_FREERTOS_HZ=1000

# PSRAM：8 MB Octal；2 MB 模组改 QUAD
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_OCT=y
CONFIG_SPIRAM_SPEED_80M=y
CONFIG_SPIRAM_USE_MALLOC=y
CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL=16384
CONFIG_SPIRAM_MALLOC_RESERVE_INTERNAL=32768
CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y

# LVGL
CONFIG_LV_CONF_SKIP=y
CONFIG_LV_COLOR_DEPTH_16=y
CONFIG_LV_DEF_REFR_PERIOD=16
CONFIG_LV_DRAW_BUF_ALIGN=4
CONFIG_LV_ATTRIBUTE_FAST_MEM_USE_IRAM=y
CONFIG_LV_USE_CLIB_MALLOC=y
CONFIG_LV_USE_CLIB_STRING=y
CONFIG_LV_USE_CLIB_SPRINTF=y
CONFIG_LV_USE_LOG=y
CONFIG_LV_USE_OBJ_NAME=y
CONFIG_LV_USE_PERF_MONITOR=y
CONFIG_LV_USE_SYSMON=y
CONFIG_LV_USE_OBSERVER=y

# 分区表
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
```

说明：

- `CONFIG_FREERTOS_HZ=1000` 影响 FreeRTOS 的 tick/延时粒度；**LVGL 的 tick 不是它驱动的**。`esp_lvgl_port` 用 `esp_timer` 每 `timer_period_ms`（默认 5 ms）调 `lv_tick_inc()`。
- `CONFIG_SPIRAM_MODE_OCT` 适合 8 MB/16 MB 模组；2 MB 模组用 `CONFIG_SPIRAM_MODE_QUAD`。
- `CONFIG_LV_DRAW_BUF_ALIGN=4` 适合 SPI DMA；如果 buffer 放 PSRAM 或走 RGB，改成 `64`。
- 不要开 `CONFIG_LV_USE_PPA`（S3 没有 PPA）。
- `CONFIG_ESPTOOLPY_FLASHFREQ_80M` 要按模组/板子支持选；不要盲目上 120 MHz。

`partitions.csv` 示例（`storage` 只有用文件系统时才需要）：

```csv
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     ,        0x6000,
phy_init, data, phy,     ,        0x1000,
factory,  app,  factory, ,        4M,
storage,  data, spiffs,  ,        4M,
```

默认的 “Single factory app, no OTA” 只给 app 1 MB；LVGL + 字体 + 图片很容易超。

### 6.4 SPI 屏的引脚配置与 panel 初始化

以 ST7789（SPI）为例，引脚用占位符；实际按板子排针选空闲 GPIO：

```c
#define LCD_HOST      SPI2_HOST
#define PIN_LCD_SCLK  12
#define PIN_LCD_MOSI  11
#define PIN_LCD_CS    10
#define PIN_LCD_DC    9
#define PIN_LCD_RST   8
#define PIN_LCD_BL    7

const spi_bus_config_t buscfg = {
    .mosi_io_num = PIN_LCD_MOSI,
    .miso_io_num = -1,
    .sclk_io_num = PIN_LCD_SCLK,
    .quadwp_io_num = -1,
    .quadhd_io_num = -1,
    .max_transfer_sz = 390 * 40 * sizeof(uint16_t),
};
ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

const esp_lcd_panel_io_spi_config_t io_config = {
    .cs_gpio_num = PIN_LCD_CS,
    .dc_gpio_num = PIN_LCD_DC,
    .spi_mode = 0,
    .pclk_hz = 40 * 1000 * 1000,
    .trans_queue_depth = 10,
    .lcd_cmd_bits = 8,
    .lcd_param_bits = 8,
};
esp_lcd_panel_io_handle_t io = NULL;
ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)LCD_HOST, &io_config, &io));

const esp_lcd_panel_dev_config_t panel_config = {
    .reset_gpio_num = PIN_LCD_RST,
    .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
    .bits_per_pixel = 16,
};
esp_lcd_panel_handle_t panel = NULL;
ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(io, &panel_config, &panel));
ESP_ERROR_CHECK(esp_lcd_panel_reset(panel));
ESP_ERROR_CHECK(esp_lcd_panel_init(panel));
ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel, true));
```

要点：

- `max_transfer_sz` 至少覆盖一次传输的字节数；如果一次刷 40 行，按 `390*40*2` 配。
- `on_color_trans_done` 不要自己设；`lvgl_port_add_disp()` 会注册。
- 背光不在 `esp_lcd` 里，单独用 GPIO/PWM 控制。
- 屏的 `rgb_ele_order` / `swap_bytes` / `mirror` 要按实物调；错了就是红蓝互换、花屏或点击偏移。

作为对照，Waveshare ESP32-S3-Touch-LCD-1.69 的官方引脚是：LCD `DC=GPIO4`、`CS=GPIO5`、`CLK=GPIO6`、`DIN=GPIO7`、`RST=GPIO8`、`BL=GPIO15`；触摸 `SCL=GPIO10`、`SDA=GPIO11`、`RST=GPIO13`、`INT=GPIO14`。这些是板厂固定接线，不能照搬到 DevKitC-1；但可以作为“SPI 屏 + I2C 触摸”接线的参考。

QSPI CO5300 的差异：

```c
const spi_bus_config_t buscfg = CO5300_PANEL_BUS_QSPI_CONFIG(
    PIN_LCD_SCLK, PIN_LCD_D0, PIN_LCD_D1, PIN_LCD_D2, PIN_LCD_D3,
    390 * 40 * sizeof(uint16_t));
ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

const esp_lcd_panel_io_spi_config_t io_config =
    CO5300_PANEL_IO_QSPI_CONFIG(PIN_LCD_CS, NULL, NULL);

const co5300_vendor_config_t vendor_config = {
    .flags = { .use_qspi_interface = 1 },
};
const esp_lcd_panel_dev_config_t panel_config = {
    .reset_gpio_num = PIN_LCD_RST,
    .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
    .bits_per_pixel = 16,
    .vendor_config = &vendor_config,
};
ESP_ERROR_CHECK(esp_lcd_new_panel_co5300(io, &panel_config, &panel));
```

CO5300 QSPI 宏的默认值：`dc_gpio_num = -1`、`pclk_hz = 40 MHz`、`lcd_cmd_bits = 32`、`lcd_param_bits = 8`、`quad_mode = true`。80 MHz 是否可用要按屏/PCB 实测。

### 6.5 `lvgl_port_add_disp` 对接

```c
const lvgl_port_display_cfg_t disp_cfg = {
    .io_handle = io,
    .panel_handle = panel,
    .buffer_size = 390 * 40,
    .double_buffer = true,
    .hres = 390,
    .vres = 450,
    .monochrome = false,
    .color_format = LV_COLOR_FORMAT_RGB565,
    .rotation = {
        .swap_xy = false,
        .mirror_x = false,
        .mirror_y = false,
    },
    .flags = {
        .buff_dma = true,
        .buff_spiram = false,
        .swap_bytes = false,
        .sw_rotate = false,
    },
};
lv_display_t *disp = lvgl_port_add_disp(&disp_cfg);
```

- `buffer_size` 是像素数，不是字节数。
- `buff_dma = true` 只允许 RGB565（或 RGB565_SWAPPED）。
- `buff_spiram = true` 时性能低于内部 SRAM；如果内部 SRAM 不够，用 4.6 的 PSRAM canvas + `trans_size`。
- `sw_rotate = true` 会在 flush 时做软件旋转；S3 没有 PPA，大图旋转很贵。

RGB 面板用 `lvgl_port_add_disp_rgb()`：

```c
const lvgl_port_display_cfg_t disp_cfg = {
    .panel_handle = panel,
    .buffer_size = 390 * 450,
    .double_buffer = true,
    .hres = 390,
    .vres = 450,
    .color_format = LV_COLOR_FORMAT_RGB565,
    .flags = {
        .buff_dma = false,
        .buff_spiram = true,
        .direct_mode = true,
        .full_refresh = true,
    },
};
const lvgl_port_display_rgb_cfg_t rgb_cfg = {
    .flags = { .bb_mode = false, .avoid_tearing = true },
};
lv_display_t *disp = lvgl_port_add_disp_rgb(&disp_cfg, &rgb_cfg);
```

RGB 需要 `esp_lcd_new_rgb_panel()` 先创建 panel，并配置 `data_width`、`timings`、`num_fbs`、`fb_in_psram`、`bounce_buffer_size_px`。`avoid_tearing` 需要至少两块 LCD buffer，可能降低帧率。

### 6.6 资源策略

SiFli 的资源层是 `assets.json` + EZIP/raw C array；ESP32-S3 没有 EZIP/EPIC，需要换一套：

| 方案 | 做法 | 适用 |
| --- | --- | --- |
| LVGL C array（推荐） | 构建期用 `lvgl_port_create_c_image()`（内部调 LVGL 的 `LVGLImage.py`）把 PNG 转成 C array；`lvgl_port_add_images()` 加入编译 | 静态图标、背景、字体图片 |
| `EMBED_FILES` | `idf_component_register(EMBED_FILES ...)` 把二进制嵌进 `.rodata`，用 `_binary_<name>_start` 符号访问 | 需要自己封装 `lv_image_dsc_t` 的原始像素 |
| 文件系统 | 挂 SPIFFS/LittleFS/FATFS，用 `lv_image_set_src(img, "A:/x.bin")` | 可替换资源、大图、多语言包 |
| PSRAM 缓存 | 启动时把热资源 `heap_caps_malloc(MALLOC_CAP_SPIRAM)` 复制过去 | 频繁重绘、旋转的图 |

`lvgl_port_create_c_image()` 支持的颜色格式：`L8,I1,I2,I4,I8,A1,A2,A4,A8,ARGB8888,XRGB8888,RGB565,RGB565A8,RGB888,TRUECOLOR,TRUECOLOR_ALPHA,AUTO`；压缩：`NONE,RLE,LZ4`（LVGL 9 才支持 compression）。它依赖 Python 的 `pypng` / `lz4`，构建时会 pip 安装；导出器要接受这个构建期依赖，或者改成导出期预生成。

**schema 冲突**：现有 `assets.json` 的 `mode` 只接受 `ezip|raw`，`placement` 只接受 `flash|psram|sram`，`transform` 只接受 `none|rotate|scale|rotate_scale`；`ezip` 又和 `transform != none` 冲突。ESP32-S3 适配层需要：

- 方案 A：新增 `mode=lvgl_c_array`（或 `c_array`），保留 `raw` 表示原始像素；`placement` 映射到 flash/PSRAM；`transform` 只影响生成时的预旋转/预缩放。
- 方案 B：ESP32-S3 适配层单独读一份 `assets.esp32.json`，不改 SiFli schema。
- 方案 C：把 `assets.json` 升级为多目标 schema，例如 `targets: { sifli: {...}, esp32: {...} }`。

**旋转/缩放**：S3 没有 PPA，运行时旋转大图很贵。建议静态资源在导出期预旋转/预缩放，运行时只贴图；动态表针之类的小图可以用 LVGL 软件变换。

### 6.7 构建 / 烧录 / 验证命令映射

| 动作 | SiFli | ESP32-S3 |
| --- | --- | --- |
| 导出 | `python -I chip-adapt/sifli/export.py <app> --dry-run --force` | `python -I chip-adapt/esp32/export.py <app> --dry-run --force` |
| 构建 | `scons --board=sf32lb52-lchspi-ulp -j8` | `cd <export> && idf.py build` |
| 构建（上位机） | `python -I chip-adapt/sifli/host/cli.py build --app <app> --actor ai --json` | `python -I chip-adapt/esp32/host/cli.py build --app <app> --actor ai --json` |
| 烧录 | `sftool`（host 封装） | `idf.py -p COMx -b 921600 flash` |
| 串口 | host broker + xterm.js | `idf.py -p COMx monitor` 或 host 的串口 broker |
| 本地 headless | `python -I core/cli.py --lvgl 9.6 --scenario ...` | 同样 `--lvgl 9.6` |
| 导出副本 headless | `LVGL_AI_USER_APP_DIR=... core/cli.py --lvgl 9.4 ...` | `LVGL_AI_USER_APP_DIR=... core/cli.py --lvgl 9.6 ...` |
| 体积 | SCons map / 手动 | `idf.py size` / `idf.py size-components` |

ESP32-S3 的导出副本是 9.6 基线，所以本地 headless 和导出副本可以用同一个 `--lvgl 9.6`；这比 SiFli 的 9.6/9.4 双基线简单。ESP32 导出器按 9.6 专用 API 生成，不把 9.4 兼容作为默认约束；同一应用要双端导出时另做变体。

### 6.8 上位机

现有 `chip-adapt/sifli/host/` 是串口 + 烧录上位机：一个 broker 独占 COM 口，网页、CLI、AI 读同一份带序号的字节流。ESP32-S3 版本建议：

- **构建**：调用 `idf.py build`，捕获 `build.log`；返回 JSON（成功/失败、文件、尺寸、耗时、日志尾部）。
- **烧录**：调用 `idf.py -p COMx -b 921600 flash`，捕获 `flash.log`；或直接用 `esptool`。
- **监视**：`idf.py monitor` 是交互式的，不适合 AI 直接消费；建议复用现有 broker 的串口读取，把字节流写进日志/会话证据，网页端用 xterm.js 看同一份流。
- **不做判定**：host 只返回证据（构建日志、烧录日志、串口日志、`idf.py size` 输出），不输出 pass/fail、baseline、approval、acceptance。
- **不引入第二套协议实现**：网页、CLI、AI 仍然共用同一个 broker 和 job 模型；ESP32-S3 只是换一个构建/烧录后端。
- **环境**：host 必须从 EIM 激活的终端继承 `IDF_PATH` / `IDF_TOOLS_PATH` / `PATH`；不要把 IDF 路径硬编码进代码，路径从 `layout.py` 或环境变量取。

---

## 7. 落地步骤（后续计划，当前未授权实施）

以下内容只是调研后的实现计划；**用户当前只要求调研，未授权实现导出器/上位机**。等确认具体整板型号后再执行。

### 阶段 0：环境与板级点亮

1. 用 EIM 安装 ESP-IDF v6.1（或 v5.5.6），确认 `idf.py --version`。
2. 用官方 `hello_world` 验证 `idf.py set-target esp32s3`、`build`、`flash`、`monitor`。
3. 选屏和触摸，拿到屏厂初始化序列、SPI/QSPI/RGB 时序、亮度命令、TE 行为、触摸 I2C 地址/INT 引脚。
4. 写一个最小 `app_main`：`lvgl_port_init` + panel + `lvgl_port_add_disp` + touch，显示纯色/棋盘，确认颜色顺序、字节序、旋转、触摸坐标。
5. 用 `idf.py size` 记录基线 RAM/flash。

### 阶段 1：导出器

1. 新建 `chip-adapt/esp32/adapter.json`：
   ```json
   {
     "schema": "lvgl-ai-chip-adapter-v1",
     "chip": "esp32s3",
     "name": "ESP32-S3 (CO5300 QSPI)",
     "board": "esp32s3",
     "sdk_version": "v6.1",
     "lvgl_version": "9.6",
     "screen": {"width": 390, "height": 450},
     "compat_lvgl_minor": 6,
     "build_command": ["idf.py", "build"],
     "templates": "templates",
     "panel_driver": "espressif/esp_lcd_co5300",
     "touch_driver": "espressif/esp_lcd_touch_cst816s"
   }
   ```
2. `layout.py` 增加 `ESP32_ADAPTER_DIR`、`ESP32_EXPORTS_DIR`、`IDF_PATH` 解析；不硬编码导出目录。
3. `export.py` 复用 SiFli 的公共逻辑（`common._read_source`、`_replace_bytes`、`registry.parse_app_entries`），但模板、资源、诊断独立。
4. 模板生成：
   - 顶层 `CMakeLists.txt`、`main/CMakeLists.txt`、`main/idf_component.yml`；
   - `sdkconfig.defaults`、`sdkconfig.defaults.esp32s3`；
   - `partitions.csv`；
   - `app_main.c`、`app/app.c`、`app/lvgl_ai_esp.h`；
   - `assets.h/.c` 或图片生成规则；
   - `export.json`、`README.md`。
5. 源码复制：和 SiFli 一样，在每个 `.c` 顶部插入 `#include "lvgl_ai_esp.h"`；按 9.6 基线做 API 扫描。若同一应用还要导出 SiFli（9.4），由应用侧另做变体，不在 ESP32 导出器里做 9.4 兼容。
6. 资源：把 `assets.json` 映射成 ESP32-S3 的资源计划；先支持 `mode=raw` / `c_array`，遇到 `mode=ezip` 给明确诊断，不生成会编译失败的工程。
7. 测试：不依赖 IDF 的契约测试，覆盖文件集合、版本锁定、资源符号、错误路径、导出副本自包含。

### 阶段 2：上位机

1. 新建 `chip-adapt/esp32/host/`（或把现有 host 抽象成后端），实现 `build` / `flash` / `monitor`。
2. `build` 前自动跑 `export.py`，和 SiFli host 的 `--app` 行为一致。
3. 从环境继承 IDF 工具链；不要在代码里写死 `C:\Espressif` 之类的路径。
4. 捕获日志、返回 JSON；串口流复用 broker。
5. 测试用 fake `idf.py` 和 fake serial，不需要真板。

### 阶段 3：验证回路

1. 源目录 headless：`python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/<app>.json`。
2. 导出副本 headless：`LVGL_AI_USER_APP_DIR=<export>/main/app python -I core/cli.py --lvgl 9.6 --scenario ...`。
3. 目标构建：`idf.py build`，检查 `idf.py size`。
4. 烧录 + 串口：`idf.py -p COMx flash monitor` 或 host。
5. 取证：build.log、flash.log、串口日志、会话证据；工具不做判定，由人类在聊天里给验收标准。

### 验证入口（建议）

```bash
# 导出器契约测试
python -I chip-adapt/esp32/run_tests.py

# 上位机测试
python -I chip-adapt/esp32/host/tests/run_tests.py

# 导出 dry-run
python -I chip-adapt/esp32/export.py <app> --dry-run --force

# 本地 headless
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/<app>.json

# 导出副本 headless
LVGL_AI_USER_APP_DIR="$PWD/chip-adapt/exports/esp32/<app>/main/app" \
  python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/<app>.json

# 构建
python -I chip-adapt/esp32/host/cli.py build --app <app> --actor ai --json
```

---

## 8. 风险与未决问题

### 8.1 需要用户确认（板型/屏幕/触摸/引脚）

1. **最终板型（已确定形态，型号待定）**：用户选择一体化 ESP32-S3 触摸屏开发板；默认候选 Waveshare ESP32-S3-Touch-AMOLED-1.8（V2），竖屏备选 Waveshare 2.06（注意其 BSP 2.0.0 源码仍用 SH8601 驱动，与产品页的 CO5300 不一致），圆形备选 Waveshare 1.75 / 1.43（注意 1.75/2.16 的 BSP 用 `esp_lvgl_adapter`，不是 `esp_lvgl_port`），官方 BSP 备选 ESP32-S3-LCD-EV-Board，性价比备选 Guition JC3248W535。请提供实际板型型号和 V1/V2 版本。
2. **屏幕模组**：具体 390x450 CO5300 模组的型号/屏厂、初始化序列、QSPI 最高时钟、亮度控制、TE 引脚；如果不用 390x450，明确实际分辨率（368x448、466x466、480x480、240x280 等）。
3. **触摸**：FT6146 是否用 `esp_lcd_touch_ft5x06` 驱动，还是要自研/找其他组件？CST820/CST816S/CST816T/CST9217/CST9220/CST3530/CST328/FT3168/AXS15231B 都要确认具体型号、I2C 地址、INT、坐标映射。
4. **引脚**：SPI/QSPI 的 SCLK/MOSI/D0–D3/CS/DC/RST/BL，I2C 的 SCL/SDA/INT/RST；如果定制一体化板，需给出屏/触摸的 FPC 定义和主控引脚；如果只是拿开发板调试，也要给排针图并避开 GPIO35–37、strapping、USB 引脚。
5. **PSRAM 容量/模式**：8 MB 还是 16 MB；Octal 还是 Quad；是否接受 80 MHz（不要默认 120 MHz Octal）。
6. **屏幕接口**：SPI、QSPI、I80 还是 RGB？这直接决定带宽、引脚数和 buffer 策略。
7. **LVGL 基线（已确定）**：用户选择 ESP32 专用 9.6 API；ESP32 导出器按 9.6 扫描/生成，不默认兼容 SiFli 9.4。需要双端导出时另做应用变体。
8. **资源 schema**：`assets.json` 是扩展 `mode`，还是新增 `assets.esp32.json`，还是升级成多目标 schema？
9. **导出目录**：`exports/esp32/<app>/` 加法式，还是把 SiFli 也重构成 `exports/<chip>/<app>/`？
10. **IDF 安装**：EIM 系统级安装（推荐），还是在 `chip-adapt/vendor/esp-idf/` 放固定版本？
11. **上位机**：新建 `chip-adapt/esp32/host/`，还是把现有 SiFli host 抽象成多后端？
12. **IDF 版本**：建议从 v6.1（当前 stable）起步；若板厂 BSP 或面板驱动在 6.1 上构建失败，退回 v5.5.6（最新 bugfix）。

### 8.2 未核实 / 冲突

| 项 | 状态 | 说明 |
| --- | --- | --- |
| FT6146 是否被 `esp_lcd_touch_ft5x06` 支持 | **未核实** | Espressif Registry 只写 FT5x06；Waveshare 1.43 的产品页标 FT3168/FT6146，但触摸驱动兼容性要实测。 |
| 390x450 CO5300 模组初始化序列 | **未核实** | 驱动是通用的，具体 gamma/电压/亮度命令要按屏厂资料。 |
| CO5300 QSPI 能否稳定跑 80 MHz | **未核实** | 官方宏默认 40 MHz；80 MHz 取决于屏、FPC、PCB。 |
| 390x450@60 fps 是否可达 | **未核实** | 4.4 只是带宽估算；要实测。 |
| Waveshare BSP 覆盖 | **部分覆盖** | 板厂 BSP 仓库有 1.8（2.0.3）、1.69（2.0.0）、1.75（3.0.1）、2.06（2.0.0）、2.16（2.0.1）；1.28/1.43/2.1/2.8/2.8C/3.5 未见组件，需要自己接 `esp_lcd`/`esp_lvgl_port`。 |
| Waveshare 1.75/2.16 的适配层 | **与 `esp_lvgl_port` 不同** | 1.75 BSP 3.0.1、2.16 BSP 2.0.1 依赖 `espressif/esp_lvgl_adapter` ~0.6（IDF >=5.5.5），不是 `esp_lvgl_port`；要统一到 `esp_lvgl_port` 需改 BSP 或自己初始化。 |
| Waveshare 2.06 的面板驱动 | **源码与产品页不一致** | BSP 2.0.0 依赖 `waveshare/esp_lcd_sh8601`，源码用 SH8601 初始化序列；产品页写 CO5300。买板后确认驱动 IC；若为 CO5300，用 `esp_lcd_co5300` 自行初始化。 |
| Waveshare 2.16 触摸型号 | **厂商资料不一致** | 产品页写 CST9220，BSP 2.0.1 依赖 `waveshare/esp_lcd_touch_cst9217`；兼容性要实测。 |
| LilyGO T-Display-S3-Touch 触摸型号 | **按实物确认** | 厂商示例用宏切换 CST328 / CST816；买板/写驱动前必须确认实物。 |
| LilyGO AMOLED 的 ESP-IDF 支持 | **厂商示例为主** | Arduino 示例已用 LVGL 9；ESP-IDF 示例在单独的 `LilyGo-Display-IDF` 仓库，未在 esp-bsp 核实。 |
| M5Dial 的 PSRAM | **已核实：无 PSRAM** | M5Stack 规格表是 S3FN8 + 8 MB Flash，没有 PSRAM；只适合 240x240 轻量 UI。 |
| ESP32-S3-BOX-3 的内存 | **已核实** | 16 MB Quad flash + 16 MB Octal PSRAM（Espressif 硬件概览）。 |
| JC3248W535 的板级规格 | **厂商页 + 待实物确认** | Guition 官方页写 16 MB flash / 8 MB PSRAM / 320x480 / AXS15231B；板级初始化/引脚以实物和 schematic 为准。 |
| `esp-bsp` 的统一版本号 | **不存在** | 各 BSP 组件独立版本；README 只给 IDF 兼容表。 |
| LVGL 文档说 `esp_lvgl_port` 支持 IDF 4.4+ | **与组件清单冲突** | LVGL 集成页写 “compatible with ESP-IDF v4.4 and above”；`esp_lvgl_port` 2.9.0 的 `idf_component.yml` 写 `idf >=5.2`。以组件清单为准，建议 >=5.2。 |
| `install.bat` / `export.bat` | **v6.1 页面未提及** | v6.1 Windows 安装页只描述 EIM；v5.5 页面用 ESP-IDF Tools Installer + `export.bat`，未见 `install.bat` 说明。不要按旧教程操作 v6.1。 |
| IDF 6.x 的 `IDF_BUILD_V2` | **只观察到组件适配** | `esp_lvgl_port` 的 CMakeLists 有 `IDF_BUILD_V2` 分支和 `CMakeLists_v2.txt`；ESP-IDF 官方文档未在本次调研中展开。第三方组件未必适配。 |

### 8.3 技术风险

1. **SPI 屏带宽不足**：390x450 用普通 SPI，40/80 MHz 只能到约 14/28 fps 的理论上限；不要承诺全屏 60 fps。
2. **QSPI 默认 40 MHz 卡边界**：368x448 或 390x450 在 40 MHz QSPI 下刚好接近 60 fps 理论上限，实际很难稳定；需要 80 MHz 或局部刷新。
3. **S3 无 PPA**：旋转/缩放/混合退回软件，黄山派上 EPIC 的效果不能直接照搬；大图旋转会明显掉帧。
4. **PSRAM 带宽与总线共享**：PSRAM 和 flash 共用 MSPI；RGB framebuffer、Wi-Fi、文件系统、LVGL 同时跑会互相挤占。
5. **RGB framebuffer 吃内存**：390x450 单帧 351 KB，双缓冲 702 KB；480x480 单帧 460.8 KB，双缓冲 921.6 KB。8 MB PSRAM 够，但要给 Wi-Fi/文件系统留余量。
6. **Flash 分区**：默认 app 1 MB 不够；需要自定义分区表和足够大的 flash（16 MB 起）。
7. **LVGL 9.6 + IDF 6.1 组合较新**：`esp_lvgl_port` 2.9.0 已适配，但其他第三方组件未必；首次构建要留时间排错。
8. **双目标基线**：用户已选择 ESP32 专用 9.6 API；若同一应用要同时导出 SiFli 9.4，需要两套变体，不能指望同一份源码零改动。
9. **资源转换依赖**：`lvgl_port_create_c_image` 构建期会 pip 安装 `pypng`/`lz4`；离线构建或自动化构建环境要预装，或改成导出期生成。
10. **触摸/旋转对齐**：panel 的 `swap_xy`/`mirror` 与 touch 的 `swap_xy`/`mirror` 必须匹配；否则点击坐标会偏。
11. **颜色格式**：RGB565 vs RGB565_SWAPPED、`swap_bytes`、panel `rgb_ele_order` 三者要对齐；错了就是红蓝互换或花屏。
12. **Waveshare 版本差异**：1.8 有 V1（SH8601/FT3168）和 V2（CO5300/CST820）；1.43 产品页标 FT3168/FT6146；买板前确认版本。

---

## 9. 真源索引

### ESP-IDF / ESP32-S3

| 主题 | 链接 |
| --- | --- |
| 文档首页 / stable 版本 | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/index.html |
| 版本与发布策略 | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/versions.html |
| 构建系统（component/CMake/EMBED_FILES） | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/build-system.html |
| `idf.py` 前端 | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/idf-py.html |
| Windows 安装（EIM） | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html |
| Windows 命令行启动项目 | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-start-project.html |
| Windows 安装（v5.5，export.bat 旧流程） | https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/get-started/windows-setup.html |
| 可下载工具与 `idf_tools.py` | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/idf-tools.html |
| Kconfig / sdkconfig.defaults | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/kconfig/configuration_structure.html |
| 分区表 | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/partition-tables.html |
| S3 LCD 总览 | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/index.html |
| SPI LCD | https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/lcd/spi_lcd.html |
| I80 LCD（S3） | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/i80_lcd.html |
| RGB LCD（S3） | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html |
| S3 SPI Master（DMA、PSRAM 直传） | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/spi_master.html |
| S3 External RAM | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/external-ram.html |
| S3 PSRAM Kconfig | https://github.com/espressif/esp-idf/blob/master/components/esp_psram/esp32s3/Kconfig.spiram |
| S3 SoC caps | https://github.com/espressif/esp-idf/blob/master/components/soc/esp32s3/include/soc/Kconfig.soc_caps.in |
| S3 soc_caps.h（GDMA/LCD/PSRAM） | https://github.com/espressif/esp-idf/blob/master/components/soc/esp32s3/include/soc/soc_caps.h |
| esp_lcd CMakeLists | https://github.com/espressif/esp-idf/blob/master/components/esp_lcd/CMakeLists.txt |
| ESP-IDF Releases | https://github.com/espressif/esp-idf/releases |

### Component Manager / Registry

| 主题 | 链接 |
| --- | --- |
| `idf_component.yml` manifest | https://docs.espressif.com/projects/idf-component-manager/en/latest/reference/manifest_file.html |
| 版本规则（`~revision`） | https://docs.espressif.com/projects/idf-component-manager/en/latest/reference/versioning.html |
| `lvgl/lvgl` 组件 | https://components.espressif.com/components/lvgl/lvgl |
| `espressif/esp_lvgl_port` | https://components.espressif.com/components/espressif/esp_lvgl_port |
| `espressif/esp_lvgl_adapter` | https://components.espressif.com/components/espressif/esp_lvgl_adapter |
| `espressif/esp_lcd_touch` | https://components.espressif.com/components/espressif/esp_lcd_touch |
| `espressif/esp_lcd_co5300` | https://components.espressif.com/components/espressif/esp_lcd_co5300 |
| `espressif/esp_lcd_gc9a01` | https://components.espressif.com/components/espressif/esp_lcd_gc9a01 |
| `espressif/esp_lcd_ili9341` | https://components.espressif.com/components/espressif/esp_lcd_ili9341 |
| `espressif/esp_lcd_touch_ft5x06` | https://components.espressif.com/components/espressif/esp_lcd_touch_ft5x06 |

### LVGL

| 主题 | 链接 |
| --- | --- |
| LVGL 仓库 | https://github.com/lvgl/lvgl |
| LVGL Releases | https://github.com/lvgl/lvgl/releases |
| LVGL v9.6.0 Kconfig | https://github.com/lvgl/lvgl/blob/v9.6.0/Kconfig |
| LVGL v9.6.0 `lv_conf_internal.h` | https://github.com/lvgl/lvgl/blob/v9.6.0/include/lvgl/config/lv_conf_internal.h |
| LVGL ESP-IDF CMake（源码编译） | https://github.com/lvgl/lvgl/blob/master/env_support/cmake/esp.cmake |
| LVGL ESP32 集成总览 | https://lvgl.io/docs/open/integration/chip_vendors/espressif/overview |
| LVGL 加入 ESP-IDF 项目 | https://lvgl.io/docs/open/integration/chip_vendors/espressif/add_lvgl_to_esp32_idf_project |
| LVGL PPA 支持（仅 P4） | https://lvgl.io/docs/open/integration/chip_vendors/espressif/hardware_accelerator_ppa |
| LVGL DMA2D 支持（P4） | https://lvgl.io/docs/open/integration/chip_vendors/espressif/hardware_accelerator_dma2d |

### esp-bsp / esp_lvgl_port

| 主题 | 链接 |
| --- | --- |
| esp-bsp 仓库 | https://github.com/espressif/esp-bsp |
| esp-bsp README（板型/IDF 兼容表） | https://github.com/espressif/esp-bsp/blob/master/README.md |
| esp_lvgl_port README | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/README.md |
| esp_lvgl_port CMakeLists | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/CMakeLists.txt |
| esp_lvgl_port idf_component.yml | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/idf_component.yml |
| esp_lvgl_port 主头文件 | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/include/esp_lvgl_port.h |
| esp_lvgl_port display 头文件 | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/include/esp_lvgl_port_disp.h |
| esp_lvgl_port 主循环源码 | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/src/lvgl9/esp_lvgl_port.c |
| esp_lvgl_port flush 源码 | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/src/lvgl9/esp_lvgl_port_disp.c |
| esp_lvgl_port touch 源码 | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/src/lvgl9/esp_lvgl_port_touch.c |
| esp_lvgl_port 性能指南 | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/docs/performance.md |
| esp_lvgl_port Changelog | https://github.com/espressif/esp-bsp/blob/master/components/esp_lvgl_port/CHANGELOG.md |
| LCD/触摸驱动列表 | https://github.com/espressif/esp-bsp/blob/master/docu/LCD.md |
| esp_lcd_touch 头文件 | https://github.com/espressif/esp-bsp/blob/master/components/lcd_touch/esp_lcd_touch/include/esp_lcd_touch.h |
| S3-LCD-EV BSP manifest | https://github.com/espressif/esp-bsp/blob/master/bsp/esp32_s3_lcd_ev_board/idf_component.yml |
| ESP-BOX-3 BSP manifest | https://github.com/espressif/esp-bsp/blob/master/bsp/esp-box-3/idf_component.yml |
| Generic BSP manifest | https://github.com/espressif/esp-bsp/blob/master/bsp/esp_bsp_generic/idf_component.yml |

### 开发板文档

| 主题 | 链接 |
| --- | --- |
| ESP32-S3-DevKitC-1 v1.1 | https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html |
| ESP32-S3-LCD-EV-Board | https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-lcd-ev-board/user_guide.html |
| Waveshare 产品页（S3 板型总表） | https://www.waveshare.com/esp32-s3-touch-lcd-2.1.htm |
| Waveshare ESP32-S3-Touch-AMOLED-1.8 | https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8 |
| Waveshare ESP32-S3-Touch-AMOLED-1.43 | https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.43 |
| Waveshare ESP32-S3-Touch-LCD-1.69 | https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.69 |
| Waveshare ESP32-S3-Touch-LCD-1.28 | https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.28 |
| Waveshare BSP 仓库 | https://github.com/waveshareteam/waveshare-esp32-components |
| Waveshare AMOLED-1.8 BSP manifest | https://github.com/waveshareteam/waveshare-esp32-components/blob/master/bsp/esp32_s3_touch_amoled_1_8/idf_component.yml |
| Waveshare LCD-1.69 BSP manifest | https://github.com/waveshareteam/waveshare-esp32-components/blob/master/bsp/esp32_s3_touch_lcd_1_69/idf_component.yml |
| Waveshare ESP32-S3-Touch-AMOLED-1.75 | https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75 |
| Waveshare ESP32-S3-Touch-AMOLED-2.06 | https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-2.06 |
| Waveshare ESP32-S3-Touch-LCD-2.8 | https://docs.waveshare.com/ESP32-S3-Touch-LCD-2.8 |
| Waveshare ESP32-S3-Touch-LCD-2.8C | https://docs.waveshare.com/ESP32-S3-Touch-LCD-2.8C |
| ESP-BOX-3 硬件概览 | https://github.com/espressif/esp-box/blob/master/docs/hardware_overview/esp32_s3_box_3/hardware_overview_for_box_3.md |
| M5Dial 规格 | https://docs.m5stack.com/en/core/M5Dial |
| M5Stack CoreS3 规格 | https://docs.m5stack.com/en/core/CoreS3 |
| LilyGO T-Display-S3 | https://github.com/Xinyuan-LilyGO/T-Display-S3 |
| LilyGO AMOLED Series | https://github.com/Xinyuan-LilyGO/LilyGo-AMOLED-Series |
| LilyGO ESP-IDF 示例 | https://github.com/Xinyuan-LilyGO/LilyGo-Display-IDF |
| Guition JC3248W535 产品页 | https://www.guition.com/esp32-display-module/3-5-inch-esp32s3-display-module |
| Espressif AXS15231B 组件 | https://components.espressif.com/components/espressif/esp_lcd_axs15231b |
