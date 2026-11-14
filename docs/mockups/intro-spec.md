# intro 默认页设计规格（800 × 600）

本规格描述 `docs/mockups/intro.html` 的视觉与交互设计，以及把它移植为 LVGL 9.6 C 时的控件映射。真源是 HTML；`user/app/intro/intro.c` 已按本规格移植（LVGL 9.4+）。

## 0. 交付物

| 文件 | 说明 |
| --- | --- |
| `docs/mockups/intro.html` | 单文件 HTML/CSS/JS 演示，无外部依赖、无外部字体和图片，固定 800 × 600 |
| `docs/mockups/intro-preview.png` | READY 初始状态，800 × 600，Edge headless 截图 |
| `docs/mockups/intro-preview-active.png` | BUILDING / 50% 状态（`#step2`），用于检查运行态 |
| `docs/mockups/intro-preview-done.png` | EVIDENCE READY 完成态（`#done`） |
| `docs/mockups/intro-spec.md` | 本文件 |

截图使用 Edge headless、`--force-device-scale-factor=1`、`--window-size=800,600`。静态状态通过 URL hash 固定，不依赖动画播放到某一帧：

```text
intro.html             -> READY
intro.html#step2       -> BUILDING，50%
intro.html#step3       -> RECORDING，75%
intro.html#done        -> EVIDENCE READY
intro.html#play        -> 自动播放一次演示序列
```

## 1. 设计方向

关键词：深色开发者工具、测量仪表、克制的技术感。

设计不依赖大字号或装饰图片，层次由以下手段建立：

- 左侧「说明 + 四步卡片」与右侧 270° 仪表形成不对称布局；仪表是视觉中心。
- 青色 `#38BDF8` 用于品牌、当前步骤、进度和交互主按钮；绿色 `#34D399` 用于品牌在线点和完成态。颜色语义固定。
- 所有标签使用大写 + 字距；正文使用 14 号 sentence case。通过字距、颜色和留白建立层级，而不是依靠字重。
- 卡片、仪表、底部控制台形成三层结构：列表层、仪表层、操作层。
- 右侧仪表使用 270° 开口向下，底部留出缺口；四枚节点标在 25/50/75/100% 位置，中心显示步骤号和百分比。

整体避免：模糊玻璃、描边图标、彩色渐变堆叠、线框表单感。

## 2. 画布、栅格与层级

- 画布：`800 × 600`，不响应式缩放；HTML 在浏览器中居中显示。
- 页边距：左右 `48`，顶部从 `28` 开始，底部控制台距底 `34`。
- 左栏：`x = 48`，宽 `348`；右栏仪表区：`x = 422 .. 754`。
- 主分隔线：`y = 64`；左栏内容从 `y = 88` 开始；卡片区 `y = 190 .. 468`；底部控制台 `y = 490 .. 566`。
- 所有坐标和尺寸取整数像素。

创建顺序即层级（从下到上）：

1. 屏幕背景。
2. 顶部分隔线与品牌、环境标签、脉冲点。
3. eyebrow、主标题、副标题、左栏分隔线。
4. 四张步骤卡片（卡片内部再按背景、边框、spine、编号、分隔线、标题、正文、指示点、halo 的顺序）。
5. 仪表标题、步骤读数、角括号、外圈、arc、中心圆盘、节点。
6. 底部控制台：面板、状态点、状态、百分比、详情、进度条、分隔线、按钮。

## 3. 颜色令牌

