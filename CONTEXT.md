# LVGL Verify Loop 术语

本文件只记录当前 skill 特有的术语，不记录实现细节。

## Language

**真源（Source of truth）**：
用户界面的权威表示，在本项目中就是 `user/app/**/*.c`；工具不维护第二份场景或对象树真源。
_Avoid_: 场景真源、UI 文件

**应用变体（App variant）**：
同一个 engine 入口 `app_create` 下由 `apps[]` 表映射的用户界面实现，每个变体暴露 `void <name>_create(void)`。
_Avoid_: 页面、demo

**场景（Scenario）**：
描述一次运行输入与证据锚点的 JSON：`app`、可选的 `display`、以及 wait / click / drag / mark / snapshot 等步骤；它不是布局真源。
_Avoid_: UI 文件、工程文件

**宿主 SDK（Host SDK）**：
`sdk/<version>/` 下预编译的宿主静态库、公共头、`lv_conf.h` 与 `manifest.json`；预编译构建只依赖它和 GCC。
_Avoid_: 工具链、SDK 包

**Engine**：
`core/engine/` 编译出的 `lvgl_engine.exe`，负责初始化 LVGL、虚拟输入、录帧、timeline 与协议回执。
_Avoid_: 模拟器、运行时（与 Runtime 区分）

**运行时（Runtime）**：
Python 控制层的一个实例，驱动一个 engine 进程并对应一次会话；它不是 Web 重实现的渲染器。
_Avoid_: 渲染器、模拟器

**会话（Session）**：
`sessions/<id>/` 下的一次可重放录制，包含 manifest、帧、timeline、日志与标注；AI 与人类共用同一种证据格式。
_Avoid_: 录像、操作记录

**证据（Evidence）**：
会话目录里可供引用的产物：`manifest.json`、`build.log`、`timeline.ndjson`、`frame_diffs.ndjson`、`engine.log`、`frames/`、`snapshots/`。
_Avoid_: 测试结果、日志

**标记与快照（Mark / Snapshot）**：
场景里的证据锚点；`mark` 在 timeline 上打点，`snapshot` 额外保存一张命名 PNG。
_Avoid_: 断言、检查点

**录制（Recording）**：
对已有会话的只读视图，通过 `Recording.open()` 读取 manifest、timeline、帧与标注；写标注是唯一可写入口。
_Avoid_: 回放器、播放器

**构建方式（Build mode）**：
源码构建（`lvgl-src/<version>`，需要 CMake/Ninja/GCC）、预编译构建（`sdk/<version>`，只需要 GCC）或 `--no-build`（直接复用 engine）；实际选择写在 `build.log` 第一行。
_Avoid_: 编译模式、工具链

**版本包（Pack）**：
与 core 同一 Release 发布的预编译版本资产，包含 `sdk/<version>`、engine 和 `pack.json`；通过 sha256 校验。
_Avoid_: 安装包、SDK

**虚拟时间（Virtual time）**：
由 tick / wait 推进的确定性时钟，不依赖墙钟；动画、定时器和录制时间轴都以它为准。
_Avoid_: 模拟时间、假时钟

**验收（Acceptance）**：
由人类在对话中给出的界面标准；工具只提供环境、输入和证据，不输出 pass/fail、baseline 或 approval。
_Avoid_: 测试结论、通过率
