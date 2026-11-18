# sift_watch

390x450 黄山派像素手表。整个界面由一块 RGB565 `lv_canvas` 程序化绘制，不依赖图片资源；兼容
LVGL 9.4（板端基线）与 9.6（本地预览）。

## 功能

- 待机表盘：实时时钟、日期、年份/电量占位、六轴重力沙漏、自动漂移、翻转手表翻转沙漏、暗待机
- 手势：拖动沙漏区域 360° 环视，拖动其余表盘区域倾斜沙漏；左/右滑切换环形页面，上滑打开应用抽屉，下滑回表盘；方向键也可倾斜；单击表盘翻转
- 物理键：KEY1 返回/主页，KEY2 确认/开始；按键、翻转和切页时 PA20 输出一次短振动脉冲
- 应用抽屉：TIMER / STOPWATCH / WEATHER / SETTINGS / ZOMBIE
- TIMER：1/3/5/10 分钟预设、开始/暂停/重置、结束提示
- STOPWATCH：60 点刻度、开始/停止、计次、重置
- WEATHER：离线样例天气、昼夜图标、°C/°F 切换
- SETTINGS：自动漂移、24H 时钟、暗待机、传感器校零；显示面板与器件信息
- ZOMBIE：无尽尸潮炮台游戏，作为应用抽屉第 5 个应用运行

界面没有 PNG/图片资源：5×7 点阵字体、图标、沙漏和页面外壳全部由绘图原语直接写入
RGB565 `lv_canvas`。

## ZOMBIE 无尽尸潮

`game/` 是 `design/zombie-cannon.html` 的 LVGL/RGB565 移植，直接复用 `sift_watch` 的
390x450 canvas，不创建第二套控件树。入口是应用抽屉里的 `ZOMBIE` 磁贴；页面保留
44 px 圆角安全区，HUD、暂停/静音按钮和弹窗都不会落进面板切角。

- 按住战场手动瞄准并提高射速；松手自动索敌开火。
- 波次无限，普通/重型/Boss 血量随波次指数增长；每 5 波刷新「屠宰者」。
- 击杀升级后三选一改装；高爆弹头、燃烧弹、哨戒炮、暴击等可持续成长。
- 左下暂停、右下静音；暂停菜单的「返回哨站」回到应用抽屉。
- 最高波次/最高分通过 `zc_hooks_t` 的 `load` / `store` 保存；当前实现是进程内静态
  存档，换成 NVM 只需替换这两个回调。
- `game/zc_game.h` 是平台接缝：`sfx` 已接到 `zc_audio`，`haptic` 已接到 PA20
  振动马达，`rand` 可替换为硬件随机源。
- AI 模式：标题停留 12 秒或战斗中 10 秒不触摸后接管；一旦接管，升级/结算菜单不再等待
  倒计时，升级立即随机选卡、结算立即重开。任何触摸或按键都会立刻交还手动控制。
- 独立 390x460 预览见 `user/app/zombie_cannon/`；黄山派部署仍以 `sift_watch` 为准，
  因为游戏源码随 `sift_watch` 一起导出。

## 声音

板端扬声器走芯片内部音频通路：`audprc`（16 kHz 单声道 PCM）→ `audcodec` **DAC1**
（`AU_DAC1P/N`）→ AW8155 功放（`PA_USING_AW8155`，PA42 使能）。`game/zc_audio.c`
在首次进入游戏时打开设备并启动一个高优先级 RT-Thread 音频线程，按 DMA 半缓冲回调
持续填充 320 个采样（20 ms）；`game/zc_synth.c` 用方波/三角/锯齿/正弦/噪声和包络
合成 17 种音效，和 HTML 版同一套事件 ID。离开 ZOMBIE 页面时关闭功放，回到游戏时
重新打开；静音按钮通过 codec mute 立即生效。

黄山派的喇叭是 **GH-1.25mm 外接 4Ω/8Ω 扬声器**，不是板载扬声器；同时确认核心板
`5-6`、`7-8`、`11-12` 三组功耗测试跳线帽已短接，否则音频功放可能没有供电。串口可以
发送 `zgame` 直接进入游戏并播放波次音效，便于确认喇叭通路。