| token | 值 | 用途 |
| --- | --- | --- |
| `bg-top` | `#0A1017` | 屏幕背景顶部 |
| `bg-bottom` | `#070B10` | 屏幕背景底部 |
| `hole` | `#080D13` | 仪表内圈底色（仅 HTML 用来模拟 arc 镂空） |
| `panel` | `#0B131C` | 面板基色 |
| `panel-deep` | `#091017` | 面板渐变底部 |
| `panel-active-a/b` | `#102433` / `#0B1822` | 活动卡片渐变 |
| `panel-done-a/b` | `#0A1617` / `#081012` | 完成卡片渐变 |
| `line` | `#182430` | 普通分隔线、卡片边框 |
| `line-2` | `#223447` | 备用描边 |
| `line-3` | `#2B3E52` | 待办节点、指示点描边 |
| `text` | `#F2F7FB` | 主文字、标题 |
| `muted` | `#93A6B9` | 副标题、卡名称 |
| `dim` | `#6B8198` | 次级标签、详情 |
| `faint` | `#40566B` | 装饰性微标签、待办编号 |
| `accent` | `#38BDF8` | 品牌、当前步骤、进度、主按钮 |
| `accent-soft` | `#7DD3FC` | 按钮 hover |
| `accent-deep` | `#1E5C7A` | next 状态描边 |
| `green` | `#34D399` | 品牌在线点、完成态 |
| `ink` | `#04131C` | 主按钮文字 |

补充状态色：

| 用途 | 值 |
| --- | --- |
| next 卡片边框 | `#1D394C` |
| next 卡片背景 A/B | `#0C1822` / `#091119` |
| next spine | `#245C78` |
| next 编号 | `#6FB9DC` |
| active 卡片分隔线 | `#1B3A4E` |
| active 卡片正文 | `#B5C7D6` |
| done 卡片边框 | `#1D3A34` |
| done 卡片分隔线 | `#17332D` |
| done 卡片标题 | `#BDCDD8` |
| done 卡片正文 | `#70879A` |
| done 圆盘边框 | `#1E4A3D` |
| 外圈 halo 描边 | `#17293A` |
| 角括号 | `#203244` |
| 控制台边框 | `#1B2A39` |
| 进度条轨道 | `#1B2A38` |
| 按钮 disabled 背景/文字 | `#102B3D` / `#6F8EA6` |

## 4. 字体与排版

只使用 LVGL 9.6 内置 Montserrat：

| 字号 | 实际行高 | HTML 字距（px） | LVGL 取整 | 出现位置 |
| --- | --- | --- | --- | --- |
| Montserrat 20 | 22 | 1.8（标题）/ 3.0（圆盘数字） | 2 / 3 | 主标题、圆盘 `01..04 / OK` |
| Montserrat 16 | 18 | 1.4 – 1.8 | 1 – 2 | 品牌、卡片标题、状态、按钮 |
| Montserrat 14 | 16 | 0.2 – 2.2 | 0 – 2 | 正文、微标签、百分比、详情 |

- LVGL 的 `text_letter_space` 是整数像素；C 代码按上表「LVGL 取整」列设置。HTML 的小数字距只是网页排版微调：副标题和卡片正文的 0.2 在 C 中取 0，标题 1.8 取 2，品牌 1.4 取 1，圆盘说明 2.2 取 2。
- HTML 的行高已经改成与 LVGL 内置字体一致：14 → 16、16 → 18、20 → 22。移植时把 label 放在表中给出的 top 坐标即可，不要再加行距。
- HTML 截图机器未安装 Montserrat，回退到 Segoe UI；最终 C 使用内置 Montserrat。两者字宽略有差异，本规格的文本区和左栏宽度已按较宽的 Montserrat 预留余量。
- 所有字号都 ≤ 20，不需要生成字体头文件。层次来自字距、颜色、大小写和位置。
- 如果后续确实需要更强的主标题，才生成 Montserrat 28；降级方案是保持 20 号、加 `text_letter_space` 到 2，并保留句点强调色。本设计默认不需要 28 号。
- 字重只用 regular。LVGL 内置 Montserrat 没有 bold；不要用 `-webkit-text-stroke` 或描边模拟粗体。
- UI 文本全部是 ASCII 英文，避免内置字体缺字。分隔符用 `/`，不用 `·`、`→`、`—`。

## 5. 坐标与尺寸

### 5.1 屏幕级元素

坐标为屏幕绝对坐标；`w/h` 省略表示由文本内容决定。

