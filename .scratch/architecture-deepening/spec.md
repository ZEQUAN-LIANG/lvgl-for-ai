# 架构深化：把浅 module 收成深 module

## 问题陈述

维护者和 AI agent 在修改这个代码库时，改动半径比实际需要的大：

- SiFli 导出器的资源计划没有内部缝。清单校验、PNG 尺寸、ezip 子进程、符号改名、缓存数学和资源代码生成挤在一个函数里；想验证一条资源规则，必须准备完整应用工程。
- 会话状态有多个主人。选项在 `Runtime` 与 `SessionStore` 各存一份，`frame_count` 在运行时与 manifest 里是两个含义，`.engine.pid` 的 `session_id`/`app` 永远是 `null`。
- web 层重造了 `Recording` 已有的帧和 timeline 读模型。`live_session` 与 `replay_model` 各自解析文件名、行形状和 URL；timeline schema 一变要改两处。
- 17 个 `import *` 兼容转发 module 没有生产调用点，文档、契约快照和 import 图都指向新 module，旧路径只剩误导。
- `Runtime` 的 interface 是隐式的：21 个构造参数、21 处 `getattr`、三份手写 double 和七处模块 patch 才能观察 live 的默认选项。
- 应用管理台在 live 启动期间拿不到 `/api/apps`：`start_live` 在 `_apps_lock` 内触发最长 600 秒的构建。
- 场景索引在同一请求里解析两遍；per-scenario display 刚合入，picker 与 live start 开始分叉。

结果是：理解一个概念要在多个小 module 之间来回跳，测试要绕过公开 interface 去假设内部结构，修一次要改多处。本 effort 只做深化设计，不改行为。

## 方案

**硬约束：重构不改变任何外部可观察行为。** 唯一有意的契约变化是 05 新增 `Recording` 的三个公开方法；其余候选的 CLI、HTTP、会话文件、manifest、导出产物、场景 schema 都必须逐字段、逐字节不变。

按 7 个候选把相关行为收进更深的 module：小 interface，大 implementation，复杂度集中在一处，调用者与测试跨同一道缝。

- **01 导出资源计划**：新增 `AssetPlan` module；导出器只负责编排、写盘和组装导出清单。
- **02 会话状态**：`SessionStore` 成为会话文件的唯一写者；`Runtime` 只保留只读转发；`EngineLink` 写 pid 时带 session 身份。
- **03 兼容转发层**：删除 17 个零生产调用点的转发 module，保留真正的公开契约。
- **04 运行时接口**：用 `RuntimeOptions` 集中组装选项，用 `RuntimeLike` Protocol 定义测试 double 的共同面。
- **05 证据读模型**：`Recording` 提供帧视图、快照视图和最新帧，web 只拼 URL。
- **06 应用管理台 live 路径**：折叠 6 个 1:1 转发方法，`_apps_lock` 不跨构建。
- **07 场景索引**：索引只解析一遍，放在场景 schema 所有者处，apps 与 web 共用。

外部行为不变由 `contract_snapshot.py compare` 与全量测试守住；只有 05 因为新增 `Recording` 公开成员而有意更新快照。实施按 `01 → 03 → 02 → 05 → 04 → 06 → 07`，每个候选独立验收。

## 用户故事

