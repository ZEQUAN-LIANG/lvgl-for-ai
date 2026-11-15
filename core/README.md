# LVGL AI Tools

真实 headless LVGL 运行时 + 取证 + 回放。工具只提供环境、输入和证据，不判定画面；验收标准由人在聊天里给出。

第三方许可声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与仓库根 `licenses/`。

本文件位于工具根 `core/`；下面列出的路径相对本目录，命令示例在**仓库根**执行。

## 工具目录

- `lvgl_ai/`：Python 控制层。`Runtime`（一个实例 = 一个 LVGL 进程 = 一次会话）、`Recording`（只读证据视图，annotations 可写）、`play_scenario`、`apps/`（应用管理 package：common / policy / registry / scaffold / trash / views）、错误类型、`web/`（HTTP/UI 适配）。
- `engine/`：C engine，负责协议、虚拟 indev、录帧、时间轴、窗口。
- `cli.py`：命令行入口。
- `assets.py`：字体/图片转 LVGL C 数组入口，不启动 engine 或网页。
- `session_report.py`：会话证据摘要入口，不启动 engine 或网页。
- `web.py`：网页端入口。
- `lvgl_ai/assets/`：资源转换实现与随包 vendored FreeType/pypng（`vendor/`）。
- `tests/`：`python -I` 测试套件。
- `api-nav/`：每个 LVGL 版本一份 API 导航。
- `tools/fetch_lvgl.py`：下载官方 LVGL、校验版本并应用本地 patch。
- `tools/fetch_png.py`：下载 pin 的 zlib / libpng 源码到 `third_party/`，供 engine 编码 PNG。
- `tools/new_app.py`：生成应用变体的源文件与场景，并注册到 `user/app/app.c`。
- `tools/export_sdk.py`：从 `lvgl-src/<version>` 导出宿主预编译 SDK 到 `sdk/<version>`。
- `tools/install_version.py`：安装其他 LVGL 版本（源码或自定义版本包），读取
  `meta/versions.json`（开发仓库与发布包同一位置）。
- `tools/release.py`：生成单个可分发 skill zip、`.sha256` 与 release manifest。
- `tools/release_all.py`：构建默认的两个完整包：`full` 与 `full-sifli`。
- `tools/sync_github.py`：把 Gitee（`origin`）的分支与标签强制镜像到 GitHub（`github`）。
- `tools/lvgl.py`：统一入口，分发 `run` / `report` / `serve` / `assets`。
- `tools/contract_snapshot.py`：记录/对比六类外部契约快照，用于重构行为冻结；用法见
  [CONTRACT_SNAPSHOT.md](CONTRACT_SNAPSHOT.md)。

## 仓库目录

| 路径 | 内容 |
| --- | --- |
| `core/` | 工具根：`lvgl_ai/` Python 控制层、`engine/` C engine、`cli.py`、`web.py`、`tests/`、`tools/`、`api-nav/` |
| `user/app/` | 应用变体源码；`app.c` 的 `apps[]` 是注册表 |
| `user/scenarios/` | 场景 JSON |
| `lvgl-src/` | 只跟踪 README；各版本源码按需下载 |
| `third_party/` | zlib / libpng 源码（按需下载，Git 忽略） |
| `build/` | engine 构建产物（Git 忽略） |
| `sdk/` | 预编译宿主 SDK（Git 忽略；由 `export_sdk.py` 生成） |
| `release/` | 解包后的 skill 目录、发布 zip、sha256 与 release manifest（Git 忽略） |
| `meta/` | 包元数据：`versions.json`；发布包还含 `VERSION.json` |
| `bin/` | `lvgl.cmd` 统一入口包装脚本 |
| `sessions/` | 会话证据（Git 忽略） |
| `docs/` | 应用变体与场景/服务端常量的索引指针页；SiFli 能力索引见 `chip-adapt/docs/sifli.html` |
| `licenses/` | 第三方许可全文 |
| `patches/` | LVGL patch 组织说明与可选 patch |
| `core/SKILL.md` | 可分发 skill 的入口契约与 agent 工作流 |

## 环境准备

发布包不自带 Python；宿主机必须提供 Python 3.9+ 并在 PATH 上（工具层只使用标准库）。
`bin\lvgl.cmd` 使用 PATH 上的 `python`（缺失时回退 `py -3`），`bin\LVGL-AI-Viewer.exe`
使用 `pythonw`（缺失时回退 `pyw`）。解压后运行仍然不需要 CMake；改
`user/app/**/*.c` 后重新编译需要 GCC 15.2.0（与随包 SDK 的 manifest 一致）。

