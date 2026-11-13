# 可分发 LVGL AI Skill

## 问题陈述

当前工具只能在开发仓库里使用：客户要拿到可用的环境，必须先安装 Python、CMake、Ninja、GCC，再下载六套 LVGL 源码（约 867 MB）、zlib/libpng 源码，涉及设备时还要下载 2.4 GB 的 SiFli SDK。这对两类用户都不可接受：

1. **客户 PC 上的 AI agent**：希望直接写 LVGL 用户应用、编译、跑场景、读证据、迭代 UI，而不是先花大量时间准备环境。
2. **客户本人**：希望解压后双击就能打开网页，点击操作，不需要管理员权限、安装器或联网。

同时，设备链路必须保留：`user/app` 是唯一源码真源，既要能在宿主上预览/取证，也要能导出到 SiFli-SDK 上烧录。未来还会接入更多 SDK，不能每接一个 SDK 就把包体扩大一倍。

现有仓库已经具备：headless 宿主、场景、会话证据、回放/live 网页、用户应用注册表、场景热更新、SiFli 导出适配层。缺的是把这一切收成一个可分发的 skill 包，并提供可重复的发布流程。

## 方案

给客户一个解压即用的 skill 目录（zip 分发），目录内自带：

- 预编译的宿主 SDK（LVGL + adapter + engine + libpng + zlib + 头文件 + `lv_conf.h`），默认 LVGL 9.6，另带 9.4 用于设备对齐。
- 预编译的 `lvgl_engine.exe`，`--no-build` 可直接运行。
- 内置 embeddable Python；author 档再内置一份精简 MinGW-w64 GCC。客户不安装 Python/编译器，也不使用 CMake/Ninja。
- 统一入口脚本，agent 通过 `run` / `report` / `serve` / `export` / `sifli` 子命令工作；人类双击启动器打开网页。
- 默认携带 SiFli add-on：适配器代码、模板、串口/烧录上位机、`ezip.exe`、pyserial、xterm.js；2.4 GB SiFli SDK、ARM 工具链和 sftool 首次使用时 bootstrap。
- 一个 release 脚本，一条命令产出 skill zip、sha256 和 release manifest；支持 viewer / author / thin 三档和保留用户数据的升级包。

开发仓库的 CMake 构建路径保持不变；发布包在没有 LVGL 源码时自动选择 prebuilt 构建。宿主应用构建改为直接调用 gcc 编译 `user/app` 并链接预编译库，不再依赖 CMake/Ninja。

三条链路共享同一份源码：

- **宿主 9.6**：日常预览、取证、网页点击。
- **宿主 9.4**：设备行为对齐，也是 SiFli 导出后宿主验证命令使用的版本。
- **设备导出**：`export.py` 原样复制应用源码，生成自包含 SiFli-SDK 工程；不预编译设备端 LVGL。

## 用户故事

