# core/tools

工具脚本按链路分组；每个脚本的参数、默认值与输出以 `--help` 和模块 docstring
为准，本页只做入口路由。

## 发布与打包

```text
release_all.py  →  构建两个完整包：full 与 full-sifli
release.py      →  构建单版本核心包（解包目录 + zip）
export_sdk.py   →  从 lvgl-src/<version> 导出 sdk/<version>/
```

发布包根目录只有 `SKILL.md`；元数据在 `meta/`，许可证在 `licenses/`，
演示图与 `SIFLI.md` 在 `docs/`，双击启动器在 `bin/`。多版本包会把各 SDK 中
完全相同的 FreeType DLL、导入库和公共头文件收到 `sdk/common/`。

`release_app.c` 是发布包内 `user/app/app.c` 的替代入口，只注册 `intro`。

## LVGL 与依赖

| 脚本 | 用途 |
|---|---|
| `install_version.py` | 安装受支持版本的源码或版本包 |
| `fetch_lvgl.py` | 下载 LVGL 源码到 `lvgl-src/` |
| `fetch_png.py` | 下载 zlib / libpng 源码到 `third_party/` |

## 应用与入口

| 脚本 | 用途 |
|---|---|
| `new_app.py` | 生成应用骨架并注册到 `user/app/app.c` |
| `lvgl.py` | `bin/lvgl.cmd` 的统一入口（`run` / `report` / `serve` / `assets`） |
| `launchers/build.py` | 重建 Windows 双击启动器（MinGW gcc + windres） |

## 契约校验与同步

| 脚本 | 用途 |
|---|---|
| `contract_snapshot.py` | 录制 / 比较外部契约快照 |
| `check_version_boundaries.py` | 校验版本边界 |
| `check_api_nav.py` | 校验 `api-nav/` |
| `sync_github.py` | Gitee → GitHub 镜像（分支 + 标签） |