| 元素 | x | y | w | h | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| 品牌脉冲点 | 48 | 37 | 6 | 6 | 圆形，绿色 |
| 品牌 | 64 | 31 | — | 18 | 16 号，字距 1.4 |
| 环境 | 右边距 48 | 32 | — | 16 | `HEADLESS / LVGL 9.6`，右对齐 |
| 顶部分隔线 | 48 | 64 | 704 | 1 | `#182430` |
| 顶部分隔线强调段 | 48 | 63 | 24 | 2 | `#38BDF8`，opacity 90% |
| eyebrow 方块 | 48 | 95 | 5 | 5 | `#38BDF8` |
| eyebrow | 62 | 89 | — | 16 | `CLOSED-LOOP TOOLING` |
| eyebrow meta | 右边缘 396 | 89 | — | 16 | `04 STEPS`，右对齐 |
| 主标题 | 48 | 112 | — | 22 | `WRITE. RUN. SEE.` |
| 副标题 | 48 | 141 | — | 16 | `A closed loop for LVGL user apps.` |
| 左栏分隔线 | 48 | 170 | 348 | 1 | `#182430` |
| 左栏强调段 | 48 | 169 | 40 | 2 | `#38BDF8`，opacity 85% |
| 卡片容器 | 48 | 190 | 348 | 278 | 4 × 62 + 3 × 10 |
| 卡片 i | 48 | 190 + i×72 | 348 | 62 | i = 0..3 |
| 仪表标题 | 428 | 89 | — | 16 | `VERIFICATION LOOP` |
| 步骤读数 | 右边距 48 | 89 | — | 16 | 右对齐，`00 / 04` |
| 左上角括号 | 428 | 118 | 18 | 18 | 上 + 左边框 |
| 右下角括号 | 734 | 452 | 18 | 18 | 下 + 右边框 |
| 外圈 halo | 422 | 120 | 332 | 332 | 1px 圆环 |
| arc | 444 | 142 | 288 | 288 | 270°，线宽 8 |
| 中心圆盘 | 472 | 170 | 232 | 232 | 圆形面板 |
| 底部控制台 | 48 | 490 | 704 | 76 | 圆角 12 |

### 5.2 步骤卡内部（相对卡片内容区，已去掉 1px 边框）

卡片内容区从卡片外框向内 1px 开始；LVGL 中把卡片 `pad_all = 0`，子对象坐标即此表。

| 元素 | x | y | w | h | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| spine | 0 | 10 | 2 | 42 | 圆角 1 |
| 编号 | 14 | 23 | 22 | 16 | 14 号，字距 1.2 |
| 竖分隔线 | 44 | 11 | 1 | 40 | |
| 标题 | 58 | 11 | — | 18 | 16 号，字距 1.4 |
| 正文 | 58 | 33 | 246 | 16 | 14 号，单行 |
| 指示点 | 322 | 26 | 10 | 10 | 圆形，1px 边框 |
| 活动 halo | 315 | 19 | 22 | 22 | 指示点外扩 7px，1px 圆环 |

### 5.3 圆盘内部（相对圆盘内容区，已去掉 1px 边框）

圆盘内容区尺寸约 230 × 230，中心在 `(115, 115)`。

| 元素 | x | y | w | h | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| 步骤数字 | 76 | 77 | 80 | 22 | 居中，20 号，字距 3 |
| 强调短线 | 104 | 110 | 24 | 2 | |
| 步骤名 | 16 | 119 | 200 | 16 | 居中，14 号，字距 2.2 |
| 百分比 | 66 | 141 | 100 | 16 | 居中，14 号，字距 1.2 |

### 5.4 底部控制台内部（相对控制台内容区，已去掉 1px 边框）

| 元素 | x | y | w | h | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| 状态点 | 18 | 12 | 8 | 8 | 圆形 |
| 状态文字 | 34 | 7 | — | 18 | 16 号，字距 1.8 |
| 百分比 | 392 | 8 | 72 | 16 | 右对齐 |
| 详情 | 34 | 30 | — | 16 | 14 号，字距 1.2 |
| 进度条 | 34 | 55 | 430 | 4 | 圆角 2 |
| 竖分隔线 | 484 | 12 | 1 | 52 | |
| 按钮 | 500 | 16 | 184 | 44 | 圆角 8 |

