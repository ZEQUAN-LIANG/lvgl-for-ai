# 黄山派（SiFli SF32LB52x）适配

把 `user/app/` 下的 LVGL 9.6 应用导出为黄山派 SiFli-SDK 工程。导出产物放在本目录的
`<app>/` 子目录，不写入下载的 SDK。

## 目标平台

| 项 | 值 |
| --- | --- |
| 开发板 | 立创黄山派，板名 `sf32lb52-lchspi-ulp` |
| SoC | SF32LB52x（HCPU，RT-Thread） |
| SDK | SiFli-SDK v2.5.1，下载到 `chip-adapt/sdk/sifli-sdk`（Gitee `SiFli/sifli-sdk`，release/v2.5） |
| LVGL | 9.4.0（SDK 内 `external/lvgl_v9`） |
| 屏幕 | CO5300，390x450，触摸 FT6146 |
| 固件构建 | `scons --board=sf32lb52-lchspi-ulp -j8`（需先运行 SDK 的 `set_env.bat` / `source export.sh`） |

## 导出产物结构

```
<app>/
  SConstruct
  project/{SConscript,Kconfig,Kconfig.proj,proj.conf,rtconfig.py}
  src/
    SConscript
    main.c                  # SDK 入口
    app/
      app.c                 # 固定入口，调用 <app>_create(lv_screen_active())
      app.h, lvgl_compat.h  # 从 user/app 复制
      lvgl_ai_sdk.h         # SDK 头或模拟桩的二选一入口
      sim_sifli.h/.c        # 仅运行时验证使用；SDK 构建排除
      <app>/...             # 应用源码原样副本（应用需兼容 LVGL 9.4）
  src/ezip/                 # ezip.exe 生成的 EZIP C 数组（SDK 构建编译）
```

## 图片资源与 EZIP

应用把 PNG 源放在 `user/app/<app>/assets/*.png`。导出时 `ezip.exe` 自动把每张 PNG 转成
EZIP C 数组：

```text
ezip -convert <png> -rgb565 -cfile 2 -section ROM3_IMG -lvgl_version 9 -outdir <tmp>
```

导出目录产生 `src/ezip/<name>.c` 和 `src/app/<app>/assets_ezip.h`。SDK 构建中
`lvgl_ai_sdk.h` 定义 `LVGL_AI_EZIP_ASSETS`，应用 include `assets_ezip.h`；本地运行时
构建不定义该宏，应用使用 `watch_assets.h` 里的 PNG/像素数组。应用代码的切换方式：

```c
#if defined(LVGL_AI_EZIP_ASSETS)
#include "assets_ezip.h"
#else
#include "watch_assets.h"
#endif
```

`src/main.c` 是 SDK 入口：

```c
littlevgl2rtt_init("lcd");
app_create();
while (1) {
    rt_uint32_t ms = lv_task_handler();
    rt_thread_mdelay(ms);
}
```

`littlevgl2rtt_init` 自动注册 LCD、触摸、按键和 FPS 统计，应用不需要自己调用
`lv_init`、`lv_display_create` 或注册 flush/read 回调。

## 应用基线：直接按 LVGL 9.4 编写

导出**不做源码降级**。应用必须直接使用 LVGL 9.4 可用的 API；版本门建议写成
`LVGL_VERSION_MINOR >= 4`，这样本地 9.6 预览和导出 9.4 都能编译。导出只做两件事：

- 原样复制应用源码，并在每个 `.c` 顶部插入 `#include "lvgl_ai_sdk.h"`（SDK/模拟头入口）
- 扫描 9.5/9.6-only API，发现时返回 `unsupported_api`，不生成会编译失败的工程

会被拒绝的符号：

- `lv_obj_set_clickable`、`lv_obj_set_scrollable`、`lv_obj_set_hidden`、`lv_obj_is_hidden`
- `lv_draw_line_dsc_t` 的 `.points` / `.point_cnt` 多段线绘制

`hspi_watch` 是按 9.4 基线写的示例；`coffee` 等 9.6 应用导出时会得到诊断而不是自动改写。

