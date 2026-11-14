# 契约快照与行为冻结

`tools/contract_snapshot.py` 记录并对比工具的外部契约，作为重构行为等价的证据。
历史票据 14（`14-architecture-deepening.md`）不在当前本地 tracker 中，视为历史不可用。
它只提供证据，不判定 UI 是否正确；由执行重构的 AI 在票内 Self-acceptance log
中自行确认，人类不参与验收。

契约快照覆盖六类：

| 类别 | 内容 |
| --- | --- |
| `http` | 路由、方法（含 405/501 反向方法探测）、状态码、`Content-Type`、JSON key 形状、错误 `code`、`/api/live/stream` 帧头、回收站 `meta.json` 形状与布局 |
| `cli` | `cli.py`、`web.py`、`tools/new_app.py` 的参数表、帮助文本、退出码、`--json` key 与错误码 |
| `protocol` | engine 命令语法与顺序、回执形状、`ready` / 回执必填字段、协议版本、engine 启动参数、`seq` 语义 |
| `session` | 普通录制与完整录制（reference + snapshot + annotations）的文件集合、manifest 字段与 artifacts、timeline / frame_diffs 行形状、`Recording` 读取必需文件与字段、`live.rgba` 生命周期 |
| `page` | 通过真实 HTTP 路由渲染的回放/空/错误三种页面变体的元素 id、class、标签、可见文案、端点引用 |
| `python` | `lvgl_ai` 顶层导出、`Runtime` / `Recording` 公开成员与签名、错误继承关系、`apps` 生命周期 interface |

参考快照：`core/tools/contract_snapshot.json`。它随仓库提交，后续票直接对比，
不要依赖某次会话的临时产物。

## 命令

所有命令从仓库根执行：

```bash
# 对比：用临时目录重新记录，与提交的契约快照逐项比较
python -I core/tools/contract_snapshot.py compare

# 差异同时写入文件（可选）
python -I core/tools/contract_snapshot.py compare --report <path>

# 重新记录契约快照（只在建立参考快照或契约经批准变化时使用）
python -I core/tools/contract_snapshot.py record
```

退出码：

- `0`：差异为空。
- `1`：存在差异；stdout 按 JSON 路径列出 `changed` / `missing` / `unexpected` / `length`。
- `2`：记录或读取失败（harness 错误）。

`compare` 会在系统临时目录创建独立 workspace，包含临时 `sessions/`、临时 repo、脚本化
engine 和 `127.0.0.1:0` 的 HTTP 服务；快照不包含绝对路径、时间、运行时生成的会话 ID 或
实际绑定端口。固定 fixture 值（例如页面探针的会话 ID）是契约的一部分。
两次 `record` 的字节必须完全一致。

## 记录与对比的边界

- 协议与会话两节用内置脚本化 engine 驱动 `Runtime`，记录的是 Python 控制层可见的
  命令/回执与证据契约；真实 C engine 的语义仍由全量测试（尤其 9.6 / 多版本集成测试）覆盖。
- `wait` / `wait frames` 回执的 `changed` 由真实 engine 的 adapter flush flag 产生：
  `core/engine/adapter_9x.c` 与 `core/engine/adapter_8x.c` 在 flush callback 设置同一
  `refresh_painted`，`core/engine/session.c` 汇总后写入回执；9.x / 8.x 边界相同，其它
  回执不带该字段。协议快照只冻结回执形状，真实语义由 `*IntegrationTest` 覆盖。
- `session` 同时记录普通录制与完整录制：前者是引擎和 `Runtime` 默认写出的文件集合；
  后者额外覆盖 `reference_diffs.ndjson`、`annotations.json` 与 `snapshots/` 的 manifest
  artifacts 映射。
- 页面一节通过真实 HTTP 路由取 HTML，只断言服务端渲染的 DOM 与文案；由 JS 在浏览器里
  动态生成的内容不在快照内，通过 HTTP 探针与全量测试间接覆盖。
- `python` 一节只记录公开名字与签名；内部 module 路径与类 MRO 名称不计入契约
  （错误继承关系按“能否被基类捕获”记录，改名保留别名时仍为零差异）。
- 文档、目录树本身不是运行时探针；它们由 `check_*` 工具和 `git status --short` 覆盖。
- 快照不是 pass/fail、approval 或像素判定；差异只是“外部行为发生变化”的证据。

## 每张后续票怎么用

开工前和交付前都运行 `compare`，差异必须为空。下表票号来自历史票据，只作历史
参考；**所有当前票**都要跑同一条命令，某节没列到不代表允许漂移。

| 票 | 重点节 | 关注点 |
| --- | --- | --- |
| 16 `apps` package | `http`、`python.apps` | `/api/apps*` 的状态码/JSON key/错误码；生命周期函数名与签名；回收站 `meta.json` 与布局 |
| 17 应用领域加固 | `http` | 创建、删除、恢复、永久删除、保护名单与 header/Content-Type 守卫 |
| 18 应用管理台 partial | `page` | 服务端渲染的 dialog 元素 id/class、可见文案、`/api/apps` 端点引用 |
| 19 `LiveSession` | `http`、`page` | live 路由状态码与 JSON key、`/api/live/stream` 帧头、页面 live 控件 |
| 20 回放模型 | `http`、`page`、`session` | 会话/时间线/diff/日志接口形状；回放页面文案与 id；模型 JSON 字段 |
| 21 标注事务 | `http`、`page`、`session` | 201/409/400 与错误码；标注表单 id；notes/regions 形状 |
| 22 `EngineLink` | `protocol` | 命令序列、回执形状、必填 ready/回执字段、`seq`、engine 参数 |
| 23 `SessionStore` | `session` | 文件集合、manifest 字段/artifacts、`Recording` 读取要求、`live.rgba` 生命周期 |
| 24 `BuildPlan` | `cli`、`protocol.engine_args` | `--json` build 错误退出码/字段；engine 启动参数；构建逻辑由全量测试覆盖 |
| 25 输入/错误词汇 | `protocol`、`cli` | 命令 token、必填回执字段、退出码映射 |
| 26 `adapter_common` | `protocol` | Python 可见命令/回执；C 侧语义由多版本测试覆盖 |
| 27 C session 编排 | `session`、`protocol` | 证据文件与行形状、命令/回执不变 |
| 28 目录契约 | `session`、`http` | 会话文件集合与回收站布局；目录本身由静态检查与全量测试覆盖 |
| 29 文档单一真源 | — | 快照不覆盖文档；用链接与静态检查工具 |
| 31 启动入口/端口探测 | `cli.web` | `web.py` 参数与帮助文本；端口探测逻辑不在快照内 |
| 32 命名清理 | 全部 | 顶层导出、别名、HTTP/CLI/协议/会话/页面必须逐项一致；内部 module 与 MRO 不计入 |
| 33 测试卫生 | 全部 | 改写测试后仍须零差异；测试只许改断言方式，不许改外部行为 |

## 差异出现时

1. 先看报告里的 JSON 路径，定位到具体契约（例如 `sections.http.probes[12].status`）。
2. 如果差异来自被重构模块的**外部行为**，修代码，不改快照。
3. 如果差异只是探针自身对实现的假设（例如内部函数改名），先确认该变化没有改变外部
   行为，再只调整探针；探针调整仍需保证 `record` 两次字节一致。
4. 契约变化不属于架构深化 spec；需要改契约时先停下来更新 SPEC 并单独评审，不要用
   `record` 覆盖快照来“修绿”。
