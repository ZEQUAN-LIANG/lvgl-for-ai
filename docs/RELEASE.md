# 发布 runbook

维护者发布 skill 版本的操作顺序。每一步都给判定条件，判定不过就停下来修，不要继续往下走。

发布对象是 Claude Code skill 的两个 zip：`full` 与 `full-sifli`。发布渠道是 Gitee（真源）
与 GitHub（镜像），两边都上传同一份 zip。

## 前置条件

- 工作树干净（`git status` 无未提交改动），当前在 `dev`。
- `GITHUB_TOKEN` 与 `GITEE_TOKEN` 在环境里（脚本只读环境变量，不读文件、不提示）。
- 有 GCC（MinGW-w64 64-bit 15.2.0，与 `dist/lvgl/*/manifest.json` 一致）；从源码构建还需要
  CMake 3.20+ 与 Ninja。
- `scripts/publish_check.py` 会把「版本号一致性 → 构建 → 验证」串成一条命令；本页每一步
  对应的裸命令也列出来，便于分段执行。

## 1. 定版本号并改齐

版本号真源是 `console/paths.py` 的 `TOOL_VERSION`。改一处不够，下列位置必须同步：

| 位置 | 说明 |
| --- | --- |
| `console/paths.py` | 真源 `TOOL_VERSION` |
| `scripts/meta/versions.json` | `tool.version` |
| `scripts/tests/tools/test_repo_contract.py` | 断言 `TOOL_VERSION` 的常量 |
| `scripts/tests/tools/test_contract_snapshot.py` | 断言快照 `tool_version` 的常量 |
| `scripts/contract_snapshot.json` | 只改 `paths.tool_version` 这一个真值，不要重录快照 |
| `README.md` / `README.zh-CN.md` | 安装指引里的 zip 文件名与版本号 |
| `CLAUDE.md` | `upload_release.py --version` 示例 |

改完自查：

```bash
python -I scripts/publish_check.py --stage version --json
```

这一步会校验上述位置是否一致，并把 `git grep` 的结果与白名单比对，列出漏改或多改。
**不要把 `user/app/perf_monitor/` 里的 `generator` 字段改掉**：那是资源生成时的历史
溯源标记，`assets doctor` 与测试都不校验它，改它反而是伪造记录。

## 2. 回归

```bash
python -I scripts/verify.py --json
```

它依次跑 lint、契约快照比对、全量测试（`--tier all`，约 941 个）与发布包冒烟
（解包后跑 `run` / `report` / `assets doctor`）。判定：退出码 0 且 `ok` 为 true。
覆盖率不够时单独看：

```bash
python -I scripts/tests/run_tests.py --tier all
python -I scripts/contract_snapshot.py compare      # 期望 differences: 0
```

## 3. 构建发布包

```bash
python -I scripts/release_all.py --out dist/release --json
```

产出（在 `dist/release/`）：

- `lvgl-verify-loop-<版本>-full-win64.zip` 与 `.sha256`、`.release.json`
- `lvgl-verify-loop-<版本>-full-sifli-win64.zip` 与 `.sha256`、`.release.json`
- `release.json`（总清单）

构建在 engine 源码、`user/app`、宿主 SDK manifest 与 GCC 版本摘要未变时复用
`dist/release/lvgl_<token>/` 的预编译 engine，只重新打包。要强制重建加 `--force-build`。

发布包内已内置 `smoke_package()` 冒烟：`--no-build` 与 `--prebuilt` 两条路径各跑一次
`intro.json`、`bin/lvgl.cmd run`、`assets doctor` 与 `serve` 起来取一次 URL。冒烟失败即构建失败。

## 4. 校验发布包

```bash
python -I scripts/publish_check.py --stage package --json
```

解包两个 zip，校验：

- 包根只有 `SKILL.md` 一个文件（另有 `api-nav/` 等目录）；
- 关键目录齐全（`console/`、`engine/`、`user/app/`、`user/scenarios/`、`scripts/`、
  `bin/lvgl.cmd`、`dist/lvgl/`、`build/`、`docs/licenses/`）；
- 不该有的目录不存在（`engine/lvgl/`、`engine/third_party/`、`smoke/`）；
- 包内 `scripts/meta/VERSION.json` 的 `tool_version` 等于本次版本号；
- 包内 `SKILL.md` 与 `docs/skill/SKILL.md` 内容一致。

## 5. 真实安装验证（skill 整体流程）

把 zip 解到真实的 skill 安装位置，用 skill 入口跑一轮完整用户流程。这一步是唯一能证明
「用户拿到包真的能用」的检查，前四步都替代不了它：

```bash
python -I scripts/publish_check.py --stage install --json
```

