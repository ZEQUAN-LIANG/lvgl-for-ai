# LVGL Verify Loop

[English](README.md) | 简体中文

**AI 写 LVGL，AI 自己验证；人只提供意图与反馈。**

一个 AI-first 的 LVGL 开发与验证平台：真实 headless LVGL 宿主、虚拟输入与虚拟时间、逐帧会话证据、网页检视台，以及通向 SiFli 与 ESP32-C6 真机的适配链路。

## 为什么 AI-first

AI 时代，code is cheap。写 C 不再是瓶颈，缺的是让 AI 看见真实画面、拿到可判定证据的回路。

所以这个项目把 LVGL 开发交给 AI：AI 读意图、写 C、跑场景、读证据、自己验收。人不写代码，只提供意图、在画面上给出反馈、给出验收标准。

一切都是 AI-first：AI 在开发者的位置上，人退到意图与反馈。

| 人 | AI |
| --- | --- |
| 提供意图与参考画面 | 写 LVGL C 代码 |
| 在画面上圈出问题（标注、白板） | 跑场景，读帧、timeline、diff 与日志 |
| 给出验收标准与最终判断 | 按验收标准自检、自验收、再修正 |

它适合用 AI 编写 LVGL 界面、需要可回放证据的团队；不适合做 GPU 性能分析。

## 它能做什么

### 默认介绍页：LVGL Verify Loop 控制台

`user/app/intro/` 是 skill 的默认应用，也是默认模板：800×600 展示页，内容由真实会话快照拼成（`user/scenarios/intro.json`）。

### AI 闭环：改 C → 跑场景 → 读证据 → 自己判定