1. 作为客户，我要把 skill zip 解压到任意目录就能用，以便不经过安装器或管理员权限。
2. 作为客户，我要包内自带 Python，以便机器上没有 Python 也能运行工具。
3. 作为客户，我要 author 档包内自带精简 GCC，以便 agent 能编译我新写的 C 代码。
4. 作为客户，我要宿主链路完全离线可用，以便内网或没有网络的环境。
5. 作为客户，我要双击启动器直接打开网页，以便不用命令行就能操作界面。
6. 作为客户，我要内置 Python 被启动器优先使用，以便不依赖 `PATH` 里的 Python。
7. 作为客户，我要包体在可控范围内（author 档约 55–65 MB zip），以便下载和拷贝。
8. 作为客户，我要升级时保留我的 `user/` 和 `sessions/`，以便不丢应用代码和会话证据。
9. 作为客户，我要路径含空格或中文也能正常构建/运行，以便放在常见目录下。
10. 作为客户，我要固定访问 `127.0.0.1:8765`，以便书签和脚本稳定。
11. 作为 AI agent，我要通过统一入口运行场景并拿到单行 JSON，以便判断会话是否完成、读取证据索引。
12. 作为 AI agent，我要看到 `annotations` / `whiteboards` 索引、整帧 PNG 路径和白板 PNG 路径，以便按“摘要 → 整帧 → 白板”的顺序取证。
13. 作为 AI agent，我要在没有 LVGL 源码时自动使用预编译 SDK，以便在客户包里也能构建用户应用。
14. 作为 AI agent，我要显式选择 `--prebuilt` 或 `--source`，以便在同一工作区里控制构建方式。
15. 作为 AI agent，我要编译错误定位到“文件:行:列”，以便快速修复 C 代码。
16. 作为 AI agent，我要链接错误列出 unresolved symbols，以便定位缺失的库或符号。
17. 作为 AI agent，我要用宿主 9.4 验证设备基线，以便在导出前发现 9.5/9.6-only API 漂移。
18. 作为 AI agent，我要把 `LVGL_AI_USER_APP_DIR` 指向导出目录也能构建，以便复用同一条 prebuilt 构建路径做宿主验证。
19. 作为 AI agent，我要执行 SiFli 导出 dry-run，以便在不下载 SDK 的情况下检查导出兼容性和资源规划。
20. 作为 AI agent，我要检查 SiFli bootstrap 状态，以便明确告诉用户缺的是 SDK、ARM 工具链还是 sftool。
21. 作为 AI agent，我要在启动网页后让人类点击操作，以便把交互验证交给人。
22. 作为 AI agent，我要在没有开发板时停在宿主验证和导出 dry-run，以便不声称设备已验证。
23. 作为 AI agent，我要在没有证据时不得声称完成，以便遵守工具“不判定、只给证据”的约束。
24. 作为发布工程师，我要用一条命令导出 9.6 和 9.4 的宿主 SDK，以便发布包不依赖 LVGL 源码。
25. 作为发布工程师，我要用一条命令生成 skill zip、sha256 和 release manifest，以便可重复发布。
26. 作为发布工程师，我要 release 脚本做 hygiene 检查，阻止开发机绝对路径、缓存、测试、vendor 大件和生成物进包。
27. 作为发布工程师，我要 release 脚本在暂存目录里跑 smoke，以便出包前就发现构建/运行/网页/导出问题。
28. 作为发布工程师，我要能选择 author / viewer / thin 三档，以便按客户能力控制体积。
29. 作为发布工程师，我要生成不含 `user/` 和 `sessions/` 的升级包，以便客户覆盖升级时不丢数据。
30. 作为发布工程师，我要 release manifest 记录 tool 版本、git commit、SDK 版本、Python/GCC 版本、适配器列表和文件哈希，以便排障和审计。
31. 作为发布工程师，我要包里附齐 LVGL、zlib、libpng、Python、GCC、ezip、pyserial、xterm.js 的许可证，以便合规分发。
32. 作为 SiFli 设备开发者，我要默认包内带适配器代码、模板和串口/烧录上位机，以便拿到包就能导出和连板子。
33. 作为 SiFli 设备开发者，我要默认包内带 `ezip.exe` 和 pyserial/xterm.js，以便带资源应用在无 SDK 时也能导出 dry-run、上位机网页也能打开。
34. 作为 SiFli 设备开发者，我要一条 bootstrap 命令检查并安装 SiFli SDK、ARM 工具链和 sftool，以便不手工翻文档。
35. 作为 SiFli 设备开发者，我要 bootstrap 固定 SDK commit、校验 `version.txt`、初始化必需子模块，以便环境可复现。
36. 作为 SiFli 设备开发者，我要导出的宿主验证命令在预编译包里直接可用，以便先宿主验证再上板。
37. 作为 SiFli 设备开发者，我要现有 `host build/flash` 流程保持不变，以便已有脚本和习惯不受影响。
38. 作为未来 SDK 适配者，我要按 `adapter.json` 目录约定新增一个适配器目录就能被 release 脚本发现并打进包，以便不修改发布脚本核心逻辑。
39. 作为未来 SDK 适配者，我要小型必需工具默认进包、大型 vendor SDK 只能 bootstrap 或显式离线包，以便包体不随 SDK 数量线性膨胀。
40. 作为维护者，我要 SDK manifest 记录编译器版本、编译 flags、include 顺序、链接顺序和库哈希，以便定位 ABI/链接问题。
41. 作为维护者，我要预编译构建在编译器版本与 manifest 不一致时直接报错，以便避免 ABI 不匹配的隐蔽崩溃。
42. 作为维护者，我要 `lv_conf.h` 随 SDK 固化并校验哈希，以便用户应用与预编译库的配置一致。
43. 作为维护者，我要 release 产物里不出现开发机绝对路径，以便包可迁移。
44. 作为维护者，我要开发仓库的 CMake 构建路径保持可用，以便继续用源码模式开发和跑现有集成测试。
45. 作为维护者，我要新增测试复用现有 CLI、BuildPlan 和 export 缝，只新增一个 release 产物缝，以便控制测试复杂度。
46. 作为维护者，我要 release 脚本可重复产出相同文件清单，以便比较两个版本或回滚。
47. 作为维护者，我要包内保留 `core/` 目录名，以便 SiFli 导出和现有文档/命令继续工作。
48. 作为维护者，我要宿主与设备的版本策略明确：默认 9.6 预览、9.4 设备对齐、导出拒绝 9.5/9.6-only API，以便减少跨版本问题。
49. 作为客户，我要 viewer 档在没有编译器时也能跑已有应用和回放，以便只需要看结果的人不必下载工具链。
50. 作为客户，我要 thin 档在首次需要编译时再下载精简工具链，以便首次下载体积最小。

