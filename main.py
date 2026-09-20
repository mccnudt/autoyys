"""入口：UAC 提权 + DPI 感知 + 启动 GUI（YYSGUI 经验移植）。"""
from __future__ import annotations

import ctypes
import os
import sys


def _ensure_admin() -> None:
    """非管理员运行会触发 DPI 虚拟化，导致图像识别坐标错位，自动提权重启。

    设置环境变量 AUTOBOT_SKIP_UAC=1 可跳过提权（仅用于打包冒烟测试）。
    """
    if os.environ.get("AUTOBOT_SKIP_UAC"):
        return
    if not ctypes.windll.shell32.IsUserAnAdmin():
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{os.path.abspath(__file__)}"', None, 1)
            sys.exit(0)
        except Exception:
            pass  # 用户拒绝 UAC则继续（可能识别失败）


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _ensure_admin()
    _enable_dpi_awareness()
    import tkinter as tk
    from gui.app import App
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