运行预编译 engine 不需要 GCC、CMake、Ninja、LVGL 源码或 `third_party/`。只有重新
编译 `user/app/**/*.c` 时需要 GCC（Windows 为 MinGW-w64 64 位，15.2.0，与 SDK
manifest 一致）；源码构建模式还需要 CMake 3.20+、Ninja 和 curl。ccache 可选，git 用于拉取 `third_party/` 的 PNG 编码器
源码以及应用 `patches/`。

资源转换器额外使用随包内置的 freetype-py（含 FreeType DLL）与 pypng，位于
`core/lvgl_ai/assets/vendor/`；不需要 `pip install`、Node.js 或联网。生成好的 C 数组
是普通 LVGL 资源，构建和运行时不再需要转换器。

host engine 默认开启 `LV_USE_FREETYPE=1`，8.3–9.6 都链接随包 FreeType 2.13.2：
`core/engine/freetype/include` 是头文件，`lib/libfreetype.dll.a` 是导入库，
`libfreetype.dll` 在构建后复制到 engine 旁边。预编译 SDK 同样携带头文件、导入库
和 DLL，预编译链接会自动把 DLL 放到 engine 目录。

### Windows：MSYS2 UCRT64

安装 [MSYS2](https://www.msys2.org/) 后，在 **MSYS2 UCRT64** 终端执行：

```bash
pacman -Syu
# 终端重启后
pacman -S --needed \
  mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-cmake \
  mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-curl \
  mingw-w64-ucrt-x86_64-ccache
```

把 `C:\msys64\ucrt64\bin` 加入 Windows `PATH`，并放在会遮蔽它的路径之前。然后在
Git Bash / PowerShell / cmd 中验证：

```bash
python --version
cmake --version
ninja --version
gcc --version
curl --version

# Git Bash
which -a cmake ninja gcc
# PowerShell / cmd
where.exe cmake
where.exe ninja
where.exe gcc
```

注意：

- `python` 建议使用 [python.org](https://www.python.org/) 安装的版本；若打开的是 Microsoft Store，请关闭 App Execution Alias，或改用 `py -3`。
- 必须使用 MinGW-w64 GCC；MSVC 不在支持路径内。
- winget 也可安装部分工具（如 `Kitware.CMake`、`Ninja-build.Ninja`），但 GCC 仍建议通过 MSYS2 获取；本仓库未在 winget 路线上复测。

## 首次运行

```bash
# 1. 检查环境
python --version
cmake --version
ninja --version
gcc --version

# 2. 下载并安装 LVGL 9.6 源码
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .

# 3. 下载 PNG 编码器源码（zlib / libpng，安装到 third_party/）
python -I core/tools/fetch_png.py --repo-root .

# 4. 跑一个场景（首次会构建 engine）
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/settings.json

# 5. 或启动网页端
python -I core/web.py --open
```

默认的 `--source auto` 会先试 GitHub codeload，再试 Gitee 镜像；Gitee 的 LVGL
镜像当前可能返回 HTML/400，下载失败时请使用默认值或预编译版本包：

```bash
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root . --source auto
```

说明：

- `fetch_lvgl.py` 成功后会输出 `installed LVGL 9.6.0 -> .../lvgl-src/9.6`，并写入 `.lvgl-ai-source.json`。
- `fetch_png.py` 会把 zlib 1.3.1 与 libpng 1.6.44 安装到 `third_party/zlib/`、`third_party/libpng/`；构建前若缺失会直接报错并提示重跑该命令。
- 首次构建会编译整个 LVGL，通常需要数分钟；工具对 configure / build 每个阶段设置 600 秒硬超时。
- CLI 成功退出码为 `0`，stdout 最后一行是会话目录；会话 `manifest.json` 的 `status` 应为 `ok`。
- 网页端默认地址 `http://127.0.0.1:8765/`；端口冲突时用 `--port 0` 或 `--port 8766`，Ctrl+C 停止。
- Windows 无控制台启动可双击 `bin/LVGL-AI-Viewer.exe`（需要 `pythonw.exe` 或 `pyw.exe` 在 PATH 中；该 exe 不随 Git 提交，用 `python -I core/tools/launchers/build.py` 生成）。

## 准备 LVGL 源码

`lvgl-src/` 不随仓库提交，只保留 `lvgl-src/README.md` 说明。源码构建前先下载并安装对应版本：

```bash
python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .
```

脚本按固定 tag 下载官方源码、校验版本宏、应用 `patches/<version>/` 下的 patch，再安装到
`lvgl-src/<version>/`；安装后写入 `.lvgl-ai-source.json` 记录 tag 与 patch。跳过 patch 用
`--no-patch`，自定义 patch 根用 `--patch-dir`。patch 的组织、生成与手动应用见
`patches/README.md`。

## 准备 PNG 编码器源码

engine 用 libpng + zlib 编码录制帧与 snapshot，不再使用 LVGL 内置 lodepng 的编码器。
`third_party/` 不随仓库提交，源码构建前先执行：

```bash
python -I core/tools/fetch_png.py --repo-root .
```

脚本按固定 tag/commit 拉取 zlib 1.3.1 与 libpng 1.6.44，校验版本后安装到
`third_party/zlib/` 和 `third_party/libpng/`；CMake 静态编译这两个库。无法访问 GitHub 时，
可先手动准备好这两个目录，或设置 `LVGL_AI_ZLIB_SRC` / `LVGL_AI_LIBPNG_SRC` 指向已有源码。

## 预编译宿主 SDK

没有 LVGL 源码时，用预编译宿主 SDK 直接编译 `user/app`。SDK 包含五份静态库
（engine / adapter / LVGL / libpng / zlib）、FreeType 导入库、公共头、FreeType
头文件、`lv_conf.h`、运行时 `libfreetype.dll` 和 `manifest.json`
（`lvgl-ai-host-sdk-v1`，记录编译器版本、defines、include 顺序、链接顺序、
运行时 DLL 与每份库的 sha256）：

```bash
# 从 lvgl-src/<version> 导出；默认输出 sdk/<version>
python -I core/tools/export_sdk.py --version 9.6
python -I core/tools/export_sdk.py --version 9.6 --json

# 重新导出已有 SDK
python -I core/tools/export_sdk.py --version 9.6 --force
```

SDK 是构建产物（`/sdk/` 不进 Git）。预编译构建只调用 GCC，不需要 CMake、Ninja、
LVGL 源码或 `third_party/`。构建前会校验 manifest 记录的编译器版本；版本不一致时
用 `LVGL_AI_GCC` 指向匹配的编译器，或重新导出 SDK。

## 构建方式选择

CLI 的选择规则：

- `lvgl-src/<version>` 存在且未显式指定时，走现有 CMake 源码构建。
- 源码缺失且 `sdk/<version>` 存在时，自动走预编译构建。
- `--prebuilt` 强制预编译；`--source` 强制源码构建。
- `--no-build` 始终只复用 `build/lvgl_<version>/lvgl_engine.exe`。

实际选择写入会话的 `build.log`（`# build mode: prebuilt` 或 CMake 阶段日志）。
预编译构建的对象缓存位于 `build/lvgl_<version>/.prebuilt/`，缓存键包含源文件、
头文件、SDK manifest 哈希与编译器版本；切换回源码构建时会删除预编译 engine，
避免 Ninja 误以为目标已是最新。

```bash
python -I core/cli.py --lvgl 9.6 --prebuilt --scenario user/scenarios/settings.json --json
python -I core/cli.py --lvgl 9.6 --source   --scenario user/scenarios/settings.json --json
```

## 安装其他 LVGL 版本

开发仓库默认只导出 `sdk/9.6`；发布包带齐六个版本。`meta/versions.json` 列出支持的
版本与是否支持 `intro`；需要自定义安装时：

```bash
python -I core/tools/install_version.py --list
python -I core/tools/install_version.py --lvgl 9.4 --source auto
python -I core/tools/install_version.py --lvgl 9.4 --no-build
python -I core/tools/install_version.py --lvgl 9.4 --mode pack --pack version-pack.zip
```

源码模式封装 `fetch_lvgl.py`、`fetch_png.py` 与 `export_sdk.py`，然后按 `meta/versions.json`
的 `sdk` 标记选择预编译或 CMake 源码构建 engine。pack 模式只解包
`sdk/<version>` 与 `build/lvgl_<token>`，不需要 CMake/Ninja；修改用户 C 代码仍需
GCC 15.2.0（与 SDK manifest 一致）。
场景可选 `"lvgl": "9.4"`，优先级是 `--lvgl` > 场景 `lvgl` > `LVGL_AI_LVGL_VERSION` > 9.6。

## 统一入口

`core/tools/lvgl.py` 把 `run` / `report` / `serve` 映射到现有入口；包内
`bin/lvgl.cmd` 只是包装脚本，不掺协议或构建逻辑：

```bash
python -I core/tools/lvgl.py run --scenario user/scenarios/settings.json --json
python -I core/tools/lvgl.py report --latest --log-tail 5
python -I core/tools/lvgl.py serve
python -I core/tools/lvgl.py assets font --app coffee --font C:\Windows\Fonts\Deng.ttf --size 16
python -I core/tools/lvgl.py assets image --app coffee --input logo.png --cf ARGB8888
python -I core/tools/lvgl.py assets doctor --json
```

字体 `--bpp 8` 只适用于 8.x 或 9.3+；9.1/9.2 的明文位图路径没有 8 bpp 分支，
工具会拒绝生成，建议改用 `--bpp 4`。

## 发布包

默认发布两个完整包（都带六个版本）：

```bash
python -I core/tools/release_all.py --out release --json
```

发布脚本按 engine 输入摘要复用 `build/release/lvgl_<token>/` 下的预编译 engine：
engine / 用户应用源码、宿主 SDK manifest 或 GCC 版本未变时不再重编，只重新打包；
`--force-build` 强制重建。Windows 双击启动器同样只在其源码摘要变化时重建。

也可以只用 `release.py` 打单版本包（产出 skill zip、`.sha256` 和 release manifest）：

```bash
# 默认 9.6；缺少 SDK 时自动导出；产物在 release/
python -I core/tools/release.py --out release --json
```

单版本 `release.py` 还会在 `release/` 保留解包后的 skill 目录
`release/lvgl-verify-loop/`：根目录只有
`SKILL.md`，其余内容在 `core/`、`user/`、`sdk/`、`build/`、`bin/`、`docs/`、
`meta/` 与 `licenses/` 下。该目录与同名 zip、`.sha256`、release
manifest 并列，可以直接在 `release/lvgl-verify-loop/` 里运行，不必先解压。

发布包只带 `user/app/intro/` 一个应用（默认介绍页与模板），其他示例应用留在开发
仓库。包内包含 `core/`、`user/`、`sdk/<version>/`、预编译 engine、`bin/lvgl.cmd`、
`bin/LVGL-AI-Viewer.exe`、`docs/intro-demo.gif`、`meta/VERSION.json`、
`meta/versions.json` 与 `licenses/`。多版本包把各 SDK 中完全相同的 FreeType DLL、
导入库和公共头文件收到 `sdk/common/`，`build/` 下不再重复放置 DLL。
LVGL 源码、`third_party/`、
`sessions/`、测试目录、`chip-adapt/vendor`、`chip-adapt/exports`、构建中间物和开发机
绝对路径不会进包（二进制里的 `__FILE__` 与调试信息也会被检查）；打包前会在暂存目录
从无关工作目录运行 `--no-build`、预编译构建、统一入口和网页端 smoke。`--skip-smoke`
只用于开发调试。

## 启动网页端

控制台入口：

```bash
python -I core/web.py
```

Windows 无控制台入口：

```text
双击 bin\LVGL-AI-Viewer.exe
或：双击 core/web.pyw
或：pythonw -I core/web.pyw
```

`web.pyw` 自动打开浏览器，并默认启用 `--exit-on-close`：最后一个网页关闭约 0.5 秒后停止服务并收尾 engine。不带参数启动（双击 `web.pyw`、`bin/LVGL-AI-Viewer.exe` 或经 `pythonw`）时，如果默认地址上已有服务在监听，它只打开页面并退出（暖启动），不会重复启动 server；带参数时保持普通启动路径。控制台入口需要显式加 `--exit-on-close` 才有相同行为。

`bin/LVGL-AI-Viewer.exe` 是带图标的完全无黑框启动入口：双击即可，只负责在 PATH 中找到 `pythonw.exe`（找不到时回退 `pyw.exe`）并启动 `core/web.pyw`；端口探测与打开的 URL 都在 Python 里。启动器源码、图标与构建脚本在 `core/tools/launchers/`，用 `python -I core/tools/launchers/build.py` 重新生成（需要 MinGW gcc 与 windres）。旧的 `.vbs` / `.cmd` 入口已移除。

默认固定端口 `8765`，地址：

```
http://127.0.0.1:8765/
```

- 页面包含回放（完整帧、关键画面、时间轴、框选标注）和 live（启动 / 停止独立 Runtime）。
- 顶部「应用」下拉从 `user/scenarios/*.json` 中声明了 `app` 的 scenario 生成；第一个应用是默认值，打开页面就会自动以测试模式预览它，选中其他应用立即切换，不需要再点「测试」，也不需要重启 `web.py`。选项里没有写死应用名。live 分辨率跟随该应用对应场景的 `display`；同一应用有多个场景时取文件名字典序第一个，画布按帧头自适应。
- 技术细节（manifest、checks、原始 diff、engine.log、build.log）默认折叠在 `<details>` 中。
- 只读像素 diff 默认关闭；打开后按 `frame_diffs.ndjson`（以及可选的参考图 diff）覆盖显示 bbox，只作证据。
- 网页端只通过 `Runtime` / `Recording` 工作，没有第二套协议客户端；live 使用独立 Runtime 和独立 engine 进程。
- 测试与录制均每 33 ms 推进一次虚拟时间（约 30 fps）；PNG 编码由 engine 的 3 个后台 worker 完成，不阻塞 tick。无输入时 timer、toast 和动画继续运行。录制固定只保留画面发生变化的帧（没有逐帧开关），HUD 时间使用虚拟时间 `t_ms`。
- 测试/录制预览走 raw 帧流：engine 写 `live.rgba`，页面通过 `GET /api/live/stream` 接到 canvas，不再轮询 PNG。`live.rgba` 是临时预览文件，停止时删除，不是证据。
- Windows 下 engine 与 cmake/ninja 子进程使用 `CREATE_NO_WINDOW`；从 `web.pyw` / `pythonw` 启动时不会弹出控制台黑框，切换应用也不会闪。
- 非 Windows、无浏览器环境不影响服务启动；`web.py` 默认不自动打开浏览器，需要时加 `--open`；`web.pyw` 会自动打开。
- 端口被占用或需要换地址时：`python -I core/web.py --host 127.0.0.1 --port 8766`。

`web.py` 支持 `--sessions-root`（默认 `LVGL_AI_SESSIONS_ROOT` 或仓库根的 `sessions/`）、`--lvgl`（live 使用，默认 `LVGL_AI_LVGL_VERSION` 或 `9.6`）、`--app NAME`（打开页面时预选并测试预览该应用）、`--manage`（打开页面时显示应用管理对话框）、`--open`（自动开浏览器）、`--exit-on-close`（最后一个网页关闭后退出）。`--app` 只影响打开的页面 URL（`?app=NAME`），有 live 会话运行时当前会话优先。

## 新建应用

```bash
# 先看计划，不写文件
python -I core/tools/new_app.py myapp --dry-run

# 生成 user/app/myapp/、user/scenarios/myapp.json，并注册到 app.c
python -I core/tools/new_app.py myapp

# 构建并跑场景
python -I core/cli.py --scenario user/scenarios/myapp.json

# 构建并在网页里直接预览
python -I core/web.py --app myapp --open
```

完整教程见 `user/app/GUIDE.md`。脚手架只生成骨架，界面仍由人/AI 写 C；新代码必须
源码构建，不能依赖预编译 engine。需要非默认分辨率时，在生成的场景顶层加
`"display": {"width": 640, "height": 480}`；尺寸在 engine 启动时传入，改尺寸不需要
重新编译 engine。

## 应用管理台

网页端顶部的「应用管理」按钮打开管理对话框；需要启动时直接打开时，用
`python -I core/web.py --manage --open`。双击 `bin/LVGL-AI-Viewer.exe` 仍打开普通页面。
管理台可以：

- 选择/预览/测试/录制应用（复用顶部现有控件）；
- 新建应用，显示源文件、场景和注册表路径；
- 查看应用目录树、`user/app/app.c` 注册和场景文件；
- 删除应用到 `user/.trash/apps/<trash-id>/`，从回收站恢复，或再次确认后永久删除；
- 查看上次操作和最近修改时间。

删除会同时移除 `user/app/app.c` 的 include 与 `apps[]` 行，并移走所有顶层 `app`
匹配的场景。`coffee`、`xiaohongshu`、`spectrum` 等内置应用受保护，不能删除。
`user/.trash/` 不参与构建。

管理接口只接受本机页面发起的 JSON POST（`Content-Type: application/json` 与
`X-LVGL-AI-Request: 1`），live 启动/运行中拒绝修改应用。

## 命令行

```bash
# scenario 顶层声明 "app" 时，CLI 自动把应用传给 engine
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/xiaohongshu.json

# 已有 build/ 产物时跳过重新构建
python -I core/cli.py --no-build --lvgl 9.6 --scenario user/scenarios/settings.json

# 没有 scenario 时用 --app；--idle 保持会话直到 Ctrl+C（headless）
python -I core/cli.py --lvgl 9.6 --app coffee --idle

# 机器可读摘要（含 app）
python -I core/cli.py --scenario user/scenarios/settings.json --json
```

`--app NAME` 选择用户应用变体，启动时写入 `LVGL_AI_DEMO`；`--scenario` 的 `app` 优先于
继承的环境变量，显式 `--app` 再覆盖 scenario。scenario 的 `app` 字段匹配
`[A-Za-z0-9_-]+`，工具不维护应用清单。

scenario 顶层可选 `"display": {"width": W, "height": H}`（`1..4096`）；CLI 把宽高传给
engine，不写时使用默认 800×600。显式 `--app` 只覆盖应用，不覆盖场景的 `display`。

录制固定只保存相对上一张保留帧发生 RGB 变化的帧（CLI 与网页 live 一致，没有逐帧开关）。`frame_count` 是保留帧数，静态画面不消耗 `max_frames` 预算，人类与 AI 都不必读重复帧；live 预览也遵循同一变化门控。

录制默认使用 3 个后台 worker 编码 PNG：主线程把保留帧复制到有界内存队列，worker 用 libpng 快速模式编码后发布到 `frames/`；`.encode/` 只保存编码中的临时 PNG。`start()` 返回时首帧 PNG 已落盘；网页 live 的录制与测试都以 33 ms（约 30fps）推进，运行中 `frames/` 可能滞后于 `timeline.ndjson` 的 frame 行，`stop()` 会等待全部编码完成再写 `end` 行。内存队列默认最多 256 MiB，可用 `LVGL_AI_ENCODE_BUDGET_BYTES` 覆盖；超过预算时主线程等待编码，队列为空时允许单个超预算帧。

`--build/--no-build` 默认 `--build`；`--no-build` 复用仓库根
`build/lvgl_<version>/lvgl_engine`，不重新编译 `user/app`。产物不存在时抛
`EngineNotFound`；改过 C 代码后仍要用源码构建。

退出码：`0` 会话正常结束；`1` build / link / crash；`2` harness、scenario、协议或环境错误。会话证据可读时，`--json` 输出与 `session_report.py --json` 相同的 `lvgl-ai-session-index-v1` 索引；读取失败时只保留 `session_id` / `manifest_path` / `app` / `error` 四个字段，不改变退出码；诊断只走 stderr。

## 会话报告

不启动 engine、不启动网页，读取已有会话的证据：

```bash
# 最新会话的索引（人类可读；加 --json 输出同一份 JSON）
python -I core/session_report.py
python -I core/session_report.py sessions/<id> --json
python -I core/session_report.py sessions/<id> --compact

# 有界查询：每行最多 N 条，全部支持 --json
python -I core/session_report.py timeline sessions/<id> --limit 20
python -I core/session_report.py diffs sessions/<id> --after-t 2280 --before-t 2300
python -I core/session_report.py frames sessions/<id> --last 3
python -I core/session_report.py notes sessions/<id> --resolve sessions/<new>
python -I core/session_report.py resolve sessions/<id> --click 41:43 --at result
python -I core/session_report.py context sessions/<id> --click 41:43 --window-ms 200
python -I core/session_report.py feedback sessions/<old> --previous sessions/<new>
```

会话根默认 `sessions/`，可用 `LVGL_AI_SESSIONS_ROOT` 覆盖；无参数或 `--latest` 取最新会话。索引是查询计划：counts、raw 文件体积/行数、timeline 终点、最大变化区域、clicks（`frame_before` / `frame_after`）、snapshots、marks、notes、whiteboards、日志尾部和 `next_reads` 命令；快照列表只保留最近 5 条与总数，避免索引膨胀。

索引字段以 `core/lvgl_ai/control/evidence.py` 的 `INDEX_FIELDS` 为准；`session_dir` 是绝对路径，索引里的 frames / snapshots / diff 图片路径相对 `session_dir`，视觉命令传 `--session` 即可解析。`recorded` 与 `Recording.open()` 使用同一规则：manifest 描述录制（`frame_count > 0` 或 artifacts 含 `timeline` / `frame_diffs`）时必须同时存在 `timeline.ndjson` 与 `frame_diffs.ndjson`，缺失按损坏证据报错；`record=False` 或 crash 会话没有这些文件时返回空列表并标记 `recorded: false`，只有 `manifest.json` 或 `engine.log` 缺失才算错误。crash / harness_error 会话的 `timeline.ndjson` 可以包含被截断的行，索引会跳过无法解析的行。未知会话或损坏文件退出码 `2`，错误只走 stderr。

`resolve` 按 timeline 行顺序选帧，不按精确 `t_ms`：input 命令只入队 LVGL，录帧发生在 `tick` / `wait`。`click --at event` 取 down 前最后一帧，`--at result` 取 up 后第一条 evidence（帧或 snapshot）；`mark` 优先同 `t_ms` 的 snapshot。

`crop`、`contact-sheet` 与 `compare --out` 的输出路径必须显式给出，且不能落在任一源会话的证据目录内：写入 `sessions/<id>/` 的新 PNG 会被 `Recording.frames` / `Recording.snapshots` 当成证据。`pixel` 只读不写。`crop` / `pixel` / `contact-sheet` 接受 `--session`，用于解析索引里的相对图片路径。`compare` 的会话输入取最后一张快照；没有快照时取文件名排序的最后一帧，规则同时写在 `--help` 与票 09。

人类反馈用 `core/feedback.py add` 写入（`author` 只能是 `human`，`source` 是 `web` / `chat`）：`--click` / `--mark` / `--input-seq` / `--t-ms` / `--frame` 选一个锚点，`--region` 可重复。note 存在 `annotations.json`，包含 `author` / `source` / `feedback_anchor`；retention 不会删除含非空 note 或白板的会话。

Python 侧的稳定入口是 `lvgl_ai.session_index(session, log_tail_lines=10, compact=False)`，接受会话目录或 `manifest.json`。

## 等待画面稳定

`Runtime.wait_stable(max_ms, stable_frames)` 以 16 ms 步进调用引擎 `wait`，累计连续 `changed=false` 的次数，达到 `stable_frames` 或 `max_ms` 上限后返回 `waited_ms` / `stable_frames` / `stable`；返回值是证据，不是 pass/fail。它只依据 `wait` 回执的 `changed` 布尔字段，与变化帧门控的保留帧数无关，因此保留帧数为 0 不会被当成稳定。

`changed` 表示该次 `wait` 期间至少有一次 display flush。9.x 与 8.x 的实现边界相同：`core/engine/adapter_9x.c` 和 `core/engine/adapter_8x.c` 都在 flush callback 里设置同一个 `refresh_painted` flag，`core/engine/session.c` 把 flag 汇总进 `wait` / `wait frames` 回执；`tick`、`pointer` 等其它回执不带该字段。支持的 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3 都具备该信号，不需要版本降级。缺 `changed` 字段的旧 engine 会在第一次轮询时报错并提示 `--build` 重建，不会无限等待。

## Python

```python
from lvgl_ai import Recording, Runtime, play_scenario

with Runtime(lvgl="9.6", app="coffee") as rt:   # app 省略时用 LVGL_AI_DEMO / 用户代码默认值
    play_scenario(rt, "user/scenarios/coffee.json")
    print(rt.recording.timeline())

recording = Recording.open("sessions/<id>")
print(recording.manifest["app"], recording.manifest["frame_count"])
```

旧 import 路径 `lvgl_ai.core`、`lvgl_ai.region`、`lvgl_ai.web.server`、`lvgl_ai.web.stream`、`lvgl_ai.web.page`、`lvgl_ai.web.region_images` 已移除；控制层请改用 `lvgl_ai` 顶层导出或 `lvgl_ai.control`，web 请改用 `lvgl_ai.web` 包内模块。

嵌入方可以用 `Runtime(lvgl="9.6", width=640, height=480)` 指定显示尺寸；宽高必须成对且
为 `1..4096`，省略时使用 engine 默认 800×600。实际尺寸以 engine 的 `ready.display` 为准。

`Recording.annotations` 是唯一可写入口；写入使用临时文件加替换。

## 会话产物

`sessions/<id>/`：

- `manifest.json`（`lvgl-ai-session-v1`）：status / app / display / record_changed_only / mode / input / build / lvgl / frame_count / checks / error / artifacts
- `error.detail`：build / link 失败包含 `log_tail`（最后 40 行、最多 8 KB）和 `command`；crash 包含 `exit_code` 与 `log_tail`
- `frames/`、`snapshots/`：保留帧与命名快照的完整 PNG；changed-only 时静态帧不落盘，`frame_count` 是保留帧数
- `timeline.ndjson`、`frame_diffs.ndjson`、`engine.log`、`build.log`
- `annotations.json`（`lvgl-ai-annotations-v1`）：`notes` 数组，每条含 `id` / `frame_no` / `t_ms` / `regions` / `tags` / `text`
- `live.rgba`：仅 live 预览期间存在，原始 RGBA8888，停止时删除；不列入 manifest artifacts
- `.encode/`：编码中的临时 PNG 目录；正常停止后删除，不列入证据

保留策略：每次新建会话后，`build_error` 会话一律删除，其余只保留最新的 10 条；没有 `manifest.json` 的目录不会动。

## 版本

`LVGL_AI_LVGL_VERSION` 选择 `lvgl-src/<version>`，支持 `9.6` / `9.5` / `9.4` / `9.1` / `8.4` / `8.3`；`LVGL_AI_LVGL_SRC` 可覆盖源码路径。`LVGL_AI_USER_APP_DIR` 可指向导出的应用目录（例如 `chip-adapt/exports/<app>/src/app`），用于运行时验证；非默认目录的构建输出在 `build/lvgl_<token>_export_<label>_<hash>`，与 `user/app` 的 `build/lvgl_<token>` 隔离。构建前会获取该目录的跨进程锁，并等待或终止 PID 文件记录的残留 engine。跨版本比较事件语义，不比较像素。

## Upgrading LVGL（升级检查清单）

升级 `lvgl-src/<version>` 或新增受支持版本前，先复核这些非公开依赖；它们不在 LVGL 的公开 API 契约内，升级时可能静默改变语义：

1. **命中测试**：`core/engine/adapter_9x.c:113` 的 `hit_test` 使用 `lv_indev_search_obj`，这是 LVGL 内部辅助函数。9.4 起 `lv_obj_class_t::name` 移入私有头，`adapter_9x.c:17-20` 按 `LVGL_VERSION_MINOR >= 4` 包含 `src/core/lv_obj_class_private.h`；升级要确认该头仍存在、`name` 字段路径未变，否则 `hit` 会退化为空。
2. **lodepng 返回类型**：`core/engine/adapter_9x.c:339-352` 假设 `lodepng_decode32` 写出的指针实际是 `lv_draw_buf_t *`，这是 LVGL 的封装行为，不是公开契约。升级要确认 `decoded->data`、`decoded->header.stride` 与 RGBA 布局仍成立，否则参考图 diff 会读错内存。
3. **版本分支与 indev 注册**：`adapter_9x.c` 使用 `lv_indev_create` / `lv_indev_set_read_cb`，`adapter_8x.c` 使用 `lv_indev_drv_init` / `lv_indev_drv_register`；9.2+ 才有对象名。`lv_conf.h`、display/layer API 与 flush 回调签名也分别落在两个 adapter 分支里，不要只改一个。
4. **支持矩阵**：9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3。升级后跑 `test_multiversion` 与各版本场景（`meta/versions.json` + `tools/install_version.py`）；跨版本只比较事件语义与 session 文件集合，不比较像素。
5. **边界检查**：`python -I core/tools/check_version_boundaries.py` 与 `python -I core/tools/check_api_nav.py` 必须通过；`core/api-nav/<version>.md` 跟随公开 API 变化更新。

新增版本时同步 `meta/versions.json`、`api-nav/` 与 `patches/<version>/`（如需 patch）；不要直接修改已安装的 `lvgl-src/<version>/`。

## 测试

```bash
python -I core/tests/run_tests.py

# 外部契约对比（重构前后都应零差异）
python -I core/tools/contract_snapshot.py compare
```

测试套件同时包含单元测试和真实 engine 的集成测试：`*IntegrationTest` 类会按仓库既有方式构建 LVGL（当前主要是 9.6，多版本测试覆盖全部支持版本），由同一次 `run_tests.py` 执行；它们不是 skip 或未执行断言。预编译与 release 集成测试在 `sdk/9.6` 缺失时会自动调用 `tools/export_sdk.py`，因此同样需要 `lvgl-src/9.6` 与 GCC。单元测试使用 fake engine / 纯函数，不构建 LVGL。

## 常见错误

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `LVGL source not found: ...` | 没有下载对应版本的 LVGL 源码 | 运行 `python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root .`，或设置 `LVGL_AI_LVGL_SRC` |
| `PNG encoder source not found: ...` | 没有下载 zlib / libpng 源码 | 运行 `python -I core/tools/fetch_png.py --repo-root .`，或设置 `LVGL_AI_ZLIB_SRC` / `LVGL_AI_LIBPNG_SRC` |
| `build tools not found on PATH: cmake, ninja, gcc` | 工具缺失，或 PATH 未生效 | 按上文 MSYS2 步骤安装，重开终端，用 `which -a` / `where.exe` 检查 |
| `CMake 3.20 or higher is required` | CMake 版本过低 | 升级 CMake |
| `engine binary not found: ...` | 使用了 `--no-build`，但 `build/` 中没有 engine | 去掉 `--no-build` 先构建 |
| `configure timed out after 600s` / `build timed out after 600s` | 单阶段超过 600 秒 | 关闭负载或杀毒扫描后重跑；已完成的阶段会保留，可增量构建 |
| `all download URLs failed:` | 网络、DNS 或代理问题 | 默认 `--source auto` 会试 codeload 与 Gitee 镜像；Gitee 不可用时改用 `--source codeload` 或版本包，并检查 `curl` 与代理环境变量 |
| `version header mismatch:` | 镜像 tag 漂移 | 删除 `.scratch/tmp/archives` 后重下，或加 `--force` |
| `[web] cannot listen on 127.0.0.1:8765:` | 端口被占用 | 用 `--port 0` 或换一个端口 |
| `cannot read scenario ...` | 场景路径写错 | 检查 `user/scenarios/` 下的文件名 |
| `python` 打开 Microsoft Store | Store 别名 | 使用 python.org 版本、`py -3`，或关闭 App Execution Alias |
| `git is required to apply LVGL patches` | 有 patch 但未安装 git | 安装 Git，或加 `--no-patch`（当前仓库默认没有 patch） |
