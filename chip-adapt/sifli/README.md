# 黄山派（SiFli SF32LB52x）适配

把 `user/app/` 下的 LVGL 9.6 应用导出为黄山派 SiFli-SDK 工程。导出产物放在本目录的
`<app>/` 子目录，不写入下载的 SDK。

## 目标平台

| 项 | 值 |
| --- | --- |
| 开发板 | 立创黄山派，板名 `sf32lb52-lchspi-ulp` |
| SoC | SF32LB52x（HCPU，RT-Thread） |
| SDK | SiFli-SDK v2.5.1，下载到 `chip-adapt/sifli/vendor/sifli-sdk`（Gitee `SiFli/sifli-sdk`，tag `v2.5.1`） |
| LVGL | 9.4.0（SDK 内 `external/lvgl_v9`） |
| 屏幕 | CO5300，390x450，触摸 FT6146 |
| 固件构建 | `cd project && scons --board=sf32lb52-lchspi-ulp -j8`（需先运行 SDK 的 `./export.ps1` / `source export.sh`） |

SDK、示例、工具链、烧录工具、原理图和数据手册都在 `vendor/`，清单见
`vendor/README.md`；这些是外部下载物，已被 `.gitignore` 忽略，不进入版本库。

## 串口与烧录上位机

`host/` 是黄山派的串口 + 烧录上位机（Python broker + xterm.js 网页 + CLI）：一个 broker
独占 COM 口，网页、CLI、AI 读同一份带序号的字节流；人类和 AI/CLI 共用 `/api/flash` job，
底层官方 `sftool.exe`。页面是终端优先的 Tabby 风格，顶部只有“终端 / 活动”标签，终端上方
是烧录 dock（PROJECT / BUILD、构建 / 仅烧录 / 构建并烧录、进度条）；`app` 从 project
路径推导，project / build / port / baud 由 `/api/suggest` 自动填。串口意外断开和 web
烧录后默认自动重连；旧 `/tools/sftool/` 官方页仅保留路由，主 UI 无入口。

```powershell
# 检查/补齐依赖（pyserial、xterm.js、SDK uv lock 环境）
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/bootstrap.ps1

python -I chip-adapt/sifli/host/server.py --open
# 或双击无黑框入口
chip-adapt/sifli/host/open-host.vbs
```

串口默认 `1000000` 波特率；依赖细节见 `host/ENVIRONMENT.md`，CLI、HTTP API 和构建环境
见 `host/README.md`。

## 共享源码与目标专属生成层

`user/app/hspi_watch` 是唯一源码真源：本地 headless（LVGL 9.6）直接编译它，导出时按
LVGL 9.4 基线原样复制到 `<app>/src/app/hspi_watch/`，只在每个 `.c` 顶部插入
`#include "lvgl_ai_sdk.h"`。共享应用只暴露 `void hspi_watch_create(void)`；
headless 的 `app_create`、SDK 的 `app_create` / `main.c` 和 `user/app/app.c` 的注册表
都属于目标侧，不进入共享源码。

导出目录完全自包含，只依赖 SiFli SDK；`chip-adapt/sifli/<app>/` 是生成物，已被
`.gitignore` 忽略，不进入版本库。

资源层是目标专属生成层：本地 `assets.h` 转发到静态 C 数组头（例如
`watch_assets.h`），导出的 `src/app/<app>/assets.h` 在 SDK 分支声明 EZIP/raw 符号、
`app_assets_init()` 和从 PNG IHDR 生成的 `<NAME>_W` / `<NAME>_H` 尺寸宏；只有本地
运行时分支才 include 静态资源头。两端暴露相同图片符号和 `WATCH_*` 尺寸宏，应用代码
只写 `#include "assets.h"`，不写平台分支。

## 导出产物结构

```
<app>/
  project/
    SConstruct              # 官方结构；从 project/ 里执行 scons
    SConscript,Kconfig,Kconfig.proj,proj.conf,rtconfig.py
  src/
    SConscript
    main.c                  # SDK 入口
    app/
      app.c                 # 固定入口：app_assets_init(); <app>_create();
      assets.h/.c           # 生成的资源层
      app.h, lvgl_compat.h  # 从 user/app 复制
      lvgl_ai_sdk.h         # SDK 头或模拟桩的二选一入口
      sim_sifli.h/.c        # 仅运行时验证使用；SDK 构建排除
      <app>/
        assets.json         # 资源清单副本
        assets.h/.c         # 生成的资源层（覆盖本地包装头）
        ...                 # 应用源码原样副本（应用需兼容 LVGL 9.4，入口为 void）
    ezip/<name>.c           # 冷 EZIP C 数组
    raw/<name>.c            # 热/旋转 raw 像素 C 数组
  export.json               # 资源角色、PNG 宽高、缓存配置与生成结果
```

## 图片资源与 assets.json

应用把 PNG 源放在 `user/app/<app>/assets/*.png`，并在 `user/app/<app>/assets.json`
声明每张图的角色：