1. 作为维护者，我要导出资源计划有自己的 module，以便只读一个地方就能理解资源规则。
2. 作为 AI agent，我要用清单和 PNG 夹具测试资源规则，以便不准备完整应用工程。
3. 作为维护者，我要导出契约测试继续走公开导出操作，以便测试不依赖内部辅助函数。
4. 作为维护者，我要一次导出的产物在字节级别不变，以便重构不改变生成工程。
5. 作为维护者，我要 `SessionStore` 是会话文件的唯一写者，以便 manifest、pid 和日志只有一个写入点。
6. 作为维护者，我要 `Runtime` 的会话属性只读转发到 `SessionStore`，以便不再维护第二份状态。
7. 作为维护者，我要“预约帧”和“落盘帧”有明确名字，以便 live 与 manifest 不说两套话。
8. 作为开发者，我要 `EngineLink` 写 pid 时带 session 身份，以便排障时知道 pid 属于哪个会话。
9. 作为 AI agent，我要删除 17 个转发 module，以便 import 图和 `rg` 结果不误导。
10. 作为维护者，我要保留 `lvgl_ai` 顶层与 `apps` 生命周期契约，以便删除不破坏公开导入。
11. 作为维护者，我要 `Runtime` 的选项集中为一个 Options，以便 live 与测试只组装一次。
12. 作为测试作者，我要一个 `RuntimeLike` Protocol，以便三份 double 有共同面。
13. 作为测试作者，我要 `FakeRuntime` 是唯一测试基类，以便新选项不再复制 double。
14. 作为维护者，我要 `live_session` 不再用 `getattr` 猜属性，以便接口错误更早暴露。
15. 作为维护者，我要 `Recording` 提供帧视图，以便 replay 不再自己解析 timeline。
16. 作为维护者，我要 `Recording` 提供快照视图，以便快照解析也只有一个入口。
17. 作为维护者，我要 `Recording` 提供最新帧，以便 live 轮询用尾读而不读全量 timeline。
18. 作为维护者，我要 `Recording` 不返回 web URL，以便读侧不依赖 web 层。
19. 作为用户，我要 live 构建期间应用管理台仍可列出应用，以便不被最长 600 秒的构建卡住。
20. 作为维护者，我要 live 错误映射集中在 dispatch，以便 6 个转发方法可以删除。
21. 作为开发者，我要 live 的 `STARTING` 语义不变，以便现有状态轮询不受影响。
22. 作为维护者，我要场景索引只解析一遍，以便 display 语义不分叉。
23. 作为开发者，我要场景索引携带 `name` 和 `display`，以便 picker 与 live start 同源。
24. 作为维护者，我要索引放在场景 schema 所有者处，以便 apps 不反向依赖 web。
25. 作为验收者，我要每个候选都跑全量测试与契约快照比较，以便重构不漂移。
26. 作为验收者，我要只有 05 更新快照，以便其他候选保持外部契约。
27. 作为维护者，我要设计先行、实施分支分离，以便工具层改动不与 SiFli 共享契约混在一起。
28. 作为 AI agent，我要设计文档留在本地 tracker，以便不进入发布包。
29. 作为维护者，我要 SiFli effort 的测试决策与 `AssetPlan` 新缝一致，以便两处设计不冲突。
30. 作为维护者，我要 04 的测试面只覆盖现有三份 double 的共同面，以便不为假想需求加抽象。
31. 作为维护者，我要 03 删除后保留顶层 `LatError` 别名，以便公开导入不变。
32. 作为维护者，我要 06 补「慢启动期间 `/api/apps` 可读」的测试，以便锁范围不会回归。

## 实现决策

### 总体

- 本 effort 只产出设计与票据，不改代码；实施另开分支。01 随 SiFli 共享应用分支，02–07 随工具分支；不把两类改动混在一起。
- 工作包：A 导出器（01）；B 会话状态与读模型（02 + 05 + 04）；C 清零与 web 收口（03 + 06 + 07）。
- 实施顺序：`01 → 03 → 02 → 05 → 04 → 06 → 07`。每个候选独立验收。
- 外部行为不变是硬约束：CLI 参数与退出码、HTTP 路由/状态码/JSON 形状、会话文件集合与 manifest 字段、导出产物字节、场景 schema 都不变。唯一有意的契约变化是 05 新增 `Recording` 公开成员。
- 不新增协议、HTTP 路由、场景词汇或第二套控制客户端；不输出 pass/fail、baseline、approval、acceptance；不做对象树、inspect、属性读取、set、param。

### 01 · 导出器资源计划

- 新增 `AssetPlan` module，作为导出适配器内部的深 module。公开 interface 只有一个入口：`plan_assets(source_dir, adapter, *, ezip_tool=None) -> AssetPlan`。
- `AssetPlan` 是数据结果，包含 `records`、`files`、`cache`、`local_header`、`has_assets`：
  - `records`：每个资源的名称、文件、mode、placement、transform、是否热加载、宽高、解码后大小。
  - `files`：相对目标路径到字节，包含 ezip/raw 资源 C 源、`assets.h`、`assets.c`。
  - `cache`：缓存配置数据，由导出编排写入项目模板；缓存数学留在 `AssetPlan` 内部。
  - `local_header`：本地静态头声明，供资源头生成使用。
