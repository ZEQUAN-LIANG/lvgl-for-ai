# user/app

用户代码目录。入口固定为 `void app_create(void)`；`user/app/**/*.c` 会被 CMake
递归收集并全部编译，不需要注册表，也不需要写 `main`。

> 发布包只带 `intro/` 一个应用；它同时是默认介绍页和默认模板。下表中的 coffee、
> xiaohongshu、spectrum、sift_watch、zombie_cannon、textarea_evidence 仅存在于
> 开发仓库。

## 应用分类

开发仓库里的应用分三类，改代码前先确认目标：

| 类别 | 应用 | 用途 |
|---|---|---|
| 示例应用 | `coffee`、`xiaohongshu`、`spectrum`、`sift_watch`、`zombie_cannon` | 演示完整界面与交互；优先从这里学写法 |
| 工具自测应用 | `asset_probe`、`textarea_evidence`、`demo/` | 资源转换探针、文本输入证据与旧版本 harness；集成测试依赖，不要随意改 |
| 发布应用 | `intro` | 发布包唯一应用，同时是默认介绍页与模板 |

`demo/` 不在 `apps[]` 表里：它由 `app_create` 在 LVGL 9.1 / 8.x 或集成测试路径下直接挂载。

## 应用变体（app）

同一个入口可以承载多个应用变体。`LVGL_AI_DEMO` 环境变量是用户代码与工具之间的契约：

| 值 | 界面 | 版本 |
|---|---|---|
| `coffee`（默认） | AURELIA C9 咖啡机，`coffee/` | LVGL 9.6 |
| `xiaohongshu` / `xhs` | 小红书复刻，`xiaohongshu/` | LVGL 9.6 |
| `spectrum` | ORBITAL 频谱播放器，`spectrum/` | LVGL 9.6 |
| `sift_watch` | 390x450 像素手表 OS，含 ZOMBIE 无尽尸潮应用，`sift_watch/` | LVGL 9.6 / 导出 9.4 |
| `zombie_cannon` | 390x460 无尽尸潮独立预览，`zombie_cannon/` | LVGL 9.6 |
| `asset_probe` | 资源转换探针（工具自测），`asset_probe/` | 9.6 / 9.1 / 8.x |
| `textarea_evidence` | 文本输入证据应用（工具自测），`textarea_evidence/` | LVGL 9.6 |
| `intro` | 项目介绍页，发布包唯一应用与默认模板，`intro/` | 发布包 9.4+ / 开发仓库 9.6 |
| 未设置 | `coffee`（开发仓库） / `intro`（发布包） | LVGL 9.6 |
| 任意值 | 旧版本忽略选择，显示 `demo/` 的 harness | 9.1 / 8.x |

未知的 `LVGL_AI_DEMO` 会打印可用值并让 engine 退出，避免悄悄跑错界面。

## 选择方式

推荐让 scenario 声明 app，CLI 会自动应用：

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/intro.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/xiaohongshu.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/spectrum.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch_zombie.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/zombie_cannon.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/zombie_cannon_ai.json
```

没有 scenario 时用 `--app`；`--idle` 保持会话直到 Ctrl+C（headless）：

```bash
python -I core/cli.py --lvgl 9.6 --app intro --idle
python -I core/cli.py --lvgl 9.6 --app coffee --idle
python -I core/cli.py --lvgl 9.6 --app xiaohongshu --idle
python -I core/cli.py --lvgl 9.6 --app spectrum --idle
python -I core/cli.py --lvgl 9.6 --app sift_watch --idle
python -I core/cli.py --lvgl 9.6 --app zombie_cannon --idle
```

网页端顶部「应用」下拉会列出 `user/scenarios/*.json` 中声明了 `app` 的选项；
第一个应用是默认值，打开页面就自动预览它；选中其他应用立即切换，不需要再点
「测试」，也不需要重启 `web.py`。

`LVGL_AI_DEMO` 仍可直接设置；显式 `--app` 优先于 scenario，scenario 优先于继承的环境变量。

## C 代码结构

每个应用暴露同一个签名，不接收对象：

```c
void <name>_create(void);
```

入口内部用 `lv_screen_active()` 取活动屏幕；应用根用 `app_set_name("<name>")` 命名，控件用 `app_obj_set_name(obj, "...")` 命名。

`app.c` 用 `apps[]` 表把名字映射到函数：

```c
static const app_entry_t apps[] = {
    {"coffee", coffee_create},
    {"xiaohongshu", xhs_page_create},
};
```

`apps=...` 日志由这张表生成，查找、默认值和未知值处理也只走这一处。

## 新增一个应用

完整可运行教程（含示例代码、场景、证据与排错）见 [GUIDE.md](GUIDE.md)。

快速路径：

```bash
python -I core/tools/new_app.py <name> --dry-run   # 先看计划
python -I core/tools/new_app.py <name>             # 生成并注册
```

脚本会创建源文件、头文件、场景，并在 `user/app/app.c` 加上 include 和 `apps[]` 一行。
生成后仍需源码构建；预编译 engine 不含新应用。

网页端也可以从顶部「应用管理」完成新建、预览、删除和恢复。删除会先把应用目录、
所有关联场景和注册移出，放进 `user/.trash/apps/<trash-id>/`；回收站里可以恢复，
再次确认后才会永久删除。`coffee`、`xiaohongshu`、`spectrum` 等内置应用受保护。

手工步骤：

1. 新建 `user/app/<name>/`，实现 `void <name>_create(void)`；入口内用 `lv_screen_active()` 取屏幕。
2. 在 `app.c` 的 `apps[]` 中加一行 `{"<name>", <name>_create}`。
3. 在 `user/scenarios/<name>.json` 顶层写 `"app": "<name>"`。
4. 需要非默认分辨率时，再写可选 `"display": {"width": W, "height": H}`（`1..4096`）；
   省略时使用引擎默认 800×600。尺寸在 engine 启动时传入，不需要重新编译。
5. 不需要改 `core/`：CLI、web 下拉和 manifest 都按这些字段工作。

## 证据

- `manifest.json` 的 `app` 字段记录本次会话选择的应用（未指定时为 `null`），
  `display` 记录实际宽高（启动失败时为 `null`）。
- `engine.log` 中 `[app] apps=...` 列出已实现的应用，`[app] app=...` 记录本次选择。
- `settings.json` 不声明 `app`，走用户代码默认值，并保留隐藏的 `demo_button` 供工具测试使用。
