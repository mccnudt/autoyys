"""ScreenDetector：一帧截图 -> ScreenResult（TDD Phase 4）。

按需检测：只查当前 FSM 状态关心的模板，既省 CPU 也避免上一场景
残留图片（如胜利图没消失）误触发下一状态。
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

from core.models import BattleProfile, MatchResult, ScreenResult, ScreenType
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
            ScreenType.EXCLUDE: (
                profile.exclude_img, profile.exclude_threshold, "exclude"),
            ScreenType.INVITE: (
                profile.invite_img, profile.invite_threshold, "invite"),
            ScreenType.READY: (
                profile.ready_img, profile.ready_threshold, "ready"),
        }

        # 若开启排除图过滤且当前关注开始图，预先检索所有排除标记中心点
        exclude_points = []
        if (profile.exclude_enabled and profile.exclude_img and
                any(t in types for t in (ScreenType.CHALLENGE, ScreenType.CHALLENGE_ALT))):
            exclude_matches = self.matcher.find_all(
                image, profile.exclude_img, profile.exclude_threshold)
            exclude_points = [m.center for m in exclude_matches if m.matched and m.center]

        for t in types:
            img_path, threshold, field = search[t]
            if not img_path:
                continue

            if exclude_points and t in (ScreenType.CHALLENGE, ScreenType.CHALLENGE_ALT):
                candidates = self.matcher.find_all(image, img_path, threshold)
                valid = []
                for c in candidates:
                    if not c.center:
                        continue
                    cx, cy = c.center
                    if not any(math.hypot(cx - ex[0], cy - ex[1]) <= profile.exclude_distance
                               for ex in exclude_points):
                        valid.append(c)
                res.excluded_count += len(candidates) - len(valid)
                if valid:
                    if strategy == "最上面":
                        m = min(valid, key=lambda p: (p.center[1], -p.score))
                    elif strategy == "最左边":
                        m = min(valid, key=lambda p: (p.center[0], -p.score))
                    else:
                        m = max(valid, key=lambda p: p.score)
                else:
                    m = MatchResult(t, None, 0.0)
            else:
                m = self.matcher.find(image, img_path, threshold, strategy)

            m.screen_type = t
            if m.matched:
                setattr(res, field, m)
        return res
