"""输入后端（TDD Phase 6 / PRD：前台真实鼠标、后台 PostMessage 两种实现）。

前台：pyautogui 缓动移动 + 随机偏移拟人化。
后台：PostMessage 客户区坐标点击/滚轮/拖拽，不动真实鼠标。

注意（实战坑）：WM_MOUSEWHEEL 的 lParam 是屏幕坐标（与点击消息的客户区
坐标不同），滚动前必须 ClientToScreen 转换。
"""
from __future__ import annotations

import ctypes
import random
import time
from ctypes import wintypes
from typing import Optional


class ForegroundInputBackend:
    """前台模式：移动真实鼠标并点击（屏幕坐标）。"""

    EASINGS = None  # 延迟初始化（需 pyautogui）

    def __init__(self) -> None:
        import pyautogui
        self._pyautogui = pyautogui
        ForegroundInputBackend.EASINGS = [
            pyautogui.easeInOutQuad, pyautogui.easeInOutElastic,
            pyautogui.easeInBack, pyautogui.easeInBounce,
        ]

    def move(self, x: int, y: int, duration: float = 0.5) -> None:
        dur, strat = self._human_move()
        self._pyautogui.moveTo(x, y, dur if duration is None else duration, strat)

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              clicks: int = 1, jitter: int = 30) -> None:
        if x is not None and y is not None:
            jx = x + random.randint(-jitter, jitter)
            jy = y + random.randint(-jitter, jitter)
            self.move(jx, jy, duration=random.uniform(0.3, 0.6))
            time.sleep(random.uniform(0.1, 0.3))
        else:
            jx = jy = None
        for i in range(clicks):
            self._pyautogui.click(jx, jy)
            if clicks > 1 and i < clicks - 1:
                time.sleep(random.uniform(0.08, 0.15))

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             duration: float = 0.5) -> None:
        self.move(x1, y1, 0.3)
        self._pyautogui.drag(x2 - x1, y2 - y1, duration=duration)

    def scroll(self, x: Optional[int], y: Optional[int], ticks: int) -> None:
        self._pyautogui.scroll(ticks, x=x, y=y)

    def _human_move(self):
        return (random.uniform(0.4, 0.8), random.choice(self.EASINGS))


class PostMessageInputBackend:
    """后台模式：向窗口客户区坐标投递鼠标消息，不占用真实鼠标。

    消息序列与 YYSGUI 验证过的实现保持一致（BUTTONDOWN -> 延时 -> BUTTONUP），
    不额外发送 WM_MOUSEMOVE。
    """

    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_MOUSEWHEEL = 0x020A
    MK_LBUTTON = 0x0001
    WHEEL_DELTA = 120

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self._user32 = ctypes.windll.user32
        # 显式声明 64 位参数类型，保证 wParam/lParam 大值/负值(如滚轮增量)正确
        self._user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.coord_scale = (1.0, 1.0)  # 物理/逻辑比例，点击坐标需除回逻辑空间

    # ---- 内部工具 ----

    def _lp(self, x: int, y: int) -> int:
        return (int(y) << 16) | (int(x) & 0xFFFF)

    def _to_logical(self, x: float, y: float) -> tuple:
        sx, sy = self.coord_scale
        if (sx, sy) != (1.0, 1.0):
            return int(round(x / sx)), int(round(y / sy))
        return int(x), int(y)

    def _client_to_screen(self, x: int, y: int) -> tuple:
        pt = wintypes.POINT(int(x), int(y))
        self._user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    # ---- 对外 ----

    def click(self, x: int, y: int, clicks: int = 1, jitter: int = 0) -> None:
        if jitter:
            x += random.randint(-jitter, jitter)
            y += random.randint(-jitter, jitter)
        x, y = self._to_logical(x, y)
        lparam = self._lp(x, y)
        for i in range(clicks):
            self._user32.PostMessageW(
                self.hwnd, self.WM_LBUTTONDOWN, 1, lparam)
            time.sleep(random.uniform(0.03, 0.06))
            self._user32.PostMessageW(self.hwnd, self.WM_LBUTTONUP, 0, lparam)
            if clicks > 1 and i < clicks - 1:
                # 连点节奏贴近前台(游戏过渡动画需要处理时间,连发会互相吞掉)
                time.sleep(random.uniform(0.25, 0.45))

    def scroll(self, x: int, y: int, ticks: int) -> None:
        """滚轮。x,y 为客户区坐标;WM_MOUSEWHEEL 的 lParam 必须是屏幕坐标。"""
        x, y = self._to_logical(x, y)
        sx, sy = self._client_to_screen(x, y)
        lparam = self._lp(sx, sy)
        delta = int(ticks) * self.WHEEL_DELTA
        wparam = (delta << 16) & 0xFFFFFFFF  # 负增量取模,避免符号扩展问题
        self._user32.PostMessageW(
            self.hwnd, self.WM_MOUSEWHEEL, wparam, lparam)

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             duration: float = 0.4, steps: int = 12) -> None:
        """后台拖拽:按下 -> 插值分步移动(带 MK_LBUTTON) -> 抬起。客户区坐标。"""
        x1, y1 = self._to_logical(x1, y1)
        x2, y2 = self._to_logical(x2, y2)
        self._user32.PostMessageW(
            self.hwnd, self.WM_LBUTTONDOWN, self.MK_LBUTTON, self._lp(x1, y1))
        step_time = max(duration / steps, 0.01)
        for i in range(1, steps + 1):
            xi = int(x1 + (x2 - x1) * i / steps)
            yi = int(y1 + (y2 - y1) * i / steps)
            self._user32.PostMessageW(
                self.hwnd, self.WM_MOUSEMOVE, self.MK_LBUTTON, self._lp(xi, yi))
            time.sleep(step_time)
        self._user32.PostMessageW(
            self.hwnd, self.WM_LBUTTONUP, 0, self._lp(x2, y2))
