# 写一个应用变体：完整流程

本文回答三件事：要生成什么、每一步做什么、这条路径复不复杂。示例代码已在本仓库用
LVGL 9.6 真实构建并跑过场景；照抄可以复现。

命令一律在**仓库根**执行，统一使用 `python -I`。

## 0. 先看结论

### 0.1 要生成什么

| 产物 | 必需 | 位置 | 作用 |
|---|---|---|---|
| C 源文件 | 是 | `user/app/<name>/<name>.c` | 界面实现 |
| 注册行 | 是 | `user/app/app.c` 的 `apps[]` | 让 `LVGL_AI_DEMO` 找到这个变体 |
| 场景 | 强烈建议 | `user/scenarios/<name>.json` | 声明 `app`，提供可重复的输入与快照 |
| 头文件 | 可选 | `user/app/<name>/<name>.h` | 多文件拆分，或给 `app.c` 提供声明 |
| 资源头 | 可选 | `user/app/<name>/` 或 `user/asset/` | 字体、图片编译进二进制 |

**不需要**写 `main`、`CMakeLists.txt`、改 `core/`、改 `lvgl-src/`，也不需要维护第二份应用清单。

### 0.2 复杂吗

工具链部分不复杂：一个 `.c`、一行注册、一个场景，构建和运行都是现成的。

| 目标 | 需要新增 | 大致工作量 |
|---|---|---|
| 单屏静态界面 | 1 个 `.c` + 1 行 + 1 个场景 | 30–60 分钟 |
| 多屏、列表、表单 | 2–5 个 `.c`，事件与状态管理 | 半天到数天 |
| 自定义字体/图片 | 生成头文件并 include | 取决于素材准备 |
| 动画、canvas、频谱一类效果 | `lv_timer` / `lv_anim` / canvas | 取决于效果本身 |

真正的复杂度来自 LVGL 界面本身和素材，不来自这个仓库的路径。唯一的额外约束是：
**所有应用变体编译进同一个二进制**，所以新增代码要避免符号冲突，并对旧版本加版本门。

---

## 1. 最小可运行示例

### 1.0 用脚手架生成（可选）

下面的代码可以手工创建，也可以让脚本一次生成源文件、头文件、场景，并自动注册到
`user/app/app.c`：

```bash
# 先看计划，不写文件
python -I core/tools/new_app.py hello --dry-run --json

# 生成并注册；--force 用于覆盖已生成的同名文件
python -I core/tools/new_app.py hello
```

脚本只生成骨架，业务界面仍要自己写。它不构建；生成后按 2.2 或 2.1 走源码构建。
名字必须是 `^[a-z][a-z0-9_]{0,31}$`，且不能与现有应用或场景重名。

双击仓库根 `open-web.vbs` 打开普通页面后，点顶部「应用管理」；也可以运行
`python -I core/web.py --manage --open` 在启动时直接打开管理对话框。管理台可以
新建、预览、删除和恢复。删除会移到 `user/.trash/apps/<trash-id>/`；内置应用受保护，
永久删除需要再次确认。

下面仍完整列出等价的手工步骤，便于理解脚本改了什么。示例会创建一个 `hello` 变体：
深色背景、标题、一个按钮，点击后状态文字变化，并把状态写进 `engine.log`。

### 1.1 头文件（推荐）

`user/app/hello/hello.h`

```c
#ifndef HELLO_H
#define HELLO_H

#include "lvgl.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6
void hello_create(void);
#endif

#endif /* HELLO_H */
```

版本门必须加：`user/app/**/*.c` 对所有 LVGL 版本都会编译，9.1 / 8.x 不启用应用变体。

### 1.2 实现

`user/app/hello/hello.c`

```c
#include "hello.h"

#if LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6

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

#endif /* LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 6 */
```

要点：

- 入口签名是 `void <name>_create(void)`，不接收 `lv_obj_t *`；用 `lv_screen_active()` 取 engine 已创建好的活动屏幕，直接往上加控件，不要自己初始化 LVGL。
- `app_set_name()` 命名当前 screen；`app_obj_set_name()` 命名具体控件。两者都来自 `user/app/app.h`，`app.c` 已把 `user/app` 加入 include 路径。
  9.2+ 才有对象名；命名后 timeline 的 `hit` 才会显示 `hello_button`。
- `printf` 走 engine 的 stdout，会进入会话的 `engine.log`。需要立即看到时加
  `fflush(stdout)`，尤其是崩溃前。
- 非 `static` 的全局符号会让所有应用变体共享一个二进制，命名加应用前缀或使用 `static`。

### 1.3 注册