### 5.5 仪表节点

arc 圆心 `(588, 286)`，半径 `144`，线宽 `8`。节点圆心在半径 `160` 的轨道上。节点框为 `8 × 8`：

| 进度 | 圆心 | 左上角 | 说明 |
| --- | --- | --- | --- |
| 25% | (440, 225) | (436, 221) | 左上 |
| 50% | (588, 126) | (584, 122) | 正上 |
| 75% | (736, 225) | (732, 221) | 右上 |
| 100% | (701, 399) | (697, 395) | 右下 |
| 起点 | (475, 399) | (473, 397) | 4 × 4，起点标记 |

角度约定：LVGL 的 0° 在 3 点钟方向、顺时针增加。`rotation = 135`，背景 arc `0 .. 270`，因此起点在左下、终点在右下，底部留出 90° 缺口。四枚节点的位置与 25/50/75/100% 的扫过角度严格对应；如果改 arc 尺寸或圆心，必须重算这四组坐标。

## 6. 组件与状态

### 6.1 步骤卡

| 状态 | 背景 | 边框 | spine | 编号 | 标题 | 正文 | 指示点 | halo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pending | `#0C141D → #091017` | 1px `#182430` | 透明 | `#40566B` | `#D8E3ED` | `#7F94A8` | 1px `#2B3E52` | 无 |
| next（仅 READY 的第一张） | `#0C1822 → #091119` | 1px `#1D394C` | `#245C78` | `#6FB9DC` | `#E7F2FA` | `#7F94A8` | 1px `#2E6B8B` | 无 |
| active | `#102433 → #0B1822` | 1px `#38BDF8` | `#38BDF8` | `#38BDF8` | `#F2F7FB` | `#B5C7D6` | 2px `#38BDF8`，内部 `#0B1822` | 1px `#38BDF8`，透明度脉冲 |
| done | `#0A1617 → #081012` | 1px `#1D3A34` | `#34D399` | `#34D399` | `#BDCDD8` | `#70879A` | 填充 `#34D399` | 无 |

- 卡片圆角 `10`，所有卡片间距 `10`。
- active 卡片额外加阴影：accent 色、垂直偏移约 `8–10`、模糊约 `28`、alpha 约 12%。
- 完成态保留绿色编号、绿色 spine、绿色指示点，形成「已走过」的痕迹；不要只把整张卡片变暗。
- active 状态只用 1px 边框 + 阴影 + 2px spine，不用 2px 全边框，避免视觉过重。

### 6.2 仪表节点

| 状态 | 外观 |
| --- | --- |
| pending | 8 × 8 圆，填充 `#070B10`，1px 边框 `#2B3E52` |
| next | 8 × 8 圆，填充透明，1px 边框 `#1E5C7A` |
| active | 8 × 8 圆，填充 `#38BDF8`，边框 `#38BDF8`；外圈 22 × 22 的 1px halo，透明度 0.18 ↔ 0.70 脉冲 |
| done | 8 × 8 圆，填充/边框 `#34D399` |

起点标记是 `4 × 4`：READY 时为 `#2E4358`，完成时绿色。它只作为轨道的零点，不参与步骤状态。

### 6.3 仪表中心圆盘

| 阶段 | 数字 | 短线 | 步骤名 | 百分比 |
| --- | --- | --- | --- | --- |
| READY / WRITING | `01` | accent | `WRITE` | 跟随 arc |
| BUILDING | `02` | accent | `BUILD` | 跟随 arc |
| RECORDING | `03` | accent | `RECORD` | 跟随 arc |
| READING | `04` | accent | `READ` | `100%` |
| EVIDENCE READY | `OK` | green | `EVIDENCE` | `100%` |

圆盘边框在完成态变为 `#1E4A3D`。`OK` 保持主文字色 `#F2F7FB`，成功语义由状态、arc、节点、短线、百分比共同表达。

### 6.4 底部控制台与按钮

