"""FSM 状态机测试（Phase 5）。"""
import pytest

from core.errors import InvalidTransition
from state.machine import GameState, StateMachine, TRANSITIONS


def test_initial_state_is_idle():
    sm = StateMachine()
    assert sm.state == GameState.IDLE


def test_normal_flow_transitions():
    sm = StateMachine()
    for target in (GameState.FIND_CHALLENGE, GameState.CLICK_CHALLENGE,
                   GameState.WAIT_BATTLE, GameState.SETTLEMENT,
                   GameState.FIND_CHALLENGE):
        sm.transition_to(target)
    assert sm.state == GameState.FIND_CHALLENGE


def test_invalid_transition_raises():
    sm = StateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition_to(GameState.SETTLEMENT)  # IDLE -> SETTLEMENT 非法


def test_any_state_can_stop():
    for start in (GameState.IDLE, GameState.FIND_CHALLENGE,
                  GameState.CLICK_CHALLENGE, GameState.WAIT_BATTLE,
                  GameState.SETTLEMENT, GameState.ERROR):
        assert GameState.STOPPED in TRANSITIONS[start], start


def test_stopped_is_terminal():
    assert not TRANSITIONS[GameState.STOPPED]


def test_update_recommends_next_state():
    sm = StateMachine()
    sm.transition_to(GameState.FIND_CHALLENGE)
    assert sm.update(detected=True, has_result=False,
                     timed_out=False) == GameState.CLICK_CHALLENGE
    sm.transition_to(GameState.CLICK_CHALLENGE)
    sm.transition_to(GameState.WAIT_BATTLE)
    assert sm.update(False, has_result=True, timed_out=False) \
        == GameState.SETTLEMENT
    assert sm.update(False, has_result=False, timed_out=True) \
        == GameState.TIMEOUT_HANDLED


def test_reset():
    sm = StateMachine()
    sm.transition_to(GameState.FIND_CHALLENGE)
    sm.reset()
    assert sm.state == GameState.IDLE


def test_wait_team_transitions():
    sm = StateMachine()
    # IDLE -> WAIT_TEAM -> WAIT_BATTLE -> SETTLEMENT -> WAIT_TEAM
    sm.transition_to(GameState.WAIT_TEAM)
    assert sm.state == GameState.WAIT_TEAM
    sm.transition_to(GameState.WAIT_BATTLE)
    assert sm.state == GameState.WAIT_BATTLE
    sm.transition_to(GameState.SETTLEMENT)
    assert sm.state == GameState.SETTLEMENT
    sm.transition_to(GameState.WAIT_TEAM)
    assert sm.state == GameState.WAIT_TEAM
    sm.transition_to(GameState.STOPPED)
    assert sm.state == GameState.STOPPED