## 实现决策

### 双链路与源码真源

- `user/app/**/*.c`、`assets.json`、`user/scenarios/*.json` 是唯一源码真源；宿主链路和设备导出都消费它，不复制出第二份共享源码。
- 宿主链路与设备链路不共享构建产物；宿主 SDK 是 x86_64/MinGW，设备端仍由 SiFli-SDK 的 SCons 构建。
- 设备端 LVGL 保持源码导出，不预编译 ARM 库。原因是 SiFli-SDK 的 SCons/Kconfig 把 LVGL 当源码组件，并带 `littlevgl2rtt`、EPIC/GE2D、板级配置；预编译会绕过配置且省不下体积大头。

### 宿主 SDK 导出

- 新增 SDK 导出模块：从开发仓库的 `lvgl-src/<version>` 构建一次，导出静态库、头文件、`lv_conf.h` 和 manifest。
- 导出内容：LVGL、adapter、engine、libpng、zlib 五份静态库，LVGL/zlib/libpng 公共头，engine 的 `lv_conf.h`。
- engine 源码抽成 `engine_core` OBJECT 库，可执行文件由它的 object 文件组成；SDK 导出时把同一组 object 归档成 engine 静态库，保证可执行文件和预编译库来自同一批编译结果。
- adapter 的源码路径宏改为可配置标签；SDK 构建写 `prebuilt-<version>`，避免把开发机路径带进包。
- SDK 库使用 Release 等价优化（`-O2`、无调试信息），ABI 与用户应用编译优化级别无关；导出后对 `.a` 去调试信息。
- 默认导出 9.6 和 9.4；其他版本按需显式指定。9.4 用于设备对齐和 SiFli 导出后的宿主验证。
- SDK manifest 契约（schema `lvgl-ai-host-sdk-v1`）：

```json
{
  "schema": "lvgl-ai-host-sdk-v1",
  "lvgl_version": "9.6",
  "lvgl_tag": "v9.6.0",
  "platform": "win64",
  "tool_version": "0.1.0",
  "compiler": {"id": "mingw-w64-gcc", "version": "8.1.0"},
  "defines": ["LV_CONF_INCLUDE_SIMPLE", "LV_KCONFIG_IGNORE", "LV_LVGL_H_INCLUDE_SIMPLE"],
  "cflags": ["-std=gnu11", "-O2", "-Wall", "-Wextra"],
  "include_dirs": [".", "include", "include/lvgl"],
  "libs": ["libengine.a", "libadapter.a", "liblvgl.a", "liblvgl_ai_libpng.a", "liblvgl_ai_zlib.a"],
  "link_flags": ["-lgdi32", "-luser32", "-static-libgcc"],
  "sha256": {"liblvgl.a": "..."}
}
```

