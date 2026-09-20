"""ScreenDetector：一帧截图 -> ScreenResult（TDD Phase 4）。

按需检测：只查当前 FSM 状态关心的模板，既省 CPU 也避免上一场景
残留图片（如胜利图没消失）误触发下一状态。
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from core.models import BattleProfile, ScreenResult, ScreenType
from vision.matcher import TemplateMatcher


class ScreenDetector:

    def __init__(self, matcher: Optional[TemplateMatcher] = None) -> None:
        self.matcher = matcher or TemplateMatcher()

    def detect(self, image: np.ndarray, profile: BattleProfile,
               types: Sequence[ScreenType],
               strategy: str = "best") -> ScreenResult:
        """检测 image 中 types 指定的画面元素(多目标策略由 strategy 决定)。"""
        res = ScreenResult()
        search = {
            ScreenType.ENTRY: (
                profile.entry_img, profile.entry_threshold, "entry"),
            ScreenType.ENTRY2: (
                profile.entry2_img, profile.entry2_threshold, "entry2"),
            ScreenType.END: (
                profile.end_img, profile.end_threshold, "end"),
            ScreenType.CHALLENGE: (
                profile.battle_img, profile.battle_threshold, "challenge"),
            ScreenType.CHALLENGE_ALT: (
                profile.alt_battle_img, profile.alt_battle_threshold,
                "challenge_alt"),
            ScreenType.SECOND: (
                profile.second_img, profile.second_threshold, "second"),
            ScreenType.VICTORY: (
                profile.victory_img, profile.victory_threshold, "victory"),
            ScreenType.FAILURE: (
                profile.defeat_img, profile.defeat_threshold, "failure"),
            ScreenType.SETTLEMENT: (
                profile.confirm_img, profile.confirm_threshold, "settlement"),
            ScreenType.SHIKIGAMI: (
                profile.shikigami_img, profile.shikigami_threshold,
                "shikigami"),
            ScreenType.ALERT: (
                profile.alert_img, profile.alert_threshold, "alert"),
        }
        for t in types:
            img_path, threshold, field = search[t]
            if not img_path:
                continue
            m = self.matcher.find(image, img_path, threshold, strategy)
            m.screen_type = t
            if m.matched:
                setattr(res, field, m)
        return res