| 状态 | 状态文字 | 详情 | 百分比 | 按钮 |
| --- | --- | --- | --- | --- |
| READY | `READY` accent | `CLICK TO PLAY THE LOOP` | `00%` dim | `RUN SCENARIO`，accent 实心，可点击 |
| WRITING | `WRITING` accent | `AUTHOR THE LVGL C INTERFACE` | `25%` accent | `RUNNING`，disabled |
| BUILDING | `BUILDING` accent | `BUILD THE REAL HEADLESS HOST` | `50%` accent | `RUNNING`，disabled |
| RECORDING | `RECORDING` accent | `REPLAY INPUT, RECORD FRAMES` | `75%` accent | `RUNNING`，disabled |
| READING | `READING` accent | `READ TIMELINE, DIFFS, LOGS` | `100%` accent | `RUNNING`，disabled |
| EVIDENCE READY | `EVIDENCE READY` green | `SESSION EVIDENCE IS READY` | `100%` green | `REPLAY`，绿色描边幽灵按钮，可点击 |

- 状态点：READY 与运行中为 accent 呼吸；完成态为绿色常亮。
- 进度条：`0..100`，轨道 `#1B2A38`，指示器 accent；完成态绿色。高 `4`，圆角 `2`。
- 主按钮：`184 × 44`，圆角 `8`，accent 实心，文字 `#04131C`，accent 阴影；运行中禁用；完成后改为透明背景 + 1px 绿色边框 + 绿色文字。
- 按钮点击区在屏幕 `x = 549..733, y = 507..551`；用于场景的 `click_at` 取命令按钮内的 `(640, 528)`。旧 `user/scenarios/intro.json` 里的 `(158, 552)` 不再命中。
- `READY` 状态的第一张卡片和第一个节点是 `next`，提示循环从 01 开始。

## 7. 状态机与时序

```text
READY
  click
    -> WRITING      t = 0 ms     arc 25%
    -> BUILDING     t = 900 ms   arc 50%
    -> RECORDING    t = 1800 ms  arc 75%
    -> READING      t = 2700 ms  arc 100%
    -> EVIDENCE READY t = 3600 ms
  click REPLAY
    -> 立即重置并重新进入 WRITING
```

- 每一步保持 `900 ms`。arc 与 progress bar 的填充动画 `550 ms`，在下一步开始前完成。
- 每个阶段的状态切换立即发生；只有 arc、bar、百分比和中心数字做过渡。
- 步骤映射固定：WRITING ↔ 01/WRITE/25%，BUILDING ↔ 02/BUILD/50%，RECORDING ↔ 03/RECORD/75%，READING ↔ 04/READ/100%，EVIDENCE READY ↔ OK/EVIDENCE/100%。
- 运行中按钮不可点击；完成态按钮变为 `REPLAY`，点击后从头播放。
- 完成态不自动回到 READY，保持证据就绪状态，直到用户点击 `REPLAY`。

## 8. 动效

| 动效 | 目标 | 参数 |
| --- | --- | --- |
| arc 填充 | arc indicator | 0 → 25/50/75/100，550 ms，ease-out cubic |
| 进度条 | bar indicator | 与 arc 同步，550 ms |
| 百分比文本 | 控制台/圆盘 | 跟随 arc 数值递增；C 中可在同一 anim 回调里更新 label |
| 品牌脉冲 | 6 × 6 绿点 | opacity 1.0 ↔ 0.35，2600 ms，ease-in-out，无限往返 |
| 状态点呼吸 | 8 × 8 点 | opacity 1.0 ↔ 0.35，1600 ms，ease-in-out，无限往返；完成态停止并常亮 |
| active 卡片 halo | 22 × 22 圆环 | opacity 0.18 ↔ 0.70，1200 ms，ease-in-out，无限往返 |
| active 节点 halo | 22 × 22 圆环 | 同上 |
| 中心数字切换 | 数字 label | opacity 0 → 1 + 向下 4px 回弹，260 ms；可选 |
| 卡片状态切换 | 背景/边框/文字 | HTML 中即时切换；C 中即时即可，不必补间 |

`prefers-reduced-motion` 在 HTML 中关闭脉冲；C 版本没有这个媒体查询，保持固定动画即可。

