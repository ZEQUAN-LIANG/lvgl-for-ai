# user/app

用户代码目录，也是唯一的源码真源。engine 调用 `app.c` 的 `void app_create(void)`，
由它分发到各应用变体的 `void <name>_create(void)`；`user/app/**/*.c` 会被构建
递归收集并全部编译，不需要注册表，也不需要写 `main`。

> 发布包只带 `intro/` 一个应用；它同时是默认介绍页和默认模板。下表中的 coffee、
> xiaohongshu、spectrum、sift_watch、zombie_cannon、perf_monitor、test_ui、
> textarea_evidence 仅存在于开发仓库。

## 应用分类

开发仓库里的应用分三类，改代码前先确认目标：

| 类别 | 应用 | 用途 |
|---|---|---|
| 示例应用 | `coffee`、`xiaohongshu`、`spectrum`、`sift_watch`、`zombie_cannon`、`perf_monitor` | 演示完整界面与交互；优先从这里学写法 |
| 工具自测应用 | `test_ui`、`textarea_evidence` | 集成测试靶子（面板 + 按键 + 焦点组）与文本输入证据；不要随意改 |
| 发布应用 | `intro` | 发布包唯一应用，同时是默认介绍页与模板 |

`test_ui` 是普通应用，与其它应用一样由目录发现、用 `--app test_ui` 或场景的
`"app"` 字段选择；它**不会**被挂到别的应用上。集成测试用它做命中靶子
（按键在 (32,300)，中心 (112,324)），`settings.json` 因此声明了 `"app": "test_ui"`。

## 应用变体（app）

同一个入口可以承载多个应用变体。变体由构建扫描 `user/app/` 下的目录自动发现，
生成 `user/app/app_registry.inc`；选择通过 CLI `--app` 或场景顶层的 `"app"` 字段，
工具层再把它转发给 engine 的环境变量 `LVGL_VERIFY_LOOP_DEMO`（内部契约，正常不需要手设）。

| 应用 | 界面 | 版本 |
|---|---|---|
| `coffee`（开发仓库默认） | AURELIA C9 咖啡机 | 9.4+ |
| `xiaohongshu` | 小红书复刻 | 9.4+ |
| `spectrum` | ORBITAL 频谱播放器 | 9.4+ |
| `sift_watch` | 手表 OS，含 ZOMBIE 无尽尸潮 | 9.4+ / 导出 9.4 |
| `zombie_cannon` | 390x460 无尽尸潮独立预览 | 9.4+ |
| `perf_monitor` | 172x320 / 320x172 性能监控 + 串口布局切换 | 9.4+ |
| `intro` | 项目介绍页，发布包唯一应用与默认模板 | 发布包 9.4+ / 开发仓库 9.4+ |
| `test_ui`、`textarea_evidence` | 工具自测（集成测试靶子、文本输入证据） | 9.4+ |
| 9.1 / 8.x | 无应用发现，只显示空屏 | 9.1 / 8.x |

9.4 及以上都能选应用；9.1 与 8.x 没有目录发现注册表（`app.c` 的注册表门是 9.4），
所以既不显示应用也不挂任何测试界面。写跨版本应用时按 **9.4 基线**，用 `app.h` 的
`app_obj_set_*` / `app_obj_is_hidden` 包装代替 9.6 才有的 `lv_obj_set_clickable`
等专用 setter。

未知应用名会打印 `[app] apps=...` 后让 engine 退出，避免悄悄跑错界面。

## 选择方式

推荐让场景声明 app，CLI 与网页端都会自动应用：

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/intro.json
```

每个应用在 `user/scenarios/<name>.json` 都有对应场景（`ls user/scenarios/` 可看全）。
没有场景时用 `--app`；`--idle` 保持会话直到 Ctrl+C（headless）：

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --app intro --idle
```

网页端顶部「应用」下拉会列出 `user/scenarios/*.json` 中声明了 `app` 的选项；
第一个是默认值，打开页面即预览，选中其他应用立即切换，不需要重启。

## C 代码结构

每个应用暴露同一个签名，不接收对象：

```c
void <name>_create(void);
```

入口内部用 `lv_screen_active()` 取活动屏幕；应用根用 `app_set_name("<name>")` 命名，控件用 `app_obj_set_name(obj, "...")` 命名。

应用目录默认不需要任何元数据文件：**目录名就是应用名**，入口按约定推导为
`void <name>_create(void)`。构建时自动生成 `app_registry.inc`：

```c
void coffee_create(void);          /* user/app/coffee/coffee_page.c */
```

`app.c` 只包含生成文件并做查找，不维护中心 `apps[]` 表。只有入口名偏离约定时才
需要在该目录放 `app.json` 写 `"entry"`（当前仓库没有这种应用）。

跨应用的约束放在根级 `user/app/app.json`——目前只有默认应用一项：

```json
{
  "default": "coffee"
}
```

`"default"` 指定的应用排在 `apps[0]`，也就是未显式选择时的默认应用；未设置时按
应用名排序取第一个。加删应用不需要改这个文件。

## 新增一个应用

完整可运行教程（含示例代码、场景、证据与排错）见 [GUIDE.md](GUIDE.md)。

快速路径：

```bash
python -I scripts/new_app.py <name> --dry-run   # 先看计划
python -I scripts/new_app.py <name>             # 生成目录、源文件和场景
```

脚本只写应用自己的目录和场景，不改 `app.c` 或其他共享文件。生成后仍需源码构建；
预编译 engine 不含新应用。

网页端也可以从顶部「应用管理」完成新建、预览、删除和恢复。删除会把应用目录和
所有关联场景移进 `user/.trash/apps/<trash-id>/`；回收站里可以恢复，再次确认后
才会永久删除。只有根级 `user/app/app.json` 指定的默认应用受保护。

手工步骤：

1. 新建 `user/app/<name>/`，实现 `void <name>_create(void)`；入口内用 `lv_screen_active()` 取屏幕。
2. 不需要元数据文件——目录名就是应用名，入口按约定推导。只有入口名不叫 `<name>_create` 时，才在该目录写 `app.json` 的 `"entry"`。
3. 在 `user/scenarios/<name>.json` 顶层写 `"app": "<name>"`。
4. 需要非默认分辨率时，再写可选 `"display": {"width": W, "height": H}`（`1..4096`）；
   省略时使用引擎默认 800×600。尺寸在 engine 启动时传入，不需要重新编译。
5. 不需要改 `console/` 或 `user/app/app.c`：CLI、web 下拉和构建都按目录自动发现。

## 证据

- `manifest.json` 的 `app` 字段记录本次会话选择的应用（未指定时为 `null`），
  `display` 记录实际宽高（启动失败时为 `null`）。
- `engine.log` 中 `[app] apps=...` 列出已实现的应用，`[app] app=...` 记录本次选择。
- `settings.json` 声明 `"app": "test_ui"`：它点 (112,324) 命中该应用的按键，
  是集成测试与旧版本发布冒烟共用的场景。