### prebuilt 构建模式

- 选择规则：`lvgl-src/<version>` 存在且未显式 `--prebuilt` 时走现有 CMake；源码缺失且 `sdk/<version>` 存在时自动走 prebuilt；显式 `--prebuilt` / `--source` 覆盖自动判断。
- 编译器解析顺序：包内 `runtime/mingw64` → `LVGL_AI_GCC` 环境变量 → `PATH` 的 `gcc`。找不到或版本与 manifest 不一致时直接报错并给出 bootstrap 提示。
- 编译参数由 manifest 提供：C 标准、优化级别、warning、defines、include 顺序；对象缓存键包含源文件、manifest 哈希和编译器版本。
- 链接顺序固定为 engine → adapter → LVGL → libpng → zlib，使用链接组避免静态库顺序问题；Windows 额外链接 `gdi32`、`user32`，并静态链接 libgcc。
- 复用现有构建诊断解析、构建日志格式和 `BuildError` / `LinkError` 语义；不新增第二套错误类型。
- 支持 `LVGL_AI_USER_APP_DIR` 指向任意用户应用目录，因此同一构建路径既能编译 `user/app`，也能编译导出工程的 `src/app`。
- 输出仍落在现有 `build/lvgl_<version>/lvgl_engine.exe`，`--no-build` 语义不变。

### 运行时打包

- 内置 Windows embeddable Python，固定版本和 SHA256；入口脚本继续使用 `python -I`，由入口脚本自己补 `sys.path`。
- author 档内置精简 MinGW：只保留 `gcc`、`as`、`ld`、`ar`、`ranlib`、`cc1`、`collect2`、必要 DLL、`libgcc`、crt、目标平台 import libs 和 C/Windows 头。
- 精简工具链保持目录结构可重定位；包装脚本只在当前进程内把 `runtime/mingw64/bin` 加到 `PATH`，不改系统环境。
- 工具链打包后必须通过两项验证：hello world 编译链接；实际 `user/app` 编译链接，产物只依赖 `KERNEL32/GDI32/USER32/msvcrt`。
- 三档：author（Python + 精简 MinGW + 预编译 engine）、viewer（Python + 预编译 engine，无编译器）、thin（Python，首次构建再下载精简 MinGW）。
- 运行时下载由固定 pins 文件驱动，记录 URL 和 SHA256；发布机一次性下载，客户默认不下载。

### release 脚本

- 输入：skill 版本、tier、平台、Python embed、精简 MinGW、适配器选择、输出目录。
- 暂存目录按 allowlist 拷贝：`SKILL.md`、`CONTEXT.md`、`VERSION.json`、`licenses/`、`core/`（去掉 tests/tools 缓存）、`user/`、`sdk/`、预编译 engine、启动器、`bin/` 包装脚本、`runtime/`、`chip-adapt/`（去掉 vendor/exports/host 缓存）。
- **默认携带 SiFli add-on**：适配器代码、模板、`host/`、`ezip.exe`、pyserial、xterm.js、`SiFli-Host.exe`；不携带 SiFli SDK 源码、`exports/`、ARM 工具链和 sftool。
- 未来适配器自动发现：只要 `chip-adapt/<chip>/` 含 `adapter.json`，就纳入发布包；小型工具默认进包，大型 SDK 走 bootstrap 或显式 `--with-<chip>-sdk` 离线包。
- hygiene 检查：文本文件中的开发机绝对路径、`__pycache__`、`.git`、`sessions/` 内容、`build/` 中间物、`chip-adapt/vendor/`、`chip-adapt/exports/`、测试目录。
- smoke 在暂存目录、临时工作目录下运行：`--no-build` 跑场景；prebuilt 9.6 编译并跑场景；prebuilt 9.4 编译并跑场景；网页可启动；SiFli 导出 dry-run（含带资源应用，验证包内 `ezip.exe` 回退）；启动器解析到包内 Python。
- 产物：skill zip、`.sha256`、release manifest（tool 版本、git commit、SDK manifest 哈希、Python/GCC 版本、适配器列表、文件数、解压/压缩体积）。
- 升级包排除 `user/` 和 `sessions/`；文档说明只替换版本化目录。
- 包根保留 `core/` 目录名；启动器放在包根，保持 target `core\web.pyw`，避免改动现有启动器配置。

