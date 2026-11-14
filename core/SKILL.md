---
name: lvgl-verify-loop
description: Write and verify LVGL user apps with a real headless runtime, scenario replay, session evidence and a prebuilt host SDK. Use when building, previewing, debugging or verifying LVGL C interfaces, or when exporting LVGL apps to a device SDK.
---

# LVGL Verify Loop

本 skill 把 LVGL 用户应用从「改代码」带到「跑场景、读证据」：真实 headless LVGL
宿主、虚拟 pointer/keypad/encoder、虚拟时间、帧与 timeline、会话回放。工具只提供
环境、输入和证据，**不判定画面**。

![intro demo](intro-demo.gif)

## 环境与入口

本包自带宿主 SDK（`sdk/`）、预编译 engine 和统一入口 `bin\lvgl.cmd`。包内若带
`runtime/python/`，命令中的 `python` 可替换为 `runtime\python\python.exe`；否则使用
PATH 上的 Python 3.9+。所有命令从包根执行。

| 入口 | 用途 |
| --- | --- |
| `bin\lvgl.cmd run ...` | 运行场景；默认重新构建，engine 已存在时可加 `--no-build` 跳过编译 |
| `bin\lvgl.cmd report ...` | 只读已有会话证据 |
| `bin\lvgl.cmd serve ...` | 打开网页端（固定 `127.0.0.1:8765`） |
| `bin\lvgl.cmd assets ...` | 字体/图片转 LVGL C 数组（不启动 engine） |
| `LVGL-AI-Viewer.exe` | Windows 双击打开网页端，优先使用包内 Python |

需要直接调用解释器时：

```bat
python -I core\cli.py --scenario user\scenarios\intro.json --json
python -I core\session_report.py --latest --log-tail 5
```

修改 `user/app/**/*.c` 并重新构建时，才需要系统 GCC（MinGW-w64 64-bit）；CMake /
Ninja 只在源码构建模式需要。发布包不内置 GCC。

## 目录

```
core/            工具层：cli.py、assets.py、web.py、session_report.py、lvgl_ai/、engine/、tools/
user/app/        唯一源码真源：应用变体 C 代码与资源头
user/scenarios/  场景 JSON
sdk/             宿主编译 SDK：默认 9.6；其他版本按需下载到 sdk/<version>
build/           预编译 engine：build/lvgl_<token>/lvgl_engine.exe
bin/             统一入口包装脚本
LVGL-AI-Viewer.exe  Windows 双击启动网页端
versions.json    版本索引：默认版本、支持列表、pack URL 与 sha256
```

`core/lvgl_ai/assets/vendor/` 随包内置 freetype-py（含 FreeType DLL）与 pypng；
资源转换不需要 Node.js、`pip install` 或联网。

`user/app/**/*.c` 是唯一源码真源；`core/`、`sdk/` 和 `build/` 不存放用户业务代码。
`intro/` 是默认介绍页与默认模板；其他应用同样在 `user/app/app.c` 的 `apps[]` 登记，
`user/scenarios/intro.json` 是 intro 的录制演示。

## 宿主工作流

1. 写或改 `user/app/**/*.c`；每个变体暴露 `void <name>_create(void)`，并在
   `user/app/app.c` 的 `apps[]` 表登记一行。
2. 跑场景：

   ```bat
   bin\lvgl.cmd run --scenario user\scenarios\<name>.json --json
   ```

   裸 `run` 默认重新构建（需要 GCC）；engine 已存在且 C 未改动时加
   `--no-build` 直接运行。
3. 读会话证据，按需改 C 代码，再跑同一场景。

构建方式由工具自动选择：`lvgl-src/<version>` 存在时走源码构建（需要 CMake、
Ninja、GCC）；源码缺失时走 `sdk/<version>` 的预编译构建（只需要 GCC）。显式
覆盖：

```bat
bin\lvgl.cmd run --prebuilt --scenario ... --json
bin\lvgl.cmd run --source   --scenario ... --json
```

实际选择写在会话的 `build.log` 第一行（`# build mode: prebuilt` 等）。已有
engine 时 `--no-build` 直接运行，不需要编译器。

## 资源转换

字体和图片用内置转换器生成 C 数组，不需要 Node.js、`pip install` 或联网：

```bat
bin\lvgl.cmd assets font --app <app> --font C:\Windows\Fonts\Deng.ttf ^
  --size 16 --bpp 4 --scan-app --name <app>_font_16

bin\lvgl.cmd assets image --app <app> --input user\app\<app>\logo.png --cf ARGB8888
```

- 默认输出 `user/app/<app>/<name>.h`，并更新 `assets.json`（源文件 SHA256、
  字号/bpp/字符集、颜色格式）。
- 字体头带 `LVGL_VERSION_MAJOR/MINOR` 版本门，同一份头可用于 8.3–9.6。
  `--bpp 8` 只用于 8.x 或 9.3+；目标 9.1/9.2 用 `--bpp 4`。
