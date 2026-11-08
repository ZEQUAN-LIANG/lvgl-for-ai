# AURELIA C9 咖啡机 demo

800×600 高级全自动咖啡机触屏 UI，只针对 LVGL 9.6。全部逻辑在 `user/app/coffee/`，工具层不感知饮品、配方或养护。

## 运行

LVGL 9.6 默认启动本应用；`user/scenarios/coffee.json` 已声明 `"app": "coffee"`，
所以一条命令即可：

```bash
# 无窗口、录制并回放完整场景
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json

# 保持会话直到 Ctrl+C（headless）
python -I core/cli.py --lvgl 9.6 --app coffee --idle
```

切到小红书应用时用对应 scenario（或网页端顶部「应用」下拉）：

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/xiaohongshu.json
```

网页 live 录制/测试模式每 100 ms 推进一次虚拟时间（10 fps），吐司、时钟、萃取和养护进度会持续变化。网页 live 默认只保留变化帧：画面不变时不会产生新 PNG，也不消耗 600 帧预算；HUD 的 `t_ms` 仍持续前进。动画密集时 600 个保留帧约对应 60 s。

CLI 场景默认仍逐帧录制：场景约 55 s 虚拟时间，默认 600 帧上限会让 manifest 标记 `truncated`，但 28 张 snapshots 仍完整写入。需要完整帧时显式提高上限（帧体积较大）：

```bash
LVGL_AI_MAX_FRAMES=4000 python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/coffee.json
```

## 功能

- **12 款饮品**：意式浓缩、双份浓缩、芮斯崔朵、美式、卡布奇诺、拿铁、澳白、玛奇朵、摩卡、冷萃、热水、蒸汽。每款有独立杯型插画、默认配方和可编辑参数。
- **配方编辑**：浓度 1–5、容量、温度 88/93/96°C、奶量、奶泡四档、双杯、预热杯；取消会恢复打开编辑器时的参数。
- **萃取过程**：虚拟时间驱动的预热、研磨、预浸、萃取、奶泡阶段；环形进度、杯中液面、压力与水温、完成态和自动返回。
- **资源模拟**：每杯消耗水、咖啡豆、奶，渣盒增长；水量/豆量/奶量不足会阻止萃取并提示。
- **三个用户档案**：Alex、Mia、访客，各自有今日杯数、本周柱状图和收藏。
- **养护**：日常冲洗、奶路清洁、除垢、滤芯更换四个程序，带进度与取消；可清空渣盒、加满水箱、补充咖啡豆、加满奶仓。
- **设置**：研磨度、咖啡温度、水硬度、预热杯、自动关机、屏幕亮度（实际调暗）、提示音、节能模式、°C/°F；恢复默认带确认弹窗。
- **待机层**：电源键进入待机，轻触唤醒，虚拟时钟持续走时。
- 所有状态变化写入 `engine.log` 的 `[coffee] ...` 行，便于取证。

## 素材

`coffee_*.h` 是生成并提交的文件。只有修改 `TEXTS` 或画法时才需要重新生成：

```bash
python -I user/app/coffee/gen_coffee_assets.py --preview .scratch/tmp/coffee-preview
```

需要 Node.js（`npx lv_font_conv`）和 Windows 自带的 `C:/Windows/Fonts/Deng.ttf`、`Dengb.ttf`。只嵌入 `TEXTS` 中用到的字符与可打印 ASCII。

## 模块

- `coffee_ui.c/.h`：数据模型、生成素材包装、通用控件、toast、模态层。
- `coffee_page.c`：外壳、顶栏、左侧导航、待机层、亮度遮罩。
- `coffee_home.c`：问候、横向饮品列表、主视觉、机器状态。
- `coffee_custom.c`：配方编辑器。
- `coffee_brew.c`：萃取动画与结果。
- `coffee_favorites.c`：按档案重建的收藏网格。
- `coffee_maintenance.c`：养护程序与补给。
- `coffee_settings.c`：设置与恢复默认。