AI 直接修改 `user/app/**/*.c`，用一条命令构建并播放场景：

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json --json
```

stdout 只有一行 JSON，指向一次会话；会话里有完整 PNG 帧、timeline、逐帧 diff 和引擎日志。AI 读这些证据、对照人给的验收标准，再决定是否修改。工具不输出 pass/fail，验收标准由人给出。

没有对象树、`inspect`、属性读取或 `set`：精确的内部状态由用户 C 代码 `printf` 到 `engine.log`，同样进入证据。

### 网页检视台：实时预览、回放、标注、白板

```bash
python -I console/entrypoints/serve.py --open
```

固定 `127.0.0.1:8765`。页面里是真实 LVGL 运行时的画面，可以实时预览或回放录制会话；右侧是标注工具，人在画面上圈出问题、写一句话，保存为标注。

白板支持单帧、时间区间与全局三种范围，适合画流程、讲意图；每块白板都要求文字或 labels，图像和文字一起交给 AI。

AI 直接读这些材料：

- 标注与白板：`annotations.json`、`whiteboards.json` 里的帧号、bbox、范围、文字与 labels；
- 用户代码：`user/app/**/*.c` 是唯一源码真源，控件创建、`lv_obj_add_event_cb` 事件绑定与状态都在 C 里；
- 运行轨迹：`timeline.ndjson` 记录每次输入命中的对象名与类型（`hit` / `hit_class`），`frame_diffs.ndjson` 记录画面变化 bbox。

三者对齐后，AI 能知道控件由哪段代码创建、事件绑到哪个回调、这次输入命中了谁、画面随后变了哪块，再按标注和白板的反馈改代码。

### 多版本验证：一套应用，六个 LVGL 版本

同一份 `apps` 与同一个场景，可以跑在 LVGL 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3 上，用 `--lvgl <version>` 选择。跨版本比较事件语义与会话文件集合，不比较像素。

SiFli 导出链路的设备应用按 LVGL 9.4 基线编写，导出时只做兼容性检查并拒绝
9.5/9.6-only API；ESP32-C6 的 Arduino 链路使用 LVGL 9.6。

### 真机链路：宿主验证，SiFli 导出或 ESP32-C6 bring-up

目前接通两块板：黄山派（SiFli SF32LB52x）走 SiFli 导出链路，微雪
ESP32-C6-LCD-1.47 走 Arduino bring-up 链路。

```bash
python -I chip-adapt/sifli/export.py sift_watch --dry-run
python -I chip-adapt/sifli/host/cli.py build --app sift_watch --actor ai --json
python -I chip-adapt/sifli/host/cli.py flash --app sift_watch --actor ai --json
```

共享源码仍是 `user/app/`；导出按 LVGL 9.4 基线复制应用源码。没有开发板时，只能停在宿主验证和导出 dry-run，不能声称设备已验证。

黄山派（SiFli SF32LB52x，板名 `sf32lb52-lchspi-ulp`）实拍，桌面串口与烧录上位机在 `chip-adapt/sifli/host/`。黄山派实际屏幕 390×450，其他尺寸的应用需要自行适配布局：

<p align="center"><img src="docs/media/huangshanpai.gif" width="280"></p>

ESP32-C6 通过 `chip-adapt/esp32/` 的 Arduino bring-up 链路支持。`perf_monitor` 已跑在微雪
ESP32-C6-LCD-1.47（172×320 ST7789）上：串口切换竖/横版，host 提供 `/perf/` 控制页和
tkinter 桌面面板。默认每 0.3 秒监控一次，导出/编译默认走增量：

```bash
python -I chip-adapt/esp32/arduino/build.py build
python -I chip-adapt/esp32/arduino/build.py flash --port COMx
python -I chip-adapt/esp32/host/host.py serve --port COMx --baud 115200 --open
python -I chip-adapt/esp32/host/perf/perf_gui.py
```

实机已验证 USB Serial/JTAG、esptool 烧录和 `SHOT` 帧缓冲抓取。正式 ESP-IDF 导出器仍在
规划中，详见 `chip-adapt/esp32/README.md` 与 `chip-adapt/esp32/docs/arduino-perf-monitor.md`。

<p align="center"><img src="docs/media/esp32-c6-perf-monitor.gif" width="260"></p>

另外两点：预编译 LVGL 库让本地只有 GCC 也能跑（`--prebuilt`）；工具与 Claude Code、Cursor 等 harness 无关，本身不绑定模型。

## 安装 skill

发布包本身就是 skill。从 [GitHub Releases](https://github.com/ZEQUAN-LIANG/lvgl-for-ai/releases)
或 [Gitee Releases](https://gitee.com/liang-zequan/lvgl-for-ai/releases) 下载 0.2.2 的两个包之一：

- `lvgl-verify-loop-0.2.2-full-win64.zip`：六个 LVGL 版本和 viewer。
- `lvgl-verify-loop-0.2.2-full-sifli-win64.zip`：上面的完整包再加 SiFli 工具。

宿主机必须提供 Python 3.9+（`python`/`pythonw`，或 `py`/`pyw`）并在 PATH 上；发布包
不自带 Python。运行包内应用不需要 CMake 或 GCC。

用一条命令把它装成 Claude Code 的个人 skill（Windows PowerShell）：

```powershell
Expand-Archive .\lvgl-verify-loop-0.2.2-full-win64.zip "$env:USERPROFILE\.claude\skills"
```

zip 里只有一层 `lvgl-verify-loop\`，所以解压后就是
`%USERPROFILE%\.claude\skills\lvgl-verify-loop\SKILL.md`。只给一个项目用，就解压到
该项目的 `.claude\skills\`。也可以右键 zip → **全部解压缩**，目标目录填同一个路径。

重启 Claude Code，然后输入：

```text
/lvgl-verify-loop
```

或者直接描述你要的 LVGL 界面。skill 会改 `user/app/**/*.c`、跑场景、读会话证据。
包内自带 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3 六个版本的预编译 LVGL 库与 engine，以及
viewer；运行它们只需要 Python 3.9+，不需要 CMake、管理员权限或版本下载。AI 改完 C
后重新构建需要 GCC 15.2.0（MinGW-w64 64 位），必须与随包预编译 LVGL 库记录的编译器版本一致。
CMake 和 Ninja 只在从 LVGL 源码构建时需要，发布包不走这条路。

不用 AI 时，打开解压后的 `lvgl-verify-loop` 文件夹，双击
`bin\LVGL-AI-Viewer.exe`（或运行 `bin\lvgl.cmd serve`）；Python 在 PATH 上时，
浏览器会打开 `http://127.0.0.1:8765`。

用 Claude Code 打开解压后的 `lvgl-verify-loop` 文件夹作为工作区（或先 `cd` 进去）；
skill 的命令都相对这个包根。如果安装在 skills 目录：

```bat
cd "%USERPROFILE%\.claude\skills\lvgl-verify-loop"
bin\lvgl.cmd run --scenario user\scenarios\intro.json --json
```

## 从源码开始

```bash
git clone https://gitee.com/liang-zequan/lvgl-for-ai.git lvgl-for-agent
cd lvgl-for-agent

# 1. 下载并安装 LVGL 9.6 源码
python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .

# 2. 下载 PNG 编码器源码（zlib / libpng）
python -I scripts/fetch_png.py --repo-root .

# 3. 跑一个场景（首次会构建 engine，通常需要几分钟）
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# 4. 打开网页检视台
python -I console/entrypoints/serve.py --open
```

成功时退出码为 `0`，stdout 最后一行是会话目录，`manifest.json` 的 `status` 为 `ok`。默认 `--source auto` 会先试 GitHub codeload，再试 Gitee 镜像；Gitee 的 LVGL 镜像可能返回 HTML/400，失败时请使用默认值或预编译版本包。

从源码开发？用 Claude Code 打开这个仓库即可；`CLAUDE.md` 说明仓库工作方式，
`SKILL.md` 是 skill 入口，不需要另外安装 skill。

