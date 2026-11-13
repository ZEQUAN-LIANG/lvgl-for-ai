# chip-adapt 外部下载物

本目录只放**外部下载物**，不进 Git（本文件除外）。不要在这里改代码；需要补丁时
改 `chip-adapt/sifli/` 的模板或导出器，不要直接改 SDK。

## 清单

| 组件 | 来源 / 版本 | 落点 | 必选 | 校验 |
| --- | --- | --- | --- | --- |
| SiFli-SDK | Gitee `SiFli/sifli-sdk` 或 GitHub `OpenSiFli/SiFli-SDK`，`release/v2.5`，commit `f4042d7e66f144feba9f88ecb7ca0eda8a92c3bc` | `vendor/sifli-sdk/` | 是 | `version.txt` = `v2.5.1`；`git rev-parse HEAD` 与上表一致 |
| ARM 工具链 | SDK `install.ps1`（需要 `uv`） | `%USERPROFILE%\.sifli\tools\arm-none-eabi-gcc\14.2.1\bin`，或 `SIFLI_SDK_TOOLS_PATH` | 是 | `arm-none-eabi-gcc --version` |
| sftool | SDK `tools.json` 声明，`install.ps1` 安装；0.2.5 win64 zip | `%USERPROFILE%\.sifli\tools\sftool\0.2.5\sftool.exe` | 是 | `sftool --version` = `sftool 0.2.5` |
| SiFli-Wiki Web Flasher | `OpenSiFli/SiFli-Wiki` 的 `source/_static/sftool` | `vendor/sifli-wiki/` | 否 | 页面 `index.html` 与 `assets/` 存在 |
| pyserial | 3.5，`bootstrap.ps1` 安装 | `sifli/host/vendor/` | 是 | `import serial` 成功 |
| xterm.js | 5.3.0，`bootstrap.ps1` 下载 | `sifli/host/web/vendor/xterm/` | 是 | JS/CSS/LICENSE 三个文件非空 |

## SDK

从仓库根执行（Gitee；GitHub 把 URL 换成 `https://github.com/OpenSiFli/SiFli-SDK.git`）：

```bash
git clone -b release/v2.5 https://gitee.com/SiFli/sifli-sdk.git chip-adapt/vendor/sifli-sdk
git -C chip-adapt/vendor/sifli-sdk checkout f4042d7e66f144feba9f88ecb7ca0eda8a92c3bc
git -C chip-adapt/vendor/sifli-sdk submodule update --init tools/SiliconSchema middleware/bluetooth
```

- 两个子模块都是构建必需：`tools/SiliconSchema` 提供分区表工具，`middleware/Kconfig`
  无条件 `rsource "bluetooth/Kconfig"`，缺 `middleware/bluetooth` 会在生成 `.config` 时失败。
- 当前本地 `git tag -l 'v2.5*'` 为空，所以用 **commit + `version.txt`** 校验，不要只认 tag。

## 工具链与 sftool

官方安装器会按 `SIFLI_SDK_TOOLS_PATH`（默认 `%USERPROFILE%\.sifli`）安装：

```powershell
cd chip-adapt/vendor/sifli-sdk
.\install.ps1
```

安装后的关键路径：

```text
%USERPROFILE%\.sifli\tools\arm-none-eabi-gcc\14.2.1\bin\arm-none-eabi-gcc.exe
%USERPROFILE%\.sifli\tools\sftool\0.2.5\sftool.exe
```

如果机器上已经有工具链，设置 `SIFLI_SDK_TOOLS_PATH` 指向同一套目录结构，不要复制进仓库。
宿主的 `bootstrap.ps1 -Check` 和 `host/cli.py status --json` 会报告实际找到的路径。

离线手装 sftool 0.2.5（Windows x64）时使用 SDK `tools.json` 里的固定资产：

```text
https://github.com/OpenSiFli/sftool/releases/download/0.2.5/sftool-0.2.5-x86_64-pc-windows-msvc.zip
SHA256 64A8C52901553858A4EFB9F9484CDE7E71473B5B70A7803956FD22A6DCDEBB5B
```

解压后的 `sftool.exe` 放到 `%USERPROFILE%\.sifli\tools\sftool\0.2.5\`；或者用
`SFTOOL_BIN` 指向它。仓库内不再维护第二份 sftool。

## 可选：Web Flasher 资源

只需要静态目录，不要整站 clone：

```bash
git clone --filter=blob:none --sparse https://github.com/OpenSiFli/SiFli-Wiki.git chip-adapt/vendor/sifli-wiki
git -C chip-adapt/vendor/sifli-wiki sparse-checkout set source/_static/sftool
```

## 上位机运行时依赖

由 `chip-adapt/sifli/host/scripts/bootstrap.ps1` 管理：

- pyserial 3.5 → `sifli/host/vendor/`，许可证 `pyserial-3.5.LICENSE.txt`。
- xterm.js 5.3.0 → `sifli/host/web/vendor/xterm/`（JS/CSS/LICENSE 缺一不可）。

## 升级流程

1. 修改本文件的版本/commit/校验值。
2. 重新下载或切换 commit；不要直接改 SDK 工作树。
3. 跑 `python -I chip-adapt/sifli/run_tests.py`、host 测试、导出 dry-run。
4. 复核 `sifli.html` 中引用的 SDK 入口路径和 `adapter.json` 的 `sdk_version`。
5. 确认 `git status` 不出现 `chip-adapt/vendor/` 或 `chip-adapt/exports/`。
