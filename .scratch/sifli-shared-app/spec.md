# hspi_watch 双端共享应用

Status: ready-for-agent

## Problem Statement

我维护 `hspi_watch` 时，本地 headless 预览和黄山派 SiFli 导出并没有真正做到同一份应用契约：

- 本地资源头提供 `WATCH_*` 尺寸宏和静态 C 数组，导出生成的 SDK 资源头只声明图片符号，不提供尺寸宏，导致共享应用源码在 SDK 分支可能编译失败。
- 导出工程的 SConscript 不收集 raw 热图源文件，旋转图片会链接缺符号。
- 本地 `hspi_watch` 场景没有声明 390x450，headless 默认 800x600，表盘居中，预览构图与设备不一致。
- 现有测试能证明源码被复制，但不能证明生成资源头、raw 源收集和场景显示尺寸仍然满足双端共享契约。

结果是：同一份应用代码虽然已经放在同一个目录，但“共享”仍停留在源码复制层，设备目标的构建风险没有被验证回路覆盖。

## Solution

把 `hspi_watch` 明确为双端共享应用变体：

- `user/app` 中的 `hspi_watch` 是唯一源码真源；本地 headless 直接使用，SiFli 导出时复制成自包含工程。
- 只共享应用入口 `void hspi_watch_create(void)`；headless 的 `app_create`、SDK 的 `main` 和注册表按目标生成或保留。
- 共享应用以 LVGL 9.4 API 为硬基线，同时能在本地 LVGL 9.6 运行。
- 应用只依赖统一的 `assets.h` 契约；本地使用静态数组，SiFli 使用 EZIP/raw，两端暴露相同的图片符号和尺寸宏。
- 导出器从 PNG 宽高生成尺寸宏，模板收集 raw 源文件，本地场景声明 390x450。
- 用现有导出契约测试和现有 CLI/场景 seam 验证，不新增第二套测试入口。

## User Stories

1. As a 黄山派固件开发者, I want 本地预览和 SiFli 导出使用同一份 `hspi_watch` 应用源码, so that 我只需要修复一次 UI 或行为问题。
2. As a 固件开发者, I want 导出工程复制应用源码并保持自包含, so that 我可以在只安装 SiFli SDK 的机器上构建。
3. As an 应用开发者, I want 共享入口只保留 `void hspi_watch_create(void)`, so that headless 和 RT-Thread 的平台入口不会进入共享代码。
4. As an 应用开发者, I want 共享应用同时兼容 LVGL 9.4 和 9.6, so that 本地预览和黄山派目标不需要维护两套实现。
5. As an 应用开发者, I want 两端 `assets.h` 暴露相同的图片符号, so that 应用代码不需要写平台分支。
6. As an 应用开发者, I want 两端 `assets.h` 暴露相同的 `WATCH_*` 尺寸宏, so that 布局代码在 SDK 分支也能编译。
7. As an 应用开发者, I want 尺寸宏从 PNG 宽高生成, so that 宏不会和图像实际尺寸漂移。
8. As a 固件开发者, I want 旋转热图以 raw 形式编译进导出工程, so that 链接不会缺少 `watch_*_raw` 符号。
9. As a 固件开发者, I want 缓存和旋转内存配置继续由资源清单生成, so that PSRAM 旋转缓冲配置不需要手工改工程。
10. As a reviewer, I want 复制一致性测试继续保证导出源码只多一行 SDK include, so that 导出过程不会悄悄改写应用代码。
11. As a reviewer, I want 生成资源头的契约测试, so that 尺寸宏和图片符号缺失会立即失败。
12. As a reviewer, I want 导出模板收集 raw 源文件的契约测试, so that 热图链接问题不会回归。
13. As a UI 开发者, I want `hspi_watch` 场景声明 390x450, so that 本地截图的构图与黄山派设备一致。
14. As an AI agent, I want 通过现有 CLI/场景 seam 跑源目录 9.6 和导出副本 9.4, so that 我能为两个目标都生成会话证据。
15. As an AI agent, I want 会话 manifest 记录 `app=hspi_watch` 和 `display=390x450`, so that 我可以确认验证对象和显示配置。
16. As a maintainer, I want 导出目录继续被 git 忽略, so that 仓库只有一份源码真源。
17. As a maintainer, I want 文档明确“共享源码 + 目标专属生成层”的边界, so that 贡献者知道哪些文件该改、哪些是生成物。
18. As a maintainer, I want coffee、xiaohongshu、spectrum 继续排除在共享范围外, so that 9.6-only 应用不会阻塞 SiFli 导出。
19. As a maintainer, I want 领域术语表中的应用入口签名与当前 `void <name>_create(void)` 保持一致, so that 文档不会继续传播旧签名。
20. As a tester, I want 明确记录 EZIP 解码和真机显示仍需 SDK 工具链验收, so that headless 通过不会被误认为设备验收完成。
21. As a 固件开发者, I want 导出器继续显式拒绝 EZIP 旋转和 9.5/9.6-only API, so that 不兼容配置在导出阶段就失败。
22. As a 固件开发者, I want 热图初始化通过生成的 `app_assets_init()` 完成, so that PSRAM/SRAM 副本在应用创建前准备好。

## Implementation Decisions