### SiFli add-on

- 默认包带 `chip-adapt/sifli` 适配器、模板、`host/`、pyserial、xterm.js、`SiFli-Host.exe` 和一份 `ezip.exe` 副本。
- `ezip.exe` 查找顺序：显式传入 → `SIFLI_EZIP` 环境变量 → 包内工具目录 → SiFli SDK 内工具。这样带资源应用在没有 SDK 时也能 `export.py --dry-run`；真正构建/烧录仍要求 SDK。
- 新增 SiFli bootstrap 模块：`--check --json` 报告 SDK 源码/commit/子模块、ARM GCC、sftool、uv、pyserial、xterm 状态；`--install` 执行固定 commit 的 clone/checkout、必需子模块初始化、SDK 安装脚本，并校验 `version.txt`、`arm-none-eabi-gcc`、`sftool`。
- `host/cli.py status --json` 与 bootstrap 状态输出保持一致的缺失项语义，方便 agent 直接转述。
- 设备导出/build/flash 流程保持不变；不引入第二套协议客户端或构建入口。
- 多 SDK 约定：每个适配器目录包含 `adapter.json`；可选提供 `bootstrap`（`--check` / `--install --json`）和 `tools/`。不引入插件框架。

### 启动器与命令包装

- 启动器 Python 查找顺序：包内 `runtime/python/pythonw.exe` → `LVGL_AI_PYTHON` → `PATH` 的 `pythonw.exe` → `pyw.exe`。
- 启动器只负责拉起 Python，不掺端口、URL、HTTP、串口逻辑。
- 新增测试钩子：设置 `LVGL_AI_LAUNCHER_CHECK=<file>` 时，启动器把解析到的命令写入该文件后退出，供 release smoke 使用。
- 统一入口脚本按子命令分发到现有 CLI、会话报告、网页、SiFli 导出和上位机 CLI；包装脚本负责设置进程内 `PATH` 和选择包内 Python。

### SKILL.md 契约

- frontmatter 只含 `name` 和 `description`。
- 必须包含：环境与入口、目录说明、宿主工作流、证据读取顺序、版本策略、SiFli 工作流、硬规则。
- 硬规则明确：不输出 pass/fail；没有证据不声称完成；精确状态只能由用户 C 代码 `printf` 到 `engine.log`；没有开发板时不得声称设备已验证。
- 版本策略明确：设备应用按 LVGL 9.4 基线写，使用 `LVGL_VERSION_MINOR >= 4` 版本门；宿主默认 9.6 预览，设备对齐用 9.4。

### 版本、许可证与命名

- `VERSION.json` 记录 tool 版本、SDK 版本、Python/GCC 版本、git commit、适配器列表。
- 测试缝、命令和文档继续使用项目术语：会话、场景、证据、回放、用户应用、导出、适配层；不使用“模拟器”单独指代宿主。
- 随包附许可证：LVGL MIT、zlib、libpng、Python PSF、GCC GPLv3（附源码获取说明）、ezip 所属 SDK 许可证、pyserial、xterm.js。

## 测试决策

### 缝（已与用户确认）

采用“复用现有缝 + 1 个新产物缝”：