## 9. HTML/CSS 到 LVGL 9.6 映射表

| HTML / CSS | LVGL 9.6 | 关键 API / 说明 |
| --- | --- | --- |
| `.screen` 垂直渐变 | 屏幕对象 | `lv_screen_active()`；`lv_obj_set_style_bg_color()`、`bg_grad_color()`、`bg_grad_dir(obj, LV_GRAD_DIR_VER, 0)`；`bg_opa = LV_OPA_COVER` |
| `.rule` 1px 线 | `lv_obj_create` | 固定宽高，`bg_color`，`border_width = 0`，`radius = 0` |
| 品牌/标题 label | `lv_label_create` | `lv_label_set_text()`；`text_font = &lv_font_montserrat_14/16/20`；`text_color`；`text_letter_space` |
| 标题中的强调句点 | label recolor 或拆 label | 优先 `lv_label_set_recolor(label, true)` + `#38BDF8 .#`；若 `LV_USE_LABEL` 未开 recolor，则用三个 label 拼 `WRITE.` / `RUN.` / `SEE.`，或接受单色 |
| `.brand-mark` 与 `.brand-rest` | 同上 | 可用 recolor；或两个 label：`LVGL` accent + `VERIFY LOOP` text |
| `.brand-pulse` / `.status-dot` | `lv_obj_create` 圆形 | `radius = LV_RADIUS_CIRCLE`；`bg_opa`；`lv_anim` 动画 `style_opa` |
| `.card` | `lv_obj_create` | `size 348 × 62`；`radius 10`；`border_width 1`；`bg_opa COVER`；`bg_grad_dir VER`；`pad_all 0`；`scrollable false`；active 时 `shadow_width/opa/color/offset_y` |
| `.card-spine` | `lv_obj_create` | `2 × 42`，`bg_color` 随状态；`border_width 0`；放在卡片内容区 `(0,10)` |
| `.card-divider` | `lv_obj_create` | `1 × 40`，`bg_color` 随状态 |
| `.card-num` / `.card-title` / `.card-body` | `lv_label_create` | 14/16/14 号；字距；正文 `width 246` + `LV_LABEL_LONG_MODE_CLIP` |
| `.card-ind` | `lv_obj_create` 圆形 | `10 × 10`；`radius = LV_RADIUS_CIRCLE`；active 时 `border_width 2`；done 时填充绿色 |
| `.card-halo` | `lv_obj_create` 圆环 | `22 × 22`；`bg_opa TRANSP`；`border_width 1`；`border_color accent`；active 时用 `lv_anim` 动画透明度 |
| `.bracket` | `lv_obj_create` | `18 × 18`；`bg_opa TRANSP`；`border_width 1`；`border_side = TOP \| LEFT`（右下角为 `BOTTOM \| RIGHT`） |
| `.halo` 外圈 | `lv_obj_create` 圆形 | `332 × 332`；`bg_opa TRANSP`；`border_width 1`；`border_color #17293A` |
| `.arc-track` + `.arc-fill` | 单个 `lv_arc_create` | `size 288 × 288`；`lv_arc_set_rotation(arc, 135)`；`lv_arc_set_bg_angles(arc, 0, 270)`；`lv_arc_set_range(arc, 0, 100)`；`lv_arc_set_value(arc, 0)` |
| arc 主轨道 | `LV_PART_MAIN` | `arc_width 8`；`arc_color #1B2C3B`；`arc_rounded false`；`bg_opa TRANSP`；`border_width 0`；`pad_all 0` |
| arc 进度 | `LV_PART_INDICATOR` | `arc_width 8`；`arc_color #38BDF8`（done 时 `#34D399`）；`arc_rounded true` |
| arc 旋钮 | `LV_PART_KNOB` | `bg_opa TRANSP`；`border_width 0`；`pad_all 0`；并 `lv_obj_set_clickable(arc, false)` |
| arc 动画 | `lv_anim_t` | `exec_cb` 调用 `lv_arc_set_value`；550 ms；`lv_anim_path_ease_out`；同时更新百分比 label |
| `.disc` | `lv_obj_create` 圆形 | `232 × 232`；`radius = LV_RADIUS_CIRCLE`；`border_width 1`；`bg_grad_dir VER`；`shadow_width/opa/offset_y`；done 时边框 `#1E4A3D` |
| `.disc-number` / `.disc-caption` / `.disc-percent` | `lv_label_create` | 20/14/14 号；中心对齐可用固定宽度 + `LV_TEXT_ALIGN_CENTER`，或 `lv_obj_align` |
| `.node` | `lv_obj_create` 圆形 | `8 × 8`；`radius = LV_RADIUS_CIRCLE`；`border_width 1`；active 时加填充色 |
| `.node.active::after` | `lv_obj_create` 圆环 | `22 × 22`；`bg_opa TRANSP`；`border_width 1`；透明度脉冲 |
| 起点节点 | `lv_obj_create` 圆形 | `4 × 4`；无边框；颜色随状态 |
| `.console` | `lv_obj_create` | `704 × 76`；`radius 12`；`border_width 1`；`bg_grad_dir VER`；`shadow_width/opa`；`pad_all 0` |
| `.status` / `.detail` / `.console-percent` | `lv_label_create` | 16/14/14 号；字距 1.8/1.2/1.2；状态颜色随阶段切换 |
| `.bar` | `lv_bar_create` | `430 × 4`；`lv_bar_set_range(bar, 0, 100)`；`lv_bar_set_value(bar, value, LV_ANIM_ON)`；`lv_obj_set_style_anim_duration(bar, 550, 0)` 对齐 arc；`radius 2`；MAIN/INDICATOR 分别设颜色 |
| `.console-sep` | `lv_obj_create` | `1 × 52`；`bg_color #182838` |
| `.btn` | `lv_button_create` | `184 × 44`；`radius 8`；`bg_color accent`；`shadow_width/opa/color`；`lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, NULL)` |
| `.btn` running | `LV_STATE_DISABLED` | `add_state(btn, LV_STATE_DISABLED)`；背景 `#102B3D`、文字 `#6F8EA6`、无阴影 |
| `.btn.done` | 自定义 done 样式 | 透明背景；`border_width 1`；`border_color green`；文字绿色；按钮文字 `REPLAY` |
| `.btn` hover/pressed | `LV_STATE_HOVERED / PRESSED` | 可选；headless 场景 click_at 不依赖 hover，实现可省略 |
| 状态机 | `lv_timer_t` | 一个 900 ms timer；tick 时 step++；到第 4 步后 `intro_finish()` 并 `lv_timer_delete`；详见第 7 节 |
| 场景点击 | `click_at` | 按钮内取点 `(640, 528)`；旧坐标 `(158, 552)` 不再有效 |

