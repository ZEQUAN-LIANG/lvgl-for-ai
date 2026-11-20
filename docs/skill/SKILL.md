---
name: lvgl-verify-loop
description: Write, preview and verify LVGL C user apps with a real headless host, scenario replay and session evidence. Use when creating, debugging or checking an LVGL user interface in C.
---

# LVGL Verify Loop

本 skill 只服务一件事：写 LVGL C 应用，跑真实 headless 场景，读会话证据。工具提供
真实 LVGL 宿主、虚拟 pointer/keypad/encoder、虚拟时间、帧与 timeline、会话回放；
**不判定画面**，验收标准由人在对话里给出。

## 环境与入口

本包自带预编译 engine 和统一入口 `bin\lvgl.cmd`。宿主机必须提供 Python 3.9+
（`python` 在 PATH；双击启动器使用 `pythonw` 或 `pyw`）。所有命令从包根执行。

| 入口 | 用途 |
| --- | --- |
| `bin\lvgl.cmd run ...` | 运行场景；改过 C 后加 `--build` 重新编译 |
| `bin\lvgl.cmd report ...` | 只读已有会话证据 |
| `bin\lvgl.cmd serve ...` | 打开网页端（固定 `127.0.0.1:8765`） |
| `bin\lvgl.cmd assets ...` | 字体/图片转 LVGL C 数组（不启动 engine） |
| `bin\LVGL-AI-Viewer.exe` | Windows 双击打开网页端 |

需要直接调用解释器时：

```bat
python -I console\entrypoints\cli.py --scenario user\scenarios\intro.json --json
python -I console\entrypoints\session_report.py --latest --log-tail 5
```

修改 `user/app/**/*.c` 并重新构建时需要系统 GCC（MinGW-w64 64-bit，版本与包内 LVGL 预编译库一致；当前 15.2.0）。发布包不内置 Python、GCC 或 CMake。

## 目录

```
SKILL.md          根目录唯一文件：skill 入口与工作流
api-nav/          各 LVGL 版本的 API 导航
user/app/         唯一源码真源：应用变体 C 代码与资源头
user/scenarios/   场景 JSON
user/sessions/    会话证据
bin/              入口：lvgl.cmd、LVGL-AI-Viewer.exe
console/          Python 控制层（只读，不写业务代码）
docs/             第三方许可
```

`user/app/**/*.c` 是唯一源码真源；`console/` 和 `bin/` 不存放用户业务代码。
`user/app/intro/` 是默认介绍页与模板；应用由 `user/app/<name>/` 目录自动发现
（目录内声明 `void <name>_create(void)` 即可，入口名偏离约定时才写该目录的
`app.json`），构建自动生成 `app_registry.inc`，没有登记应用名的中心表；
`user/scenarios/intro.json` 是 intro 的录制演示。

## 宿主工作流

1. 写或改 `user/app/**/*.c`；每个变体暴露 `void <name>_create(void)`，目录名即
   应用名，不需要元数据文件。
2. 跑场景：

   ```bat
   bin\lvgl.cmd run --scenario user\scenarios\<name>.json --json
   ```

3. 读会话证据，按需改 C 代码，再跑同一场景。

改过 C 后加 `--build` 重新编译（需要 GCC）；只运行已有 engine 时用 `--no-build`，
不需要编译器。没有 `--build` 的裸 `run` 在包里复用预编译 engine。

## 资源转换

字体和图片用内置转换器生成 C 数组，不需要 Node.js、`pip install` 或联网：

```bat
bin\lvgl.cmd assets font --app <app> --font C:\Windows\Fonts\Deng.ttf ^
  --size 16 --bpp 4 --scan-app --name <app>_font_16

bin\lvgl.cmd assets image --app <app> --input user\app\<app>\logo.png --cf ARGB8888
```

- 默认输出 `user/app/<app>/<name>.h`，并更新 `user/.cache/assets/<app>.json`
  （源文件 SHA256、字号/bpp/字符集、颜色格式）。