- **现有运行时/构建缝（复用）**：`Runtime` + `BuildPlan` 的 scripted runner seam，以及 CLI 的外部边界。覆盖 prebuilt 选择、编译/链接命令、错误映射、`--json`、`--no-build`、`LVGL_AI_USER_APP_DIR`。先例：`test_build_plan`、`test_cli`。
- **现有 SiFli 导出缝（复用）**：`export.py --dry-run` 的外部行为。覆盖 ezip 回退、无 SDK 导出、带资源导出。先例：`test_export`、`test_asset_plan`。
- **新产物缝（唯一新增）**：release 脚本的输出——skill 目录/zip 作为黑盒。测试检查包内清单、manifest、hygiene、体积，并把包解压到临时目录，从任意工作目录运行 `bin/lvgl.cmd` 的公开子命令做 smoke。
- **启动器**：复用现有静态配置测试（`test_launchers`），新增 `LVGL_AI_LAUNCHER_CHECK` 解析测试；真实启动行为放在 release smoke。
- 不新增 `make_sdk` / `prebuilt_build` / `make_runtime` 的独立单元缝；它们的契约通过现有构建缝和 release 产物缝覆盖。

### 好测试的定义

- 只测外部行为：命令行的输入输出、退出码、`--json` 内容、会话证据文件集合、导出的 SDK/包清单、zip 内容。
- 不测实现细节：不断言内部对象缓存文件名、临时目录结构、具体编译中间文件数量。
- 构建相关的断言使用现有的 scripted runner seam，不启动真实编译器；真实编译只放在 opt-in 集成测试。
- 发布相关的断言以“包解压后能否工作”为准，而不是以“脚本内部调用了哪些函数”为准。

### 测试矩阵

**单元/快速测试（不需要 LVGL 源码或编译器）**

- prebuilt 选择规则：源码存在、源码缺失、显式 `--prebuilt` / `--source` 的优先级。
- manifest 解析：字段缺失、版本不匹配、哈希不匹配、libs 顺序。
- 编译器解析顺序：包内 runtime、环境变量、PATH；版本不一致时报错。
- 编译/链接命令构造与对象缓存失效条件（通过 scripted runner）。
- 诊断解析与 `BuildError` / `LinkError` 映射（复用现有先例）。
- ezip 回退顺序：包内工具可让带资源应用 dry-run 成功。
- release 清单：allowlist/exclude、绝对路径扫描、`SKILL.md`/`VERSION.json` 生成、zip 内容、upgrade 包排除 `user/`/`sessions/`。

**集成测试（opt-in，与现有 `*IntegrationTest` 同机制）**

- 导出 9.6 SDK；移除/改名 `lvgl-src/9.6` 后，用 prebuilt 构建并跑场景，`--json` 为 `ok`。
- 导出 9.4 SDK；用 `LVGL_AI_USER_APP_DIR` 指向导出工程的 `src/app` 构建并跑场景。
- release 产出 author 档包，解压到临时目录，从不同 cwd 运行 `--no-build`、prebuilt 9.6、prebuilt 9.4。
- release 产出默认带 SiFli add-on 的包，运行 `export.py --dry-run`（无 SDK）和 `host status --json`（无 SDK 时给出缺失项）。
- 启动器 `LVGL_AI_LAUNCHER_CHECK` 解析到包内 Python。

**手动验收（干净 Windows VM）**

- 无 Python、无编译器、无 VS、无管理员权限、断网。
- 解压后双击启动器打开网页；`bin/lvgl.cmd run --scenario ... --json` 成功；author 档 prebuilt 编译成功并运行。
- 路径含空格、中文；非管理员账户；Windows 10/11。
- SiFli：`bootstrap --check` 明确报缺失项；有网络时 `bootstrap --install` 后可 export/build/flash。

### 回归

- 现有单元测试、构建集成测试、SiFli 适配器测试、host 测试全部保持通过。
- 开发仓库的 CMake 构建路径、`--no-build`、会话证据格式、网页协议保持不变。

## 不做