## 10. 移植注意事项

1. **字号上限**：默认只用内置 14/16/20。主标题 20 号 + 1.8px 字距 + 句点强调色已经足够；不要为了「更像网页」临时引入 24+ 字体。如果必须放大，生成 Montserrat 28 的字体头文件并在 spec 中记录；降级方案是保持 20 号。
2. **行高**：内置 Montserrat 的 `line_height` 是 14 → 16、16 → 18、20 → 22。HTML 已按此设置，C 中直接使用表中 top 坐标，不要再套 18/20/26 的网页行高。
3. **容器 padding**：每张卡片、圆盘、控制台都要 `lv_obj_set_style_pad_all(obj, 0, 0)`，子坐标才与本文表格一致。子坐标是相对内容区（已去掉 1px 边框）。
4. **arc 不要拆成多段**：一个 `lv_arc` 同时提供主轨道和进度；不要用多个对象拼 270° 弧。`arc_rounded` 在主轨道为 false、indicator 为 true，才能得到设计里的平头轨道和圆头进度。
5. **旋钮必须隐藏**：`LV_PART_KNOB` 的 `bg_opa = TRANSP`、`border_width = 0`、`pad_all = 0`，并设置 `lv_obj_set_clickable(arc, false)`，否则场景点击或 pointer 事件可能改值。
6. **渐变只用垂直**：屏幕、卡片、圆盘、控制台都使用 `LV_GRAD_DIR_VER`。不要依赖 CSS 的 conic-gradient / mask；它们在 C 里对应的是 `lv_arc`。
7. **阴影是 LVGL shadow**：使用 `shadow_width`、`shadow_opa`、`shadow_color`、`shadow_offset_y`。不要尝试 blur、backdrop-filter、clip-path 或 SVG 效果。
8. **recolor 兜底**：`lv_label_set_recolor()` 依赖 `LV_USE_LABEL` 的 recolor 能力；如果配置关闭，主标题用单色，品牌拆成两个 label。不能让构建因为 recolor 失败。
9. **缓存无关的 pulse**：品牌点、状态点、active halo 的脉冲用 `lv_anim` 动 `style_opa`。完成态要停止状态点动画并设为不透明常亮；品牌点可以继续呼吸。
10. **状态点与按钮状态**：`RUNNING` 用 `LV_STATE_DISABLED`，并改 label 文本；`REPLAY` 用 done 样式。不要只改文字不改视觉，否则会和 disabled 状态混淆。
11. **时长对齐**：ARC/bar 550 ms，步骤 900 ms；900 ms 的等待足以让 550 ms 的填充结束。场景快照在每步 900 ms 后取，画面已稳定。
12. **对象命名**：建议保留 `intro_brand`、`intro_title`、`intro_card_write/build/record/read`、`intro_arc`、`intro_arc_value`、`intro_status`、`intro_progress`、`intro_button`、`intro_button_label` 等名字，并用 `app_obj_set_name()` 登记。工具没有对象树，名字只用于场景命中和证据阅读。
13. **ASCII 文本**：所有 UI 文案保持 ASCII，尤其是 `WRITE. RUN. SEE.`、`HEADLESS / LVGL 9.6`、`EVIDENCE READY`。不要引入内置字体没有的箭头或分隔符。
14. **点击坐标**：按钮内取点 `(640, 528)`。如果保留旧场景的 `(158, 552)`，会点在卡片/空白处，不会触发序列。
15. **完成态保持**：`EVIDENCE READY` 不自动回到 READY；保持绿色证据态直到 `REPLAY`。这与「会话证据」的语义一致：取证完成后画面应停留，便于录制和阅读。
16. **不引入后端**：HTML 的演示序列完全是前端 `setTimeout`；C 版本用 `lv_timer` + `lv_anim`。两者都不调用 CLI、网页或后端接口。