`user/app/app.c` 改两处。

顶部 include：

```c
#include "coffee/coffee_ui.h"
#include "xiaohongshu/xhs_page.h"
#include "spectrum/spectrum.h"
#include "hello/hello.h"
```

`apps[]` 加一行：

```c
static const app_entry_t apps[] = {
    {"coffee", coffee_create},
    {"xiaohongshu", xhs_page_create},
    {"spectrum", spectrum_create},
    {"hello", hello_create},
};
```

名字必须与场景里的 `"app": "hello"` 完全一致。别名只有 `xhs` → `xiaohongshu` 一处，
不要为自己的应用另加别名逻辑。

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

场景不是构建必需，但它承担三件事：

1. 顶层 `"app"` 让 CLI 和网页端知道选哪个应用变体。
2. 把点击、拖拽、等待写成可重复的输入。
3. `mark` / `snapshot` 给证据加锚点。

顶层还可以选 `"display"` 声明屏幕尺寸：

```json
"display": {"width": 640, "height": 480}
```

不写时使用引擎默认 **800×600**；宽高是 `1..4096` 的整数。尺寸在 engine 启动时传入，
改分辨率不需要重新编译 engine，但应用布局必须按该尺寸编写。网页顶部「应用」下拉会
跟随该应用对应场景的 `display`；同一应用有多个场景时取文件名字典序第一个，CLI 不受
此限制。示例按钮 160×48 居中，在默认 800×600 下中心点是 `(400, 300)`。`click_at` 默认
按下 64 ms 再抬起；坐标就是屏幕逻辑像素。

---

## 2. 运行与预览

### 2.1 网页端（推荐）

```bash
python -I core/web.py
```

打开 `http://127.0.0.1:8765/`。也可以直接指定应用，页面会预选并自动以测试模式预览：

```bash
python -I core/web.py --app hello --open

# 直接打开应用管理对话框
python -I core/web.py --manage --open
```

顶部「应用」下拉会从 `user/scenarios/*.json` 中声明了
`app` 的文件生成选项，选中 `hello` 即开始测试模式预览。改代码后重新运行命令并重新
选择即可；页面预览来自运行时 framebuffer，不是重实现的渲染器。

Windows 无控制台入口：

```text
双击 core/web.pyw
```

### 2.2 CLI

```bash
# 跑场景；默认 --build，会重新编译 user/app
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/hello.json

# 机器可读摘要：stdout 只有一行 JSON
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/hello.json --json

# 只保留画面变化的帧
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/hello.json --record-changed-only

# 没有场景时直接选应用；--idle 保持会话到 Ctrl+C
python -I core/cli.py --lvgl 9.6 --app hello --idle
```

选择优先级：显式 `--app` > 场景的 `app` > 环境变量 `LVGL_AI_DEMO` > `apps[0]`（当前是
`coffee`）。

### 2.3 看证据

会话写在 `sessions/<id>/`：

| 文件 | 看什么 |
|---|---|
| `manifest.json` | `status` 是否为 `ok`、`app` 是否为 `hello`、`display` 与 `frame_count` |
| `engine.log` | `[app] apps=...`、`[app] app=hello`、你自己的 `[hello] ...` |
| `timeline.ndjson` | 输入行的 `hit` / `hit_class`，例如 `hit: "hello_button"` |
| `snapshots/` | `mark` / `snapshot` 对应的命名画面 |
| `frames/` | 每个保留帧的完整 PNG |

工具不判定画面对错，只提供证据。验收标准由人在聊天里给。

---

## 3. 工具负责什么，你负责什么

| 工具负责 | 你负责 |
|---|---|
| 构建 `user/app/**/*.c`，链接 LVGL | 控件树、布局、样式 |
| 启动 engine、初始化 LVGL、显示与刷新 | 事件回调与状态 |
| 虚拟 pointer / keypad / encoder | 定时器、动画、canvas |
| 录帧、timeline、frame diff、快照 | 字体、图片、素材生成 |
| 会话、回放、网页预览、实时帧流 | 需要精确状态时自己 `printf` |

所以新增应用时不用碰构建系统。真正要写的是 LVGL 代码。

---

## 4. 常用能力速查

### 4.1 屏幕与布局

- 默认屏幕 800×600，32 位色，LVGL heap 16 MiB；场景顶层 `display` 可覆盖（`1..4096`）。
- 非默认尺寸时用 `lv_display_get_horizontal_resolution()` /
  `lv_display_get_vertical_resolution()` 读取实际宽高再布局，不要写死 800×600。