- `AssetPlan` 内部吸收：资源清单校验、PNG 尺寸读取、ezip 子进程调用、符号改名、缓存计算、资源头/源生成。manifest 缺省、名称大小写冲突、坏 PNG、零尺寸、不支持的 transform、ezip 符号缺失等错误继续使用现有 `asset_*` 错误码。
- 导出编排只做：适配器加载、源码与模板复制、入口源码生成、导出清单生成、缓存配置落盘、文件写入、警告与命令组装。
- 导出产物必须字节一致；现有 16 个导出契约测试继续通过公开导出操作进入。
- `AssetPlan` 是新的 module 级测试面，不是新的外部协议；测试可以直接调用 `plan_assets`，用资源清单与 PNG 夹具覆盖缓存、符号、尺寸和错误规则。

### 02 · 会话状态

- `SessionStore` 成为会话状态的唯一写者：选项、manifest 输入、日志、pid 身份与落盘帧计数都由它拥有。
- `Runtime` 的下列属性改为只读转发到 `SessionStore`：`app`、`build`、`record`、`live_frame`、`record_changed_only`、`mode`、`lvgl_src`、`sessions_root`、`max_log_bytes`、`session_retention`、`ready`。
- `mode` 与 `ready` 在引擎 `ready` 回执后写回 store；`SessionStore` 增加最小的 setter/property，`Runtime` 不再保存第二份副本。
- `Runtime` 保留引擎与构建参数：`lvgl`、`width`、`height`、`window`、`headless`、`timeout`、`diff_threshold`、`reference`、`max_frames`。
- `Runtime.frame_count` 保留原名，语义明确为“引擎回执的预约帧”；manifest 的 `frame_count` 是“停止并 drain 后的落盘帧”。两者不合并；接口文档写清区别。
- `EngineLink` 在构造时接收 `session_id` 与 `app`；写 `.engine.pid` 时一并落盘，不再写 `null` 身份。
- `Runtime` 的公开构造签名、公开属性名与 `Recording` 读侧都不变；契约快照不因 02 更新。

### 03 · 兼容转发层

- 删除 `lvgl_ai.core` 兼容包的全部 12 个转发 module，以及 `web` 下 4 个旧路径别名和 `lvgl_ai.region` 别名，共 17 个文件。
- 保留 `lvgl_ai` 顶层公开导出与 `apps` 生命周期 interface；`LatError` 仍是 `ToolError` 的顶层别名。
- 契约快照只记录公开名字与签名，不记录内部 module 路径；删除不改变被冻结的契约。
- 兼容测试裁剪为公开导出断言并改名，不再断言旧路径可达；README 记一条“旧 import 路径已移除”。
- 风险：发布包可能被仓外 harness import 旧路径。文档没有旧路径承诺；若需要保守，先发布移除说明，不保留 17 个文件。

### 04 · 运行时接口

- 在 `runtime` module 内新增 `RuntimeOptions`，集中承载生产侧构造选项；`as_kwargs()` 供默认 Runtime 工厂使用。`Runtime` 的 21 参数构造签名保持不变，Options 是内部组装与测试缝，不是新公开 API。
- `RuntimeOptions` 不包含私有测试/嵌入 seam（engine path、engine command、configure/build command）；测试仍可直接向 `Runtime` 传这些参数。
- 在 `runtime` module 内新增 `RuntimeLike` Protocol，描述 `LiveSession` 与场景执行使用的共同面：生命周期、会话身份/路径、`ready`、`app`、`mode`、`frame_count`、`t_ms`、`pid`、`exit_code`、`log_tail`、`record_error`、`tick`、`wait`、`pointer`、`key`、`encoder`、`mark`、`snapshot`。Protocol 不进 `__all__`。
- `LiveSession` 用 `RuntimeOptions` 组装选项，默认工厂仍构造 `Runtime(**options.as_kwargs())`；21 处 `getattr` 改为直接属性访问。
- `FakeRuntime` 是测试侧唯一基类；`contract_snapshot` 的两个 stub 保持独立（工具不依赖测试），但成员面与 `RuntimeLike` 对齐。
- Protocol 只覆盖现有三份 double 的共同面，不为假想需求增加成员。

