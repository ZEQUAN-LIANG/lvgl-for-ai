# 第三方许可声明

LVGL AI Tools 的 C engine 静态链接 LVGL 及其内置的 lodepng，并静态链接 zlib 与 libpng。
仓库包含 C engine 源码与 Python 控制层源码，但不包含 LVGL 源码树（`lvgl-src/`）或
PNG 编码器源码树（`third_party/`）；源码构建时以用户获取的源码树为准。

资源转换器（`core/assets.py`）额外随包内置 freetype-py 与 pypng；pypng 只在生成图片时使用。
FreeType 2.13.2 还作为 LVGL 运行时 TTF 加载库链接进 host engine（`LV_USE_FREETYPE=1`），
`libfreetype.dll` 会随 engine 和 host SDK 一起分发。

## LVGL

- 版本：源码构建支持 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3。
- 许可证：MIT
- 版权：Copyright (c) 2025 LVGL Kft
- 上游：<https://github.com/lvgl/lvgl>
- 完整文本：`licenses/LVGL-MIT.txt`（与 LVGL 源码树 `LICENCE.txt` 一致）

## lodepng

- 版本：LVGL 9.x 内置 `src/libs/lodepng`；LVGL 8.x 内置 `src/extra/libs/png`。
- 许可证：zlib
- 版权：随 LVGL 9.6 分发的 `LICENSE.txt` 为 Copyright (c) 2005–2018；同一树的
  `lodepng.c` 文件头写 2005–2023；8.x 文件头为 2005–2020。条款相同，均为 zlib。
- 用途：engine 用 lodepng 解码 reference PNG；完整帧与 snapshot 的 PNG 编码已改用
  libpng + zlib。
- 完整文本：`licenses/lodepng-zlib.txt`（取自 LVGL 9.6 的 `LICENSE.txt`）；源码构建时
  也可在对应 LVGL 树的 `src/libs/lodepng/LICENSE.txt`（9.x）或
  `src/extra/libs/png/lodepng.c` 文件头（8.x）中查看。

## zlib

- 版本：1.3.1（tag `v1.3.1`，commit `51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf`）
- 许可证：zlib
- 版权：Copyright (C) 1995-2022 Jean-loup Gailly and Mark Adler
- 上游：<https://github.com/madler/zlib>
- 用途：libpng 的 deflate 压缩；engine 静态链接。
- 完整文本：`licenses/zlib.txt`
- 获取：`python -I core/tools/fetch_png.py --repo-root .` 安装到 `third_party/zlib/`，
  源码树不随仓库提交。

## libpng

- 版本：1.6.44（tag `v1.6.44`，commit `f5e92d76973a7a53f517579bc95d61483bf108c0`）
- 许可证：PNG Reference Library License version 2
- 版权：Copyright (c) 1995-2024 The PNG Reference Library Authors；Copyright (c)
  2018-2024 Cosmin Truta；Copyright (c) 2000-2002, 2004, 2006-2018 Glenn
  Randers-Pehrson；Copyright (c) 1996-1997 Andreas Dilger；Copyright (c) 1995-1996
  Guy Eric Schalnat, Group 42, Inc.
- 上游：<https://github.com/pnggroup/libpng>
- 用途：engine 编码录制帧与 snapshot 的 PNG。
- 完整文本：`licenses/libpng.txt`
- 获取：`python -I core/tools/fetch_png.py --repo-root .` 安装到 `third_party/libpng/`，
  源码树不随仓库提交。

## freetype-py

- 版本：2.5.1（win_amd64 wheel，随包只复制 `freetype/` 包）
- 许可证：new/revised BSD
- 版权：Copyright (c) 2011-2014, Nicolas P. Rougier
- 上游：<https://github.com/rougier/freetype-py>
- 用途：资源转换器的 FreeType Python 绑定；只在生成字体 C 数组时使用。
- 完整文本：`licenses/freetype-py.txt`

## FreeType

- 版本：2.13.2（freetype-py 2.5.1 win_amd64 wheel 内置的 `libfreetype.dll`）
- 许可证：FreeType Project License（FTL）
- 版权：Copyright (C) 1996-2024 David Turner, Robert Wilhelm, and Werner Lemberg
- 上游：<https://freetype.org/>
- 用途：TTF/OTF/TTC 字形栅格化；生成字体 C 数组时使用，同时作为
  `LV_USE_FREETYPE` 的运行时库链接进 host engine 和 host SDK。
- 完整文本：`licenses/FreeType.txt`

## pypng

- 版本：0.20220715.0（随包只复制 `png.py`）
- 许可证：MIT
- 版权：Copyright (c) 2005-2022 David Jones 及 pypng contributors
- 上游：<https://gitlab.com/drj11/pypng>
- 用途：PNG 解码（含调色板、16-bit、隔行）；只在生成图片 C 数组时使用。
- 完整文本：`licenses/pypng.txt`

## lv_font_conv（算法参考）

- 版本：1.5.3
- 许可证：MIT
- 版权：Copyright (c) 2018 authors
- 上游：<https://github.com/lvgl/lv_font_conv>
- 用途：内置字体 emitter 的位图打包、字形度量与 cmap 优化参考；`lv_font_conv`
  本身不随本包分发，也不需要 Node.js。
- 完整文本：`licenses/lv_font_conv-MIT.txt`

## Python（宿主依赖）

- 发布包**不自带** Python，也不附带 Python 许可证文本；宿主机必须安装
  Python 3.9+ 并加入 PATH，其许可证以宿主安装为准。
- 资源转换用的 freetype-py / FreeType / pypng 见上文。

## SiFli 工具资产

- `sifli-tools` 资产包含 pyserial 3.5（BSD-3-Clause，文本在
  `chip-adapt/sifli/host/vendor/pyserial-3.5.LICENSE.txt`）和 xterm.js 5.3.0
  （MIT，文本在 `chip-adapt/sifli/host/web/vendor/xterm/LICENSE`）。
- 不包含 SiFli SDK、ARM 工具链、sftool 或固件；这些由用户按
  `chip-adapt/vendor/README.md` 安装，许可证以官方包为准。

## 构建期工具

- CMake、Ninja、GCC（MinGW-w64）、ccache：只在源码构建模式使用，各自许可证以本机
  安装为准。发布包不内置 GCC/CMake/Ninja，开箱即跑只使用预编译 engine。

## 用户模板资产

- `user/app/demo/demo_assets.h` 的 16×16 棋盘图片与位图字体由本仓库工具链生成并作为 C
  数组包含在源码中，随用户模板一起提供；不包含第三方字体或图片文件。

## 本工具自身

- LVGL AI Tools 自身源码使用仓库根目录 `LICENSE`（发布包内为 `licenses/LICENSE`）。
  本声明不改变任何第三方代码的许可证。
