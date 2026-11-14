# 写一个应用变体

本文只讲把界面代码写进 `user/app/` 的最小闭环。按版本的 API 细节见
`core/api-nav/<version>.md`；工具与证据的完整约定见包根 `SKILL.md`。

命令从包根执行。改过 C 代码后必须重新构建，`--no-build` 只复用当前 engine。

## 1. 最小示例

示例 `hello`：深色背景、标题、一个按钮，点击后状态文字变化，并把状态写进
`engine.log`。

### 1.1 头文件

`user/app/hello/hello.h`

```c
#ifndef HELLO_H
#define HELLO_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4
void hello_create(void);
#endif

#endif /* HELLO_H */
```

版本门必须加：`user/app/**/*.c` 对所有 LVGL 版本都会编译，9.1 / 8.x 不启用应用
变体。

### 1.2 实现

`user/app/hello/hello.c`

```c
#include "hello.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4

#include "app.h"

#include <stdio.h>

static void hello_click_cb(lv_event_t * event)
{
    lv_obj_t * status = lv_event_get_user_data(event);
    lv_label_set_text(status, "clicked");
    printf("[hello] clicked\n");
}

void hello_create(void)
{
    lv_obj_t * screen = lv_screen_active();
    app_set_name("hello");
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101318), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    lv_obj_t * title = lv_label_create(screen);
    lv_label_set_text(title, "HELLO");
    lv_obj_set_style_text_font(title, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(title, lv_color_hex(0xE6E8EB), 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 24);
    app_obj_set_name(title, "hello_title");

    lv_obj_t * status = lv_label_create(screen);
    lv_label_set_text(status, "waiting");
    lv_obj_set_style_text_color(status, lv_color_hex(0x9AA3AD), 0);
    lv_obj_align(status, LV_ALIGN_CENTER, 0, 48);
    app_obj_set_name(status, "hello_status");

    lv_obj_t * button = lv_button_create(screen);
    lv_obj_set_size(button, 160, 48);
    lv_obj_align(button, LV_ALIGN_CENTER, 0, 0);
    app_obj_set_name(button, "hello_button");

    lv_obj_t * button_label = lv_label_create(button);
    lv_label_set_text(button_label, "CLICK");
    lv_obj_center(button_label);
    app_obj_set_name(button_label, "hello_button_label");

    lv_obj_add_event_cb(button, hello_click_cb, LV_EVENT_CLICKED, status);

    printf("[hello] created\n");
}

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 4 */
```

要点：

- 入口签名是 `void <name>_create(void)`，不接收对象；用 `lv_screen_active()` 取
  engine 已创建好的活动屏幕，不要自己初始化 LVGL。
- `app_set_name()` 命名当前 screen，`app_obj_set_name()` 命名控件；两者来自
  `user/app/app.h`。9.2+ 才有对象名，命名后 timeline 的 `hit` 才会显示名字。
- `printf` 进入会话的 `engine.log`；需要立即看到时加 `fflush(stdout)`。
- 所有应用变体编译进同一个二进制：非 `static` 全局符号要加应用前缀。

### 1.3 注册

在 `user/app/app.c` 顶部 include，并在现有 `apps[]` 表里追加一行：

```c
#include "hello/hello.h"

static const app_entry_t apps[] = {
    /* ... existing entries ... */
    {"hello", hello_create},
};
```

名字必须与场景里的 `"app": "hello"` 完全一致。

### 1.4 场景

`user/scenarios/hello.json`

```json
{
  "schema": "lvgl-ai-scenario-v1",
  "name": "hello",
  "app": "hello",
  "steps": [
    {"type": "wait", "ms": 100},
    {"type": "mark", "id": "start"},
    {"type": "snapshot", "label": "start"},
    {"type": "click_at", "x": 400, "y": 300},
    {"type": "wait", "ms": 100},
    {"type": "mark", "id": "clicked"},
    {"type": "snapshot", "label": "clicked"}
  ]
}
```

场景不是构建必需，但顶层 `"app"` 决定选哪个变体，steps 提供可重复输入，
`mark` / `snapshot` 给证据加锚点。可选 `"display": {"width": W, "height": H}`
覆盖默认 800×600；尺寸在 engine 启动时传入，不需要重新编译。

## 2. 运行与预览

```bat
:: 跑场景；改过 C 后加 --build
bin\lvgl.cmd run --build --scenario user\scenarios\hello.json --json

:: 网页端
bin\lvgl.cmd serve
```

网页端打开 `http://127.0.0.1:8765/`，顶部「应用」下拉会列出
`user/scenarios/*.json` 中声明了 `app` 的应用；选中即切换预览。

CLI 也支持 `--app hello --idle`（无场景，保持会话到 Ctrl+C）和 `--json`
（stdout 只有一行摘要）。

