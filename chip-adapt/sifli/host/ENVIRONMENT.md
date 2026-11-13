# SiFli host 环境与依赖

本文件记录 `chip-adapt/sifli/host` 在 Windows 上的运行与构建依赖。能由脚本完成的部分
只写运行方式；下面只保留脚本不能代劳的说明和容易踩的坑。

## 快速开始

从仓库根运行 PowerShell：

```powershell
# 只检查：不下载、不安装、不改写文件
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/bootstrap.ps1 -Check

# 补齐 pyserial（含许可证）、xterm.js 和 SDK uv lock 环境
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/bootstrap.ps1

# 启动 host
python -I chip-adapt/sifli/host/server.py --open
```

`-Check` 退出码 0 表示全部就绪，1 表示仍有 `MISSING` 行。`WARN`（例如许可证文本缺失）
不阻塞。默认模式只自动处理 pyserial（含许可证）、xterm.js 和 SDK lock venv；Python、uv、
SDK 源码、ARM 工具链与 sftool 属于环境级安装，缺失时脚本给出恢复位置，不擅自改动系统。

## 依赖清单

| 依赖 | 版本 / 安装方式 | 位置 | 说明 |
| --- | --- | --- | --- |
| Python | 3.9+，`python` 在 PATH | 系统安装 | host 只用标准库 + pyserial |
| pyserial | 3.5 | `host/vendor/serial/` | 离线 import；许可证 `host/vendor/pyserial-3.5.LICENSE.txt` 由 bootstrap 下载 |
| xterm.js | 5.3.0 | `host/web/vendor/xterm/` | 浏览器从 `/vendor/xterm/` 加载，运行时不访问 CDN |
| uv | 近期版本 | 系统安装 | 用来装 SDK lock 环境；bootstrap 不自动安装 |
| SiFli SDK | v2.5.1，commit `f4042d7e` | `chip-adapt/vendor/sifli-sdk/`（不进 Git） | 含 `tools/locks/default/uv.lock`；初始化 `tools/SiliconSchema` 与 `middleware/bluetooth` 子模块 |
| SDK lock venv | `uv sync --project <lock> --no-dev` | `.../locks/default/.venv/` | 提供 scons 和构建依赖 |
| ARM 工具链 | SDK `install.ps1` | `%USERPROFILE%\.sifli\tools\arm-none-eabi-gcc\14.2.1\bin`（或 `SIFLI_SDK_TOOLS_PATH`） | 提供 gcc；不进 Git |
| sftool | 0.2.5 | `%USERPROFILE%\.sifli\tools\sftool\0.2.5\sftool.exe`（或 `SFTOOL_BIN` / PATH） | 官方烧录 CLI；由 SDK `install.ps1` 安装 |

SDK、工具链和 sftool 的下载、版本与校验见 `chip-adapt/vendor/README.md`。

## 脚本之外的手工步骤

只有脚本报 `MISSING` 且不在自动补齐范围时才需要：

- **Python 3.9+**：安装后确保 `python --version` 可用。
- **uv**：按 <https://docs.astral.sh/uv/getting-started/installation/> 安装。
- **SiFli SDK / 工具链 / sftool**：按 `chip-adapt/vendor/README.md` 恢复；工具链和 sftool 由 SDK `install.ps1` 安装到 `~/.sifli`，不要复制进仓库。
- **许可证文件**：bootstrap 会自动补齐 `host/vendor/pyserial-3.5.LICENSE.txt`
  （来源 <https://raw.githubusercontent.com/pyserial/pyserial/v3.5/LICENSE.txt>，校验大小和版权行）
  与 `host/web/vendor/xterm/LICENSE`。补不齐时只保留 `WARN`，不影响运行。

## 非显然的坑

### pyserial 是 vendor 的，不是系统包

`serial_backend.py` 在 import 前把 `host/vendor` 插入 `sys.path`，所以
`python -I chip-adapt/sifli/host/server.py` 不需要系统里安装 pyserial。手动重装必须用：

```powershell
python -m pip install --target chip-adapt/sifli/host/vendor --no-deps pyserial==3.5
```

pip 会在 `vendor/` 生成 `bin/` 和 `pyserial-3.5.dist-info/`；两者都不是运行时依赖，
bootstrap 安装后会删除它们。许可证由 bootstrap 单独从 pyserial v3.5 的 `LICENSE.txt`
下载到 `vendor/pyserial-3.5.LICENSE.txt`。删除 dist-info 后 `pip show pyserial`
不再能发现该包，这是预期行为。

### xterm.js 也是 vendor 的

页面通过 `/vendor/xterm/xterm.js` 和 `/vendor/xterm/xterm.css` 加载本地副本。
JS、CSS、LICENSE 三个文件缺一不可。bootstrap 只从 jsDelivr 的 `xterm@5.3.0`
补缺失或零字节文件；内容非空但校验失败时不会覆盖，需要手工删除后重跑。

### uv lock 环境固定用 Python 3.13

`tools/locks/default/pyproject.toml` 要求 `>=3.13,<3.14`。本机 `python` 可以是别的版本，
`uv sync` 会自行查找或下载匹配的 3.13 解释器。构建时 `build_flash.py` 的查找顺序是：
PATH 里的 `scons` → `uv run --project <lock> scons` → 官方 `export.ps1`。
不要把 SDK 的依赖装进系统 Python。

### RTT_CC 等变量由 host 注入

host 构建时设置 `RTT_CC=gcc`、`SIFLI_SDK`/`SIFLI_SDK_PATH`、`PYTHONPATH=<sdk>/tools/build`、
`RTT_EXEC_PATH=<toolchain>/tools/arm-none-eabi-gcc/<version>/bin`、`CONAN_HOME`、`PKGS_ROOT` 等。
工具链路径从 `%USERPROFILE%\.sifli` 或 `SIFLI_SDK_TOOLS_PATH` 发现；手工在 shell 里跑
`scons` 时至少要设 `RTT_CC=gcc` 并 source 官方 `export.ps1`，否则 SDK 的 `GetLinkScript`
不会搜索 gcc linker script，链接阶段会缺脚本。

### 导出模板的修复

这些不是依赖，但缺了会表现为构建失败；仓库中的模板已包含修复：

- `chip-adapt/sifli/templates/project/Kconfig.proj`：只保留 `CUSTOM_MEM_MAP`；image cache
  符号由 SDK `middleware/lvgl/Kconfig_mem` 提供，重复定义会让 Kconfig 直接 abort。
- `chip-adapt/sifli/templates/src/SConscript`：把 `src/main.c` 编进工程。

### sftool 只做 CLI

host 解析 `sftool.exe` 的逐行 `NN%` 输出来更新进度条；`sftool-gui`、`Impeller` 等 GUI
工具没有集成。`sftool --version` 应输出 `sftool 0.2.5`。查找顺序是 `SFTOOL_BIN` →
`config.json` 的 `sftool` → `~/.sifli/tools/sftool/<version>` → `<toolchain_root>/tools/sftool`
→ PATH；不要在仓库里再放一份 sftool。

## 许可证

| 组件 | 版本 | 许可证 | 位置 |
| --- | --- | --- | --- |
| pyserial | 3.5 | BSD-3-Clause | `vendor/pyserial-3.5.LICENSE.txt` |
| xterm.js | 5.3.0 | MIT | `web/vendor/xterm/LICENSE` |

两者都是未修改的上游发布物。pyserial 由 bootstrap 用
`python -m pip install --target host/vendor --no-deps pyserial==3.5` 安装，安装后删除
`bin/` 与 dist-info；xterm.js 从 jsDelivr 的 `xterm@5.3.0` 下载。