- 使用 `--reference` 时，参考 PNG 必须与本次会话的分辨率一致。
- 用 `lv_obj_set_pos` / `lv_obj_set_size` / `lv_obj_align` 做绝对布局，或用 `LV_USE_FLEX`
  / `LV_USE_GRID` 做弹性布局。
- 控件默认继承父对象；先创建父容器，再创建子控件。
- 画布类效果用 `lv_canvas`；参考 `user/app/spectrum/`。

### 4.2 字体

`core/engine/lv_conf.h` 默认只开启：

- `lv_font_montserrat_14`（默认字体）
- `lv_font_montserrat_16`
- `lv_font_montserrat_20`

其他字号或字形需要自己生成 C 头文件，例如：

```c
#include "my_font_24.h"   /* 由 lv_font_conv 生成，声明 const lv_font_t */

lv_obj_set_style_text_font(label, &my_font_24, 0);
```

生成的头文件放在 `user/app/<name>/` 或 `user/asset/`；两者都在 include 路径里。
`spectrum/gen_spectrum_assets.py` 和 `coffee/gen_coffee_assets.py` 是现有示例，不是通用
工具；修改字体文案时才需要重跑。

### 4.3 图片与资源

- 推荐把图片转成 C 数组（`lv_image_dsc_t`），用 `lv_image_set_src(obj, &my_image)`。
- `user/asset/` 已加入编译 include 路径，适合放共享资源头；目录契约见
  [`user/asset/README.md`](../asset/README.md)。
- 工具没有提供运行时资源文件加载约定，不要依赖从磁盘读 PNG；把资源编译进二进制。
- 大图会占用 16 MiB 的 LVGL heap，注意尺寸和数量。

### 4.4 事件

```c
static void on_click(lv_event_t * event)
{
    if(lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    lv_obj_t * target = lv_event_get_target(event);
    (void)target;
    printf("[myapp] clicked\n");
}

lv_obj_add_event_cb(button, on_click, LV_EVENT_CLICKED, NULL);
```

常见事件：`LV_EVENT_CLICKED`、`LV_EVENT_VALUE_CHANGED`（slider / switch / dropdown）、
`LV_EVENT_PRESSING` / `LV_EVENT_RELEASED`（拖拽）。场景里的 `click_at` 和 `drag` 最终都是
真实 pointer 事件。

键盘与编码器默认绑定在隐藏的 demo group 上。新应用最简单只做 pointer；确实需要键盘或
编码器时，自己创建 `lv_group_t`、添加控件，并对 keypad / encoder indev 调用
`lv_indev_set_group()`。

### 4.5 定时器与动画

```c
static void tick_cb(lv_timer_t * timer)
{
    (void)timer;
    /* 每 16 ms 更新一次 */
}

lv_timer_create(tick_cb, 16, NULL);
```

- 时间来自虚拟时钟：场景的 `wait`、`tick`、live ticker 推进它，不是墙钟。
- 网页测试模式每 33 ms 推进一次虚拟时间，录制模式 100 ms；场景 `wait` 按 16 ms 步进。
- `lv_anim` 同样由 `lv_timer_handler` 驱动，写动画不需要真实 `sleep`。
- 不要在回调里阻塞等待；用状态机或定时器。

### 4.6 命名与证据

- 给会被点击、拖拽、聚焦的控件命名：`app_obj_set_name(obj, "myapp_button")`。
- 应用根 screen 用 `app_set_name("myapp")` 命名，入口函数本身不接收对象。
- 命名后 `timeline.ndjson` 的输入行会出现 `"hit": "myapp_button"`，配合 `hit_class` 定位。
- 名字在同一界面内保持唯一；跨应用加应用前缀，避免阅读证据时混淆。
- 9.1 与 8.x 没有对象名，`hit` 为空，只能看 `hit_class`。

### 4.7 多文件拆分

- `user/app/**/*.c` 会递归收集并全部编译，不需要为每个文件改构建。
- 可以按 `page.c` / `ui.c` / `model.c` 拆分；`app.c` 只需要 include 各应用的入口头文件。
- **所有应用变体在同一个二进制里**：全局函数和变量要么 `static`，要么加应用前缀
  （现有代码用 `coffee_*`、`spectrum_*`）。
- 所有 `.c` 对所有支持版本都会编译；只在 9.6+ 使用的代码必须放进版本门，否则 9.1 /
  8.x 构建会失败。

### 4.8 双端共享（SiFli 导出）

`hspi_watch` 是双端共享示例：`user/app/hspi_watch/` 是唯一源码真源，本地 headless
直接编译，SiFli 导出时复制成自包含工程。共享代码只暴露
`void hspi_watch_create(void)`，以 LVGL 9.4 可用 API 为硬基线；`app_create`、
`main.c` 和注册表留在目标侧，不进入共享源码。

