# user/app

用户代码目录，也是唯一的源码真源。`user/app/**/*.c` 会被构建系统递归收集并全部
编译，不需要写 `main`，也不需要改构建文件。

## 入口与注册

engine 调用 `app.c` 的 `void app_create(void)`。`app_create` 读取
`LVGL_VERIFY_LOOP_DEMO`（未设置时取 `apps[0]`），在 `apps[]` 表中查找并调用对应变体：

```c
#include "intro/intro.h"

static const app_entry_t apps[] = {
    {"intro", intro_create},
};
```

每个变体暴露统一的 `void <name>_create(void)`，内部用 `lv_screen_active()` 取
engine 已创建好的活动屏幕。未知名字会打印 `[app] apps=...` 后退出。

本包自带 `intro`：默认介绍页，也是默认模板，按 9.4+ 版本门编写。
9.1 / 8.x 不启用应用变体，只显示内置 harness。

## 选择方式

推荐让场景声明 `app`，CLI 和网页端都会自动应用：

```bat
bin\lvgl.cmd run --scenario user\scenarios\intro.json --json
bin\lvgl.cmd run --app <name> --idle
```

优先级：显式 `--app` > 场景 `app` > 环境变量 `LVGL_VERIFY_LOOP_DEMO` > `apps[0]`。
网页端顶部「应用」下拉从 `user/scenarios/*.json` 中声明了 `app` 的场景生成。

## 命名与证据

- 应用根用 `app_set_name("<name>")`，交互控件用 `app_obj_set_name(obj, "...")`
  命名；两者来自 `user/app/app.h`。
- 命名后 `timeline.ndjson` 的输入行会出现 `"hit": "..."`；9.1 / 8.x 没有对象名，
  `hit` 为空，只能看 `hit_class`。
- `manifest.json` 的 `app` 记录本次选择，`display` 记录实际宽高；`engine.log`
  中 `[app] apps=...` 与 `[app] app=...` 可核对注册和选择。
- 精确状态（checked / value / text / focus）只能用应用代码 `printf` 到
  `engine.log`，没有对象树或属性读取接口。

新增应用、资源生成与排错见 [GUIDE.md](GUIDE.md)。
