# ORBITAL · spectrum

`spectrum` 是 LVGL 9.6 的音频频谱播放器应用变体。布局常量在 `spectrum.h`，视觉资源已生成为提交的 `spectrum_*.h`；两者是本应用的真源：

- 左侧 `PLAY QUEUE`：三首模拟曲目，点击切歌；下面是 PEAK / RMS / SYNC 与信号参数。
- 中间全屏 800×600 HUD canvas：中央旋转封面 + 六种频谱效果。
- 右侧 `TELEMETRY`：BPM、KEY、LEVEL、LOW/MID/HIGH、LOUDNESS 段码、迷你频谱和六种模式按钮。
- 底部：进度、上一首/播放暂停/下一首、调色板、AUTO、收藏、音量。

全部数据由程序合成，没有真实音频输入；`spectrum_sim_update()` 生成 48 个对数频段、节拍包络、drop、峰值保持与波形。

## 六种模式

| 模式 | 画面 |
|---|---|
| `ORBIT` | 64 段径向频谱 + 外圈卫星 + 中央唱片 |
| `DUAL` | 外圈顺时针、内圈逆时针的双环频谱 |
| `RADIAL` | 72 根由内向外辐射的频谱柱 |
| `SPIRAL` | 240 个节点组成的旋转螺旋 |
| `SONAR` | 雷达扫描线 + 20 个频段光点 |
| `STARS` | 260 条向外跃迁的星轨 + 节拍冲击波 |

`AUTO` 开启后每 8 秒轮换一次模式；调色板在 ION / MAGMA / VERDANT 之间循环，影响屏幕渐变、面板边线、仪表、按钮与封面选择。

## 操作

全部用 pointer（触摸/鼠标）：

- 点击左侧队列行切歌。
- 点击右侧 2×3 模式网格切换效果。
- 点击播放/暂停、上一首/下一首、收藏、调色板、AUTO。
- 拖拽进度条或音量条；按下即跳转。

键盘/编码器 indev 仍绑定在隐藏的 `demo` group 上（工具测试依赖它），因此本应用只使用 pointer。

## 场景

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/spectrum.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/spectrum.json --record-changed-only
```

场景会依次进入六种模式并快照，再验证切歌、换调色板、收藏、暂停、拖动进度与音量。交互坐标直接来自 `spectrum_page.c` 的布局常量。

网页端启动 `python -I core/web.py` 后，顶部「应用」下拉会多出 `spectrum`（来自场景的 `app` 字段）；测试模式可以实时看动画。

## 实现要点

- 画布是 `LV_DRAW_BUF_DEFINE_STATIC(..., 800, 600, LV_COLOR_FORMAT_XRGB8888)`，每帧 `lv_canvas_init_layer` → `lv_draw_rect/line/arc` → `lv_canvas_finish_layer` → 一次 `lv_obj_invalidate`。
- 背景是斜向三段渐变、40/160 px 网格与径向暗角预烘焙成 800×600 XRGB 底图；四处加性辉光用预计算 alpha 蒙版逐帧叠加；扫描线与 stage 暗角做成独立 ARGB 叠加层。
- 封面拆成静态 `base` 与旋转 `spin` 两层：`base` 含渐变、黑胶与中心孔，`spin` 只含电弧、霓虹轮廓与碎片；`spin` 使用 `LV_BLEND_MODE_ADDITIVE` 叠在 `base` 上。为减少小尺寸缩放误差，另有 96/88/78 px 的旋转层与 88/78 px 底板。
- 没有径向/锥形渐变：HUD 环、频谱柱与粒子都用圆/线/矩形/圆弧近似；封面辉光用 256×256 的加性 alpha 贴图按尺寸缩放后直接写入画布。
- 图标、字体、光晕贴图与封面层已生成并提交；构建不依赖转换器、Node 或网络。
- 字体只包含 ASCII：Segoe UI Bold 14，Consolas Regular 7/8/9，Consolas Bold 9/32。
- 播放/暂停、切歌、调色板、AUTO、收藏全部有 `spectrum_*` 命名，便于 timeline hit 证据定位。
- `(112,324)` 区域（左侧 SIGNAL 表）没有可点击控件，隐藏的 `demo_button` 仍能被工具的 `settings.json` 场景命中。

## 重新生成资源

`spectrum_*.h` 已提交，构建不依赖转换器。字体用内置工具重生成（只含 ASCII）：

```bat
bin\lvgl.cmd assets font --app spectrum --font C:\Windows\Fonts\segoeuib.ttf ^
  --size 14 --bpp 4 --range 0x20-0x7E --name spectrum_sans_14
bin\lvgl.cmd assets font --app spectrum --font C:\Windows\Fonts\consola.ttf ^
  --size 7 --bpp 4 --range 0x20-0x7E --name spectrum_mono_7
```

封面层可用已提交的 `covers_src/*.png` 直接转换：

```bat
bin\lvgl.cmd assets image --app spectrum --input user\app\spectrum\covers_src\cover_01.png --cf ARGB8888
```

图标与光晕是程序化绘制的，当前以提交的 `spectrum_icons.h` / `spectrum_glow.h` 为准；
若要重生成，先导出 PNG 再用 `assets image`。旧的 `gen_spectrum_assets.py` 已删除。

## 相关文件

- `spectrum.h`：布局常量、模式/调色板/字体/图标枚举、模型 API。
- `spectrum_ui.c`：唯一包含生成资源的 TU、模拟音频、控件构建器、调色板混合。
- `spectrum_page.c`：外壳、面板、运输区、事件、16 ms 定时器与 UI 刷新。
- `spectrum_viz.c`：canvas 背景/HUD 与六种效果。
