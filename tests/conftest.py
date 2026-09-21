"""测试公共夹具。"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

# 让 tests/ 可以直接 import 项目包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import BattleProfile  # noqa: E402
from state.machine import GameState  # noqa: E402


def make_screen(w=64, h=48, value=200) -> np.ndarray:
    """一张合法（非黑）的假截图。"""
    return np.full((h, w, 3), value, dtype=np.uint8)


@pytest.fixture
def profile() -> BattleProfile:
    return BattleProfile(
        name="测试配置",
        battle_img="battle.png",
        victory_img="victory.png",
        defeat_img="defeat.png",
        confirm_img="",
        max_runs=3,
        battle_timeout=10,
        pre_battle_delay=0,
        detect_interval=0,
        timeout_click=(800, 450),
    )


class FakeWM:
    """WindowManager Mock。valid 可控。"""

    def __init__(self, valid=True):
        self.valid = valid

    def is_window_valid(self, hwnd):
        return self.valid

    def is_window_minimized(self, hwnd):
        return False

    def get_windows(self, keyword=""):
        return []

    def get_client_rect(self, hwnd):
        return (0, 0, 800, 600)


class FakeCapture:
    """ScreenCapture Mock：按脚本依次返回截图或异常。frames 里的 None/异常会被抛出。"""

    def __init__(self, frames=None, valid=True):
        self.frames = list(frames or [])
        self.calls = 0
        self.valid = valid

    def capture(self, hwnd=None):
        self.calls += 1
        if self.frames:
            f = self.frames.pop(0)
            if isinstance(f, Exception):
                raise f
            return f
        return make_screen()

    def screen_to_client(self, hwnd, x, y):
        return (x - 11, y - 22)

    def client_size(self, hwnd):
        return (800, 600)


class FakeDetector:
    """ScreenDetector Mock：按预设脚本返回检测结果，耗尽后循环（模拟挑战按钮周期性出现）。

    script: list[list[str]]，每拍返回的命中类型列表，如 [["challenge"], [], ["victory"]]
    另记录每拍请求检测的类型，供断言"按需检测"。
    """

    FIELD = {"challenge": "challenge", "victory": "victory",
             "failure": "failure", "settlement": "settlement",
             "shikigami": "shikigami", "challenge_alt": "challenge_alt",
             "second": "second", "entry": "entry", "entry2": "entry2",
             "end": "end", "alert": "alert", "exclude": "exclude",
             "invite": "invite", "ready": "ready", "chest": "chest"}

    def __init__(self, script):
        self.script = list(script) or [[]]
        self.i = 0
        self.requested = []
        self.strategies = []  # 每拍的多目标策略
        self.matcher = _FakeMatcher()

    def detect(self, image, profile, types, strategy="best"):
        self.requested.append([t.value for t in types])
        self.strategies.append(strategy)
        hits = self.script[self.i % len(self.script)]
        self.i += 1
        from core.models import MatchResult, ScreenResult
        res = ScreenResult()
        allowed = {t.value for t in types}  # 只返回实际请求检测的类型
        for t in hits:
            if t not in allowed:
                continue
            m = MatchResult(ScreenType_of(t), (400, 300), 0.95)
            setattr(res, self.FIELD[t], m)
        return res


class _FakeMatcher:
    def __init__(self):
        self.chests = []

    def find_all(self, image, template_name, threshold=0.8):
        from core.models import MatchResult, ScreenType
        res = []
        for pt in self.chests:
            res.append(MatchResult(ScreenType.CHEST, pt, 0.9))
        return res


def ScreenType_of(t):
    from core.models import ScreenType
    return {"challenge": ScreenType.CHALLENGE,
            "victory": ScreenType.VICTORY,
            "failure": ScreenType.FAILURE,
            "settlement": ScreenType.SETTLEMENT,
            "shikigami": ScreenType.SHIKIGAMI,
            "challenge_alt": ScreenType.CHALLENGE_ALT,
            "second": ScreenType.SECOND,
            "entry": ScreenType.ENTRY,
            "entry2": ScreenType.ENTRY2,
            "end": ScreenType.END,
            "alert": ScreenType.ALERT,
            "exclude": ScreenType.EXCLUDE,
            "invite": ScreenType.INVITE,
            "ready": ScreenType.READY,
            "chest": ScreenType.CHEST}[t]


class FakeInput:
    """InputController Mock：记录点击/滚动/拖拽。"""

    def __init__(self):
        self.clicks = []
        self.scrolls = []
        self.drags = []
        self.is_background = True

    def click(self, x, y, clicks=1):
        self.clicks.append((x, y, clicks))

    def scroll(self, x, y, ticks):
        self.scrolls.append((x, y, ticks))

    def drag(self, x1, y1, x2, y2):
        self.drags.append((x1, y1, x2, y2))

    def screen_to_client(self, x, y):
        return (x - 11, y - 22)

    def bind(self, hwnd, screen_to_client=None):
        pass


class FakeDebug:
    """DebugManager Mock（注意必须实现控制器用到的全部方法）。"""

    def save_error(self, img, exc):
        return "fake.png"

    def save_screenshot(self, img, tag=""):
        return "fake.png"

    def describe_image(self, img):
        return "fake"

    @staticmethod
    def gdi_object_count():
        return 0


@pytest.fixture
def fake_wm():
    return FakeWM()


@pytest.fixture
def fake_input():
    return FakeInput()
