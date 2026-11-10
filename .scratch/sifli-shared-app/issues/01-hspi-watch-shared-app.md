# 01: hspi_watch 双端共享应用收口

**What to build:** 让同一份 `hspi_watch` 应用源码在本地 headless 和 SiFli 导出之间真正共享：导出资源层暴露与本地一致的尺寸和图片符号契约，raw 热图进入导出构建，本地场景按 390x450 运行，并用双端会话证据和文档收口证明共享契约成立。

**Blocked by:** None (can start immediately)

**Status:** resolved

- [ ] 导出 `hspi_watch` 时，生成资源头包含 `WATCH_*` 尺寸宏和与本地一致的图片符号；尺寸从 PNG 宽高生成；SDK 分支不 include 本地静态资源头。
- [ ] 导出工程收集 raw 热图源文件，并把 raw 目录加入 include 路径；旋转表针和圆环不再链接缺符号。
- [ ] 导出源码复制一致性测试保持通过；新增生成资源头尺寸/符号契约测试和 raw 源收集契约测试。
- [ ] `hspi_watch` 场景声明 390x450；源目录用 LVGL 9.6 跑 headless 后，会话满足 `status=ok`、`app=hspi_watch`、`display=390x450`。
- [ ] 导出副本用 LVGL 9.4 跑 headless 后，会话满足 `status=ok`、`app=hspi_watch`、`display=390x450`，并保留 timeline/snapshot 证据。
- [ ] 导出工程保持自包含，只依赖 SiFli SDK；生成目录继续不进入版本库。
- [ ] 文档说明“共享源码 + 目标专属生成层”、`void <name>_create(void)` 入口、390x450 场景和 EZIP/真机验证边界；领域术语表中的旧入口签名同步修正。
- [ ] 不移植 coffee、xiaohongshu、spectrum；不让 SiFli 工程直接引用或 symlink 本仓库源码；不在本地引入 EZIP 解码。

## Comments

- 2026-11-10: 实现于 `feat/sifli-shared-app`，提交 `5906a0c`、`75891cc`。导出契约测试 15 个通过（fake ezip，不依赖 SiFli SDK）；源目录 9.6 与导出副本 9.4 headless 均 `status=ok`、`app=hspi_watch`、`display=390x450`，证据在 `.scratch/tmp/sifli-shared-app/evidence/`。代码审查发现已修复：契约测试不再跳过、坏 PNG/宏名冲突有测试、自包含断言加强、文档 9.4 命令同步。EZIP 解码、scons 固件构建和真机显示仍待 SDK 工具链环境验收。
