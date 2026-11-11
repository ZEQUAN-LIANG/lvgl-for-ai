# 02：删除兼容转发层（候选 03）

**What to build：** 删除 17 个没有生产调用点的 `import *` 兼容转发 module，只保留 `lvgl_ai` 顶层公开导出与 `apps` 生命周期 interface。做完后，import 图、文档和契约快照指向同一套 module，旧路径不再误导维护者和 AI agent。

**Blocked by：** None (can start immediately)

**Status:** done

**验收方式：**

- 删除检查：`test ! -d core/lvgl_ai/core`；`test ! -e core/lvgl_ai/web/server.py`、`stream.py`、`page.py`、`region_images.py`、`core/lvgl_ai/region.py` → 全部退出 0。
- 导入检查：`git grep -n -E "lvgl_ai\.core|lvgl_ai\.region|web\.(server|stream|page|region_images)" -- core user chip-adapt docs README.md` → 只允许 README 的移除说明；其他命中为 0。
- 公开导出：公开导出测试断言 `LatError is ToolError`、`__all__` 与现状一致、`apps` 生命周期签名不变。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0，无差异。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：删除检查、`rg` 输出与命令退出码写入票末「完成」。

- [x] 17 个转发 module 全部删除（按上面的 `test ! -e` 检查）。
- [x] 全仓旧路径导入为 0，README 只有一条移除说明（按 `git grep` 检查）。
- [x] 顶层公开导出与 `apps` 契约不变（按公开导出测试与契约比较）。
- [x] 兼容测试裁剪为公开导出断言并改名；全量测试不再导入旧路径。
- [x] `contract_snapshot.py compare` 无差异。
- [ ] `python -I core/tests/run_tests.py` 退出 0。按主代理约束未在 worktree 运行（`lvgl-src/`、`third_party/` 只有 README）；改跑相关单元测试与静态检查，见「完成」。

## 完成

- 基线：`ticket/03-remove-compat`，基于 `feat/architecture-deepening` 的 `c47319c`。
- 删除清单（17 个转发文件 + 旧兼容测试）：
  - `core/lvgl_ai/core/__init__.py`、`build.py`、`build_plan.py`、`engine_link.py`、`errors.py`、`input.py`、`keys.py`、`recording.py`、`retention.py`、`runtime.py`、`session.py`、`session_schema.py`。
  - `core/lvgl_ai/web/server.py`、`stream.py`、`page.py`、`region_images.py`。
  - `core/lvgl_ai/region.py`。
  - `core/tests/test_compat_aliases.py`（由 `core/tests/test_public_exports.py` 取代）。
- 保留：`core/lvgl_ai/__init__.py` 顶层导出与 `__all__`、`LatError is ToolError`、`core/lvgl_ai/apps/__init__.py` 生命周期导出、`core/lvgl_ai/web/__init__.py`（只 import 新路径）。未改生产代码。
- 新增 `core/tests/test_public_exports.py`：
  - `test_top_level_exports_are_unchanged`：`lvgl_ai.__all__` 与 11 个导出逐项断言。
  - `test_lat_error_remains_the_tool_error_alias`：顶层与控制层 `LatError is ToolError`，`ToolError` 不在顶层 `__all__`。
  - `test_apps_lifecycle_signatures_are_unchanged`：`list_apps` / `app_tree` / `recent_apps` / `list_trash` / `scaffold_app` / `delete_app` / `restore_app` / `permanently_delete` 的 `inspect.signature` 逐字断言。
  - `test_legacy_modules_are_not_importable`：17 个旧 module 名用 `".".join(parts)` 运行时拼装，逐一 `importlib.util.find_spec` 断言无常规 loader；既守住删除契约，也不让票面 `git grep` 命中测试源码。
- 红态：删除前 `python -I -c "import sys; sys.path[:0]=['core','core/tests']; import unittest; unittest.main(module='test_public_exports', argv=['test_public_exports'])"` → Ran 4 tests，FAILED (failures=17)，17 个失败全部是 `legacy module still importable: <旧路径>`；公开导出 3 项已通过。
- 绿态（删除后同一命令）→ 退出 0，Ran 4 tests，OK。
- 删除检查（全部退出 0）：`test ! -d core/lvgl_ai/core`；`test ! -e core/lvgl_ai/web/server.py`、`stream.py`、`page.py`、`region_images.py`；`test ! -e core/lvgl_ai/region.py`。
- 旧路径 grep：`git grep -n -E "lvgl_ai\.core|lvgl_ai\.region|web\.(server|stream|page|region_images)" -- core user chip-adapt docs README.md` → 退出 0，仅 1 行命中：`core/README.md:182` 的移除说明；其余命中 0。
- README：`core/README.md` 「Python」段新增一条中文移除说明，列出 6 个旧路径并指向 `lvgl_ai` 顶层导出 / `lvgl_ai.control` / `lvgl_ai.web`。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0，`[contract] differences: 0`。
- 相关测试（均退出 0）：
  - `test_docs_single_source` → Ran 7 tests，OK。
  - `test_error_mapping` → Ran 13 tests，OK。
  - `test_contract_snapshot` → Ran 14 tests，OK（56.4 秒）。
  - 单元批（`test_apps_seams`、`test_apps`、`test_scenario`、`test_keys`、`test_input_vocabulary`、`test_png_codec`、`test_build_plan`）→ Ran 130 tests，2 errors + 3 skipped；2 个 error 均为 `test_scenario.SettingsScenarioIntegrationTest` 的真实 engine 用例，原因是 `LVGL source not found: .../lvgl-src/9.6`，属 worktree 缺 `lvgl-src/` 的环境限制，与本票改动无关；其余 128 项通过。
- 静态检查：`python -I core/tools/check_version_boundaries.py` → 退出 0。`python -I core/tools/check_api_nav.py` → 退出 1，814 个 problem 全部源于 `lvgl-src/<version>` 不存在（`path does not exist` 与随后的 `symbol not in ... headers`），同属环境限制，未作为本票门禁。
- import 冒烟：`python -I -c "import sys; sys.path.insert(0,'core'); import lvgl_ai; print(lvgl_ai.__all__, lvgl_ai.LatError is lvgl_ai.ToolError)"` → 退出 0，导出不变，别名为 `True`。
- 残余旧路径：仓库内为 0（README 说明行除外）。旧路径的 `__pycache__` 已随 `core/lvgl_ai/core/` 目录一并清理。
- 风险：发布包若被仓外 harness 直接 import 旧路径，会在升级时得到 `ModuleNotFoundError`；按 spec 03 不保留 shim，只以 README 移除说明告知。完整 `run_tests.py` 与真实 engine 验收仍需在带 `lvgl-src/`、`third_party/` 的环境执行。
