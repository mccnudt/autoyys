"""DebugManager：错误/识别失败现场保存（TDD Phase 3 Task 013 + Phase 10 Task 050）。

输出目录：logs/，文件名带标签与时间戳，自动清理超出上限的旧文件。
"""
from __future__ import annotations

import ctypes
import os
import time
from typing import Optional

import cv2
import numpy as np

from vision.capture import ImageValidator


class DebugManager:

    def __init__(self, log_dir: str, max_files: int = 20) -> None:
        self.log_dir = log_dir
        self.max_files = max_files
        os.makedirs(log_dir, exist_ok=True)

    @staticmethod
    def gdi_object_count() -> int:
        """当前进程 GDI 对象数（诊断截图环节句柄泄漏）。"""
        try:
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            user32 = ctypes.windll.user32
            user32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetGuiResources.restype = ctypes.c_uint
            return int(user32.GetGuiResources(k32.GetCurrentProcess(), 0))
        except Exception:
            return -1

    def save_screenshot(self, image: np.ndarray, tag: str = "debug") -> str:
        return self._save(image, tag)

    def save_match_result(self, image: np.ndarray, tag: str = "match") -> str:
        return self._save(image, tag)

    def save_error(self, image: Optional[np.ndarray], error: Exception,
                   tag: str = "error") -> str:
        name = f"{tag}_{type(error).__name__}"
        if image is None:
            return ""
        return self._save(image, name)

    def _save(self, image: np.ndarray, tag: str) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.log_dir, f"{tag}_{ts}.png")
        cv2.imwrite(path, image)
        self._cleanup()
        return path

    def _cleanup(self) -> None:
        files = sorted(
            f for f in os.listdir(self.log_dir) if f.endswith(".png"))
        for f in files[:-self.max_files] if len(files) > self.max_files else []:
            try:
                os.remove(os.path.join(self.log_dir, f))
            except OSError:
                pass

    @staticmethod
    def describe_image(image: np.ndarray) -> str:
        """人类可读的画面状态描述（全黑/正常），附 GDI 对象数。"""
        if not ImageValidator.is_valid(image):
            return f"画面无效/全黑 GDI对象={DebugManager.gdi_object_count()}"
        return f"画面正常 GDI对象={DebugManager.gdi_object_count()}"
