# user/asset

`user/asset/` 是共享资源头的目录，只放编译期资源（C 数组、`lv_font_t`、
`lv_image_dsc_t` 等），由 `user/app/**/*.c` 直接 `#include`。

## 契约

- 本目录参与编译 include 路径：CMake 的 `LVGL_AI_USER_ASSET_DIR` 指向这里
  （开发仓库见 `core/engine/CMakeLists.txt`，发布包见
  `lvgl-ai-new/engine/CMakeLists.txt`）。
- 资源编译进二进制；工具没有运行时资源加载约定，不要依赖从磁盘读取 PNG 等文件。
- 单个应用专用的资源优先放在 `user/app/<name>/`；本目录放多个应用共享的头文件。
- `user/` 随发布包分发，本目录也随包分发；只有 `user/.trash/`（应用回收站）不随包分发。
- 修改资源头后必须走源码构建，不要用 `--no-build` 跑旧二进制。

## 当前内容

仓库当前没有共享资源头，本目录只保留本说明。现有示例资源在各自应用目录：

- `user/app/demo/demo_assets.h`
- `user/app/spectrum/spectrum_*.h`（由 `gen_spectrum_assets.py` 生成）

新增资源头时直接放进本目录即可；构建会自动加入 include 路径，不需要改
`CMakeLists.txt`。
