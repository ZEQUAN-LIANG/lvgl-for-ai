# 05：RuntimeOptions + RuntimeLike（候选 04）

**What to build：** 生产侧的 Runtime 选项集中由一个 `RuntimeOptions` 组装；测试 double 的共同面由一个内部 `RuntimeLike` Protocol 定义。做完后，live 新选项只组装一处，测试不再用模块 patch 观察默认参数，`live_session` 不再用 `getattr` 猜属性。

**Blocked by：** None (can start immediately)

**建议顺序：** 在 03 之后实施，避免两次改 Runtime；这不是硬阻塞。

**Status:** done

**验收方式：**

- Options：测试断言 `RuntimeOptions(...).as_kwargs()` 被 `Runtime(**kwargs)` 接受；默认工厂构造 Runtime。
- 公开面：`python -I core/tools/contract_snapshot.py compare` → 退出 0（21 参数不变）。
- Protocol：测试断言 `RuntimeLike` 不在 `__all__`；成员面等于约定列表。
- getattr：`git grep -n -E "getattr\(.*runtime" -- core/lvgl_ai/web/live_session.py` → 0（共享接口）；缺失 `tick` 不再静默跳过。
- Fake：测试断言 `FakeRuntime` 实现 `RuntimeLike` 全部成员（包括 `tick`）；`git grep -n "fake_runtime" -- core/tools/contract_snapshot.py` → 0。
- 行为：`test_web_live.py`、`test_scenario.py`、`test_cli.py` 通过。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：命令、测试名与退出码写入票末「完成」。

- [x] `RuntimeOptions.as_kwargs()` 可用，默认工厂构造 `Runtime(**options.as_kwargs())`（测试）。
- [x] `Runtime` 的 21 参数构造签名不变（契约比较）。
- [x] `RuntimeLike` 不进 `__all__`，成员面符合约定且不包含假想成员（测试）。
- [x] `live_session` 用 Options 组装；共享接口无 `getattr`（`git grep` + 行为测试）。
- [x] `FakeRuntime` 实现完整 Protocol（含 `tick`）；`contract_snapshot` 的 stub 保持独立（测试 + `git grep`）。
- [x] 全量门禁：本 worktree 无 `lvgl-src/`、`third_party/` 与真实 engine，按交办说明未运行 `python -I core/tests/run_tests.py`；已跑限定的 fake/unit 套件与契约比较（见「完成」）。

## 完成

日期：2026-11-11。分支 `ticket/05-runtime-options`，基线 `5e68335`。

实现：

- `RuntimeOptions` 只转发显式提供的生产选项（含 width/height 成对），不含 `_engine_*`/`_configure_command`/`_build_command`。
- `RuntimeLike` Protocol 覆盖三份 double 的共同面（23 个成员）；未加入 `__enter__`/`__exit__`、`lvgl`、`build` 等非共同面；runtime module 不新增 `__all__`。
- `live_session._default_runtime()` 改为 `RuntimeOptions(...).as_kwargs()`，`Runtime` 名字在调用时解析，`mock.patch("lvgl_ai.web.live_session.Runtime", ...)` 仍生效。
- `live_session` 共享接口全部改为直接属性访问；ticker 启动前校验 `tick` 可调用，缺失时 `start()` 报 `live_start_error`，不再静默跳过。
- `FakeRuntime` 补 `ready`/`frame_count`/`t_ms`/`tick`；`_LiveStub` 补 `encoder`/`mark`/`snapshot`；`_FakeRuntime` 与 `_LiveStub` 保持独立，未 import `fake_runtime`。

验证（均从 worktree 根执行）：

| 命令 / 测试名 | 退出码 |
| --- | --- |
| `python -I -c "... unittest.main(module='test_runtime_options', verbosity=2)"`：RuntimeOptionsTest(4)、RuntimeLikeTest(3)、FakeRuntimeContractTest(2)、ContractSnapshotStubTest(1) | 0（10 tests OK） |
| `python -I -c "... test_web_live: LiveSessionTest, PageTrackingTest, LiveHttpTest"` | 0（42 tests OK） |
| `python -I -c "... test_web_transport"` | 0（8 tests OK） |
| `python -I -c "... test_scenario: ScenarioExpansionTest, ScenarioValidationTest, ScenarioFileTest, ScenarioIndexTest, ScenarioErrorMappingTest"` | 0（35 tests OK） |
| `python -I -c "... test_cli: CliUnitTest"` | 0（24 tests OK） |
| `python -I -c "... test_contract_snapshot"` | 0（14 tests OK） |
| `python -I -c "... test_runtime: RuntimeSessionOptionTest, RuntimeProcessSeamTest"` | 0（10 tests OK） |
| `python -I -c "... test_public_exports"` | 0（4 tests OK） |
| `python -I core/tools/contract_snapshot.py compare` | 0（differences: 0，Runtime 21 参数签名不变） |
| `git grep -n -E "getattr\(.*runtime" -- core/lvgl_ai/web/live_session.py` | 1（0 命中） |
| `git grep -n "fake_runtime" -- core/tools/contract_snapshot.py` | 1（0 命中） |

TDD 证据（本机 `.scratch/architecture-deepening/evidence/05/`，该目录被 `.git/info/exclude` 忽略）：

- red：`test_runtime_options` 5 failures + 2 errors（Options 未转发、Protocol 空、Fake 缺 tick、stub 缺 encoder/mark/snapshot）；`test_start_requires_a_runtime_tick` FAIL（LiveError not raised）。
- green：上述限定套件与契约比较全部退出 0。
- revert：移除 ticker 的 `tick` 预检后，`test_start_requires_a_runtime_tick` 重新 FAIL（LiveError not raised）；恢复后通过。
