# game · ZOMBIE 无尽尸潮

`zombie-cannon.html` 的 C/RGB565 移植。模块不依赖 LVGL、不分配内存、不创建控件树；
宿主只提供 framebuffer、定时器、触摸坐标和可选的回调。

## 文件

| 文件 | 作用 |
|---|---|
| `zc_game.h` | 稳定平台接缝：生命周期、输入、音效/振动/随机/存档 hooks |
| `zc_game.c` | 游戏逻辑、实体池、波次、升级、AI 模式、HUD 与弹窗 |
| `zc_audio.c/.h` | 板端 audprc/audcodec/AW8155 扬声器通路与事件队列；headless 空实现 |
| `zc_synth.c/.h` | 可移植的 16 kHz 单声道音效合成器（PC WAV 预览也用它） |
| `zc_art.c/.h` | 程序化背景、炮台/沙袋、雾/余烬、精灵绘制 |
| `zc_gfx.c/.h` | RGB565 图元、5×7 像素字、中文点阵字、alpha 混合 |
| `zc_cjk_font.c/.h` | 由 HTML 版同一套 SimSun 光栅化生成的中文点阵 |
| `zc_font5x7.h` | 由 HTML `FONT` 表生成的 5×7 像素字 |
| `zc_sprites_data.h` | 由 HTML `SPRITE_DEFS` 生成的 4 种僵尸精灵 |

## 宿主契约

```c
zc_config_t cfg = {
    .width = 390, .height = 450,
    .safe_inset = 44,      /* 圆角手表；普通 390x460 预览填 0 */
    .embedded = true,      /* 显示返回哨站/暂停退出按钮 */
    .show_scanlines = true,
    .hooks = &hooks,
};
zc_create(fb, backdrop, &cfg);  /* backdrop 可为 NULL，退化为逐帧程序化背景 */
zc_enter();                     /* 回到标题 */
zc_tick(now_ms, elapsed_ms);    /* 逻辑帧，25–30 Hz 即可 */
zc_render();                    /* 全量重绘到 fb，宿主负责 invalidate */
zc_pointer(action, x, y);
zc_key(lv_key);
if(zc_wants_exit()) { zc_clear_exit(); /* 回到手表应用抽屉 */ }
```

`fb` 和 `backdrop` 都是 `uint16_t` 的 RGB565，尺寸为 `width × height`。建议
`backdrop` 只分配一次并缓存；没有它也能跑，只是每帧重画静态背景。

## 平台 hooks

`zc_hooks_t` 是唯一的硬件接缝：

- `sfx(id)`：17 种程序化音效 ID；`sift_watch` 已接到 `zc_audio` 的
  audprc → audcodec **DAC1** → AW8155 扬声器通路。黄山派需要外接 GH-1.25mm
  4Ω/8Ω 喇叭，并短接核心板 5-6、7-8、11-12 跳线帽。
- `haptic(kind)`：点击、受击、Boss、升级、死亡；`sift_watch` 已映射到 PA20 马达。
- `rand()`：可换成硬件随机源；为空时使用内部 xorshift。
- `load/store(save)`：最高分、最高波次、静音状态。`sift_watch` 当前是进程内静态存档，
  换成 NVM 只需替换这两个回调。

## AI 模式

长时间没有触摸输入时，游戏自动接管：

- 标题停留 12 秒：自动开始，HUD 出现 `AI` 标。
- 战斗中 10 秒不触摸：自动索敌/开火并亮起 `AI` 标。
- 一旦 AI 接管，后续菜单不再等待倒计时：升级卡立即从当前三张里随机选一张，toast
  前缀 `AI ·`；结算立即重开。
- 任何触摸、按键或点击卡片都会立刻恢复手动控制并重置计时；未接管时升级/结算仍保留
  6 秒/12 秒倒计时。

## 适配说明

- 逻辑分辨率以 390×460 为基准；`height=450` 时底部美术整体上移 10 px（`dy=-10`），
  HUD 与底部按钮使用 `safe_inset` 避开 44 px 圆角。
- 精灵来自 ASCII 调色板，逐格写 `scale×scale`，没有大图或解码器依赖。
- 在表盘 390x450 + 圆角安全区下跳过动态移动雾和全屏扫描线，板端 `sift_render()`
  从约 43 ms/帧降到 24–30 ms/帧；390x460 独立预览保留完整效果。静态背景已在
  PSRAM 预渲染，EZIP 只适合改造成 `lv_image` 分层后省 Flash/启动解码，不能直接
  memcpy 到当前 canvas。
- 中文点阵由 `.scratch/tmp/zc/fontgen.mjs` 用与 HTML 相同的 SimSun/阈值生成；改文案后
  需要重新生成 `zc_cjk_font.c`。
- 导出 `sift_watch` 时这些 `.c/.h` 会原样复制；不要使用 LVGL 9.5/9.6-only API。
