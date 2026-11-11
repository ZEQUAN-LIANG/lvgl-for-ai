# 01：导出资源计划收成 AssetPlan（候选 01）

**What to build：** SiFli 导出器把资源清单校验、PNG 尺寸读取、ezip 子进程、符号改名、缓存数学和资源头/源生成收进一个 `AssetPlan` module；导出器只负责编排、写盘和组装导出清单。做完后，维护者可以用资源清单和 PNG 夹具单独验证资源规则，同时导出产物与现在逐字节一致。

**Blocked by：** None (can start immediately)

**Status:** open

**验收方式：**

- 导出契约：`python -I chip-adapt/sifli/test_export.py` → 退出 0，全部测试 OK。
- 全量：`python -I core/tests/run_tests.py` → 退出 0，无 failure/error。
- 契约快照：`python -I core/tools/contract_snapshot.py compare` → 退出 0，无差异。
- 字节一致：复用导出契约测试的 fake ezip 注入方式，改动前把 `hspi_watch` 导出到临时目录 A；改动后用同一夹具导出到 B；`diff -r A B` → 无输出、退出 0。fake ezip 与临时目录不进入仓库。
- 记录：每条命令的退出码、测试数、`diff -r` 结果写入票末「完成」。

- [ ] `AssetPlan` 的公开入口是 `plan_assets(source_dir, adapter, *, ezip_tool=None) -> AssetPlan`，返回 `records`、`files`、`cache`、`local_header`、`has_assets`；module 测试断言五个字段存在且类型符合约定。
- [ ] 资源清单校验、缺省清单、PNG 尺寸、ezip 调用、符号改名、缓存计算、资源头/源生成只在 `AssetPlan` 内；代码审查 `export_app` 的资源路径只调用 `plan_assets`，不含 `subprocess`、PNG 解析、缓存数学或资源头生成代码。
- [ ] 现有导出契约测试全部通过（命令见上）；导出入口、`asset_*` 错误码与公开资源契约不变，测试断言错误码与生成文件内容。
- [ ] 改动前后对同一 `hspi_watch` 夹具的导出逐字节一致（`diff -r` 见上）。
- [ ] 新增 `AssetPlan` module 级测试，覆盖：缺省清单、坏 PNG、零尺寸、名称大写冲突、不支持的 transform、ezip 符号缺失、缓存配置、尺寸宏；使用资源清单 + PNG 夹具 + fake ezip。
- [ ] 在没有 SiFli SDK 的工作区运行上述测试通过；测试无跳过标记，不启动真实 ezip，不构建 engine。
- [ ] 全量测试与契约比较通过（命令见上）。
