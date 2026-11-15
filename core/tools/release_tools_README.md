# core/tools

工具脚本按链路分组；每个脚本的参数、默认值与输出以 `--help` 和模块 docstring
为准，本页只做入口路由。

## 发布与打包

```text
export_sdk.py   →  从 lvgl-src/<version> 导出 sdk/<version>/
```

发布包根目录只有 `SKILL.md`；元数据在 `meta/`，许可证在 `licenses/`，
演示图与 `SIFLI.md` 在 `docs/`，双击启动器在 `bin/`。多版本包会把各 SDK 中
完全相同的 FreeType DLL、导入库和公共头文件收到 `sdk/common/`。

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