```json
{
  "schema": "lvgl-ai-assets-v1",
  "local_header": "watch_assets.h",
  "assets": {
    "watch_bg":   {"file": "watch_bg.png",   "mode": "ezip", "placement": "flash", "transform": "none"},
    "watch_hour": {"file": "watch_hour.png", "mode": "raw",  "placement": "psram", "transform": "rotate"}
  },
  "cache": {"image_cache_psram_size": 524288, "rotate_mem": "psram"}
}
```

- `mode=ezip`：构建期转成 EZIP C 数组，放 `src/ezip/`，运行时由 EPIC 解码；不能旋转/缩放。
- `mode=raw`：构建期转成 raw 像素 C 数组，放 `src/raw/`；`placement=psram/sram` 时生成
  `app_assets_init()`，用 `app_cache_copy_alloc()` 把热图复制到 PSRAM/SRAM。
- `mode=ezip` 且 `transform != none` 会直接报 `asset_transform_conflict`，不会生成错误工程。
- 未在 `assets.json` 里声明的 PNG 会报 `asset_unlisted`；文件名必须与资源名一致。
- PNG 不是有效 IHDR 或宽高为 0 会报 `asset_invalid`，不会把坏图交给 `ezip.exe`。
- 资源名大写后重复（例如 `foo` 与 `FOO` 都会生成 `FOO_W` / `FOO_H`）会报
  `asset_macro_conflict`，导出直接失败而不是生成重复宏。
- `cache` 可覆盖脚本按资源大小算出的默认值；`image_cache_psram_size`、
  `image_cache_sram_size`、`rotate_mem`、`lv_cache_def_size`、
  `lv_image_header_cache_cnt` 都会写进 `project/proj.conf`。
- `export.json` 的 `assets` 记录每张资源的 `mode`、`placement`、`transform`、`hot`、
  `width`、`height` 和 `size`；`width` / `height` 来自 PNG IHDR，是生成 `_W` / `_H`
  尺寸宏的同一份资源元数据。

导出目录生成 `src/app/<app>/assets.h` 和 `assets.c`：

- SDK 构建（`LVGL_AI_EZIP_ASSETS`）声明 EZIP/raw 符号；热图通过
  `app_asset_<name>()` 返回 PSRAM/SRAM 副本。
- 本地运行时构建不定义该宏，`assets.h` 包含 `local_header` 指定的头（例如
  `watch_assets.h`），并提供空的 `app_assets_init()`。

应用代码只写 `#include "assets.h"`，不再自己判断 `LVGL_AI_EZIP_ASSETS`。

生成资源头的尺寸宏来自 PNG IHDR：资源名大写后加 `_W` / `_H`，例如
`watch_ring.png` 生成 `WATCH_RING_W` / `WATCH_RING_H`。导出模板把 `src/raw/*.c`
纳入编译，并把 `src/raw/` 加入 include 路径，旋转表针和圆环不会因缺 raw 源文件或
符号而链接失败。

导出脚本调用 `ezip.exe` 时会在临时目录里用相对文件名运行，并读取自动生成的
`output/<name>.c`；不再依赖 `-outdir`。常用参数是
`-convert <png> -rgb565 -cfile 2/1 -section ROM3_IMG/ROM2_IMG -lvgl_version 9 -chip sf52x`。

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

导出的 `src/app/app.c` 入口是 `void app_create(void)`；它先调用 `app_assets_init()`，
再调用 `void <app>_create(void)`。应用入口不接收 `lv_obj_t *`，内部用
`lv_screen_active()` 取屏幕。

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

导出、源码复制和 EZIP 转换全部在适配脚本里，`core/` 不包含芯片导出逻辑。导出的
README 和返回的验证命令使用 `adapter.json` 的 `lvgl_version`（当前 9.4）：导出工程跟随
SiFli SDK 的 LVGL 9.4 基线，而源目录本地预览仍用 9.6。

## 运行时验证（不烧录）

源目录用 LVGL 9.6 跑本地 headless：

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/hspi_watch.json
```

导出副本用 LVGL 9.4 跑同一场景；SDK 专有函数由 `sim_sifli` 桩处理：

```bash
LVGL_AI_USER_APP_DIR="$PWD/chip-adapt/sifli/hspi_watch/src/app" \
  python -I core/cli.py --lvgl 9.4 --scenario user/scenarios/hspi_watch.json
