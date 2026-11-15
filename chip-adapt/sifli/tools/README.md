# SiFli tools

`SiFli-Host.exe` 是黄山派上位机的 Windows 双击入口，等价于：

```text
python -I chip-adapt/sifli/host/server.py --open
```

它只负责在 PATH 中找到 `pythonw.exe`（缺失时回退 `pyw.exe`）并启动 host，不探测端口、
不拼 URL、不碰串口。两者都找不到时会弹出错误提示。

启动器源码、图标和构建脚本在 `scripts/launchers/`。修改后从仓库根重新生成：

```bash
python -I scripts/launchers/build.py
```

`SiFli-Host.exe` 是构建产物，不要手改；图标由 `scripts/launchers/icons.py` 生成。
两个双击启动器都不进 Git，首次构建或清理后重新运行上面的命令即可。
