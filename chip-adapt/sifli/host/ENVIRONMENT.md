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
不阻塞。默认模式只自动处理 pyserial（含许可证）、xterm.js 和 SDK lock venv；Python、uv、SDK 源码与
sftool 属于环境级安装，缺失时脚本给出恢复位置，不擅自改动系统。

## 依赖清单

| 依赖 | 版本 / 安装方式 | 位置 | 说明 |
| --- | --- | --- | --- |
| Python | 3.9+，`python` 在 PATH | 系统安装 | host 只用标准库 + pyserial |
| pyserial | 3.5 | `host/vendor/serial/` | 离线 import；许可证 `host/vendor/pyserial-3.5.LICENSE.txt` 由 bootstrap 下载 |
| xterm.js | 5.3.0 | `host/web/vendor/xterm/` | 浏览器从 `/vendor/xterm/` 加载，运行时不访问 CDN |
| uv | 近期版本 | 系统安装 | 用来装 SDK lock 环境；bootstrap 不自动安装 |
| SiFli SDK | v2.5.1 | `chip-adapt/sifli/vendor/sifli-sdk/`（不进 Git） | 含 `tools/locks/default/uv.lock` |
| SDK lock venv | `uv sync --project <lock> --no-dev` | `.../locks/default/.venv/` | 提供 scons 和构建依赖 |
| sftool | 0.2.5 | `chip-adapt/sifli/vendor/toolchain/sftool/sftool.exe` | 官方烧录 CLI |

SDK 源码、工具链和 sftool 的下载与放置见 `chip-adapt/sifli/vendor/README.md`。

## 脚本之外的手工步骤

只有脚本报 `MISSING` 且不在自动补齐范围时才需要：

- **Python 3.9+**：安装后确保 `python --version` 可用。
- **uv**：按 <https://docs.astral.sh/uv/getting-started/installation/> 安装。
- **SiFli SDK / 工具链 / sftool**：按 `chip-adapt/sifli/vendor/README.md` 恢复，保持表中的相对路径不变。
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
`RTT_EXEC_PATH=<toolchain>/arm-none-eabi/bin`、`CONAN_HOME`、`PKGS_ROOT` 等。
手工在 shell 里跑 `scons` 时至少要设 `RTT_CC=gcc`；否则 SDK 的 `GetLinkScript`
不会搜索 gcc linker script，链接阶段会缺脚本。

### 导出模板的两处修复

这两处不是依赖，但缺了会表现为构建失败；仓库中的模板已包含修复：

- `chip-adapt/sifli/templates/project/Kconfig.proj`：补齐 image cache 的 Kconfig 符号。
- `chip-adapt/sifli/templates/src/SConscript`：把 `src/main.c` 编进工程。

### sftool 只做 CLI

host 解析 `sftool.exe` 的逐行 `NN%` 输出来更新进度条；`sftool-gui`、`Impeller` 等 GUI
工具没有集成。`sftool --version` 应输出 `sftool 0.2.5`。