资源统一通过 `assets.h` 契约使用：两端暴露相同图片符号和 `WATCH_*` 尺寸宏，导出端
从 PNG 宽高生成宏。`user/scenarios/hspi_watch.json` 声明 390x450。完整导出说明、
raw 源收集和 EZIP/真机验证边界见
[`chip-adapt/sifli/README.md`](../../chip-adapt/sifli/README.md)。

---

## 5. 硬约束与常见坑

| 约束 | 说明 |
|---|---|
| 只改用户目录 | `user/app/**/*.c`、`user/scenarios/`、`user/asset/`；不要改 `core/` 或 `lvgl-src/` |
| 不写 `main` | engine 负责初始化、tick、刷新和退出 |
| 应用变体仅 9.6+ | 9.1 / 8.x 忽略选择，固定显示 `demo/` 的 harness |
| 未知应用名会退出 | engine 打印 `[app] apps=...` 后 `exit(1)`，检查 `apps[]` 与场景是否一致 |
| 名字格式 | 场景 `app` 匹配 `[A-Za-z0-9_-]+`；`apps[]` 精确匹配 |
| 不要动 demo harness | `app.c` 里 `demo_harness_create(false)` 和隐藏的 `demo_button` 是工具集成测试的固定目标 `(112, 324)` |
| 改过 C 不能用 `--no-build` | 预编译 engine 是旧产物；默认 `--build` 才会重新编译 |
| 没有对象树 / `inspect` / `set` | 精确状态只能在自己的 C 代码里 `printf` 到 `engine.log` |
| 不写第二个协议客户端 | 只用 `Runtime` / `Recording` / `play_scenario` |
| 会话清理 | 删除 `build_error` 会话，只保留最新 10 条 |

---

## 6. 排错表

| 现象 | 先检查 |
|---|---|
| 网页下拉里没有新应用 | `user/scenarios/<name>.json` 是否存在、JSON 是否合法、顶层是否有 `app` |
| engine 启动即退出，日志有 `unknown app=` | `apps[]` 名字与场景 `app` 是否完全一致；`[app] apps=` 里有没有它 |
| `build_error` | `sessions/<id>/build.log`；常见是 include 路径、版本门漏了、9.6 不存在的 API |
| `link_error` | 声明了 `<name>_create` 但没有定义，或版本门把定义排除了 |
| `harness_error` | 场景字段拼写、未知字段、类型不匹配 |
| 画面空白 | 看 `snapshots/`；确认控件创建在 `screen` 上、尺寸非零、颜色与透明度正确、没有被父对象裁剪 |
| 点击没反应 | 坐标是否在控件内；控件是否 `clickable`；回调事件码是否正确；是否被上层对象盖住；timeline 的 `hit` 是谁 |
| 动画不动 | 定时器是否创建、周期是否合理；测试模式是否在推进虚拟时间 |
| 改了代码画面没变 | 是否误用 `--no-build`；构建是否失败后回退到旧二进制 |
| 9.1 / 8.x 看不到自己的应用 | 预期行为；应用变体只在 9.6+ 启用 |
| timeline 的 `hit` 为空 | LVGL 低于 9.2 没有对象名；本项目 app 变体不受影响 |

---

## 7. 参考实现

- `user/app/spectrum/`：canvas、六种动画、定时器、自定义字体与图片、资源生成脚本。
- `user/app/coffee/`：多页面、状态机、定时器、自定义字体。
- `user/app/xiaohongshu/`：另一个完整页面实现。
- `docs/app.html`：入口、注册、选择链路的真源索引。
- `docs/scenario-server.html`：场景格式与服务端常量的真源索引。
- `.scratch/ai-tools/SPEC.md`：工具的设计真源与范围。

## 8. 提交前检查清单

- [ ] 源文件在 `user/app/<name>/`，入口签名是 `void <name>_create(void)`
- [ ] `user/app/app.c` 有 include 和 `apps[]` 注册行
- [ ] 只在 9.6+ 使用的代码有版本门
- [ ] 全局符号带应用前缀或为 `static`
- [ ] 交互控件已 `app_obj_set_name`，应用根已 `app_set_name`
- [ ] `user/scenarios/<name>.json` 顶层写了 `"app": "<name>"`
- [ ] 构建成功，`manifest.json` 的 `status` 为 `ok`
- [ ] `engine.log` 有预期状态，`timeline.ndjson` 的 `hit` 指向预期控件
- [ ] 没有修改 `core/`、`lvgl-src/`、demo harness
