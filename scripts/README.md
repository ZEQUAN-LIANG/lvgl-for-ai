# tools

工具脚本按链路分组；每个脚本的参数、默认值与输出以 `--help` 为准，本页只做入口路由。

> 发布包内的本页由 `release_tools_README.md` 覆盖，只列出随包脚本。

## 发布与打包

```text
release_all.py  →  构建两个完整包：full 与 full-sifli
release.py      →  构建单版本核心包（解包目录 + zip）
upload_release.py → 上传 zip 到 GitHub / Gitee Release（token 只读环境变量）
export_sdk.py   →  从 engine/lvgl/<version> 导出 dist/lvgl/<version>/
publish_check.py → 发布链路自检：版本号一致性 / 包内容 / 真实安装 / 线上资产
```

发版顺序与判定条件见 `docs/RELEASE.md`；`publish_check.py` 是它的可执行检查。四个 stage
（`version` / `package` / `install` / `remote`）可单独跑，不带 `--stage` 时按序全跑。

发布包根目录只有 `SKILL.md` 一个文件（`api-nav/` 是目录）；元数据在
`scripts/meta/`，许可证在 `docs/licenses/`，双击启动器在 `bin/`。发布包不含
C engine 源码与 LVGL 源码。多版本包会把各 LVGL 库中完全相同的 FreeType DLL、
导入库和公共头文件收到 `dist/lvgl/common/`。

`release_all.py` / `release.py` 按 engine 输入摘要复用
`dist/release/lvgl_<token>/` 下的预编译 engine；engine / 用户应用源码、预编译 LVGL 库
manifest 或 GCC 版本未变时不再重编，只重新打包。`--force-build` 强制重建，
启动器同样按源码摘要复用。

`release_app.c` 是发布包内 `user/app/app.c` 的替代入口；它包含由 `app.json`
生成的 `app_registry.inc`，发布包里只有 `intro`。

## 回归

| 脚本 | 用途 |
|---|---|
| `verify.py` | 一键跑 lint、契约快照、全量测试与发布包冒烟；`--skip-tests` / `--skip-package` 可分段执行 |

## LVGL 与依赖

| 脚本 | 用途 |
|---|---|
| `install_version.py` | 安装受支持版本的源码或版本包 |
| `fetch_lvgl.py` | 下载 LVGL 源码到 `engine/lvgl/` |
| `fetch_png.py` | 下载 zlib / libpng 源码到 `engine/third_party/` |

## 应用与入口

| 脚本 | 用途 |
|---|---|
| `new_app.py` | 生成应用骨架、`app.json` 与场景 |
| `lvgl.py` | `bin/lvgl.cmd` 的统一入口（`run` / `report` / `serve` / `assets`） |
| `launchers/build.py` | 重建 Windows 双击启动器（MinGW gcc + windres） |

## 契约校验与同步

| 脚本 | 用途 |
|---|---|
| `contract_snapshot.py` | 录制 / 比较外部契约快照 |
| `check_version_boundaries.py` | 校验版本边界 |
| `check_api_nav.py` | 校验 `docs/skill/api-nav/` |
| `lint.py` | ruff / clang-format / cppcheck / comments 的统一入口（不进发布包） |
| `sync_github.py` | Gitee → GitHub 镜像（分支 + 标签） |