## 看懂证据

一次会话就是 `user/sessions/<id>/` 这个目录：

```text
user/sessions/<id>/
  manifest.json          # 状态、应用、分辨率、帧数
  timeline.ndjson        # 输入事件、帧区间、marks
  frame_diffs.ndjson     # 逐帧变化 bbox
  frames/                # 完整 PNG，只保留画面变化的帧
  snapshots/             # 命名快照
  engine.log             # 运行日志，精确状态由 C 代码 printf 到这里
  build.log              # 实际构建命令与编译器输出
  annotations.json       # 人的标注（可选）
```

`--json` 的 stdout 只有一行，例如（截取关键字段，路径已简化）：

```json
{"session_id": "20261114-095536-1d9d", "session_dir": "user/sessions/20261114-095536-1d9d", "status": "ok", "app": "coffee", "display": {"width": 800, "height": 600}, "frame_count": 305, "error": null}
```


AI 的结论必须指向这些文件。`status: ok` 表示会话正常结束；界面是否满足验收标准，由人判定。

## 版本与真机

- 宿主默认 LVGL 9.6，用于日常预览与取证；发布包里的 `intro` 应用按 9.4+ 编写。
- 0.2.2 只发布两个 zip：`full` 带全部六个 LVGL 版本和 engine；`full-sifli` 再加
  SiFli 工具。两者都要求宿主机安装 Python 3.9+，不自带运行时；没有逐版本下载步骤。
- 随包 LVGL 库用 GCC 15.2.0 导出；走预编译路径重新编译用户 C 时需要同一个 GCC 版本。
  CMake/Ninja 只在从 LVGL 源码构建时需要。
- 设备应用按 LVGL 9.4 基线编写；导出只做兼容性检查，不自动改写源码。
- 查看版本，或只在自定义构建时使用源码安装：

  ```bash
  python -I scripts/install_version.py --list
  python -I scripts/install_version.py --lvgl 9.4 --mode source
  ```

  源码模式需要 CMake/Ninja/GCC。场景可选 `"lvgl": "9.4"`；`--lvgl` 优先于场景，
  场景优先于 `LVGL_VERIFY_LOOP_LVGL_VERSION`。
- SiFli 只在 `full-sifli` 里：自研导出/上位机层、`SiFli-Host.exe`、pyserial/xterm、
  `sift_watch` 源码和导出示例；不包含 SiFli SDK、ARM 工具链、sftool 或固件。
  SDK、工具链与 sftool 安装见 `chip-adapt/vendor/README.md`。
- ESP32-C6 支持位于开发仓库 `chip-adapt/esp32/`；当前发布包不带 Arduino 导出器、
  host 或固件。

## 环境依赖

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.9+ 且在 PATH 上；发布包不自带 | 只用标准库，不需要 `pip install`；engine 在所有版本默认 `LV_USE_FREETYPE=1` 并链接随包 FreeType 2.13.2；命令统一用 `python -I` |
| GCC | MinGW-w64 64 位，15.2.0 | 只有重新编译用户 C 时需要，且必须与随包 LVGL 库的 manifest 一致；预编译 engine 不需要 |
| CMake | ≥ 3.20 | 仅从 LVGL 源码构建需要；发布包不需要 |
| Ninja | 任意近版 | 仅从 LVGL 源码构建需要；发布包不需要 |
| curl | 任意近版 | 仅下载 LVGL / PNG 源码时使用 |
| 磁盘 | 约 1 GB 可用 | LVGL 源码与构建产物 |

Windows 推荐 MSYS2 UCRT64。完整安装步骤、PATH 配置、首次运行说明与常见错误见 `console/README.md`。

## 更多文档

- `console/README.md`：工具用法、环境安装、常见错误、测试、静态检查与格式化。
- `user/app/GUIDE.md`：写用户应用。
- `docs/skill/`：skill 入口契约 `SKILL.md` 与各版本 `api-nav/`。
- `chip-adapt/sifli/README.md` / `chip-adapt/docs/sifli.html`：SiFli 适配层与能力边界。
- `chip-adapt/esp32/README.md`：ESP32-C6 板级说明、host 控制页、桌面 GUI 与 Arduino bring-up。
- `chip-adapt/esp32/docs/arduino-perf-monitor.md`：ST7789 + LVGL 旋转、烧录与 `SHOT` 验证说明。
- `CONTEXT.md`：领域术语表。
- `CLAUDE.md`：AI 编码代理的仓库工作说明。
- 发布包根目录的 `SKILL.md`（源码仓库里是 `docs/skill/SKILL.md`）：已安装 skill 的 AI 入口契约与 agent 工作流。

## 许可

本项目源码为 MIT，见根目录 `LICENSE`。LVGL、lodepng、zlib、libpng 的许可全文见 `docs/licenses/`。
