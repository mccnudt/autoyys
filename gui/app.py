"""App：主窗口 = 工具栏 + 标签页容器（自定 Phase 12，移植 YYSGUI 多标签）。"""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk

from .tab import BotTab

_STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "gui_state.json")


def _app_version() -> str:
    """从项目根的 VERSION 文件读版本号;读不到回退 1.0(打包后从 _MEIPASS/exe 旁找)。"""
    import sys
    bases = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    if getattr(sys, "frozen", False):
        bases.insert(0, getattr(sys, "_MEIPASS", "") or
                     os.path.dirname(sys.executable))
    for base in bases:
        try:
            with open(os.path.join(base, "VERSION"), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return "1.0"


class App:

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(f"Onmyoji AutoBot v{_app_version()} - 通用战斗模板挂机")
        self._restore_window_state()
        root.minsize(680, 500)

        toolbar = ttk.Frame(root, padding=(10, 6))
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="＋ 新建标签页",
                   command=self.new_tab).pack(side=tk.LEFT)
        ttk.Label(toolbar,
                  text="（每个标签页一个独立挂机会话，可绑定不同游戏窗口）",
                  foreground="gray", font=("", 9)).pack(side=tk.LEFT, padx=(10, 0))

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.tabs: list[BotTab] = []
        self.new_tab()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _restore_window_state(self) -> None:
        """恢复上次窗口尺寸/位置;无存档则默认最大化。"""
        try:
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            geo = state.get("geometry", "")
            if geo:
                self.root.geometry(geo)
                return
        except (OSError, ValueError):
            pass
        self.root.geometry("980x1000")
        try:
            self.root.state("zoomed")  # 默认最大化
        except Exception:
            pass

    def _save_window_state(self) -> None:
        try:
            state = {"geometry": self.root.geometry()}
            with open(_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except OSError:
            pass

    def new_tab(self) -> BotTab:
        # 沿用最大页号+1，避免与既有配置/日志文件冲突
        next_id = max((t.tab_id for t in self.tabs), default=0) + 1
        tab = BotTab(self.notebook, self, next_id)
        self.tabs.append(tab)
        self.notebook.add(tab, text=f"页{next_id}")
        self.notebook.select(tab)
        return tab

    def close_tab(self, tab: BotTab) -> None:
        if tab not in self.tabs:
            return
        if tab.worker and tab.worker.is_alive:
            tab.worker.stop()
            tab.worker.join(timeout=0.3)
        self.tabs.remove(tab)
        self.notebook.forget(tab)
        try:
            tab.destroy()
        except Exception:
            pass
        if not self.tabs:
            self.new_tab()  # 至少保留一页

    def on_close(self) -> None:
        """优雅退出：通知所有标签页后台 Worker 停止并等待安全交还资源，再销毁窗口。"""
        running_workers = [tab.worker for tab in self.tabs
                           if tab.worker and tab.worker.is_alive]
        for w in running_workers:
            w.stop()
        for w in running_workers:
            w.join(timeout=0.5)
        self._save_window_state()
        self.root.destroy()