它会：

1. 把 `%USERPROFILE%\.claude\skills\lvgl-verify-loop`（如果存在）整体移到
   `%TEMP%\lvgl-verify-loop-skill-backup\` 下带时间戳的目录。**备份必须放在 skills 目录
   之外**：留在 `skills/` 里的任何目录都会被 Claude Code 当成第二个 skill 扫出来；
2. 解压 `full` 包到 `skills\lvgl-verify-loop\`；
3. 从包根跑 `console/entrypoints/cli.py --scenario user/scenarios/intro.json --json`，
   等价于 `bin\lvgl.cmd run`；
4. 跑 `console/entrypoints/session_report.py --latest --log-tail 3` 与
   `console/entrypoints/assets_tool.py doctor --json`；
5. 校验会话目录里有 `manifest.json`、`timeline.ndjson`、`frames/`，manifest 的
   `status` 是 `ok`，且 `tool_version` 与本次版本一致；
6. 通过后删掉备份、保留新装版本；任何一步失败就删掉新装目录并从备份还原。

`--keep-backup` 保留备份目录便于回滚；默认删除。

## 6. 打 tag 并推送

```bash
git add -A && git commit -m "release: lvgl-verify-loop 0.2.3"
git tag -a v0.2.3 -m "lvgl-verify-loop 0.2.3"
git push origin dev
git push origin v0.2.3
```

历史惯例：`v0.2.0` / `v0.2.1` / `v0.2.2` 都打在 `dev` 上，线上 Release 的 target 也是 `dev`。
tag 名是 `v<版本号>`。

## 7. 发布到 Gitee

```bash
python -I scripts/upload_release.py --version 0.2.3 --replace --json
```

- 只读 `GITEE_TOKEN` / `GITHUB_TOKEN`。
- 资产清单来自 `dist/release/release.json`：两个 zip + 两个 `.sha256` + `release.json`。
- `--replace` 删除同名旧资产再上传；不加则同名跳过。
- 不传 `--notes-file` 时保留线上 Release 正文；要写正文就先放
  `dist/release/RELEASE_NOTES.md` 或传 `--notes-file`。
  **注意时序**：`release_all.py` 的清理阶段会删掉 `dist/release/RELEASE_NOTES.md`，
  所以它必须在第 3 步构建**之后**写，否则会被无声清掉。
- 只看 Gitee：`--target gitee`。

判定：`--json` 输出里 `gitee` 字段是 Release 页面 URL，且页面上有 5 个资产。

## 8. 镜像到 GitHub

```bash
python -I scripts/sync_github.py --dry-run
python -I scripts/sync_github.py
```

它把 `origin`（Gitee）的分支与 **所有** tag 强推到 `github`。注意：

- 分支用 `--force-with-lease`，tag 用 `--force`。这是一次**覆盖式镜像**，GitHub 侧
  独有的分支或 tag 会被丢掉。
- 上一步已经在 GitHub 建过 Release 也没关系：tag 被更新后 Release 仍指向同名 tag。

判定：输出 `synced <N> branches and <M> tags`，且 `git ls-remote --heads github` 的
`dev` 与本机 `origin/dev` 同一个 commit。

## 9. GitHub 发布 Release

```bash
python -I scripts/upload_release.py --version 0.2.3 --target github --replace --json
```

与第 7 步同一个脚本、同一份资产，只是打到 GitHub。新 Release 会自动创建，`target_commitish`
默认 `dev`。正文与 Gitee 用同一份 `RELEASE_NOTES.md`。

## 10. 收尾核对

两边页面都要有：两个 zip、两个 `.sha256`、一个 `release.json`，且 zip 的 sha256 与本地一致。

```bash
python -I scripts/publish_check.py --stage remote --json
```

它对比 Gitee 与 GitHub 两个 Release 的资产名集合与大小，并复核本地 zip 的 sha256。

## 回滚

- 包有问题：删掉线上 Release 的资产并重发（`--replace`），或直接删除该 Release；
  tag 要用 `git push --delete` + 重新打。
- 安装验证把旧 skill 弄坏了：用第 5 步留下的备份目录还原。
- GitHub 被镜像覆盖掉了不该覆盖的分支：从 `origin` 重新取回正确内容，或从本地备份分支恢复。
  **强推不可自动恢复**，执行第 8 步前先跑 `--dry-run`。

## 与其它文档的分工

- 本页：维护者发版顺序与判定条件。
- `CLAUDE.md`：AI 代理在本仓库的工作说明（命令索引、架构、硬约束）。
- `console/README.md`：工具用法、环境准备、常见错误。
- `docs/skill/SKILL.md`：skill 的入口契约（发布出去的用户侧工作流）。
