"""FSM：游戏流程状态机（TDD Phase 5，对应 PRD 2.3 流程图）。

流程：
IDLE -> FIND_CHALLENGE -> CLICK_CHALLENGE -> WAIT_BATTLE -> SETTLEMENT -> FIND_CHALLENGE ...
异常路径：任意状态 -> ERROR -> STOPPED；WAIT_BATTLE 超时经 TIMEOUT_HANDLED 回 FIND_CHALLENGE。
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet

from core.errors import InvalidTransition


class GameState(Enum):
    IDLE = "idle"
    FIND_ENTRY = "find_entry"      # 副本入口图1查找(未配置则跳过整个入口段)
    CLICK_ENTRY = "click_entry"
    FIND_ENTRY2 = "find_entry2"    # 副本入口图2查找(未配置则跳过)
    CLICK_ENTRY2 = "click_entry2"
    FIND_CHALLENGE = "find_challenge"
    CLICK_CHALLENGE = "click_challenge"
    FIND_SECOND = "find_second"    # 第二段图查找(如结界突破"进攻"),未配置则跳过
    CLICK_SECOND = "click_second"
    WAIT_BATTLE = "wait_battle"
    SETTLEMENT = "settlement"
    CLICK_END = "click_end"        # 副本结束图点击,点完回入口段
    TIMEOUT_HANDLED = "timeout_handled"  # 超时坐标已点击，缓冲后回 FIND_CHALLENGE
    ERROR = "error"
    STOPPED = "stopped"


# 合法转换表：state -> 允许的目标集合
TRANSITIONS: Dict[GameState, FrozenSet[GameState]] = {
    GameState.IDLE: frozenset({
        GameState.FIND_ENTRY, GameState.FIND_CHALLENGE,
        GameState.ERROR, GameState.STOPPED}),
    GameState.FIND_ENTRY: frozenset({
        GameState.CLICK_ENTRY, GameState.ERROR, GameState.STOPPED}),
    GameState.CLICK_ENTRY: frozenset({
        GameState.FIND_ENTRY2, GameState.FIND_CHALLENGE,
        GameState.ERROR, GameState.STOPPED}),
    GameState.FIND_ENTRY2: frozenset({
        GameState.CLICK_ENTRY2, GameState.ERROR, GameState.STOPPED}),
    GameState.CLICK_ENTRY2: frozenset({
        GameState.FIND_CHALLENGE, GameState.ERROR, GameState.STOPPED}),
    GameState.FIND_CHALLENGE: frozenset({
        GameState.CLICK_CHALLENGE, GameState.CLICK_END,
        GameState.ERROR, GameState.STOPPED}),
    GameState.CLICK_CHALLENGE: frozenset({
        GameState.FIND_SECOND, GameState.WAIT_BATTLE,
        GameState.ERROR, GameState.STOPPED}),
    GameState.FIND_SECOND: frozenset({
        GameState.CLICK_SECOND, GameState.ERROR, GameState.STOPPED}),
    GameState.CLICK_SECOND: frozenset({
        GameState.WAIT_BATTLE, GameState.ERROR, GameState.STOPPED}),
    GameState.WAIT_BATTLE: frozenset({
        GameState.SETTLEMENT, GameState.TIMEOUT_HANDLED,
        GameState.ERROR, GameState.STOPPED}),
    GameState.TIMEOUT_HANDLED: frozenset({
        GameState.FIND_CHALLENGE, GameState.ERROR, GameState.STOPPED}),
    GameState.SETTLEMENT: frozenset({
        GameState.FIND_CHALLENGE, GameState.ERROR, GameState.STOPPED}),
    GameState.CLICK_END: frozenset({
        GameState.FIND_ENTRY, GameState.FIND_CHALLENGE,
        GameState.ERROR, GameState.STOPPED}),
    GameState.ERROR: frozenset({GameState.STOPPED}),
    GameState.STOPPED: frozenset(),
}


class StateMachine:
    """当前状态 + 合法转换验证 + 重置。"""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._state = GameState.IDLE

    @property
    def state(self) -> GameState:
        return self._state

    def transition_to(self, target: GameState) -> GameState:
        if target not in TRANSITIONS[self._state]:
            raise InvalidTransition(
                f"非法状态转换: {self._state.value} -> {target.value}")
        self._state = target
        return self._state

    def can_transition(self, target: GameState) -> bool:
        return target in TRANSITIONS[self._state]

    def update(self, detected: bool, has_result: bool,
               timed_out: bool) -> GameState:
        """根据检测结果推荐下一个状态（只推荐，不强制转换）。

        - FIND_CHALLENGE 中检测到开始图 -> CLICK_CHALLENGE
        - WAIT_BATTLE 中出现胜负 -> SETTLEMENT
        - WAIT_BATTLE 超时 -> TIMEOUT_HANDLED
        """
        s = self._state
        if s == GameState.FIND_CHALLENGE and detected:
            return GameState.CLICK_CHALLENGE
        if s == GameState.WAIT_BATTLE and has_result:
            return GameState.SETTLEMENT
        if s == GameState.WAIT_BATTLE and timed_out:
            return GameState.TIMEOUT_HANDLED
        return s
