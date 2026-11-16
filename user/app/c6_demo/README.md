# c6_demo

面向微雪 **ESP32-C6-LCD-1.47（无触摸，172×320，ST7789）** 的 LVGL 9.6 演示应用，
同时在本地 headless 宿主上可跑。它只有 LVGL 依赖，不包含 ESP-IDF 头文件。

## 页面

| 页面 | 内容 |
| --- | --- |
| `home` | 模拟时钟、uptime、load bar、串口提示 |
| `status` | CPU / MEM / NET 三条 bar，HEAP 与 uptime |
| `about` | 板型、LVGL 版本、无触摸说明、ESP-IDF 导出提示 |

底部 `PREV` / `NEXT` 按钮用于本地 headless 指针验证；真机没有触摸，页面切换走串口命令
（固件侧下一步用 `esp_console` 注册 `pages` / `page` 命令）。

应用暴露的页面 API：

```c
bool c6_demo_page_show(const char *name);
bool c6_demo_page_next(void);
bool c6_demo_page_prev(void);
const char *c6_demo_page_current(void);
size_t c6_demo_page_count(void);
const char *c6_demo_page_name(size_t index);
```

目标侧调用这些函数时要包在 `lvgl_port_lock(0)` / `lvgl_port_unlock()` 里。

## 本地验证

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 \
  --scenario user/scenarios/c6_demo.json --json
```

场景会点 `NEXT` 两次、`PREV` 两次，保留 `home` / `status` / `about` 的 snapshot 与
timeline 证据。预期 `status=ok`、`display=172x320`、`app=c6_demo`，点击命中
`c6_demo_next` / `c6_demo_prev`。

## 资源

当前没有图片资源，全部是 LVGL 控件。C6 没有 PSRAM，不要在这里加全屏 canvas；要画图时
用局部 canvas（例如 172×80），不要把 172×320×2 的整个 framebuffer 放进静态内存。

## 下一步

- 在 ESP-IDF 模板里生成 `app_main.c`：ST7789 + `esp_lvgl_port` + `c6_demo_create()`。
- `sdkconfig` 要打开 `LV_USE_LABEL` / `LV_USE_BUTTON` / `LV_USE_BAR`、Montserrat 14/16/20
  和 `LV_USE_OBJ_NAME`；否则 `lv_font_montserrat_*` 或控件符号会缺。
- 加 `esp_console` 命令通道，把页面 API 接到串口。
- 用 `chip-adapt/esp32/host/` 的网页/CLI 做页面切换验证。
