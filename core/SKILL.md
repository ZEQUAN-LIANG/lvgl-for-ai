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

本包自带宿主 SDK（`sdk/`）和预编译 engine，但**不内置 Python**；请使用系统
Python 3.9+。所有命令从包根执行，统一使用 `python -I`。

| 入口 | 用途 |
| --- | --- |
| `bin\lvgl.cmd run ...` | 构建 `user/app` 并播放场景 |
| `bin\lvgl.cmd report ...` | 只读已有会话证据 |
| `bin\lvgl.cmd serve ...` | 打开网页端（固定 `127.0.0.1:8765`） |
| `LVGL-AI-Viewer.exe` | Windows 双击打开网页端（需要 `pythonw.exe` 或 `pyw.exe`） |

也可以直接调用：

```bat
python -I core\cli.py --scenario user\scenarios\intro.json --json
python -I core\session_report.py --latest --log-tail 5
python -I core\web.py
```

## 目录

```
core/     工具层：cli.py、web.py、session_report.py、lvgl_ai/、engine/、tools/
user/     唯一源码真源：app/**/*.c 与 scenarios/*.json
sdk/      预编译宿主 SDK：静态库、公共头、lv_conf.h、manifest.json
build/    预编译 engine 与按目录隔离的构建缓存
bin/      统一入口包装脚本
LVGL-AI-Viewer.exe  Windows 双击启动网页端
versions.json      版本索引：默认版本、支持列表、intro 支持
```

`user/app/**/*.c` 是唯一源码真源；`core/`、`sdk/` 和 `build/` 不存放用户业务代码。
本包只带 `user/app/intro/` 一个应用；它同时是默认介绍页和默认模板。启动时不指定
app 就运行它，`user/scenarios/intro.json` 是它的录制演示。coffee、xiaohongshu、
spectrum 等示例只在开发仓库里，不随发布包分发。

## 宿主工作流

1. 写或改 `user/app/**/*.c`，入口固定为 `void app_create(void)`；新应用在
   `user/app/app.c` 的 `apps[]` 表登记一行。
2. 跑场景：

   ```bat
   bin\lvgl.cmd run --scenario user\scenarios\<name>.json --json
   ```

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

`record=False` 不写 frames/timeline/frame_diffs；`--no-build` 不重新编译。
`status=ok` 只表示会话正常结束，不表示界面满足验收标准。

## 版本策略

- 宿主默认 LVGL **9.6**，用于日常预览与取证。
- 发布包里的 `intro` 应用按 **9.4+** 版本门编写；9.1 / 8.x 只能跑旧 harness，
  不能使用 intro 应用变体。
- 设备应用按 LVGL **9.4** 基线编写，使用 `LVGL_VERSION_MINOR >= 4` 版本门；
  设备对齐用 `--lvgl 9.4`（需要 `sdk/9.4` 或 `lvgl-src/9.4`）。
- 导出只做兼容性检查并拒绝 9.5/9.6-only API，不自动改写源码。

## 版本安装

默认包只带 `sdk/9.6` 和 9.6 engine。安装其他版本：

```bat
python -I core\tools\install_version.py --list
python -I core\tools\install_version.py --lvgl 9.4 --source auto
python -I core\tools\install_version.py --lvgl 9.4 --mode pack --pack path\to\pack.zip
```

- **源码模式**：下载 `lvgl-src/<version>` 与 `third_party/`，9.6 额外导出预编译 SDK，
  其他版本用 CMake/Ninja/GCC 源码构建 engine；`--no-build` 只准备源码。
  `--source auto` 先试 GitHub codeload；Gitee 的 LVGL 镜像可能返回 HTML/400，失败时
  用 `--source codeload` 或 pack 模式。
- **pack 模式**：解包已构建的 `sdk/<version>` 与
  `build/lvgl_<token>/lvgl_engine`，不需要 CMake/Ninja；修改用户 C 代码仍然需要 GCC。
- `versions.json` 是版本索引：默认版本、支持列表、是否支持 intro。场景可选
  `"lvgl": "9.4"`；优先级是 `--lvgl` > 场景 `lvgl` > `LVGL_AI_LVGL_VERSION` > 默认 9.6。

## SiFli 工作流

设备链路沿用 `chip-adapt/sifli/` 适配层，共享源码仍是 `user/app/`：

```bat
python -I chip-adapt\sifli\export.py <app> --dry-run --force
python -I chip-adapt\sifli\host\cli.py build --app <app> --actor ai --json
python -I chip-adapt\sifli\host\cli.py flash --app <app> --actor ai --json
```

导出按 LVGL 9.4 基线复制应用源码，只做 9.5/9.6-only API 兼容性检查；构建/烧录
需要 SiFli SDK、ARM 工具链和 sftool。没有开发板时，只能停在宿主验证和导出
dry-run，不得声称设备已验证。本发布包为 host-only，不包含 `chip-adapt/`、SiFli
SDK 和串口/烧录上位机；上述命令适用于带适配层的完整工作区。

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