## 导出命令

适配层自带的脚本：

```bash
python -I chip-adapt/sifli/export.py hspi_watch --dry-run
python -I chip-adapt/sifli/export.py hspi_watch
```

导出、源码复制和 EZIP 转换全部在适配脚本里，`core/` 不包含芯片导出逻辑。

## 运行时验证（不烧录）

导出产物可以在本仓库的 headless 运行时上跑通，SDK 专有函数由 `sim_sifli` 桩处理：

```bash
LVGL_AI_USER_APP_DIR="$PWD/chip-adapt/sifli/hspi_watch/src/app" \
  python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/hspi_watch.json
```

`lvgl_ai_sdk.h` 用 `__has_include("littlevgl2rtt.h")` 判断环境：SDK 构建拿真实头，
运行时验证拿 `sim_sifli.h`。桩只用于验证，不代表 EPIC、触摸或真实刷新行为。

## 高帧率：SF32LB52x 实际加速能力

| 能力 | 52x 可用 | 说明 |
| --- | --- | --- |
| EPIC 2D | 是 | 填充、图片旋转/缩放、掩码、A2/A4/A8/L8、YUV、字体合成 |
| EZIP 硬件解压 | 是 | 大图/动画优先转 EZIP，EPIC 直接解码合成 |
| LCDC | 是 | 异步刷屏，PSRAM framebuffer |
| GE2D / DMA2D | 否 | SDK 无对应驱动 |
| VGLITE / V2D GPU | 否 | 仅 SF32LB58x |
| 硬件 JPEGD | 否 | 仅 SF32LB57x（`LV_USE_SIFLI_JPEGD`） |

模板 `proj.conf` 已启用：

```ini
CONFIG_LV_DEF_REFR_PERIOD=16
CONFIG_CONFIG_LV_OS_RTTHREAD=y
CONFIG_LV_FB_TWO_NOT_SCREEN_SIZE=y
CONFIG_LV_FB_LINE_NUM=100
CONFIG_LV_USE_EZIP=y
CONFIG_IMAGE_CACHE_IN_PSRAM_SIZE=1048576
CONFIG_ROTATE_MEM_IN_PSRAM=y
```

`LV_USE_DRAW_EPIC` 由 `lv_conf_sifli.h` 在板级 `CONFIG_BSP_USING_EPIC=y` 时强制开启，
不要写不存在的 `LV_USE_DRAW_SIFLI`。

### AI 写 UI 的高帧率规则

1. 大图、背景、动画帧先转 EZIP：
   `tools/png2ezip/ezip.exe -convert x.png -rgb565 -binfile 2 -binext .ezip -lvgl_version 9`，
   运行时 `lv_image_set_src(img, "A:/x.ezip")`。
2. 旋转/缩放的图片先复制到 RAM（`app_cache_copy_alloc(..., ROTATE_MEM)`），不要直接旋转
   Flash 上的图。
3. 只失效变化区域：`lv_obj_invalidate_area()`；重活挂到 `LV_EVENT_REFR_START` 或只在
   数值变化时执行。
4. 动画区域避免圆角、阴影、圆弧、复杂渐变，这些会回退到软件绘制。
5. 用 `lv_get_fps()`、`set_display_fps_and_cpu_load(1)`、串口 `fps2` 测量，不猜。
6. 不要使用 52x 不存在的加速 API（`LV_USE_VGLITE`、GE2D、硬件 JPEG）。

## 已知限制

- 本机未安装 SiFli-ENV/ARM 工具链，`scons` 固件构建未在导出流程中执行。
- 黄山派实际屏幕 390x450；非 390x450 设计的应用需要自行适配布局。
- `coffee` 等 9.6 应用不导出；导出器会返回 `unsupported_api` 诊断。
- EZIP 转换依赖 SDK 的 `tools/png2ezip/ezip.exe`（Windows）；其他平台使用同目录的 `ezip_linux` / `ezip_mac` 需另行适配。
- `hspi_watch` 是 390x450 的表盘示例，本地运行时验证使用 PNG 像素数组，真机使用 EZIP。
