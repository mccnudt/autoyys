"""InputController：统一输入入口 + 坐标映射（TDD Task 027/028）。

- 绑定 hwnd 时为后台模式：点击走 PostMessage（客户区坐标），
 并提供 screen_to_client 供配置里的屏幕坐标（如超时点击坐标）转换。
- 未绑定时为前台模式：点击走真实鼠标（屏幕坐标）。
"""
from __future__ import annotations

from typing import Optional

from input.backends import ForegroundInputBackend, PostMessageInputBackend


class InputController:

    def __init__(self, hwnd: Optional[int] = None) -> None:
        self._fg: Optional[ForegroundInputBackend] = None  # 惰性创建（避免无屏环境 import 开销）
        self.hwnd: Optional[int] = None
        self.backend: Optional[PostMessageInputBackend] = None
        self._screen_to_client = None  # callable(x, y) -> (x, y)
        self.bind(hwnd)

    @property
    def foreground(self) -> ForegroundInputBackend:
        if self._fg is None:
            self._fg = ForegroundInputBackend()
        return self._fg

    def bind(self, hwnd: Optional[int],
             screen_to_client=None) -> None:
        """绑定后台窗口；hwnd=None 切回前台模式。

        screen_to_client: 由截图层注入的坐标转换函数（避免循环依赖）。
        """
        self.hwnd = hwnd
        self._screen_to_client = screen_to_client
        self.backend = PostMessageInputBackend(hwnd) if hwnd else None

    @property
    def is_background(self) -> bool:
        return self.backend is not None

    def screen_to_client(self, x: int, y: int) -> tuple:
        """屏幕坐标 -> 当前绑定窗口客户区坐标；前台模式原样返回。"""
        if self.backend is not None and self._screen_to_client is not None:
            return self._screen_to_client(x, y)
        return (x, y)

    def click(self, x: int, y: int, clicks: int = 1) -> None:
        """点击。后台模式传客户区坐标，前台模式传屏幕坐标。"""
        if self.backend is not None:
            self.backend.click(x, y, clicks=clicks, jitter=8)
        else:
            self.foreground.click(x, y, clicks=clicks, jitter=8)

    def scroll(self, x: Optional[int], y: Optional[int], ticks: int) -> None:
        """滚轮。后台模式 x,y 为检测坐标系(自动转逻辑客户区再转屏幕 lParam)。"""
        if self.backend is not None:
            if self._screen_to_client is not None:
                x, y = self._screen_to_client(x, y)
            self.backend.scroll(x, y, ticks)
        else:
            self.foreground.scroll(x, y, ticks)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """拖拽。后台模式传检测坐标系(自动转逻辑客户区)。"""
        if self.backend is not None:
            conv = self._screen_to_client or (lambda a, b: (a, b))
            ax, ay = conv(x1, y1)
            bx, by = conv(x2, y2)
            self.backend.drag(ax, ay, bx, by)
        else:
            self.foreground.drag(x1, y1, x2, y2)
