<!-- 来源：https://docs.waveshare.net/ESP32-C6-LCD-1.47/FAQ/ 抓取日期：2026-11-18。内容版权归微雪电子（Waveshare）所有，此处仅为本地开发参考资料。 -->

# 产品 FAQ

<details>

<summary>问：使用过程中屏幕底部出现黑色阴影</summary>

答：使用时请务必将屏幕亮度控制在 50% 以内，切勿长时间满亮度运行。亮度过高会使屏幕温度升高，温度过高可能导致屏幕出现黑色阴影，影响正常显示。如显示出现异常，请将开发板静置一段时间后，再烧录较低亮度的程序使用。

</details>

<details>

<summary>问：希望程序得到更多库支持？</summary>

答：可以订阅该存储库并提交 issue 说明需求，工程师收到后会第一时间评估：[ESP32-display-support](https://github.com/waveshareteam/ESP32-display-support/tree/master)

</details>

<details>

<summary>问：模块下载程序后，重新下载，有时会出现无法连接串口，或者烧录失败的情况？</summary>

答：可长按 BOOT 按键，同时按下 RESET，然后松开 RESET，再松开 BOOT 按键，此时模块可进入下载模式，可解决大部分无法下载的问题。

</details>

<details>

<summary>问：模块出现一直复位的情况，从设备管理器查看识别状况会一闪一闪的？</summary>

答：这种情况可能是由于 Flash 空白导致 USB 口不稳定，可长按 BOOT 按键，同时按下 RESET，然后松开 RESET，再松开 BOOT 按键，此时模块可进入下载模式烧录固件（程序）即可解决该情况。

</details>

<details>

<summary>问： 程序首次编译超级慢怎么处理？</summary>

答：首次编译很慢属于正常情况，耐心等待即可

</details>

<details>

<summary>问： ESP-IDF 烧录成功串口显示“waiting for download...”怎么处理？</summary>

答：若开发板有复位键则按下复位键；若没有复位键，请重新上电

</details>

<details>

<summary>问： 找不到 AppData 文件夹怎么处理？</summary>

- 部分 AppData 文件夹是默认隐藏的，可以设置为显示。

- 英文系统：资源管理器->View->勾选“Hidden items”

- 中文系统：文件资源管理器->查看->显示->勾选“隐藏的项目”

</details>

<details>

<summary>问：怎么查看自己使用的 COM 口？</summary>

**Windows 系统**：

1. 通过设备管理器查看： 按下 Windows + R 键打开“运行”对话框； 输入 `devmgmt.msc` 并按回车键打开设备管理器； 展开“端口（COM 和 LPT）”部分，这里会列出所有的 COM 端口及其当前状态。

2. 使用命令提示符查看： 打开命令提示符（CMD）； 输入 `mode` 命令，这将显示所有 COM 端口的状态信息。

3. 查看硬件连接： 如果你已经连接了外部设备到 COM 口，通常设备会占用一个端口号，可以通过查看连接的硬件来确定使用的是哪个端口。

**Linux 系统**：

1. 使用 `dmesg` 命令查看： 打开终端。

2. 使用 `ls` 命令查看： 输入 `ls /dev/ttyS*` 或 `ls /dev/ttyUSB*` 来列出所有的串口设备。

3. 使用 `setserial` 命令查看： 输入 `setserial -g /dev/ttyS*` 来查看所有串口设备的配置信息。

</details>

<details>

<summary>问：如何使用 SquareLine Studio 设计界面？</summary>

参考 **[SquareLine Studio 使用教程](https://www.waveshare.net/wiki/Waveshare_SquareLine_Studio)**。

</details>

<details>

<summary>问：在使用 MAC 设备时，程序烧录失败？</summary>

答：安装 [MAC 驱动程序](https://www.waveshare.net/w/upload/0/04/CH34XSER_MAC.7z) 后重新烧录。

</details>

<details>

<summary>问：为什么代码没问题且成功烧录，运行后没有输出？</summary>

- 查看原理图，针对不同开发板的 Type-C 接口，对应代码处理输出不同：

  - USB 直出的开发板，支持 printf 函数打印输出，若想支持 Serial 函数打印输出则需要使能 USB CDC On Boot 功能或者 HWCDC 声明

  - UART 转 USB 的开发板，支持 printf 函数和 Serial 函数打印输出，无需使能 USB CDC On Boot

</details>

<details>

<summary>问：如何恢复出厂模式？</summary>

答：烧录出厂 bin 文件，参考 [Flash 固件的烧录与擦除](https://www.waveshare.net/wiki/ESP32-C6-LCD-1.47#Flash.E5.9B.BA.E4.BB.B6.E7.9A.84.E7.83.A7.E5.BD.95.E4.B8.8E.E6.93.A6.E9.99.A4)

</details>

<details>

<summary>问：屏幕问题</summary>

答：此类产品的屏幕与背板采用一体式贴合设计，为确保正常使用，建议避免自行拆卸或撬开胶层。若因拆解导致屏幕受损，将无法进行维修

</details>

<details>

<summary>问：没有 SD 卡可以使用我们的产品吗？</summary>

答：可以的，只是用不了有关 SD 卡部分的功能，其他没有影响

</details>
