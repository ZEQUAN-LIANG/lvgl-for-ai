# scripts

发布包里的维护入口；完整用法见 `console/README.md`，AI 入口见包根 `SKILL.md`。

## 入口

| 脚本 | 用途 |
|---|---|
| `lvgl.py` | `bin/lvgl.cmd` 的统一入口：`run` / `report` / `serve` / `assets` |
| `new_app.py` | 生成应用骨架、`app.json` 与场景 |

## 元数据

`scripts/meta/versions.json` 是版本索引（`lvgl-verify-loop-versions-v2`）；
`scripts/meta/VERSION.json` 记录发布版本、LVGL 版本、GCC 版本与 git commit。

包内不包含 C engine 源码、LVGL 源码或 zlib/libpng 源码：预编译 engine 在
`build/lvgl_<version>/`，预编译宿主库在 `dist/lvgl/<version>/`，用户代码只通过
`dist/lvgl/` 的静态库与头文件重新编译。

多版本包把各版本完全相同的 FreeType DLL、导入库与公共头文件收到
`dist/lvgl/common/`。
