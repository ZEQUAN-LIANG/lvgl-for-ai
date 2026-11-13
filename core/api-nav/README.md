# LVGL API 导航

给写 `user/app/*.c` 的 AI 用的按版本 API 导航。每份文件只讲 `app_create()` 里常见任务涉及的函数、类型、头文件路径和最小片段，不做全量 API 转储；跨版本差异集中在每份的「与相邻版本差异」一节。

## 按版本选择

`LVGL_AI_LVGL_VERSION` 选择 `lvgl-src/<version>`，默认是 9.6：

| 版本 | 文档 | 源码根 | adapter | 对象名 API | `hit` / `hit_class` |
|---|---|---|---|---|---|
| 9.6 | [9.6.md](9.6.md) | `lvgl-src/9.6/` | 9x | 有（`LV_USE_OBJ_NAME=1`） | 有名字时有 `hit`；`hit_class` 为 `lv_button` / `lv_obj` / `lv_label` / `lv_image` |
| 9.5 | [9.5.md](9.5.md) | `lvgl-src/9.5/` | 9x | 有（`LV_USE_OBJ_NAME=1`） | 有名字时有 `hit`；`hit_class` 带 `lv_` 前缀 |
| 9.4 | [9.4.md](9.4.md) | `lvgl-src/9.4/` | 9x | 有（`LV_USE_OBJ_NAME=1`） | 有名字时有 `hit`；`hit_class` 带 `lv_` 前缀 |
| 9.1 | [9.1.md](9.1.md) | `lvgl-src/9.1/` | 9x | 无（9.2 起才有） | `hit` 永远为空；`hit_class` 为 `btn` / `obj` / `label` / `image` |
| 8.4 | [8.4.md](8.4.md) | `lvgl-src/8.4/` | 8x | 无 | `hit` 永远为空；`hit_class` 为 `lv_btn` / `lv_obj` / `lv_label` / `lv_img` |
| 8.3 | [8.3.md](8.3.md) | `lvgl-src/8.3/` | 8x | 无 | `hit` 永远为空；`hit_class` 为 `lv_btn` / `lv_obj` / `lv_label` / `lv_img` |

`LVGL_AI_LVGL_SRC` 可以覆盖源码路径；覆盖后请以实际源码头文件为准。文档路径按对应版本的官方 tag 核对。

## 使用约定

- 用户只写 `user/app/*.c`，入口固定为 `void app_create(void)`；不写 main，不注册 display / indev，不碰构建。
- 工具（运行时）负责 `lv_init`、运行时尺寸的 XRGB8888 display（默认 800×600）、标准虚拟 pointer / keypad / encoder indev 与虚拟时间；焦点组由 `user/app` 自己创建和挂载。
- 精确状态（checked / value / text / focus / scroll）只能 `printf` 到 stdout，最终进入 `engine.log`；没有 tree、inspect、set、param，也不要在 app 里造运行时查询入口。
- 这份导航是静态文档，只服务写代码，不参与判定；验收标准由人类在聊天里给。
- 8.x 的 `lvgl_compat.h` 提供 `lv_screen_active()`、`lv_image_create()`、`lv_image_set_src()` 三个 9.x 同名 shim，分别展开为 `lv_scr_act()`、`lv_img_create()`、`lv_img_set_src()`。

## 工具回执：wait 的 changed

引擎 `wait` / `wait frames` 回执可带 `changed` 布尔字段，表示该次等待期间是否至少发生过一次 display flush。`Runtime.wait_stable` 以 16 ms 步进轮询该字段；它不使用 changed-only 的保留帧数，因此静态画面保留帧数为 0 也算稳定，而持续重绘时即使没有新 PNG 也不会被当成稳定。

版本边界：`core/engine/adapter_9x.c`（9.6 / 9.5 / 9.4 / 9.1）与 `core/engine/adapter_8x.c`（8.4 / 8.3）都在 flush callback 设置同一个 `refresh_painted` flag，由 `core/engine/session.c` 汇总进 `wait` 回执；`tick`、`pointer`、`key` 等其它回执不带 `changed`。各支持版本不需要降级；缺少该字段的旧 engine 会提示 `--build` 重建。

## 校验

文档里的反引号 `lv_*` 符号必须能在对应 `lvgl-src/<version>` 头文件中找到；该版本没有的符号只能在「与相邻版本差异」等显式标注处出现。可重复校验：

```bash
python -I core/tools/check_api_nav.py
```

脚本逐文件报告符号总数、缺失符号、例外（显式版本差异与 8.x shim）、头文件路径、固定章节、任务索引条数、片段数和行数。退出码 0 表示全部通过。

## 版本速查

- 9.x：`lv_screen_active()`、`lv_display_*`、`lv_button_create()`、`lv_image_create()`、`lv_obj_delete()`、`lv_obj_remove_flag()`、`lv_event_get_target_obj()`。
- 8.x：`lv_scr_act()`、`lv_disp_*`、`lv_btn_create()`、`lv_img_create()`、`lv_obj_del()`、`lv_obj_clear_flag()`、`lv_event_get_target()`。
- 9.6 专有：`lv_obj_set_clickable()`；9.5 / 9.4 / 9.1 用 `lv_obj_remove_flag(obj, LV_OBJ_FLAG_CLICKABLE)`。
- 9.1 差异：无对象名 API、无 `lv_label_set_recolor()`；文本换行常量仍是 `LV_LABEL_LONG_WRAP`（9.4+ 为 `LV_LABEL_LONG_MODE_WRAP`，8.x 也用旧名）。
- 8.4 相对 8.3 只多 `lv_calendar_header_dropdown_set_year_list()`；本导航覆盖的 API 相同。

## 文件

- [9.6.md](9.6.md)
- [9.5.md](9.5.md)
- [9.4.md](9.4.md)
- [9.1.md](9.1.md)
- [8.4.md](8.4.md)
- [8.3.md](8.3.md)