## 3. 资源

字体和图片用内置转换器生成 C 数组，不需要 Node.js 或联网：

```bat
bin\lvgl.cmd assets font --app hello --font C:\Windows\Fonts\Deng.ttf ^
  --size 24 --bpp 4 --scan-app --name hello_font_24

bin\lvgl.cmd assets image --app hello --input user\app\hello\logo.png --cf ARGB8888
```

```c
#include "hello_font_24.h"
#include "logo.h"

lv_obj_set_style_text_font(label, &hello_font_24, 0);
lv_image_set_src(image, &logo);
```

- 资源头和源码同目录；`assets.json` 记录字体路径、字号、bpp、字符集和图片
  SHA256，便于重放。
- `--scan-app` 收集应用字符串字面量里的字形；动态文本用 `--text-file` 或
  `--text`，中文优先用 `--text-file`。
- 图片支持 `RGB565`、`ARGB8888`、`RGB888`、`A8`；`--cf auto` 按 alpha 自动选择。
- 资源编译进二进制，不要依赖从磁盘读 PNG；大图会占用 LVGL heap（默认 16 MiB）。

## 4. 常用能力

### 事件

```c
static void on_click(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    printf("[myapp] clicked\n");
}

lv_obj_add_event_cb(button, on_click, LV_EVENT_CLICKED, NULL);
```

常见事件：`LV_EVENT_CLICKED`、`LV_EVENT_VALUE_CHANGED`（slider / switch /
dropdown）、`LV_EVENT_PRESSING` / `LV_EVENT_RELEASED`（拖拽）。场景里的
`click_at` 和 `drag` 最终都是真实 pointer 事件。

### 定时器与动画

```c
static void tick_cb(lv_timer_t * timer)
{
    (void)timer;
    /* 每 16 ms 更新一次 */
}

lv_timer_create(tick_cb, 16, NULL);
```

时间来自虚拟时钟：场景的 `wait`、`tick`、live ticker 推进它，不是墙钟。
`lv_anim` 同样由 `lv_timer_handler` 驱动。不要在回调里阻塞等待。

### 多文件拆分

`user/app/**/*.c` 会递归收集并全部编译，可以按 `page.c` / `ui.c` / `model.c`
拆分；`app.c` 只需要 include 各应用的入口头文件。

## 5. 约束与排错

| 约束 | 说明 |
|---|---|
| 只改用户目录 | `user/app/**/*.c`（含应用自己的资源头）与 `user/scenarios/` |
| 不写 `main` | engine 负责初始化、tick、刷新和退出 |
| 版本门 | 只在 9.4+ 使用的代码必须放进版本门，否则 9.1 / 8.x 构建会失败 |
| 未知应用名会退出 | engine 打印 `[app] apps=...` 后 `exit(1)` |
| 改过 C 不能用 `--no-build` | 预编译 engine 是旧产物 |
| 没有对象树 / `inspect` / `set` | 精确状态只能在自己的 C 代码里 `printf` |

| 现象 | 先检查 |
|---|---|
| 网页下拉里没有新应用 | `user/scenarios/<name>.json` 是否存在、JSON 是否合法、顶层是否有 `app` |
| engine 启动即退出，日志有 `unknown app=` | `apps[]` 名字与场景 `app` 是否完全一致 |
| `build_error` | `sessions/<id>/build.log`；常见是 include 路径、版本门漏了、9.6 不存在的 API |
| `link_error` | 声明了 `<name>_create` 但没有定义，或版本门把定义排除了 |
| `harness_error` | 场景字段拼写、未知字段、类型不匹配 |
| 画面空白 | 看 `snapshots/`；确认控件创建在 screen 上、尺寸非零、没有被父对象裁剪 |
| 点击没反应 | 坐标是否在控件内、控件是否 clickable、是否被上层对象盖住；看 timeline 的 `hit` |
| 改了代码画面没变 | 是否误用 `--no-build`；构建是否失败后回退到旧二进制 |

## 6. 提交前检查清单

- [ ] 源文件在 `user/app/<name>/`，入口签名是 `void <name>_create(void)`
- [ ] `user/app/app.c` 有 include 和 `apps[]` 注册行
- [ ] 只在 9.4+ 使用的代码有版本门
- [ ] 全局符号带应用前缀或为 `static`
- [ ] 交互控件已 `app_obj_set_name`，应用根已 `app_set_name`
- [ ] `user/scenarios/<name>.json` 顶层写了 `"app": "<name>"`
- [ ] 构建成功，`manifest.json` 的 `status` 为 `ok`
- [ ] `engine.log` 有预期状态，`timeline.ndjson` 的 `hit` 指向预期控件