```

`lvgl_ai_sdk.h` 用 `__has_include("littlevgl2rtt.h")` 判断环境：SDK 构建拿真实头，
运行时验证拿 `sim_sifli.h`。桩只用于验证，不代表 EPIC、触摸或真实刷新行为。
`hspi_watch` 场景声明 390x450；两次运行都应得到 `status=ok`、`app=hspi_watch`、
`display=390x450`，并保留 timeline/snapshot 证据。

## 验证边界

- 导出契约测试可重复执行且不依赖 SiFli SDK：
  `python -I chip-adapt/sifli/test_export.py`。覆盖源码复制一致性、生成资源头尺寸宏与
  图片符号、raw 源收集、导出副本自包含和错误路径。
- 两次 headless 场景运行是手动验证步骤，不是测试套件的一部分：分别执行上文的源目录
  9.6 和导出副本 9.4 命令，以会话 `manifest.json` 的 `status=ok`、`app=hspi_watch`、
  `display=390x450` 以及保留的 timeline/snapshot 为证据。
- 需要 SDK 工具链：EZIP 解码、`scons` 固件构建/链接和真机显示。headless 通过只证明
  共享源码和本地静态资源回退可用，不等于设备验收。

## SF32LB52x 加速能力与资源规则

| 能力 | 52x 可用 | 说明 |
| --- | --- | --- |
| EPIC 2D | 是 | 填充、图片混叠/缩放/旋转（EZIP 仅混叠/缩放，不可旋转）、掩码、A2/A4/A8/L8、YUV、字体合成；渲染列表模式另支持圆角矩形、边框、圆弧、线、多边形、点阵字 |
| EZIP 硬件解压 | 是 | 大图/动画优先转 EZIP，EPIC 直接解码合成 |
| LCDC | 是 | 异步刷屏，PSRAM framebuffer |
| GE2D / DMA2D | 否 | SDK 无对应驱动 |
| VGLITE / V2D GPU | 否 | 仅 SF32LB58x |
| 硬件 JPEGD | 否 | 仅 SF32LB57x（`LV_USE_SIFLI_JPEGD`） |

模板 `proj.conf` 的基础项：

```ini
CONFIG_LV_DEF_REFR_PERIOD=16
CONFIG_CONFIG_LV_OS_RTTHREAD=y
CONFIG_LV_FB_TWO_NOT_SCREEN_SIZE=y
CONFIG_LV_FB_LINE_NUM=100
CONFIG_LV_USE_EZIP=y
```

导出脚本按 `assets.json` 追加缓存配置：

```ini
CONFIG_IMAGE_CACHE_IN_PSRAM_SIZE=<热图 PSRAM 池>
CONFIG_IMAGE_CACHE_IN_SRAM_SIZE=<热图 SRAM 池>
CONFIG_ROTATE_MEM_IN_PSRAM=y   # 或 CONFIG_ROTATE_MEM_IN_SRAM=y
CONFIG_LV_CACHE_DEF_SIZE=<v9 图片缓存字节数>
CONFIG_LV_IMAGE_HEADER_CACHE_DEF_CNT=<文件图片头缓存条目数>
```

`LV_USE_DRAW_EPIC` 在 `lv_conf_sifli.h` 中对非 MSVC 构建恒为 1；板级
`CONFIG_BSP_USING_EPIC=y` 决定 EPIC 驱动源码是否编译。不要写不存在的
`LV_USE_DRAW_SIFLI`。

### AI 写 UI 的资源与路径规则

1. 静态冷图用 `mode=ezip`；旋转/缩放/热图用 `mode=raw`，由 `assets.json` 的
   `placement` 决定放 flash、PSRAM 还是 SRAM。脚本会生成 `app_assets_init()` 和
   `app_asset_<name>()`，不要在 app 里手写 `app_cache_copy_alloc()`。
2. 需要文件加载的大图/可替换资源，在 app 内用 `lv_image_set_src(img, "A:/x.ezip")`；
   导出器当前只生成 C 数组，不复制 `.ezip` 文件。
3. 只失效变化区域：`lv_obj_invalidate_area()`；重活挂到 `LV_EVENT_REFR_START` 或只在
   数值变化时执行。
4. 单步渲染模式下，圆角、阴影、圆弧、线、复杂渐变会回退软件绘制；开启
   `CONFIG_DRV_EPIC_NEW_API=y`（渲染列表）后，圆角矩形、边框、圆弧、线、多边形、点阵字
   可走 EPIC，阴影仍走软件。
5. 用 `lv_get_fps()`、`set_display_fps_and_cpu_load(1)`、串口 `fps2` 测量，不猜。
6. 不要使用 52x 不存在的加速 API（`LV_USE_VGLITE`、GE2D、硬件 JPEG）。

## 已知限制

- 本机未安装 SiFli-ENV/ARM 工具链，`scons` 固件构建未在导出流程中执行。
- 黄山派实际屏幕 390x450；非 390x450 设计的应用需要自行适配布局。
- `coffee` 等 9.6 应用不导出；导出器会返回 `unsupported_api` 诊断。
- EZIP 转换依赖 SDK 的 `tools/png2ezip/ezip.exe`（Windows）；其他平台使用同目录的 `ezip_linux` / `ezip_mac` 需另行适配。
- `assets.json` 必须声明 `assets/*.png` 里的每张图；缺失会报 `asset_unlisted`。
- `hspi_watch` 是 390x450 的表盘示例；`watch_bg` 用 EZIP，旋转表针/ring 用 raw PSRAM。
  本地运行时验证使用 `watch_assets.h`，真机使用 `assets.h` 生成的资源层。
