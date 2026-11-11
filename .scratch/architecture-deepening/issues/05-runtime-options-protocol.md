# 05：RuntimeOptions + RuntimeLike（候选 04）

**What to build：** 生产侧的 Runtime 选项集中由一个 `RuntimeOptions` 组装；测试 double 的共同面由一个内部 `RuntimeLike` Protocol 定义。做完后，live 新选项只组装一处，测试不再用模块 patch 观察默认参数，`live_session` 不再用 `getattr` 猜属性。

**Blocked by：** None (can start immediately)

**建议顺序：** 在 03 之后实施，避免两次改 Runtime；这不是硬阻塞。

**Status:** open

**验收方式：**

- Options：测试断言 `RuntimeOptions(...).as_kwargs()` 被 `Runtime(**kwargs)` 接受；默认工厂构造 Runtime。
- 公开面：`python -I core/tools/contract_snapshot.py compare` → 退出 0（21 参数不变）。
- Protocol：测试断言 `RuntimeLike` 不在 `__all__`；成员面等于约定列表。
- getattr：`git grep -n -E "getattr\(.*runtime" -- core/lvgl_ai/web/live_session.py` → 0（共享接口）；缺失 `tick` 不再静默跳过。
- Fake：测试断言 `FakeRuntime` 实现 `RuntimeLike` 全部成员（包括 `tick`）；`git grep -n "fake_runtime" -- core/tools/contract_snapshot.py` → 0。
- 行为：`test_web_live.py`、`test_scenario.py`、`test_cli.py` 通过。
- 全量：`python -I core/tests/run_tests.py` → 退出 0。
- 记录：命令、测试名与退出码写入票末「完成」。

- [ ] `RuntimeOptions.as_kwargs()` 可用，默认工厂构造 `Runtime(**options.as_kwargs())`（测试）。
- [ ] `Runtime` 的 21 参数构造签名不变（契约比较）。
- [ ] `RuntimeLike` 不进 `__all__`，成员面符合约定且不包含假想成员（测试）。
- [ ] `live_session` 用 Options 组装；共享接口无 `getattr`（`git grep` + 行为测试）。
- [ ] `FakeRuntime` 实现完整 Protocol（含 `tick`）；`contract_snapshot` 的 stub 保持独立（测试 + `git grep`）。
- [ ] `python -I core/tests/run_tests.py` 退出 0；契约比较无差异。