### 05 · 证据读模型

- `Recording` 新增三个公开方法：
  - `frame_views()`：按帧号排序的帧视图，字段为 `file`、`frame_no`、`t_ms`。
  - `snapshot_views()`：快照视图，除 `file`、`frame_no`、`t_ms` 外增加 `label`。
  - `latest_frame()`：最新保留帧的同一组字段；没有帧时返回 `None`。
- `Recording` 不返回 URL，不依赖 web 层；URL 由 web 的 URL helper 拼接。
- `latest_frame()` 的 timeline 尾部读取留在 `Recording` 内部，继续使用 256 KiB 上限；`frame_views()` 可以读取完整 timeline。
- `live_session` 的最新帧与 `replay_model` 的帧/快照条目改用这三个方法；两处不再各自解析文件名、`frame_no` 回退、`t_ms` 回退和 timeline 行形状。
- 这是一次有意的公开成员变化：实施 05 时用 `contract_snapshot.py record` 更新快照，并在对比说明里只允许这三个新增成员。
- 时间轴、帧差异与 manifest schema 不变；`live.rgba` 仍不是证据。

### 06 · 应用管理台 live 路径

- 删除 `WebApp` 上 6 个 1:1 live 转发方法；`LiveError` 在 HTTP dispatch 里与 `HttpError` 并列映射，HTTP 状态码与 JSON 形状不变。
- `start_live` 只在 `_apps_lock` 内读取场景 display；`LiveSession.start()` 移到锁外，最长 600 秒的构建不再阻塞 `/api/apps`。
- 应用变更保护继续由 `live.is_active()` 负责；不改变 `LiveSession` 的 `STARTING` / `RUNNING` / `IDLE` 语义，也不把 `/api/live` 状态轮询改成异步。
- 新增一条慢启动测试：live 启动仍在进行时，`/api/apps` 能立即返回应用列表。

### 07 · 场景索引

- `scenario_index` 移到场景 schema 所有者处，成为 apps 与 web 共用的唯一索引入口。
- 索引条目统一为 `path`、`basename`、`app`、`name`、`display`、`valid`、`error`；无效场景保留错误文本，不中断其他条目。
- `apps` 视图、应用回收站、web 的应用 picker 与 live start 的 display 查找都消费同一个索引；web 不再自己 glob 与解析场景。
- 不新增场景 schema 字段；排序与去重规则保持在调用者可见的行为里。

### 契约与 schema

- 不改变 `lvgl-ai-session-v1`、`lvgl-ai-timeline-v1`、`lvgl-ai-frame-diffs-v1`、`lvgl-ai-annotations-v1`、`lvgl-ai-scenario-v1`、`lvgl-ai-engine-v1`、`lvgl-ai-assets-v1`、`lvgl-ai-export-v1` 的字段与行形状。
- 不改变 CLI 退出码、`--json` 字段、HTTP 路由/状态码/JSON key、引擎命令行参数、导出 `export.json` 字段。
- `Runtime` 公开构造签名与成员名不变；`Recording` 只新增 05 的三个方法。

## 测试决策

### 缝

- 外部验收只有一个缝：现有公开行为，包括 CLI、HTTP、会话文件与导出产物；由 `contract_snapshot.py compare` 与全量测试守住。不新建协议客户端，不复制 HTTP 路由或场景词汇。
- 内部 module 缝按候选挂在已有公开 module 上：
  - 01：`AssetPlan.plan_assets` 是导出适配器内部的 module 级缝；导出契约测试仍走公开导出操作。
  - 02：`SessionStore` 的 manifest/pid 写入与 `Runtime` 的公开只读属性。
  - 03：`lvgl_ai` 顶层公开导出；删除后用导入测试与全量测试验证。
  - 04：`RuntimeOptions` / `RuntimeLike` 是内部组装与测试缝；`Runtime` 公开接口不变。
  - 05：`Recording` 的三个新方法。
  - 06：HTTP `/api/live/*` 与 `/api/apps` 端点。
  - 07：`scenario_index` 函数。
