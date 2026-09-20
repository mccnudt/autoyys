"""TemplateMatcher：模板加载/缓存/匹配（TDD Phase 4）。

模板按 (路径, mtime) 缓存 —— 同一模板 0.5s 轮询一次时避免反复读盘解码。
多目标策略：同一界面出现多个相同按钮时(如结界突破的进攻列表),
可选 点最高分/最上面/最左边 的那一处(收集全部命中+NMS去重)。
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from core.models import MatchResult, ScreenType


def _imread_unicode(path: str) -> Optional[np.ndarray]:
    """Unicode 安全读图。

    cv2.imread 在 Windows 上无法读取含中文的路径(非 ASCII 代码页问题),
    而模板图文件名含模板名(如 999爬塔_victory.png),必须用
    np.fromfile + cv2.imdecode 代替。
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class TemplateRegistry:
    """模板图缓存：path -> (mtime, BGR ndarray)。文件被覆盖时自动失效重读。"""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, np.ndarray]] = {}

    def load(self, path: str) -> Optional[np.ndarray]:
        if not path or not os.path.exists(path):
            return None
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        tpl = _imread_unicode(path)
        if tpl is not None:
            self._cache[path] = (mtime, tpl)
        return tpl

    def clear(self) -> None:
        self._cache.clear()


_SHARED_REGISTRY: Optional[TemplateRegistry] = None


def get_shared_registry() -> TemplateRegistry:
    """获取进程级全局共享模板缓存(跨多标签页复用已解码的模板内存)。"""
    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is None:
        _SHARED_REGISTRY = TemplateRegistry()
    return _SHARED_REGISTRY


class TemplateMatcher:
    """cv2TM_CCOEFF_NORMED 模板匹配，返回目标中心点。"""

    def __init__(self, registry: Optional[TemplateRegistry] = None) -> None:
        self.registry = registry or get_shared_registry()

    def find(self, image: np.ndarray, template_name: str,
             threshold: float, strategy: str = "best",
             scales: Optional[Sequence[float]] = None) -> MatchResult:
        """在 image（BGR）中找 template_name（路径），返回 MatchResult。

        strategy: "best"=全局最高分(默认); "最上面"=命中里 y 最小;
                  "最左边"=命中里 x 最小(多目标用 NMS 去重)。
        scales: 尺度列表，如 (1.0, 0.9, 1.1, 0.8, 1.25)，支持跨分辨率等比自适应。
        未找到时 center=None、score=最高分。
        """
        st = ScreenType.NONE
        tpl = self.registry.load(template_name)
        if image is None or image.size == 0 or tpl is None:
            return MatchResult(st, None, 0.0)

        search_scales = [1.0] if not scales else ([1.0] + [s for s in scales if s != 1.0])
        best_match = MatchResult(st, None, 0.0)

        ih, iw = image.shape[:2]
        orig_th, orig_tw = tpl.shape[:2]

        for s in search_scales:
            if s == 1.0:
                cur_tpl = tpl
                tw, th = orig_tw, orig_th
            else:
                tw, th = int(orig_tw * s), int(orig_th * s)
                if tw < 5 or th < 5 or tw > iw or th > ih:
                    continue
                cur_tpl = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_LINEAR)

            if tw > iw or th > ih:
                continue

            res = cv2.matchTemplate(image, cur_tpl, cv2.TM_CCOEFF_NORMED)
            if strategy in ("最上面", "最左边"):
                ys, xs = np.where(res >= threshold)
                if len(xs) == 0:
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    if max_val > best_match.score:
                        best_match = MatchResult(st, None, float(max_val))
                    continue
                kept = []
                for x, y in sorted(zip(xs.tolist(), ys.tolist()),
                                   key=lambda p: res[p[1], p[0]], reverse=True):
                    if all(abs(x - kx) >= tw // 2 or abs(y - ky) >= th // 2
                           for kx, ky in kept):
                        kept.append((x, y))
                key = (lambda p: (p[1], p[0])) if strategy == "最上面" \
                    else (lambda p: (p[0], p[1]))
                kx, ky = min(kept, key=key)
                return MatchResult(st, (kx + tw // 2, ky + th // 2),
                                   float(res[ky, kx]))

            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                center = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
                return MatchResult(st, center, float(max_val))
            if max_val > best_match.score:
                best_match = MatchResult(st, None, float(max_val))

        return best_match
