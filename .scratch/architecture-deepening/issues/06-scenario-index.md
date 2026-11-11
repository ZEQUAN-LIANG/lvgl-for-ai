# 06：场景索引单源（候选 07）

**What to build：** 场景索引只解析一遍，放在场景 schema 所有者处，apps、应用回收站、web 应用 picker 与 live start 的 display 查找共用同一入口。做完后，per-scenario display 不再有两份解析。

**Blocked by：** None (can start immediately)

**Status:** open

**验收方式：**

- 索引：`test_apps_seams.py` 或新增测试用有效/无效场景夹具断言 7 个字段与错误文本。
- 去重：`git grep -n -E "load_scenario|glob\(" -- core/lvgl_ai/web` → 无场景目录 glob 或 `load_scenario` 组装 picker/display（场景执行路径除外）。
- 行为：`test_web_apps.py`、`test_apps.py`、`test_apps_seams.py` 断言 picker、display、回收站输出不变。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：测试名、`git grep` 输出与命令退出码写入票末「完成」。

- [ ] `scenario_index` 位于场景 schema 所有者 module，返回 `path`、`basename`、`app`、`name`、`display`、`valid`、`error`（索引测试）。
- [ ] 无效场景保留错误文本且不阻断其他条目；不新增场景 schema 字段（索引测试）。
- [ ] apps 视图、应用回收站、web picker、live start 的 display 查找消费同一索引（`git grep` + 行为测试）。
- [ ] web 层不再自行 glob 场景目录或调用 `load_scenario` 组装 picker/display（`git grep` 检查）。
- [ ] picker、display、回收站与 apps 行为不变（现有测试）。
- [ ] 全量测试与契约比较通过。
