# ESP32 文档资料

本目录存放板卡官方文档的离线镜像，供本仓库开发与 AI 代理直接查阅，不参与构建。

## ESP32-C6-LCD-1.47

来源：[微雪文档 · ESP32-C6-LCD-1.47](https://docs.waveshare.net/ESP32-C6-LCD-1.47/)（中文站），
抓取日期 2026-11-18。覆盖该页面的全部 7 个子页面，页面内截图已下载到
`ESP32-C6-LCD-1.47/images/`，正文图片链接改为本地相对路径。

| 文件 | 页面 |
| --- | --- |
| `ESP32-C6-LCD-1.47/00-overview.md` | 产品简介、特性、接口引脚、参数 |
| `ESP32-C6-LCD-1.47/01-resources-and-documents.md` | 示例程序、原理图、芯片手册、工具、社区项目 |
| `ESP32-C6-LCD-1.47/02-arduino.md` | Arduino 开发环境、库版本、LVGL_Arduino 示例 |
| `ESP32-C6-LCD-1.47/03-esp-idf.md` | ESP-IDF 环境、VS Code 扩展、ESP-IDF 示例 |
| `ESP32-C6-LCD-1.47/04-firmware-flashing.md` | Flash Download Tool 烧录与擦除 |
| `ESP32-C6-LCD-1.47/05-faq.md` | 产品 FAQ |
| `ESP32-C6-LCD-1.47/06-technical-support.md` | 技术支持联系方式 |

补充文档：

- [`arduino-perf-monitor.md`](arduino-perf-monitor.md)：PERF TAPE 在 ESP32-C6 上的
  临时 Arduino 适配，含 ST7789 引脚、LVGL 9.6 配置、partial buffer、软件旋转
  flush、内存/Flash 数字和排障。
- [`../../../docs/media/esp32-c6-perf-monitor.mp4`](../../../docs/media/esp32-c6-perf-monitor.mp4)：
  `perf_monitor` 实机演示（无音频）。

说明：

- 正文由 Docusaurus 页面 HTML 转换而来，标题、表格、代码、列表、提示框保持原结构；
  少数富文本（如折叠块）以 `<details>` 原样保留。
- 页面里的下载链接（示例程序 zip、原理图 PDF、芯片手册等）在正文里仍指向外网；对应文件
  已另行下载到 `chip-adapt/vendor/esp32/`（不进 Git，清单与 SHA256 见
  `chip-adapt/vendor/README.md`）。
- 内容版权归微雪电子（Waveshare）所有，仅作本地开发参考资料；与官方在线页面不一致时，
  以官方页面为准。