PC 上可以先听合成器的离线渲染：

```text
.scratch/tmp/zc/zc_sfx_demo.wav
```

该文件由 `zc_synth.c` 直接渲染，不含板端 DAC/功放音染；真机音量由 codec 的
`AUDIO_CTL_SETVOLUME` 和 AW8155 增益决定。

## 手势

页面环顺序是 `WATCH → APPS → TIMER → STOPWATCH → WEATHER → SETTINGS`：

- 表盘拖动：沙漏区域拖动环视 3D 视角，沙漏区域外拖动倾斜沙漏；短距离或慢速拖动优先倾斜
- 左滑：下一页；右滑：上一页；快速滑动或长距离滑动优先切页
- 上滑：打开应用抽屉；下滑：回表盘
- 单击表盘（表头应用图标除外）翻转沙漏；应用页的按钮和开关正常响应
- 六轴：表盘朝下并保持约 160 ms，翻转一次沙漏；回到朝上后约 1.2 s 重新武装

没有 IMU 时不会响应翻转手势，沙漏排空后保持空态，不会自动翻回；`SIFT_IMU_FACE_DOWN_MG`
（默认 `550`）和 `SIFT_IMU_FACE_UP_MG`（默认 `-250`）按加速度计 z 轴单位为 mg 设置。
如果黄山派实物 z 轴方向相反，把这两个阈值对调即可。

## 本地预览

```bash
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch.json
python -I console/entrypoints/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch_zombie.json
```

390×450 像素设计预览在 `user/app/sift_watch/design/watch-app.html`，用浏览器直接打开；
`design/` 只放浏览器原型，不参与编译。

### 沙漏伪 3D（PSEUDO3D）

HTML 预览和板端 `sift_watch.c` 使用同一套低成本伪 3D：

- **点击**：单击表盘（表头应用图标除外）翻转一次沙漏，木架、玻璃和沙体一起播放约 680 ms
  的 X 轴 3D 旋转；转到 180° 时交换上下腔的沙量。
- **环视**：在沙漏区域拖动。左右拖动让视角绕沙漏转满 360°，上下拖动改变俯仰；在时钟/页脚
  区域滑动仍是切页，表头点击仍打开应用抽屉，避免两套手势互相抢占。
- **倾斜**：六轴、方向键和沙漏区域外的拖动仍驱动 roll/pitch，用于 HUD 和自动漂移显示。
- **沙体**：沙漏内部是 24×32×24 的三维体素网格，按玻璃旋转体裁掉外部；每个体素受重力下落，
  可沿 8 个斜向滑动，从颈部漏到下半腔。三维堆积会自然形成漏斗和锥形沙堆，能填满玻璃截面。
- **渲染**：只画至少有一个空邻居的表面体素，按投影深度装进 16 个桶，从远到近绘制；每个体素
  是一枚预生成的沙粒 sprite（底色 + 暗边 + 高光），尺寸按当前视角体素投影的最宽轴缩放到
  4–8 px，环视时相邻沙粒不会露出块状缝隙。不做逐粒排序、逐粒 3D 投影或全屏 alpha 合成。
- **3D 表现**：木架由 4 根立柱 + 2 个上下木盖盒组成，用正交投影、面法线剔除、按深度分前后
  两批绘制；翻转时面法线一起旋转。**分组按盒子中心深度**而不是最近的角点：一根立柱贯穿
  整个沙漏高度，按角点分组会在高俯仰时把后立柱误分到前层，画到沙上。
- **玻璃**：旋转体的每一行圆截面按 16 边形逐点投影。任何"轴对齐椭圆"都只在不翻转时正确，
  翻转和环视同时非零时投影椭圆的主轴会倾斜最多 83°，所以端面环也用投影多边形而不是
  解析椭圆。侧面**不做逐四边形填充**：颈部半径从 82 骤降到 17，四边形在屏幕上的投影会
  自交，扫描线填充会漏像素或重复混合，形成横带和竖梳；薄玻璃本来也主要靠轮廓和高光
  可见。现在侧面只画左右轮廓（外线 + 内侧 2 px 厚壁线）和一层 alpha 4 的剪影薄雾，
  端面用 16 边形半透明填充（按端面深度分前后两批），高光带由解析求出的镜面方向决定，
  随视角移动。玻璃、木架和沙体在环视、俯仰、翻转时共用一套 `project3` 几何。
