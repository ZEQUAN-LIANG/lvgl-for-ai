# intro

发布包的默认应用，也是默认模板；按 LVGL 9.4+ 版本门编写。启动时不指定 app 就会
运行它；`user/scenarios/intro.json` 录制了它的演示序列。

## 作为模板使用

1. 复制 `user/app/intro/` 为 `user/app/<name>/`，把文件、`intro_*` 符号和头文件宏改掉。
2. 在 `user/app/app.c` 的 include 与 `apps[]` 里登记 `<name>_create`。
3. 新建 `user/scenarios/<name>.json`，顶层写 `"app": "<name>"`。
4. 改过 C 代码后用源码构建跑场景：

   ```bat
   python -I core\cli.py --lvgl 9.6 --scenario user\scenarios\<name>.json --json
   ```

`intro` 用到的控件与写法：`lv_obj` 卡片、`lv_label`、`lv_button`、`lv_bar`、`lv_arc`、
`lv_timer` 和 `lv_anim`；字体只用内置的 Montserrat 14/16/20。把它精简成自己的界面时，
保留 `void intro_create(void)` 入口和 `app_set_name` / `app_obj_set_name` 命名即可。