- 图片头按目标 major 生成：9.x 头在 9.1–9.6 通用；8.x 用 `--lvgl 8.4` 单独生成。
- `--scan-app` 从应用 `.c/.h` 字符串字面量收集字形；动态文本用 `--text-file` 或
  `--text`，中文优先用 `--text-file`。
- host engine 默认 `LV_USE_FREETYPE=1`；运行时 TTF 加载只用于 host 预览，
  设备资源不要依赖宿主绝对路径。
- 生成的 `*.h` 和 `assets.json` 提交到项目。

## 证据读取顺序

`--json` 的 stdout 只有一行，包含 `session_id`、`session_dir`、`status`、
`frame_count`、`snapshots`、`marks`、`log_tail` 和 `error`。随后：

1. 读 `session_dir/manifest.json`：`status`、`app`、`display`、`frame_count`、
   `error.detail`。
2. 读 `session_dir/build.log`：实际构建命令、`build mode`、原始编译器输出。
3. 读 `session_dir/timeline.ndjson` 与 `frame_diffs.ndjson`：输入命中对象
   （`hit` / `hit_class`）、帧区间、变化 bbox。
4. 读 `annotations.json` / `whiteboards.json` 的文字与 bbox，再按需打开
   `frames/`、`snapshots/` 或 `regions/` 里的 PNG。

会话目录还包含 `engine.log`。退出码：`0` 正常结束；`1` build / link / crash；
`2` harness、scenario、协议或环境错误。`record=False` 不写 frames/timeline/
frame_diffs；`--no-build` 不重新编译。`status=ok` 只表示会话正常结束，不表示界面
满足验收标准。精确状态只能用应用 C 代码 `printf` 到 `engine.log`。

## 版本策略

- 宿主默认 LVGL **9.6**，用于日常预览与取证。
- `intro` 应用按 **9.4+** 版本门编写；9.1 / 8.x 只显示内置 harness。
- 设备应用按 LVGL **9.4** 基线编写；设备对齐用 `--lvgl 9.4`。
- 导出只做兼容性检查并拒绝 9.5/9.6-only API，不自动改写源码。

## 版本安装

core 包只带 `sdk/9.6` 和 9.6 engine；其他版本是同一 Release 里的预编译 pack。
第一次运行缺失版本时会询问是否下载；`--yes` 跳过询问，`--offline` 禁止联网：

```bat
bin\lvgl.cmd run --lvgl 9.4 --scenario user\scenarios\intro.json --json
bin\lvgl.cmd run --lvgl 9.4 --yes --scenario ... --json
bin\lvgl.cmd run --lvgl 9.4 --offline --scenario ... --json
```

也可以显式安装：

```bat
python -I core\tools\install_version.py --list
python -I core\tools\install_version.py --lvgl 9.4 --mode pack
python -I core\tools\install_version.py --lvgl 9.4 --mode source
```

- **pack 模式**：从 `versions.json` 下载并校验 sha256，解包 `sdk/<version>`、
  `build/lvgl_<token>/lvgl_engine` 和 legacy 的 `smoke/`；不需要 CMake/Ninja，
  修改用户 C 代码仍需要 GCC。
- **源码模式**：下载 `lvgl-src/<version>` 与 `third_party/`，导出 SDK 后用
  CMake/Ninja/GCC 构建 engine。
- pack 的 `pack.json` 记录 `core_version`；版本不匹配会明确报错。
- 场景可选 `"lvgl": "9.4"`；优先级是 `--lvgl` > 场景 `lvgl` >
  `LVGL_AI_LVGL_VERSION` > 默认 9.6。

## SiFli 工作流

SiFli 链路在单独的 **`sifli-tools`** 资产里，不塞进 core。把 core zip 和
`sifli-tools` zip 解压到同一父目录即可合并；资产内默认 demo 是 `sift_watch`：

```bat
bin\sifli.cmd
python -I chip-adapt\sifli\export.py sift_watch --dry-run --force
python -I chip-adapt\sifli\host\cli.py build --app sift_watch --actor ai --json
python -I chip-adapt\sifli\host\cli.py flash --app sift_watch --actor ai --json
```

资产包含自研 `chip-adapt/sifli/`、`SiFli-Host.exe`、pyserial/xterm、
`user/app/sift_watch/` 源码和导出示例；**不包含** SiFli SDK、ARM 工具链、sftool、
驱动或固件。构建/烧录前按 `chip-adapt/vendor/README.md` 安装官方依赖；没有开发板
时只能停在导出 dry-run 或 fake serial 测试，不得声称设备已验证。

## 硬规则

- **不输出 pass/fail、baseline、approval、acceptance**；验收标准由人类在对话中
  给出。
- **没有证据不声称完成**：结论必须指向 `session_dir` 里的 manifest、build.log、
  timeline、frames/snapshots。
- **没有对象树、`inspect`、属性读取或 `set`**；精确状态只能由用户 C 代码
  `printf` 到 `engine.log`，再做证据读取。
- 改过 `user/app/*.c` 后必须重新构建；`--no-build` 只用于运行当前 engine。
- 不写第二套协议客户端；只用 `Runtime` / `Recording` / `summarize_session`。
- 路径含空格或中文时，命令中的路径要用引号包住。
