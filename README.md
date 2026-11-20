# LVGL 验证循环

一个面向 LVGL 的 AI 优先开发与验证平台。AI 编写 C 代码、AI 验证运行结果、人类仅需提供意图和反馈。

## 概述

本项目实现了一套完整的 AI 驱动 LVGL 用户界面开发工作流：

- **AI 根据人类意图编写 LVGL C 代码**
- **AI 运行测试场景验证代码**
- **AI 读取会话证据（帧、时间线、日志）**
- **AI 判断结果是否满足验收标准**

人类只需提供意图、参考视觉效果和验收标准——无需编写代码。

## 核心特性

### 无头 LVGL 引擎

真正的无头 LVGL 运行环境，无需显示器即可运行，非常适合自动化测试和 CI/CD 流程。

### 多版本支持

一套代码库支持六个 LVGL 版本：9.6、9.5、9.4、9.1、8.4、8.3。

### 网页检视台

访问 `http://127.0.0.1:8765` 实时预览和回放，包含：
- 逐帧会话回放
- 人工反馈标注工具
- 白板功能用于草拟流程和意图

### 会话证据

每次运行生成完整的证据文件：
- 完整 PNG 帧图像
- 包含输入事件的时间线
- 每帧的变化区域差异图
- 用户 C 代码的运行时日志

### 真机支持

- **SiFli SF32LB52x**（黄山派）通过导出工具链
- **ESP32-C6**（Waveshare ESP32-C6-LCD-1.47）通过 Arduino 适配

## 快速开始

### 从发布包安装

从 [GitHub Releases](https://github.com/ZEQUAN-LIANG/lvgl-for-ai/releases) 或 [Gitee Releases](https://gitee.com/liang-zequan/lvgl-for-ai/releases) 下载：

- `lvgl-verify-loop-0.2.2-full-win64.zip` - 包含六个 LVGL 版本和查看器
- `lvgl-verify-loop-0.2.2-full-sifli-win64.zip` - 上述内容 + SiFli 工具

需要 Python 3.9+ 并在系统 PATH 中。

### 运行一个场景

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json --json
```

输出为一行 JSON，包含会话目录路径。

### 打开网页检视台

```bash
python -I console/entrypoints/serve.py --open
```

服务固定在 `http://127.0.0.1:8765`。

## 从源码开始

```bash
git clone https://gitee.com/liang-zequan/lvgl-for-ai.git
cd lvgl-for-ai

# 安装 LVGL 9.6 源码
python -I scripts/fetch_lvgl.py --version 9.6 --repo-root .

# 安装 PNG 编码器源码
python -I scripts/fetch_png.py --repo-root .

# 运行一个场景
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# 打开网页检视台
python -I console/entrypoints/serve.py --open
```

## 会话证据结构

```
user/sessions/<id>/
  manifest.json          # 状态、应用、分辨率、帧数
  timeline.ndjson        # 输入事件、帧跨度、标记
  frame_diffs.ndjson     # 每帧变化的边界框
  frames/                # 完整 PNG（仅变化的帧）
  snapshots/             # 命名快照
  engine.log             # 用户 C 代码的运行时日志
  build.log              # 构建命令和编译器输出
  annotations.json       # 人工标注（可选）
```

## 环境依赖

| 依赖 | 说明 |
|------|------|
| Python 3.9+ | 在 PATH 中；不打包在发布物中 |
| GCC 15.2.0 | MinGW-w64 64 位；仅用于重编译用户 C 代码 |
| CMake ≥3.20 | 仅 LVGL 源码构建需要 |
| Ninja | 仅 LVGL 源码构建需要 |
| curl | 用于下载 LVGL/PNG 源码 |

## 文档

- `console/README.md` - 工具使用和环境配置
- `user/app/GUIDE.md` - 编写用户应用
- `chip-adapt/sifli/README.md` - SiFli 适配层
- `chip-adapt/esp32/README.md` - ESP32-C6 开发板设置
- `CONTEXT.md` - 领域术语表

## 许可

MIT 许可。详见 `LICENSE` 文件。第三方许可见 `docs/licenses/` 目录。