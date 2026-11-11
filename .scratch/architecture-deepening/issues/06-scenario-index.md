# 06：场景索引单源（候选 07）

**What to build：** 场景索引只解析一遍，放在场景 schema 所有者处，apps、应用回收站、web 应用 picker 与 live start 的 display 查找共用同一入口。做完后，per-scenario display 不再有两份解析。

**Blocked by：** None (can start immediately)

**Status:** done

**验收方式：**

- 索引：`test_apps_seams.py` 或新增测试用有效/无效场景夹具断言 7 个字段与错误文本。
- 去重：`git grep -n -E "load_scenario|glob\(" -- core/lvgl_ai/web` → 无场景目录 glob 或 `load_scenario` 组装 picker/display（场景执行路径除外）。
- 行为：`test_web_apps.py`、`test_apps.py`、`test_apps_seams.py` 断言 picker、display、回收站输出不变。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：测试名、`git grep` 输出与命令退出码写入票末「完成」。

- [x] `scenario_index` 位于场景 schema 所有者 module，返回 `path`、`basename`、`app`、`name`、`display`、`valid`、`error`（索引测试）。
- [x] 无效场景保留错误文本且不阻断其他条目；不新增场景 schema 字段（索引测试）。
- [x] apps 视图、应用回收站、web picker、live start 的 display 查找消费同一索引（`git grep` + 行为测试）。
- [x] web 层不再自行 glob 场景目录或调用 `load_scenario` 组装 picker/display（`git grep` 检查）。
- [x] picker、display、回收站与 apps 行为不变（现有测试）。
- [ ] 全量测试与契约比较通过。契约比较已通过；全量测试按主代理约束未在 worktree 运行（缺 `lvgl-src/`、`third_party/`，真实 engine 不可用），由主代理合并后执行。

## 完成

- 改动文件：
  - `core/lvgl_ai/scenario.py`：新增 `scenario_index(root, *, scenarios_dir=None, include_symlinks=False)`，条目统一为 `path`、`basename`、`app`、`name`、`display`、`valid`、`error` 七个字段；无效场景保留 `load_scenario` 错误文本并继续处理其他条目；`path` 为相对 `root` 的 POSIX 路径，目录外回退绝对 POSIX 路径。未新增场景 schema 字段。`include_symlinks=False` 保持 apps/回收站跳过 symlink，web picker/display 传 `True` 保持跟随 symlink。
  - `core/lvgl_ai/apps/views.py`：删除本地 `scenario_index`，`list_apps` / `_orphans` / `scenarios_for_app` 消费 `..scenario.scenario_index`；应用回收站经 `scenarios_for_app` 使用同一索引，`trash.py` 未改。
  - `core/lvgl_ai/web/webapp.py`：`_scenario_apps_locked` 改为消费共享索引并传 `include_symlinks=True`，删除场景目录 `glob("*.json")` 与 `load_scenario`；picker 仍按文件名排序后按 `app` 去重、再按 `(name, app)` 排序；`_scenario_display_locked` 仍从同一 picker 数据取 display。
  - `core/tests/test_scenario.py`：新增 `ScenarioIndexTest`（7 字段、无效场景错误文本、独立 `scenarios_dir`）。
  - `core/tests/test_apps_seams.py`：`ViewsSeamTest` 改调共享 `scenario_index`，并新增 `test_scenario_index_skips_symlinked_scenarios`。
  - `core/tests/test_web_live.py`：新增 `test_symlinked_scenarios_stay_in_the_picker_and_live_display`，覆盖 picker 与 live start display 跟随 symlink。
  - `core/tests/support.py`：新增 `symlinked_file()`；Windows 无 symlink 权限时写普通文件并定向 patch `Path.is_symlink`，不跳过、不放宽断言。
- 红态：`ScenarioIndexTest` → 退出 1，Ran 3 tests，ERROR (errors=3)，`AttributeError: module 'lvgl_ai.scenario' has no attribute 'scenario_index'`。
- 绿态：`ScenarioIndexTest` → 退出 0，Ran 3 tests，OK。测试名：`test_entries_carry_seven_fields_and_invalid_errors`、`test_one_invalid_scenario_does_not_block_the_others`、`test_index_accepts_an_independent_scenarios_dir`。
- 行为锚点：退出 0，Ran 13 tests，OK。测试名：`ScenarioIndexTest` 三条，`test_apps.AppDomainTest.test_list_apps_tree_and_recent`，`test_apps_seams.ViewsSeamTest.test_scenario_index_records_invalid_files`、`test_scenarios_for_app_and_recent_kinds`，`test_web_apps.WebAppsTest.test_list_and_tree_use_the_temp_repo`、`test_delete_trash_restore_and_purge`，`test_web_live.LiveHttpTest.test_scenario_apps_include_display`、`test_live_start_forwards_the_scenario_display`、`test_live_start_without_a_scenario_display_uses_the_default`、`test_live_page_lists_apps_declared_by_scenarios`、`test_page_query_preselects_app`。
- symlink 回归修复：原 apps 视图跳过 symlink、原 web picker/display 跟随 symlink；共享索引初版统一跳过造成 web 行为变化。现由 `include_symlinks` 参数区分，两条行为测试：
  - 红态：`test_web_live.LiveHttpTest.test_symlinked_scenarios_stay_in_the_picker_and_live_display` → 退出 1，Ran 1 test，FAIL，`AssertionError: 'coffee' not found in {}`；同时 `test_apps_seams.ViewsSeamTest.test_scenario_index_skips_symlinked_scenarios` 保持 OK。
  - 绿态：上述两条 → 退出 0，Ran 2 tests，OK。
- fake/unit 回归：`test_scenario` 单元类、`test_apps`、`test_apps_seams`、`test_web_apps`、`test_web_live.{LiveSessionTest,PageTrackingTest,LiveHttpTest}` → 退出 0，Ran 127 tests，OK。
- 去重检查：`git grep -n -E "load_scenario|glob\(" -- core/lvgl_ai/web` → 无输出，退出 1（git grep 无匹配）。web 层不再自行 glob 场景目录或调用 `load_scenario`。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0，`differences: 0`（symlink 修复后复跑）。
- 全量测试：按主代理约束未在 worktree 运行（`lvgl-src/`、`third_party/` 只有 README，真实 engine 不可用），留给主代理合并后执行。
- 风险/边界：`WebApp(scenarios_dir=...)` 继续生效，由 `test_index_accepts_an_independent_scenarios_dir` 和 `test_web_live` display 测试覆盖。apps/回收站仍跳过 symlink，web picker 与 live display 仍跟随 symlink；固定文件名排序、按 app 去重、`(name, app)` 排序、错误文本与 display 输出不变。`apps/policy.py` 的保留名扫描不在本票范围，未改。
