"""自动化过程中的领域异常（对应 TDD 第 7 节错误处理）。"""
from __future__ import annotations


class AutoBotError(Exception):
    """所有领域异常的基类。"""


class WindowLost(AutoBotError):
    """绑定的目标窗口已失效（关闭/崩溃）。"""


class CaptureFailed(AutoBotError):
    """截图失败或画面无效（全黑/尺寸为0）。"""


class BattleTimeout(AutoBotError):
    """战斗在 max_wait 内未出现胜负结果。"""


class UnknownScreen(AutoBotError):
    """画面长时间无法识别为任何已知状态。"""


class InvalidTransition(AutoBotError):
    """状态机收到非法状态转换。"""