- **沙粒**：sprite 尺寸对投影后的体素间距**向上取整**，取整不足会在沙粒之间留下黑点。
- **成本**：模拟约 18k 格、15 Hz；板端直接写 RGB565 canvas，渲染每帧扫描 18k 格做表面判断，
  再画约 2–4k 个缩放 sprite，外加约 80×450 次玻璃轮廓扫描判断。HTML 预览使用同样的体素和
  深度分桶，不依赖 WebGL。

两端的页面外壳、背景光晕和玻璃透明度仍有旧有差异，但沙漏的视角、翻转和 pitch 表现一致。
上板如果帧耗时吃紧，先按「注意」里的建议拆分静态背景和局部刷新，再用 `fps2` 实测。

## 黄山派导出

```bash
python -I chip-adapt/sifli/export.py sift_watch --force
LVGL_VERIFY_LOOP_APPS_DIR="$PWD/chip-adapt/exports/sift_watch/src/app" \
  python -I console/entrypoints/cli.py --lvgl 9.4 --scenario user/scenarios/sift_watch_zombie.json
```

`game/` 下的 `.c/.h` 会随 `sift_watch` 递归复制和编译；导出器按 LVGL 9.4 基线扫描，
不需要额外模板或资源声明。

导出后再执行：

```bash
cd chip-adapt/exports/sift_watch/project
scons --board=sf32lb52-lchspi-ulp -j8
```

## 板载六轴

应用在 LVGL 9.4 + SiFli 构建时，如果 `ACC_USING_LSM6DSL` 或 `CONFIG_ACC_USING_LSM6DSL`
被打开，会初始化 I2C3 上的 LSM6DSL 驱动（LSM6DS3TR-C 使用同一驱动族），读取加速度并用
首帧滤波值作为倾斜零点。导出模板 `chip-adapt/sifli/templates/project/proj.conf` 已带下面
三行，每次 export 都会写进导出的 `project/proj.conf`：

```ini
CONFIG_BSP_USING_I2C3=y
CONFIG_SENSOR_USING_6D=y
CONFIG_ACC_USING_LSM6DSL=y
```

`imu_update()` 对 ax/ay/az 做 alpha = 3/4 的一阶 EMA：按 40 ms 渲染节拍读取时只滞后
一个采样（约 40 ms），既能压掉单点毛刺，又不会让倾斜明显变慢。`SENSOR ZERO` 校零会同时
重置滤波状态和零点。角度按 60°/g（约 16.7 mg/度）映射：

```text
roll  = (filtered_x - base_x) * 60 / 1000   clamp ±45
pitch = (filtered_y - base_y) * 60 / 1000   clamp ±32
```

因此约 30° 的倾斜能得到接近 30° 的读数。表盘翻转仍用滤波后的 az 判断；黄山派这块板的
加速度计 z 轴朝屏幕内部，实测桌面朝上时 `az ≈ -1008 mg`，所以
`SIFT_IMU_FACE_DOWN_MG = 550`、`SIFT_IMU_FACE_UP_MG = -250`。
没有传感器驱动时，表盘使用自动漂移 + 方向键
倾斜，不会阻塞 UI；翻转手势和传感器倾斜都不可用。触摸由 `littlevgl2rtt_init("lcd")`
注册的 FT6146 pointer indev 提供。

## 物理按键与振动

SDK 构建（`LVGL_VERIFY_LOOP_EZIP_ASSETS`）里应用直接轮询 GPIO，不依赖 button 中间件：

- KEY1：`BSP_KEY1_PIN`（默认 34 / PA34）→ `sift_handle_key(LV_KEY_HOME)`，在应用页返回，
  表盘页不切页
- KEY2：`BSP_KEY2_PIN`（默认 43 / PA43）→ `sift_handle_key(LV_KEY_ENTER)`，确认/开始/打开
- 两键在 `board.conf` 中都是 active high；`rt_pin_mode(pin, PIN_MODE_INPUT_PULLDOWN)` 后
  按 20 ms 去抖、只在按下沿触发，轮询在 40 ms 的渲染定时器里
