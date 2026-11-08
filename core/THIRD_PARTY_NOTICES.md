# 第三方许可声明

LVGL AI Tools 的 C engine 静态链接 LVGL 及其内置的 lodepng。仓库包含 C engine 源码与
Python 控制层源码，但不包含 LVGL 源码树（`lvgl-src/`）；源码构建时以用户放置的 LVGL
源码树为准。

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
- 用途：engine 用 lodepng 编码完整帧 PNG。
- 完整文本：`licenses/lodepng-zlib.txt`（取自 LVGL 9.6 的 `LICENSE.txt`）；源码构建时
  也可在对应 LVGL 树的 `src/libs/lodepng/LICENSE.txt`（9.x）或
  `src/extra/libs/png/lodepng.c` 文件头（8.x）中查看。

## Python 标准库

- 运行时使用系统 Python 3.9+ 的标准库；仓库不复制 CPython 或标准库文件。
- 许可证：Python Software Foundation License（以本机 Python 安装的许可为准）。

## 构建期工具

- CMake、Ninja、GCC（MinGW-w64）、ccache：只在源码构建模式使用，各自许可证以本机
  安装为准。

## 用户模板资产

- `user/app/demo/demo_assets.h` 的 16×16 棋盘图片与位图字体由本仓库工具链生成并作为 C
  数组包含在源码中，随用户模板一起提供；不包含第三方字体或图片文件。

## 本工具自身

- 仓库未为 LVGL AI Tools 自身源码声明单独许可证；如需对外分发，由仓库所有者补充
  `LICENSE`。本声明不改变任何第三方代码的许可证。