- **共享范围**：只把 `hspi_watch` 纳入双端共享；coffee、xiaohongshu、spectrum 保持现状。
- **源码真源**：`user/app` 中的 `hspi_watch` 是唯一真源；导出时复制，不使用 symlink 或相对路径引用。
- **导出物**：SiFli 导出工程保持自包含，只依赖 SiFli SDK；生成目录继续不进入版本库。
- **入口契约**：共享应用只暴露 `void hspi_watch_create(void)`；SiFli 的 `app_create()` 封装、`main` 和 headless 注册表分别由目标侧维护。
- **LVGL 基线**：共享应用以 LVGL 9.4 可用 API 为硬约束；本地 9.6 只用于预览和验证，不要求导出器做源码降级。
- **资源 API**：应用只 include `assets.h`；本地实现为静态 C 数组，SDK 实现为 EZIP/raw；两端必须暴露同名图片符号、`WATCH_*` 尺寸宏和 `app_assets_init()`。
- **尺寸来源**：生成资源头的尺寸宏从 PNG IHDR 读取，命名规则为资源名大写后加 `_W` / `_H`；SDK 分支不 include 本地静态资源头。
- **热/冷资源**：资源清单继续声明 `mode`、`placement` 和 `transform`；热图通过 `app_cache_copy_alloc()` 生成运行时副本，并由 `app_assets_init()` 在应用创建前初始化。
- **raw 源收集**：导出模板必须把 raw 资源源文件纳入编译，并把 raw 目录加入 include 路径。
- **缓存配置**：PSRAM/SRAM 图片缓存和旋转内存配置继续由资源清单生成，不手工维护导出工程配置。
- **场景显示**：`hspi_watch` 场景声明 390x450；应用继续按黄山派目标屏固定布局，不引入响应式布局。
- **错误行为**：保留现有显式导出错误，包括资源 transform 冲突、未注册应用、9.5/9.6-only API 和不兼容目标目录。
- **Schema**：不新增协议或场景 schema；复用现有场景 `display` 字段和资源清单。
- **文档**：更新 SiFli 导出说明和应用写作指南，说明共享源码、生成层和验证边界；修正领域术语表中过时的入口签名。
- **不做的事**：不引入共享 `app_create` / `main`，不在本地引入 EZIP 解码，不跟踪生成工程，不为其他应用做 9.4 移植。

## Testing Decisions

- **好测试的标准**：只验证外部可观察行为——导出器生成的工程内容、公开资源契约、场景运行结果和会话 manifest；不测试导出器内部辅助函数或具体实现步骤。
- **主 seam（现有）**：导出契约测试直接调用公开导出操作，检查：
  - 复制后的应用源码除顶部 SDK include 外与真源一致；
  - 生成资源头包含 `WATCH_*` 尺寸宏和两端一致的图片符号；
  - 导出模板收集 raw 源文件；
  - 资源清单驱动的缓存配置和 `export.json` 仍然生成。
- **次 seam（现有）**：CLI/场景 seam 运行 `hspi_watch` 场景：
  - 源目录用 LVGL 9.6 跑一次；
  - 导出副本用 LVGL 9.4 跑一次；
  - 断言会话状态为 `ok`、`app=hspi_watch`、`display=390x450`，并保留 timeline/snapshot 作为证据。
- **复用优先**：不新增运行时 harness；导出契约测试仍走公开导出操作。`AssetPlan` 的 module 级测试由 `.scratch/architecture-deepening/spec.md` 定义，是新的导出器内部测试缝，不替代导出契约测试。
- **先例**：现有 SiFli 导出测试已经覆盖源码复制、资源清单和缓存配置；现有应用 seam 测试覆盖入口注册；现有 CLI/场景测试覆盖会话 manifest 和 timeline。
- **不在本机自动化的部分**：SDK 分支的 EZIP 解码、SCons 固件构建、链接和真机显示仍需要装有 SiFli 工具链的环境验收；headless 通过只证明共享源码和本地资源回退可用。

## Out of Scope

- 把 coffee、xiaohongshu、spectrum 移植到 LVGL 9.4。
- 让 SiFli 工程直接引用或 symlink 本仓库源码。
- 共享 `app_create()`、`main.c` 或应用注册表。
- 在本地 headless 中引入 EZIP 解码。
- 跟踪或提交生成的 SiFli 导出工程。
- 为不同屏幕做响应式表盘布局。
- 修改 core 运行时、场景协议或导出错误码语义。
- 在本机自动执行 SiFli SDK 固件构建和真机验收。

## Further Notes

- PR !6 已合并到 `dev`，合并提交对应“按 assets 清单生成资源层并统一 void 应用入口”；当前共享模型已经是“源码复制 + 目标专属生成层”，本 spec 是合并后的契约收尾。
- 当前已知的两个契约缺口是：SDK 生成资源头缺少尺寸宏，导出模板不收集 raw 源文件；两者都应在实现阶段修复。
- 本机没有 SiFli 工具链，因此 EZIP 分支和真机显示只能做静态契约检查，不能作为自动化验收。
- 仓库没有找到已配置的远程 issue tracker 和 triage 标签词汇；按本地 Markdown tracker 约定发布，ticket 位于同目录的 `issues/` 下。
- `CONTEXT.md` 中应用变体入口仍写成带 `lv_obj_t * screen` 的旧签名，和当前 `void <name>_create(void)` 不一致，应随文档更新修正。
- 现有全量测试可能存在与本功能无关的环境失败；验证以聚焦导出测试和两次 headless 场景运行为准。