- 字体头带 `LVGL_VERSION_MAJOR/MINOR` 版本门，同一份头可用于 8.3–9.6。
  `--bpp 8` 只用于 8.x 或 9.3+；目标 9.1/9.2 用 `--bpp 4`。
- 图片头按目标 major 生成：9.x 头在 9.1–9.6 通用；8.x 用 `--lvgl 8.4` 单独生成。
- `--scan-app` 从应用 `.c/.h` 字符串字面量收集字形；动态文本用 `--text-file` 或
  `--text`，中文优先用 `--text-file`。
- 生成的 `*.h` 提交到项目；重放账本在 `user/.cache/`（不进 Git）。

## 证据读取顺序

`--json` 的 stdout 只有一行 `lvgl-verify-loop-session-index-v1` 索引（`session_report.py
--json` 同一份文档）：`session_dir`、`status`、counts、raw 文件体积/行数、
timeline 终点、diffs、frames、marks、snapshots、clicks、annotations、
whiteboards、`log_tail`、`next_reads`。先读索引，再按 `next_reads` 查询：

```bash
python -I console\entrypoints\session_report.py user\sessions\<id> --json
python -I console\entrypoints\session_report.py timeline user\sessions\<id> --limit 20
python -I console\entrypoints\session_report.py diffs user\sessions\<id> --top 5
python -I console\entrypoints\session_report.py resolve user\sessions\<id> --click 41:43 --at result
python -I console\entrypoints\session_report.py context user\sessions\<id> --click 41:43
```

1. 需要构建原因时读 `session_dir/build.log`；需要精确状态时读 `engine.log`。
2. `timeline` / `diffs` / `frames` 默认有上限；不要直接整读 100 KB 的 ndjson。
3. 人类反馈在 `notes` 里；跨轮定位用 `notes --resolve` 或
   `feedback --previous`。按需打开索引给出的帧、快照或 `regions/` PNG。
4. 聊天里的人类反馈用 `python -I console\entrypoints\feedback.py add` 写入，不手改
   `annotations.json`。

退出码：`0` 正常结束；`1` build / link / crash；`2` harness、scenario、协议或环境
错误。`status=ok` 只表示会话正常结束，不表示界面满足验收标准。精确状态只能用应用
C 代码 `printf` 到 `engine.log`。

## 版本策略

- 宿主默认 LVGL **9.6**，用于日常预览与取证。
- `intro` 应用按 **9.4+** 版本门编写；9.4 及以上都能按目录发现并选择应用，
  9.1 / 8.x 没有该注册表，只显示空屏。
- 包内已带齐 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3，不需要安装其他版本。
- 场景可选 `"lvgl": "9.4"`；优先级是 `--lvgl` > 场景 `lvgl` >
  `LVGL_VERIFY_LOOP_LVGL_VERSION` > 默认 9.6。
- 跨版本只比较事件语义与 session 文件集合，不比较像素。

## 宿主机依赖

- **Python 3.9+**：运行所有命令的前提；`python` 必须在 PATH，双击启动器使用
  `pythonw` 或 `pyw`。发布包不内置 Python。
- **GCC**（MinGW-w64 64-bit，15.2.0）：只在改过 `user/app/**/*.c` 后 `--build`
  重新编译时需要；版本必须与包内 LVGL 预编译库一致。

没有 Python 不能运行；没有 GCC 只能运行已有 engine，不能重新编译用户 C。

## 硬规则

- **不输出 pass/fail、baseline、approval、acceptance**；验收标准由人类在对话中
  给出。
- **没有证据不声称完成**：结论必须指向 `session_dir` 里的 manifest、build.log、
  timeline、frames/snapshots。
- **没有对象树、`inspect`、属性读取或 `set`**；精确状态只能由用户 C 代码
  `printf` 到 `engine.log`，再做证据读取。
- 改过 `user/app/*.c` 后必须用 `--build` 重新构建（需要 GCC）；`--no-build` 只用于
  运行当前 engine。
- 只改 `user/app/` 与 `user/scenarios/`；不改 `console/`、`bin/` 或会话证据目录。
- 路径含空格或中文时，命令中的路径要用引号包住。