- 按下时串口打印 `[sift_watch] key1 press` / `[sift_watch] key2 press`，表盘底部短暂显示
  `KEY1` / `KEY2`，即使当前页面没有可切换的目标也有视觉反馈

振动马达按 PA20（`SIFT_VIBE_PIN`）配置为输出，按键、六轴翻转和切页时拉高约 25 ms，
由 `sift_tick_cb` 里的 `vibe_update()` 关断；板子没装马达也不会影响其他功能。headless
构建里按键扫描和振动都是空实现，不会改变本地预览行为。

## 性能与 EZIP

在板端用 `lv_tick_get()` 量过 `sift_render()`：表盘约 24–26 ms/帧；ZOMBIE 最初约
43 ms/帧（40 ms 定时器已经装不下），主要消耗是每帧约 1000 个 alpha 混合雾点加全屏
扫描线。ZOMBIE 在 390x450 圆角屏幕（`safe_inset=44`）上关闭这两项动态叠层，静态
背景仍保留在 PSRAM，帧耗时降到 24–30 ms；HTML/390x460 预览不受影响。

适合做图片/EZIP 的静态内容：

- 游戏 390x450 静态背景（目前已在 PSRAM 预渲染；EZIP 主要省 Flash，不省每帧 CPU）
- 标题画面、HUD 面板、沙袋/铁丝网、炮台静态件
- 4 种僵尸的 2 帧 normal/flash/silhouette 精灵
- 表盘静态星空/沙漏玻璃/木架、应用抽屉图标

当前游戏和表盘都写一整块 RGB565 canvas。EZIP 由 EPIC 在 `lv_image` 绘制时解压；
要把它变成每帧收益，需要把静态层拆成 `lv_image` 对象、动态元素用独立对象/局部刷新，
而不是继续往整屏 canvas 里画。直接往 framebuffer 贴图则应使用 **raw RGB565**（或
预渲染精灵缓存），EZIP 不能直接 memcpy 到 canvas。下一步如果还要压帧时间，优先做
静态层缓存/object 分层，而不是盲目加 EZIP。

## 注意

- 画布缓冲为 390x450x2 ≈ 351 KB。板端构建检测到 `app_mem.h` 时用
  `app_canvas_mem_alloc()` 从 PSRAM cache 分配；本地 headless 仍用 `lv_malloc()`，
  使用 16 MiB LVGL 堆，不受影响。`user/app/sift_watch/assets.json` 是 cache-only
  清单（`assets: {}` + `image_cache_psram_size: 2097152`），导出器把它写进
  `proj.conf`，同时容纳 351 KB 手表画布和 351 KB 游戏静态背景。
- 物理键由本应用直接 `rt_pin_read()` 轮询（见「物理按键与振动」），不走 SDK 的 button 中间件。
  换板后如果 `BSP_KEY1_PIN`/`BSP_KEY2_PIN` 没有定义，回退到 PA34/PA43；振动引脚固定为 PA20
  （`SIFT_VIBE_PIN`），换板需要确认马达确实接在该脚且为高电平驱动。
- 当前 `sift_render()` 每 40 ms 全量重绘 390x450 RGB565 canvas 并全屏 invalidate，追求的是开发效率
  和像素一致性，不是最小 CPU/带宽。上板如果帧耗时或内存吃紧，优先把静态背景、小时钟和沙漏拆成
  独立图层，只对动态区域做局部刷新；不要先把像素绘制换成另一套 UI 体系。
- 面板按 **44 px 圆角**处理：`sift_render()` 最后调用 `draw_panel_mask()` 把四个角涂成 `COL_INK`，
  HTML 预览使用同值的 `--panel-radius`。厂家 wiki 没有给圆角数值，这个值来自 1.85" 面板实物照片；
  如果上板发现实际圆角不同，同时调整 `SIFT_PANEL_RADIUS` 和 HTML 的 `--panel-radius`。底部提示已上移到
  y=419，顶部 SIFT/电池和底部状态行都在圆角安全区内。
