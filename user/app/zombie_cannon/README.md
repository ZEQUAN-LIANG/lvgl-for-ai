# zombie_cannon

`zombie-cannon.html` 的 LVGL 9.6 独立预览：390x460 RGB565 canvas，用来和 HTML 版逐帧
核对标题、战斗、升级卡与结算画面。

游戏实现不在本目录，而在 `user/app/sift_watch/game/`。本目录只提供 390x460 的
`zombie_cannon_create()` 外壳；同一份 `zc_game.c` 也被 `sift_watch` 的 ZOMBIE 应用使用。

## 本地预览

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/zombie_cannon.json
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/zombie_cannon_ai.json
```

第一个场景依次截图：标题、波次开始、手动瞄准、自动射击、暂停、恢复、升级选择；
`zombie_cannon_ai` 在标题停留 12.5 秒，验证 AI 自动接管并亮起 HUD 的 `AI` 标。

## 操作

- 按住战场：手动瞄准，射速更快。
- 松手：自动索敌开火。
- 左下暂停，右下静音；升级时点击三张卡之一。

## 与黄山派的关系

黄山派实际屏幕是 390x450。部署入口是 `sift_watch` 的 ZOMBIE 应用（应用抽屉第 5 个
磁贴），不是这个独立应用；`sift_watch` 会以 390x450 和 44 px 圆角安全区运行同一份
游戏代码。

本目录没有 `assets.json`，也不需要图片资源。游戏只写 RGB565 framebuffer；音效、振动、
随机数和高分持久化通过 `game/zc_game.h` 的 `zc_hooks_t` 注入。`sift_watch` 已接好
振动、进程内存档和 audprc/audcodec/AW8155 扬声器；本独立预览的 hooks 为空，所以
PC/headless 下静音，板端声音以 `sift_watch` 的 ZOMBIE 应用为准。

AI 模式两端一致：标题 12 秒或战斗中 10 秒不触摸后接管；一旦接管，升级/结算菜单
不再等待秒数，升级立即随机选卡、结算立即重开。任何触摸或按键立即恢复手动；未接管时
升级卡仍保留 6 秒、结算仍保留 12 秒倒计时。

板端 390x450 会跳过动态移动雾和全屏扫描线，`sift_render()` 从约 43 ms 降到
24–30 ms；本 390x460 预览保留完整雾/扫描线效果。静态背景已在 PSRAM 预渲染，
EZIP 只有在改成 `lv_image` 分层后才有每帧收益。

导出 `sift_watch` 时 `export.py` 会递归复制 `sift_watch/game/`，因此独立预览目录不需要
进入 SiFli 导出产物。
