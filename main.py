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


def _setup_excepthook() -> None:
    """生产级未捕获异常守护：将顶层崩溃堆栈记入 logs/crash.log，杜绝闪退无法排查。"""
    import traceback

    def _hook(exc_type, exc_val, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        try:
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(os.path.dirname(sys.executable)
                                   if getattr(sys, "frozen", False) else base_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "crash.log"), "a", encoding="utf-8") as f:
                f.write(f"\n--- 严重崩溃记录 ---\n{msg}\n")
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_val, exc_tb)

    sys.excepthook = _hook


def main() -> None:
    _setup_excepthook()
    _ensure_admin()
    _enable_dpi_awareness()
    import tkinter as tk
    from gui.app import App
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
