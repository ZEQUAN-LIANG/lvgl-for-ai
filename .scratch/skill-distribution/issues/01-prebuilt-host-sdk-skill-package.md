# 01：预编译宿主 SDK + 最小离线 skill 包闭环

**What to build：** 从现有 LVGL 9.6 源码导出一份宿主预编译 SDK；在不使用 LVGL 源码、第三方源码、CMake 或 Ninja 的情况下，用 gcc 直接编译 `user/app` 并链接 SDK，跑一个场景并产出会话证据；再把工具层、用户区、宿主 SDK、预编译 engine 和统一入口打成 release zip。把 zip 解压到任意目录后，从与包无关的工作目录执行 `lvgl run --scenario ... --json` 仍能构建、运行、产出证据，`lvgl serve` 能启动网页。

本票不包含：内置 Python、精简 MinGW、双击启动器、SiFli add-on、9.4 SDK、多 SDK 约定、viewer/thin 档、升级包、代码签名。这些留给后续票。

**Blocked by：** None (can start immediately)

**Status:** open

- [ ] 导出宿主 SDK 后，SDK manifest 至少记录 LVGL 版本、编译器版本、defines、include 顺序、链接顺序和五份静态库的哈希；manifest 中的哈希与文件实际内容一致。
- [ ] LVGL 源码不可用时，CLI 自动选择预编译构建；显式 `--prebuilt` 与 `--source` 能覆盖自动判断。选择结果可从构建日志或 `--json` 观察到。
- [ ] 使用预编译 SDK 构建现有 `user/app` 并运行一个场景，`--json` 返回 `status=ok`，会话目录包含该场景应有的 manifest、timeline、frames/snapshots 等证据文件。
- [ ] 故意制造编译错误时，CLI 返回构建失败，诊断包含文件、行、列；故意制造链接错误时，返回链接失败并列出 unresolved symbol；两种情况下构建日志都包含实际命令和原始输出。
- [ ] 预编译 engine 放进包后，`lvgl run --no-build ... --json` 无需编译器即可运行并产出会话证据。
- [ ] release 脚本产出一个 zip，包含工具层、用户区、宿主 SDK、预编译 engine、统一入口和 `SKILL.md`；不包含 LVGL 源码、第三方源码、会话、测试、SiFli vendor 目录、SiFli 导出目录和开发机绝对路径。
- [ ] 将 zip 解压到临时目录后，从与包无关的工作目录执行 `lvgl run --scenario ... --json` 成功并产出会话证据；`lvgl serve` 在同一环境能启动并对本机请求返回成功响应。
- [ ] 现有测试全部通过；新增测试只落在已确认的缝上：用现有 BuildPlan scripted runner 覆盖预编译选择、命令构造和错误映射；用 release 产物黑盒覆盖包内清单、排除项和解压后的 smoke。
- [ ] 开发仓库的 CMake 构建路径不受影响：LVGL 源码存在且未指定 `--prebuilt` 时仍走现有 CMake 流程，现有构建集成测试通过。

**验收记录：** 保留 release zip 的 sha256、解压后的 smoke 命令输出、产生的会话 ID 与 `--json` 摘要；编译/链接错误用例保留 `build.log`。