- 不把 SiFli SDK 2.4 GB、ARM 工具链、sftool 默认打包。
- 不预编译设备端 LVGL；设备端继续源码导出 + SCons。
- 不做安装器、MSI、注册表写入、管理员权限、系统级 PATH 修改。
- 不要求客户安装 Python、CMake、Ninja、GCC、VS Build Tools。
- 不改变开发仓库的 CMake 构建路径和现有测试语义。
- 不把 `core/` 改名成 `tool/` 或类似名称。
- 不引入第二套协议客户端；网页、CLI、报告继续走 `Runtime` / `Recording` / `summarize_session`。
- 不输出 pass/fail、baseline、approval、acceptance。
- 不自动把 9.6 应用改写成 9.4；导出只做兼容性检查并拒绝。
- 不默认做代码签名，不默认支持 Linux/macOS。
- 不把 `lvgl-src`、`third_party`、`chip-adapt/vendor`、`chip-adapt/exports`、`sessions`、测试目录打进客户包。
- 不重新访谈用户；本规格只合成当前对话与代码库已知内容。

## 补充说明

### 已实测的基线

- 直接调用 gcc 编译现有 23 个 `user/app` C 文件 + 链接现有静态库和 engine object：约 35 秒，输出 7.5 MB engine，仅依赖 `KERNEL32/GDI32/USER32/msvcrt`。
- 宿主静态库实测：LVGL 9.6 约 2.3 MB（去调试信息约 2.1 MB），libpng 约 0.32 MB，zlib 约 0.13 MB；合计约 2.7 MB。
- 头文件：LVGL 9.6 公共头约 3.9 MB，zlib/libpng 头约 1.1 MB。
- 默认 add-on 小件：`chip-adapt/sifli` 约 2.9 MB，host vendor 约 1.4 MB，`ezip.exe` 约 233 KB。
- 本机完整 MinGW 约 466 MB；精简后预计约 110 MB 解压、约 30 MB 压缩。Python embeddable 约 25 MB 解压、约 11 MB 压缩。

### 体积目标

- author 档：约 190 MB 解压，55–65 MB zip。
- viewer 档：约 80 MB 解压，约 25 MB zip。
- thin 档：约 80 MB 解压（不含 MinGW），首次构建再下载工具链。
- `user/app` 当前 24 MB；如需瘦身，release 脚本提供示例应用筛选选项。

### 风险与对策

- **ABI 不匹配**：随包固定 GCC；manifest 记录版本；prebuilt 构建前比对，不一致直接报错。
- **`lv_conf.h` 漂移**：固化进 SDK 并校验哈希；用户不可修改。
- **embeddable Python 的 `-I` 行为**：release 第一阶段就做 smoke；失败则改用 standalone Python 或由包装脚本隔离环境。
- **工具链不可重定位**：保持目录结构；包装脚本注入进程内 PATH；在带空格/中文路径的 VM 验证。
- **`ezip.exe` 再分发许可**：先确认 SDK 许可；不允许时改为 bootstrap 时获取，或导出前强制 bootstrap。
- **SmartScreen**：默认不签名，文档说明；可选签名作为发布选项。
- **升级覆盖用户数据**：升级包排除 `user/`、`sessions/`；文档写清替换范围。
- **未来 SDK 膨胀**：默认只带适配器和小工具；大 SDK 只走 bootstrap 或显式离线包。

### 里程碑

1. **M1 宿主 SDK + prebuilt 构建**：SDK 导出、engine 静态库、prebuilt 构建、选择规则、错误映射；无源码也能构建并跑场景。
2. **M2 发布脚本 + 运行时 + 启动器**：运行时打包、release 脚本（host-only）、统一入口、启动器内置 Python、`SKILL.md`；干净 VM 断网可用。
3. **M3 SiFli 默认 add-on**：适配器进包、ezip 回退、bootstrap、状态输出；无 SDK 可 dry-run，有 SDK 可 build/flash。
4. **M4 多 SDK 约定 + 加固**：adapter 自动发现、离线 add-on 选项、升级包、许可证、CI smoke。
5. **M5 可选档位**：viewer / thin、运行时按需下载、非 Windows 说明。

### 待确认项

- 默认是否带全部示例应用（当前 24 MB），还是只带少量示例、其余由用户新建。
- 是否需要 `--with-sifli-sdk` 生成完全离线的设备大包。
- 是否对启动器做代码签名。
- 第一版是否只支持 Windows x64。
