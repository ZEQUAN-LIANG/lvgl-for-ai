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

### 国内网络：用 China mirror 安装

`install.ps1` 默认从 GitHub Releases 下载工具链；国内直连经常只有几十 KB/s，
`arm-none-eabi` 一个包就有 300 MB。SDK 自带镜像开关，设置后：

- GitHub Release 资产改走 `https://downloads.sifli.com/github_assets`
- PyPI 默认源改成 `https://mirrors.ustc.edu.cn/pypi/simple`
- `uv` 的 Python 下载元数据改走 `https://uv.agentsmirror.com`

仓库封装入口默认开启镜像，并会在结束后校验 gcc/sftool：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/install-toolchain.ps1
```

- 需要上游源：加 `-NoMirror`。
- `-Offline`、`-Profile <name>`、`-Targets <names>` 转发给 SDK 安装器；`-DryRun` 只打印命令、不安装。
- 不要直接改 `vendor/sifli-sdk/`；封装脚本只调用 SDK 安装器。

等价的手工方式（PowerShell，环境变量只对当前会话生效）：

```powershell
cd chip-adapt/vendor/sifli-sdk
$env:SIFLI_SDK_MIRROR_CHINA = "1"
.\install.ps1
```

`SIFLI_SDK_MIRROR_CHINA` 的取值为 `1/true/yes/on`；`host/cli.py build` 也读取同一个变量，
构建时 `uv` 会使用同一组镜像。`install.ps1` 还接受 `--mirror <url>` 指定自定义
GitHub 资产镜像前缀。

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

## ESP32-C6-LCD-1.47 资料

微雪产品页与文档页链接的附件，2026-11-18 下载；只作本地参考，不参与构建。
示例程序包内含 `Arduino/`、`ESP-IDF/` 和 `Firmware/ESP32-C6-LCD-1.47-Test.bin`。

| 文件 | 来源 | 落点 | 大小 | SHA256 |
| --- | --- | --- | --- | --- |
| 示例程序包 | `https://files.waveshare.net/wiki/ESP32-C6-LCD-1.47/ESP32-C6-LCD-1.47-Demo.zip` | `esp32/demo/ESP32-C6-LCD-1.47-Demo.zip` | 62,844,090 | `4B960E8CCD58E54E60494A2A6DA62531695C9152C9950153CAD34ACC496C4EE4` |
| 原理图 | `https://www.waveshare.net/w/upload/c/c3/ESP32-C6-LCD-1.47_schemetics.pdf` | `esp32/hardware/ESP32-C6-LCD-1.47_schemetics.pdf` | 387,049 | `D8DED2DA08268E27148C700B38C2B1BA62BCA2B734153C7C6E88ECC5E5C72E51` |
| 3D 工程图纸 | `https://www.waveshare.net/w/upload/9/9f/ESP32-C6-LCD-1.47-3D_Drawing.rar` | `esp32/hardware/ESP32-C6-LCD-1.47-3D_Drawing.rar` | 1,988,484 | `55F999CCEC3BA41E38DA8893AFBE2137D75BD82B0E1B06EA96808C5AC33A7037` |
| 数据手册（中文） | `https://documentation.espressif.com/esp32-c6_datasheet_cn.pdf` | `esp32/manuals/esp32-c6_datasheet_cn.pdf` | 1,564,663 | `467C5306994F4E752C27BD195FECAB7D861AA2CF678E6A7DFE4B3E8982F5A876` |
| 数据手册（英文） | `https://documentation.espressif.com/esp32-c6_datasheet_en.pdf` | `esp32/manuals/esp32-c6_datasheet_en.pdf` | 1,003,247 | `C9BF7ECE109859A93BE2B4D780370478655A7830C0C171CEA6670CAF8AB3C339` |
| 技术参考手册（中文） | `https://documentation.espressif.com/esp32-c6_technical_reference_manual_cn.pdf` | `esp32/manuals/esp32-c6_technical_reference_manual_cn.pdf` | 12,929,803 | `8FD50AA490CFF1A8FF35CDA8EA143B8A04B9A166A2E6E0AB0C4E15850490FF88` |
| 技术参考手册（英文） | `https://documentation.espressif.com/esp32-c6_technical_reference_manual_en.pdf` | `esp32/manuals/esp32-c6_technical_reference_manual_en.pdf` | 12,683,821 | `E08D5B61EBCFA2A78F9735E3F721817CB1DC2DF9CF05096D2F0399EABA9F1734` |
| Flash Download Tool | `https://dl.espressif.com/public/flash_download_tool.zip` | `esp32/tools/flash_download_tool.zip` | 25,943,693 | `C1FBF280AA04CD8FBE725BFF74360FB0A7C83FBD49AFCAF37F6C14A6575EA9BC` |
| 串口调试助手 Sscom 5.13.1 | `https://www.waveshare.net/w/upload/b/b3/Sscom5.13.1.zip` | `esp32/tools/Sscom5.13.1.zip` | 420,199 | `D85CCE9C2494EC7DE0163410F45D998C03ED181F01536979A3E0A0DD1256AA07` |
| 蓝牙调试助手 | `https://www.waveshare.net/w/upload/2/2e/ESP32-C6_TO_BLEAssist.zip` | `esp32/tools/ESP32-C6_TO_BLEAssist.zip` | 4,748,243 | `5FDCE249ECB351F44AC396B77E2F52C34E65310C713DA0F23307DA04EB9B7FD2` |
| CH34x macOS 驱动 | `https://www.waveshare.net/w/upload/0/04/CH34XSER_MAC.7z` | `esp32/drivers/CH34XSER_MAC.7z` | 4,123,873 | `C041275B27906B6BEEA109C0D73F937B48E09894373FF4D34D2011A0AEE3DC7E` |
| LVGL 视频教程 | `https://files.waveshare.net/wiki/ESP32-C6-LCD-1.47/ESP32-C6-LVGL-Video.mp4` | `esp32/video/ESP32-C6-LVGL-Video.mp4` | 210,623,798 | `4D6B42B0B8AB9910E0812FCED62E7A749F65B5C35D4AC05290C3D63949135488` |

校验方式（Git Bash）：

```bash
cd chip-adapt/vendor/esp32
sha256sum demo/ESP32-C6-LCD-1.47-Demo.zip   # 与上表逐项对照
```

## 升级流程

1. 修改本文件的版本/commit/校验值。
2. 重新下载或切换 commit；不要直接改 SDK 工作树。
3. 跑 `python -I chip-adapt/sifli/run_tests.py`、host 测试、导出 dry-run。
4. 复核 `sifli.html` 中引用的 SDK 入口路径和 `adapter.json` 的 `sdk_version`。
5. 确认 `git status` 不出现 `chip-adapt/vendor/` 或 `chip-adapt/exports/`。