- 新增的 module interface 只有 `AssetPlan.plan_assets` 与 `Recording` 的三个方法；它们是深 module 的 interface，不是新的外部协议。整个 effort 不新增第二套控制协议。

### 好测试

- 只测外部可观察行为：导出产物、公开资源契约、会话文件与 manifest、HTTP 响应、CLI 一行 JSON、场景命令序列。
- 不测内部辅助函数；module 级测试只针对深 module 的 interface，不假设私有结构。
- 测试数据用现有夹具风格：临时会话目录、fake engine、fake ezip、资源清单与 PNG 夹具；不启动真实 LVGL 的单元测试不构建 engine。
- 真实证据沿用现有集成测试组织：`*IntegrationTest` 类、由全量测试入口执行、真实构建 engine；不新增跳过标记。

### 先例

- 导出契约：fake ezip + 公开导出操作，已有 16 个测试。
- 会话证据：临时会话夹具 + `Recording` + CLI `--json`。
- 运行时：`Runtime.start()` + fake engine；场景：`normalize_steps` + `play_scenario` + `FakeRuntime`。
- web：`_PageParser` 与 HTTP 客户端测试；实时预览用 raw 帧流。
- 视觉：`png_codec` 纯函数 + 小图夹具。

### 门禁

- 每个候选完成后：全量测试通过 + `contract_snapshot.py compare` 无差异（05 除外）。
- 05 完成后：有意 `record` 新快照；对比报告只允许 `Recording` 的三个新增成员，其他差异视为回归。
- 01 完成后：导出产物字节一致；现有导出契约测试全绿；新增 `AssetPlan` module 测试。
- 06 完成后：新增慢启动期间 `/api/apps` 可读的测试，且原有 `STARTING` 状态测试不变。

## 不做

- 不改外部行为：CLI 参数与退出码、HTTP 路由/状态码/JSON 形状、会话文件集合、manifest 字段、导出产物字节、场景 schema。
- 不新增协议客户端、HTTP 路由或场景词汇；不复制运行时命令。
- 不做 pass/fail、baseline、approval、acceptance。
- 不做对象树、活对象 inspect、属性读取、set、param。
- 不把 URL 拼装或 web 语义放进 `Recording`。
- 不把 `LiveSession.start()` 改成异步；不改变 `STARTING` 语义。
- 不为假想需求增加 Protocol 成员、Options 字段或新抽象。
- 不保留旧兼容 import 路径；按 03 直接删除。
- 不在本 effort 写实现代码；不把 01 与 02–07 混在同一分支。
- 不改 LVGL 源码；不改 SiFli SDK 固件构建、EZIP 解码或真机验收。
- 不恢复旧 workbench；不把审计 HTML 当文档索引。

## 补充说明

- 本 effort 的本地 tracker 是 `.scratch/architecture-deepening/`；`.scratch/` 已在 `.git/info/exclude` 中，不进入发布包或 Git。
- 设计树已在对话中逐项确认：产出只设计、分支分离、7 个候选的 module 边界与接口、测试缝、实施顺序、文档与门禁。
- SiFli 共享应用 effort 的测试决策需要与 01 对齐：`AssetPlan` 有自己的 module 级测试面，同时导出契约测试继续走公开导出操作。实施 01 时更新该 effort 的 spec，不提前改写现状。
- 契约快照脚本的 docstring 引用了架构深化票据；本 spec 取代该占位引用，实施时可把指针改到这里。
- `CONTEXT.md` 不新增术语：本轮没有新的领域概念；`AssetPlan`、`RuntimeOptions`、`RuntimeLike` 是架构名，不是产品语言。
- 没有被否决的候选，因此不记录 ADR。
- 下一步：用 `to-tickets` 按 7 个候选切票；每张票引用本 spec 的对应小节与测试决策。