## 11. 与现有 `intro.c` 的差异

现有实现已经具备正确的结构（卡片、arc、bar、status、button、900 ms timer、`app_obj_set_name`），本设计主要改变视觉与信息层级：

- 卡片从「整行变亮」改为 `next / active / done` 三态；完成态保留绿色轨迹。
- arc 从 220 × 220 放大到 288 × 288，外圈 332 × 332，中心圆盘 232 × 232；增加 4 个节点和 1 个起点标记。
- 增加四角括号中的两枚（左上、右下）、外圈 halo、圆盘短线。
- 标题仍为 20 号，但增加字距和 accent 句点；副标题与 eyebrow 形成三级信息。
- 底部控制台从简单的 bar + label + 按钮改为一体化面板，包含状态点、状态、百分比、详情、进度条和按钮。
- 按钮点击区从 `(158, 552)` 移到 `(640, 528)`；场景需要同步修改。
- 完成态按钮从实心 accent 改为绿色描边幽灵按钮，状态点常亮。

## 12. 自查记录

- 截图尺寸：`800 × 600`，`--force-device-scale-factor=1`，无滚动条。
- READY、BUILDING、EVIDENCE READY 三种状态均已截图并肉眼检查；按钮完整，无裁切；4 张卡片和底部控制台在 800 × 600 内。
- 最小字号 14，主要信息 16/20；对比度以深色面板为背景，正文与微标签可读。
- 所有 UI 元素可映射到 LVGL 9.6 的 rect / label / button / bar / arc / anim / timer；没有图片、外部字体、blur、backdrop-filter、clip-path 或复杂 SVG。
