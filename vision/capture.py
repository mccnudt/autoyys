"""ScreenCapture：后台 PrintWindow 截客户区（TDD Phase 3）。

实现要点（来自 YYSGUI 实战经验，必须保留）：
- PW_RENDERFULLCONTENT：Win11 下 DWM 合成窗口必需；
- SelectObject 先保存旧位图、用完换回再 DeleteObject，否则 GDI 对象泄漏，
  长时间挂机后截图全黑；
- 前台模式（hwnd 为空）回退 pyautogui 全屏截图。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

import cv2
import numpy as np

from core.errors import CaptureFailed

_BITMAPINFOHEADER_FIELDS = [
    ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
    ("biClrImportant", wintypes.DWORD)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = _BITMAPINFOHEADER_FIELDS


class ScreenCapture:
    """capture(hwnd) -> BGR np.ndarray。

    hwnd=None 时使用前台 pyautogui 截全屏（虚拟屏幕）。

    DPI 缩放适配（高分屏 125%/150% 必需）：
    DPI-unaware 的模拟器窗口按逻辑尺寸渲染，而屏幕显示与 pyautogui 截屏
    都是物理像素。calibrate() 测量两者的比例 scale（物理/逻辑），
    capture() 随后把 PrintWindow 帧缩放到物理尺寸供模板匹配；
    点击坐标由 InputController 按同一比例折算回窗口逻辑坐标。
    """

    PW_RENDERFULLCONTENT = 0x00000002
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self.scale = (1.0, 1.0)  # (物理/逻辑) x, y；1.0=无缩放

    # ---- 对外接口 ----

    def capture(self, hwnd: Optional[int] = None) -> np.ndarray:
        if hwnd:
            img = self._capture_printwindow(hwnd)
            sx, sy = self.scale
            if (sx, sy) != (1.0, 1.0):
                img = cv2.resize(
                    img, (int(round(img.shape[1] * sx)),
                          int(round(img.shape[0] * sy))))
        else:
            import pyautogui
            import PIL.Image
            shot: PIL.Image.Image = pyautogui.screenshot()
            img = cv2.cvtColor(np.array(shot.convert("RGB")), cv2.COLOR_RGB2BGR)
        if not ImageValidator.is_valid(img):
            raise CaptureFailed("截图无效（尺寸为0或画面全黑）")
        return img

    def client_size(self, hwnd: int) -> tuple:
        rc = wintypes.RECT()
        self._user32.GetClientRect(hwnd, ctypes.byref(rc))
        return (rc.right - rc.left, rc.bottom - rc.top)

    def screen_to_client(self, hwnd: int, x: int, y: int) -> tuple:
        pt = wintypes.POINT(int(x), int(y))
        self._user32.ScreenToClient(hwnd, ctypes.byref(pt))
        return (pt.x, pt.y)

    def calibrate(self, hwnd: int) -> tuple:
        """测量 PrintWindow 尺寸与屏幕物理区域的比例。

        返回 (scale_x, scale_y)；两者都≈1 时重置为 1（无缩放）。
        屏幕对照失败（如多屏/最小化）时保持 1.0，行为与 YYSGUI 一致。
        """
        try:
            import pyautogui
            pw_w, pw_h = self.client_size(hwnd)
            x, y, _, _ = self._client_rect_screen(hwnd)
            shot = pyautogui.screenshot(region=(x, y, pw_w, pw_h))
            fg_w, fg_h = shot.size
            if (fg_w, fg_h) != (pw_w, pw_h) and pw_w > 0 and pw_h > 0:
                sx, sy = fg_w / pw_w, fg_h / pw_h
            else:
                sx = sy = 1.0
        except Exception:
            sx = sy = 1.0
        if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
            sx = sy = 1.0
        self.scale = (sx, sy)
        return self.scale

    def _client_rect_screen(self, hwnd: int) -> tuple:
        """客户区左上角的屏幕坐标 + 宽高。"""
        pt = wintypes.POINT()
        rc = wintypes.RECT()
        self._user32.ClientToScreen(hwnd, ctypes.byref(pt))
        self._user32.GetClientRect(hwnd, ctypes.byref(rc))
        return (pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top)

    # ---- 后台截图实现 ----

    def _capture_printwindow(self, hwnd: int) -> np.ndarray:
        # PrintWindow(PW_RENDERFULLCONTENT) 会把整窗（含标题栏等非客户区）
        # 画进 DC：若按客户区尺寸建位图，游戏内容会整体下移一个标题栏高度、
        # 底部被裁掉，模板匹配全部失配。因此按整窗尺寸建位图，
        # 再按客户区在窗口内的偏移裁剪出客户区画面。
        wr = wintypes.RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(wr))
        win_w, win_h = wr.right - wr.left, wr.bottom - wr.top
        pt = wintypes.POINT()
        self._user32.ClientToScreen(hwnd, ctypes.byref(pt))
        off_x, off_y = pt.x - wr.left, pt.y - wr.top
        cw, ch = self.client_size(hwnd)
        if win_w <= 0 or win_h <= 0 or cw <= 0 or ch <= 0:
            raise CaptureFailed(
                f"窗口尺寸无效 (win={win_w}x{win_h}, client={cw}x{ch})，"
                f"窗口可能已最小化")

        hdc_win = self._user32.GetDC(hwnd)
        hdc_mem = self._gdi32.CreateCompatibleDC(hdc_win)
        bmp = self._gdi32.CreateCompatibleBitmap(hdc_win, win_w, win_h)
        # 关键：先保存旧位图，用完换回后再删除，否则 DeleteObject 失败导致 GDI 泄漏
        old_bmp = self._gdi32.SelectObject(hdc_mem, bmp)
        try:
            self._user32.PrintWindow(hwnd, hdc_mem, self.PW_RENDERFULLCONTENT)
            bih = _BITMAPINFOHEADER()
            bih.biSize = ctypes.sizeof(bih)
            bih.biWidth = win_w
            bih.biHeight = -win_h  # 负值=自上而下
            bih.biPlanes = 1
            bih.biBitCount = 32
            bih.biSizeImage = win_w * win_h * 4
            buf = ctypes.create_string_buffer(bih.biSizeImage)
            self._gdi32.GetDIBits(hdc_mem, bmp, 0, win_h, buf,
                                  ctypes.byref(bih), 0)
            arr = np.frombuffer(buf, dtype=np.uint8).reshape(
                (win_h, win_w, 4))
            img = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            img = img[off_y:off_y + ch, off_x:off_x + cw]
            if img.size == 0:
                raise CaptureFailed("客户区裁剪结果为空")
            return img
        finally:
            self._gdi32.SelectObject(hdc_mem, old_bmp)
            self._gdi32.DeleteObject(bmp)
            self._gdi32.DeleteDC(hdc_mem)
            self._user32.ReleaseDC(hwnd, hdc_win)


class ImageValidator:
    """截图有效性校验（TDD Task 012）：非空、尺寸>0、非全黑。"""

    BLACK_MEAN_THRESHOLD = 3.0

    @staticmethod
    def is_valid(img: Optional[np.ndarray]) -> bool:
        if img is None or img.size == 0 or img.ndim != 3:
            return False
        if img.shape[0] <= 0 or img.shape[1] <= 0:
            return False
        if float(img.mean()) < ImageValidator.BLACK_MEAN_THRESHOLD:
            return False
        return True

    @staticmethod
    def is_black(img: np.ndarray) -> bool:
        return float(img.mean()) < ImageValidator.BLACK_MEAN_THRESHOLD
