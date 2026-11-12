# sift_watch

390x450 黄山派像素手表。整个界面由一块 RGB565 `lv_canvas` 程序化绘制，不依赖图片资源；兼容
LVGL 9.4（板端基线）与 9.6（本地预览）。

## 功能

- 待机表盘：实时时钟、日期、年份/电量占位、六轴重力沙漏、自动漂移、翻转手表翻转沙漏、暗待机
- 手势：拖动表盘倾斜沙漏，左/右滑切换环形页面，上滑打开应用抽屉，下滑回表盘；方向键也可倾斜
- 应用抽屉：TIMER / STOPWATCH / WEATHER / SETTINGS
- TIMER：1/3/5/10 分钟预设、开始/暂停/重置、结束提示
- STOPWATCH：60 点刻度、开始/停止、计次、重置
- WEATHER：离线样例天气、昼夜图标、°C/°F 切换
- SETTINGS：自动漂移、24H 时钟、暗待机、传感器校零；显示面板与器件信息

界面没有 PNG/图片资源：5×7 点阵字体、图标、沙漏和页面外壳全部由绘图原语直接写入
RGB565 `lv_canvas`。

## 手势

页面环顺序是 `WATCH → APPS → TIMER → STOPWATCH → WEATHER → SETTINGS`：

- 表盘拖动：直接倾斜沙漏；短距离或慢速拖动优先倾斜
- 左滑：下一页；右滑：上一页；快速滑动或长距离滑动优先切页
- 上滑：打开应用抽屉；下滑：回表盘
- 单击：只操作当前页面的按钮，不再翻转沙漏
- 六轴：表盘朝下并保持约 160 ms，翻转一次沙漏；回到朝上后约 1.2 s 重新武装

没有 IMU 时不会响应翻转手势，沙漏排空后保持空态，不会自动翻回；`SIFT_IMU_FACE_DOWN_MG`
（默认 `-550`）和 `SIFT_IMU_FACE_UP_MG`（默认 `250`）按加速度计 z 轴单位为 mg 设置。
如果黄山派实物 z 轴方向相反，把这两个阈值对调即可。

## 本地预览

```bash
python -I core/cli.py --lvgl 9.6 --scenario user/scenarios/sift_watch.json
```

## 黄山派导出

```bash
python -I chip-adapt/sifli/export.py sift_watch
LVGL_AI_USER_APP_DIR="$PWD/chip-adapt/sifli/sift_watch/src/app" \
  python -I core/cli.py --lvgl 9.4 --scenario user/scenarios/sift_watch.json
```

导出后再执行：

```bash
cd chip-adapt/sifli/sift_watch/project
scons --board=sf32lb52-lchspi-ulp -j8
```

## 板载六轴

应用在 LVGL 9.4 + SiFli 构建时，如果 `ACC_USING_LSM6DSL` 或 `CONFIG_ACC_USING_LSM6DSL`
被打开，会初始化 I2C3 上的 LSM6DSL 驱动（LSM6DS3TR-C 使用同一驱动族），读取加速度并用
首帧作为倾斜零点。默认导出工程没有打开该驱动，需要把下面三行加入导出的
`project/proj.conf` 后重新构建：

```ini
CONFIG_BSP_USING_I2C3=y
CONFIG_SENSOR_USING_6D=y
CONFIG_ACC_USING_LSM6DSL=y
```

没有传感器驱动时，表盘使用自动漂移 + 方向键倾斜，不会阻塞 UI；翻转手势和传感器倾斜
都不可用。触摸由 `littlevgl2rtt_init("lcd")` 注册的 FT6146 pointer indev 提供。

## 注意

- 画布缓冲为 390x450x2 ≈ 351 KB。板端构建检测到 `app_mem.h` 时用
  `app_canvas_mem_alloc()` 优先从 PSRAM cache 分配；本地 headless 仍用 `lv_malloc()`，
  使用 16 MiB LVGL 堆，不受影响。PSRAM cache 由导出的 `proj.conf` 的
  `IMAGE_CACHE_IN_PSRAM_SIZE` 提供。
- KEY1/KEY2 的 GPIO 扫描没有在本应用里实现；触摸、六轴和应用内返回键是可用的输入。需要物理键时，
  在导出工程中实现 SDK 的 `button_key_read()` 弱符号，并把键值映射到 `LV_KEY_ENTER/ESC/NEXT`。
- 当前 `sift_render()` 每 40 ms 全量重绘 390x450 RGB565 canvas 并全屏 invalidate，追求的是开发效率
  和像素一致性，不是最小 CPU/带宽。上板如果帧耗时或内存吃紧，优先把静态背景、小时钟和沙漏拆成
  独立图层，只对动态区域做局部刷新；不要先把像素绘制换成另一套 UI 体系。
- 面板按 **44 px 圆角**处理：`sift_render()` 最后调用 `draw_panel_mask()` 把四个角涂成 `COL_INK`，
  HTML 预览使用同值的 `--panel-radius`。厂家 wiki 没有给圆角数值，这个值来自 1.85" 面板实物照片；
  如果上板发现实际圆角不同，同时调整 `SIFT_PANEL_RADIUS` 和 HTML 的 `--panel-radius`。底部提示已上移到
  y=419，顶部 SIFT/电池和底部状态行都在圆角安全区内。
