"""WindowManager：扫描/验证 Windows 窗口，读取客户区尺寸（TDD Phase 2）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import List, Optional, Tuple

from core.models import WindowInfo


class WindowManager:
    """基于 user32 的窗口枚举与校验。仅依赖 ctypes，不引入 pywin32。"""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32

    # ---- 扫描 ----

    def get_windows(self, keyword: str = "") -> List[WindowInfo]:
        """所有标题含 keyword 的可见顶层窗口（keyword 为空返回全部）。"""
        res: List[WindowInfo] = []
        user32 = self._user32
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    title = buf.value
                    if not keyword or keyword in title:
                        w, h = self.get_client_rect(hwnd)[2:]
                        res.append(WindowInfo(hwnd, title, w, h))
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return res

    def get_window(self, hwnd: int) -> Optional[WindowInfo]:
        """按 hwnd 查窗口信息，失效返回 None。"""
        if not self.is_window_valid(hwnd):
            return None
        n = self._user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        self._user32.GetWindowTextW(hwnd, buf, n + 1)
        w, h = self.get_client_rect(hwnd)[2:]
        return WindowInfo(hwnd, buf.value, w, h)

    # ---- 校验 ----

    def is_window_minimized(self, hwnd: int) -> bool:
        return bool(self._user32.IsIconic(hwnd))

    def is_window_valid(self, hwnd: int) -> bool:
        # 仅校验 IsWindow，与 YYSGUI 验证过的行为一致：
        # IsWindowVisible 会误伤部分模拟器窗口形态（如置顶工具窗/多开托管窗）
        return bool(self._user32.IsWindow(hwnd))

    def get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """返回 (x, y, width, height)。窗口失效时宽高为 0。"""
        rc = wintypes.RECT()
        pt = wintypes.POINT()
        self._user32.ClientToScreen(hwnd, ctypes.byref(pt))
        if self._user32.GetClientRect(hwnd, ctypes.byref(rc)):
            return (pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top)
        return (0, 0, 0, 0)
