# 02：删除兼容转发层（候选 03）

**What to build：** 删除 17 个没有生产调用点的 `import *` 兼容转发 module，只保留 `lvgl_ai` 顶层公开导出与 `apps` 生命周期 interface。做完后，import 图、文档和契约快照指向同一套 module，旧路径不再误导维护者和 AI agent。

**Blocked by：** None (can start immediately)

**Status:** open

**验收方式：**

- 删除检查：`test ! -d core/lvgl_ai/core`；`test ! -e core/lvgl_ai/web/server.py`、`stream.py`、`page.py`、`region_images.py`、`core/lvgl_ai/region.py` → 全部退出 0。
- 导入检查：`git grep -n -E "lvgl_ai\.core|lvgl_ai\.region|web\.(server|stream|page|region_images)" -- core user chip-adapt docs README.md` → 只允许 README 的移除说明；其他命中为 0。
- 公开导出：公开导出测试断言 `LatError is ToolError`、`__all__` 与现状一致、`apps` 生命周期签名不变。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0，无差异。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：删除检查、`rg` 输出与命令退出码写入票末「完成」。

- [ ] 17 个转发 module 全部删除（按上面的 `test ! -e` 检查）。
- [ ] 全仓旧路径导入为 0，README 只有一条移除说明（按 `git grep` 检查）。
- [ ] 顶层公开导出与 `apps` 契约不变（按公开导出测试与契约比较）。
- [ ] 兼容测试裁剪为公开导出断言并改名；全量测试不再导入旧路径。
- [ ] `contract_snapshot.py compare` 无差异。
- [ ] `python -I core/tests/run_tests.py` 退出 0。
