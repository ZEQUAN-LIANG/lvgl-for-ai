# intro：docs/index.html 的 LVGL 移植

新的默认介绍页。`docs/index.html` 的 800×600 版本，按同一套布局、文案和交互做成真实 LVGL 控件；不是网页截图轮播。旧的 `user/app/intro` 实现已删除，由这份代码取代。

## 运行

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/intro.json --json
```

场景 `user/scenarios/intro.json` 会依次覆盖六个屏幕、Loop 的步进/播放/停止、版本切换、滚动和键盘 tab 导航。

## 分辨率

选择 **800×600**：页面自己的状态栏写着 `800 × 600`，Overview 在 800×600 下刚好一屏；其他屏幕在 workspace 内滚动，和网页一致。

## 结构

- `intro_ui.c`：壳层（app bar、tab bar、status bar、workspace）、FreeType 字体、文本/矩形构建器、六个屏幕的交互。
- `intro_layout.c`：按 800×600 浏览器布局生成的静态矩形、图片和逐行文本数据。
- `assets/`：从 `docs/img/` 缩放出的 PNG 源，以及 `intro-*.png` / `watch-*.png` 动画帧。
- `intro_img_*.h`：`core/assets.py image` 生成的 LVGL 图片数组；`assets.json` 记录来源与颜色格式。
- `user/scenarios/intro.json`：演示场景。

## 交互与动画

| 交互 | 实现 |
|---|---|
| 六个 tab 切换 | 220 ms fade + 8 px slide，`lv_anim` |
| 键盘 / encoder | tab 加入 `lv_group`；方向键、Home/End、Enter；`LV_STATE_FOCUS_KEY` 显示 focus ring |
| Loop 步进 | 点击任一步停止播放；`lv_arc` 300 ms 动画；2600 ms `lv_timer` 自动播放 |
| Loop 播放按钮 | 播放 / Stop，绿色状态；离开 Loop 自动停止 |
| 版本切换 | 6 个版本格；detail 180 ms fade + 4 px slide |
| 滚动 | workspace 垂直拖拽滚动；无滚动条 |
| 媒体 | Overview/Evidence/Versions 用 `lv_image`；Intro 和 watch GIF 转成 `lv_animimg` |

`intro` 是发布包唯一的默认应用，LVGL 9.4+ 编译；9.1 / 8.x 不编译该变体。9.4/9.5 没有 FreeType 变量字重接口，display 字体改用静态 `segoeuib.ttf`，标题仍保持粗体；9.6 使用 Bahnschrift 的 variable weight。

## 字体

运行时用 FreeType 加载宿主机字体：

- Bahnschrift：display / 标题 / 数字（9.4/9.5 用 Segoe UI Bold 代替）
- Candara / Candara Bold：正文
- Consolas / Consolas Bold：mono / 代码 / 标签
- Segoe UI Symbol：箭头、▶/■ 等缺少的字形

这是 host 预览路径；导出设备时应改成随应用编译的字体头或设备字体，不要依赖 `C:\Windows\Fonts`。

## 与网页的差异

- 文字由 LVGL FreeType 栅格化，网页由浏览器（Windows 上通常是 DirectWrite）栅格化。布局、字号、换行和交互按浏览器盒子对齐，但**逐像素 diff 不可能为 0**；当前 800×600 截图对比约 PSNR 22–25 dB，差异集中在文字抗锯齿和图片重采样边缘。
- `docs/index.html` 的 GIF 是 93 帧；这里用 5 帧 `lv_animimg` 表示 Intro 的五个阶段，watch 用 8 帧。需要逐帧一致时应改为更多帧或启用 `lv_gif`。
- 外部链接、复制按钮、视频链接是 web-only；设备端只保留展示或写入日志。
- 网页的 hash 深链接、`history.pushState`、`aria-live` 是浏览器能力，LVGL 不实现。
- 场景录制有默认 600 帧上限；本页面有 REC/eyebrow 呼吸灯和两个 `lv_animimg`，长时间录制会先到上限，快照仍会照常保存。
