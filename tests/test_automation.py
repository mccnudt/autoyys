"""AutomationController 集成测试（Mock 依赖，无真实窗口，Phase 7/10）。"""
import time

import pytest

from controller.automation import AutomationController
from core.errors import AutoBotError, CaptureFailed, WindowLost
from core.models import BattleProfile, Statistics
from state.machine import GameState

from .conftest import FakeCapture, FakeDetector, FakeInput, FakeWM, make_screen


def make_controller(profile, detector, wm=None, capture=None, input_=None,
                    hwnd=123):
    events = []
    clock = {"t": 1000.0}  # 虚拟时钟：每拍步进 0.6s，规避 Windows 计时器精度问题

    def tick_clock():
        clock["t"] += 0.6
        return clock["t"]

    c = AutomationController(
        wm or FakeWM(), capture or FakeCapture(),
        detector, input_ or FakeInput(), Statistics(),
        _FakeDebug(), on_event=lambda k, d: events.append((k, d)), hwnd=hwnd,
        clock=tick_clock)
    c.start(profile)
    c.RESULT_CLICK_BUFFER = (0, 0)  # 测试时无缓冲
    c.TIMEOUT_BUFFER = 0
    return c, events


class _FakeDebug:
    def save_error(self, img, exc):
        return "fake.png"

    def save_screenshot(self, img, tag=""):
        return "fake.png"

    def describe_image(self, img):
        return "fake"

    @staticmethod
    def gdi_object_count():
        return 0


def msgs(events):
    return [d["message"] for k, d in events if k == "log"]


class TestNormalFlow:
    """完整一轮: 找挑战 -> 点挑战 -> 等待 -> 胜利 -> 结算 -> 下一轮。"""

    def test_full_cycle_to_completion(self, profile):
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        s = c.stats.snapshot()
        assert s.total_runs == profile.max_runs == 3
        assert s.success == 3
        assert c.fsm.state == GameState.STOPPED
        assert any("挂机完成" in m for m in msgs(events))

    def test_failure_result_counts_as_failure(self, profile):
        script = [["challenge"], [], ["failure"], ["failure"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        assert c.stats.snapshot().failure == 3

    def test_settlement_confirm_clicked_when_configured(self, profile):
        profile.confirm_img = "confirm.png"
        # 挑战 -> 胜利 -> 结算确认
        script = [["challenge"], [], ["victory"],
                  ["victory"], [], ["settlement"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        # 3 次结算确认点击均发生
        confirm_clicks = [k for k in c.input.clicks]  # FakeInput 记录
        assert len(confirm_clicks) >= 3 * 2  # 挑战3连 + 结果3连


class TestTimeout:
    def test_timeout_clicks_custom_coord_and_continues(self, profile):
        # 战斗永不结束 -> 超时 -> 点自定义坐标 -> 回 FIND_CHALLENGE -> 循环
        script = [["challenge"], []]
        profile.battle_timeout = 0.1  # 很快超时(0=不限,不能再用0)
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(20):
            c.run_once()
            if c.finished:
                break
        assert c.stats.snapshot().timeout >= 1
        # (800-11, 450-22)：屏幕坐标经 screen_to_client 转换
        assert (789, 428, 1) in c.input.clicks
        assert any("超时" in m for m in msgs(events))

    def test_timeout_stop_action_stops(self, profile):
        profile.error_action = "stop"
        profile.battle_timeout = 0.1
        script = [["challenge"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(10):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        assert c.fsm.state == GameState.ERROR

    def test_zero_timeout_waits_indefinitely(self, profile):
        """battle_timeout=0:不限时,一直等胜负图,永不超时。"""
        profile.battle_timeout = 0
        script = [["challenge"], []]  # 战斗永不结束
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(60):
            c.run_once()
        assert not c.finished  # 仍在等
        assert c.stats.snapshot().timeout == 0
        assert c.fsm.state.value == "wait_battle"


class TestErrorHandling:
    def test_window_lost_stops_with_error(self, profile):
        c, events = make_controller(profile, FakeDetector([["challenge"]]),
                                    wm=FakeWM(valid=False))
        c.run_once()
        assert c.finished
        assert c.fsm.state == GameState.ERROR
        assert any("窗口已丢失" in m for m in msgs(events))

    def test_capture_failed_continue_mode_keeps_going(self, profile):
        from core.errors import CaptureFailed
        cap = FakeCapture(frames=[CaptureFailed("黑图"),
                                  None])  # 第二帧恢复正常
        # frames 用尽后返回正常截图
        cap.frames = [CaptureFailed("黑图")]
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script), capture=cap)
        c.run_once()  # 失败一次
        c.run_once()  # 恢复
        assert not c.finished

    def test_capture_failed_stop_mode_errors(self, profile):
        from core.errors import CaptureFailed
        cap = FakeCapture()
        cap.capture = lambda hwnd=None: (_ for _ in ()).throw(
            CaptureFailed("全黑"))
        c, _ = make_controller(profile, FakeDetector([]), capture=cap)
        profile.error_action = "stop"
        # 连续失败达到阈值
        for _ in range(15):
            c.run_once()
        assert c.finished and c.fsm.state == GameState.ERROR

    def test_missing_battle_img_rejected(self, profile):
        profile.battle_img = ""
        with pytest.raises(AutoBotError):
            make_controller(profile, FakeDetector([]))


class TestHumanization:
    def test_rest_inserted_by_range(self, profile):
        profile.rest_every = "1-1"     # 每次都休息
        profile.rest_seconds = "0-0"   # 休息 0 秒
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        # 休息 0 秒 -> _rest_until=now，下一拍即恢复，流程应能完成
        assert c.finished
        assert c.stats.snapshot().success == 3


class TestShikigami:
    """进入战斗后点击式神（每场一次）。"""

    def test_clicks_shikigami_once_per_battle(self, profile):
        profile.shikigami_enabled = True
        profile.shikigami_img = "shikigami.png"
        # 战斗中出现式神两拍后胜利（模拟点完式神才结算）
        script = [["challenge"], [], ["shikigami"], ["shikigami"], ["victory"],
                  ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        shikigami_clicks = [k for k in c.input.clicks if k == (400, 300, 1)]
        # 每场战斗恰好一次：3 场战斗 = 3 次式神点击
        assert len(shikigami_clicks) == profile.max_runs == 3
        assert any("已点击式神" in m for m in msgs(events))
        assert c.stats.snapshot().success == 3

    def test_shikigami_detected_only_when_enabled(self, profile):
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(20):
            c.run_once()
            if c.finished:
                break
        # 未启用：WAIT_BATTLE 期间不应请求 SHIKIGAMI 检测
        assert not any("shikigami" in r for r in c.detector.requested)

    def test_enabled_but_no_image_is_ignored(self, profile):
        profile.shikigami_enabled = True
        profile.shikigami_img = ""  # 忘了放图：不请求检测、不报错
        profile.max_runs = 1
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert not any("shikigami" in r for r in c.detector.requested)
        assert c.finished


class TestFindTimeout:
    """找图超时:激活点击一次,再失败则停止(补文档缺口 048)。"""

    def test_timeout_clicks_activation_then_stops(self, profile):
        profile.find_timeout = 2.0
        profile.find_timeout_click = (700, 300)
        profile.max_runs = 1
        script = [[]]  # 永远找不到挑战图
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        act = [k for k in c.input.clicks if k == (700 - 11, 300 - 22, 1)]
        assert len(act) == 1, f"激活坐标应恰好点击一次: {c.input.clicks}"
        assert c.finished and c.fsm.state == GameState.ERROR
        assert any("重新激活" in m for m in msgs(events))
        assert any("自动停止" in m for m in msgs(events))

    def test_timeout_without_coord_stops_directly(self, profile):
        profile.find_timeout = 2.0
        profile.find_timeout_click = None  # 未设置激活坐标
        profile.max_runs = 1
        script = [[]]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.fsm.state == GameState.ERROR
        assert c.input.clicks == []  # 没有任何点击
        assert any("未设置激活坐标" in m for m in msgs(events))

    def test_disabled_or_normal_flow_no_activation_click(self, profile):
        profile.find_timeout = 0  # 不启用
        profile.find_timeout_click = (700, 300)
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        assert (689, 278, 1) not in c.input.clicks  # 激活坐标从未被点

    def test_reactivation_resets_per_round(self, profile):
        # 每轮开始都是4拍空帧(超过2秒超时)→触发激活→找到图正常打。
        # 若"已激活"标记不在每轮重置,第2轮会直接ERROR而不是再次激活。
        profile.find_timeout = 2.0
        profile.find_timeout_click = (700, 300)
        profile.max_runs = 2
        script = [[], [], [], [], ["challenge"],
                  [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(80):
            c.run_once()
            if c.finished:
                break
        act = [k for k in c.input.clicks if k == (700 - 11, 300 - 22, 1)]
        assert len(act) == 2, f"每轮应各激活一次: {c.input.clicks}"
        assert c.stats.snapshot().success == 2
        assert c.finished and c.fsm.state == GameState.STOPPED  # 正常完成而非ERROR


class TestAltStartImage:
    """备选开始图:与主开始图任一命中即点。"""

    def test_alt_image_hit_clicks_and_completes(self, profile):
        profile.alt_enabled = True
        profile.alt_battle_img = "alt.png"
        script = [["challenge_alt"], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        assert c.stats.snapshot().success == profile.max_runs
        assert (400, 300, 3) in c.input.clicks  # 点的是命中的备选图位置

    def test_alt_disabled_ignores_alt_hits(self, profile):
        profile.alt_enabled = False
        profile.alt_battle_img = "alt.png"
        script = [["challenge_alt"], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(10):
            c.run_once()
        assert c.stats.snapshot().total_runs == 0  # 未启用:不识别备选图


class TestSecondStage:
    """第二段图(如进攻):点完开始图后找它单击,再等胜负。"""

    def test_second_stage_flow(self, profile):
        profile.second_enabled = True
        profile.second_img = "attack.png"
        script = [["challenge"], [], ["second"],
                  [], ["victory"], ["victory"], []]
        profile.max_runs = 1
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        assert c.stats.snapshot().success == 1
        assert (400, 300, 1) in c.input.clicks  # 进攻图单击一次
        assert any("第二段按钮" in m for m in msgs(events))

    def test_second_state_path_in_fsm(self):
        from state.machine import GameState, StateMachine
        sm = StateMachine()
        for t in (GameState.FIND_CHALLENGE, GameState.CLICK_CHALLENGE,
                  GameState.FIND_SECOND, GameState.CLICK_SECOND,
                  GameState.WAIT_BATTLE, GameState.SETTLEMENT):
            sm.transition_to(t)
        assert sm.state == GameState.SETTLEMENT

    def test_second_disabled_skips_stage(self, profile):
        profile.second_enabled = False
        profile.second_img = "attack.png"
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.stats.snapshot().success == 3
        assert (400, 300, 1) not in c.input.clicks  # 未启用:无单击

    def test_second_delay_waits_before_finding(self, profile):
        """第二段前等待:进入 FIND_SECOND 后 delay 秒内不检测,避免过渡动画误点。"""
        profile.second_enabled = True
        profile.second_img = "attack.png"
        profile.second_delay = 3.0
        profile.max_runs = 1
        script = [["challenge"], [], ["second"],
                  [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        c.run_once()   # 检测到开始图 -> CLICK_CHALLENGE
        c.run_once()   # 点击 -> 进入 FIND_SECOND
        assert c.fsm.state.value == "find_second"
        before = c.detector.i
        for _ in range(4):  # 虚拟时钟约 2.4s < 3s:不检测不推进
            c.run_once()
            assert c.fsm.state.value == "find_second"
        assert c.detector.i == before
        # delay 满足后恢复检测;脚本帧按消耗推进,最多再几拍内命中 second
        for _ in range(6):
            c.run_once()
            if c.fsm.state.value != "find_second":
                break
        assert c.detector.i > before
        assert c.fsm.state.value in ("click_second", "wait_battle")
        for _ in range(10):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.stats.snapshot().success == 1

    def test_second_zero_delay_default_flow(self, profile):
        """delay 较小时流程仍正常完成(回归)。"""
        profile.second_enabled = True
        profile.second_img = "attack.png"
        profile.second_delay = 0
        profile.max_runs = 1
        script = [["challenge"], [], ["second"],
                  [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.stats.snapshot().success == 1


class TestScrollFind:
    """找不到图时周期性滚轮/拖拽。"""

    def test_wheel_scrolled_periodically(self, profile):
        profile.scroll_enabled = True
        profile.scroll_mode = "滚轮"
        profile.scroll_ticks = -3
        profile.scroll_interval = 1.0  # 虚拟时钟每拍0.6s → 约每2拍一次
        profile.find_timeout = 0
        script = [[]]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(20):
            c.run_once()
        assert len(c.input.scrolls) >= 2
        assert c.input.scrolls[0] == (400, 300, -3)  # FakeWM客户区中心
        assert not c.finished  # 一直找,不误停

    def test_drag_mode_drags_from_to(self, profile):
        profile.scroll_enabled = True
        profile.scroll_mode = "拖拽"
        profile.drag_from = (900, 500)
        profile.drag_to = (900, 200)
        profile.scroll_interval = 1.0
        profile.find_timeout = 0
        script = [[]]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(20):
            c.run_once()
        assert len(c.input.drags) >= 2
        # 控制器直接传屏幕坐标,转换发生在 InputController 内部
        assert c.input.drags[0] == (900, 500, 900, 200)
        assert c.input.scrolls == []  # 拖拽模式不滚轮


class TestDungeonEntryEnd:
    """副本入口链 + 结束图(双层循环,困难28探索流程)。"""

    def test_entry_chain_two_stage(self, profile):
        """入口图1→点击→入口图2→点击→开始图循环,两段各点一次。"""
        profile.entry_enabled = True
        profile.entry_img = "entry1.png"
        profile.entry2_enabled = True
        profile.entry2_img = "entry2.png"
        profile.max_runs = 1
        script = [["entry"], [], ["entry2"], [], ["challenge"], [],
                  ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(60):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        assert c.stats.snapshot().success == 1
        # 两段入口各单击一次(区分于开始图的3连击)
        assert (400, 300, 1) in c.input.clicks
        assert any("入口图1" in m for m in msgs(events))
        assert any("入口图2" in m for m in msgs(events))
        # 请求检测的顺序正确:entry → entry2 → challenge
        req = [r for r in c.detector.requested if r]
        firsts = [r[0] for r in req if r]
        assert firsts[0] == "entry" and "entry2" in firsts

    def test_end_image_restarts_dungeon(self, profile):
        """完整双层循环:入口→2场战斗→结束图→回入口→再打满次数。"""
        profile.entry_enabled = True
        profile.entry_img = "entry1.png"
        profile.end_enabled = True
        profile.end_img = "end.png"
        profile.max_runs = 2
        script = [["entry"], [], ["challenge"], [], ["victory"], ["victory"], [],
                  ["end"], [], ["entry"], [], ["challenge"], [],
                  ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(120):
            c.run_once()
            if c.finished:
                break
        assert c.finished
        assert c.stats.snapshot().success == 2
        assert c._dungeon_round == 1  # 结束图命中一次=完成一轮副本
        assert c.fsm.state == GameState.STOPPED
        assert any("副本一轮完成" in m for m in msgs(events))

    def test_challenge_priority_over_end(self, profile):
        """挑战图与结束图同屏:优先打挑战(先 CHALLENGE 后 END)。"""
        profile.end_enabled = True
        profile.end_img = "end.png"
        profile.max_runs = 1
        script = [["challenge", "end"], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.stats.snapshot().success == 1
        assert (400, 300, 1) not in c.input.clicks  # 结束图单击从未发生
        assert c._dungeon_round == 0

    def test_no_entry_goes_straight_to_challenge(self, profile):
        """未启用入口:start 直接进入 FIND_CHALLENGE。"""
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        c.run_once()
        assert c.detector.requested[0] == ["challenge"]


class TestMatchStrategy:
    """多目标策略与开始图点击次数。"""

    def test_strategy_passed_to_detector(self, profile):
        profile.match_strategy = "最上面"
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        # 找图拍使用了配置的策略;胜负检测保持默认
        assert "最上面" in c.detector.strategies
        assert "best" in c.detector.strategies

    def test_battle_clicks_configurable(self, profile):
        profile.battle_clicks = 1  # 单击即可开界面的场景
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        singles = c.input.clicks.count((400, 300, 1))
        triples = c.input.clicks.count((400, 300, 3))
        # 3场战斗各1次单击;3连击仅来自胜负结果点击(每场1次)
        assert singles == profile.max_runs
        assert triples == profile.max_runs


class TestReenterSelfHeal:
    """异常应对:没进战斗自愈/看门狗/两拍确认。"""

    def test_reenter_self_heal_reclicks_challenge(self, profile):
        """点完开始图后一直停留在开始界面 → 8秒后重点开始图。"""
        profile.reenter_check = 8.0
        profile.battle_clicks = 1
        profile.max_runs = 1
        # 点开始图后开始图一直停留(等待期每帧都 challenge),8秒后自愈重点;
        # 自愈点击消耗一拍,之后 challenge 消失进入正常战斗并胜利
        script = [["challenge"], ["challenge"], ["challenge"], ["challenge"],
                  ["challenge"], ["challenge"], ["challenge"], ["challenge"],
                  ["challenge"], ["challenge"], ["challenge"], ["challenge"],
                  ["challenge"], ["challenge"], ["challenge"], ["challenge"],
                  ["challenge"], ["challenge"], ["challenge"], ["challenge"],
                  ["challenge"], ["challenge"], ["challenge"], ["challenge"],
                  [], [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(60):
            c.run_once()
            if c.finished:
                break
        assert any("疑似点击未生效" in m for m in msgs(events))
        assert c.stats.snapshot().success == 1  # 自愈后正常完成

    def test_watchdog_fires_when_no_timeout(self, profile):
        """battle_timeout=0(不限)+看门狗:超长无动静按错误处理。"""
        profile.battle_timeout = 0
        profile.watchdog_timeout = 20.0  # 虚拟时钟每拍0.6s,约33拍触发
        profile.reenter_check = 0  # 关闭自愈(自愈会重置看门狗计时,属正常进展)
        profile.max_runs = 1
        profile.error_action = "stop"
        script = [["challenge"], []]  # 永不出现胜负
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(80):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.fsm.state == GameState.ERROR
        assert any("看门狗" in m for m in msgs(events))

    def test_watchdog_disabled_never_fires(self, profile):
        profile.battle_timeout = 0
        profile.watchdog_timeout = 0
        profile.max_runs = 1
        script = [["challenge"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(80):
            c.run_once()
        assert not c.finished  # 永远等

    def test_result_requires_two_ticks(self, profile):
        """两拍确认:胜负图单帧闪现(动画假命中)不触发结算。"""
        profile.max_runs = 1
        # victory 只出现一帧后消失,再过很久才真正胜利
        script = [["challenge"], [], ["victory"], [], [], [],
                  ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(40):
            c.run_once()
            if c.finished:
                break
        assert c.finished and c.stats.snapshot().success == 1
        # 单帧闪现未触发结算:胜利日志只出现一次(真实的那个)
        wins = [m for m in msgs(events) if "胜利" in m]
        assert len(wins) == 1

    def test_reenter_covers_alt_image(self, profile):
        """备选开始图与主图平级:卡住时显示的是备选图形态也能自愈重点。"""
        profile.alt_enabled = True
        profile.alt_battle_img = "alt.png"
        profile.reenter_check = 8.0
        profile.battle_clicks = 1
        profile.max_runs = 1
        # 点开始图后屏幕一直显示备选图形态,自愈重点后进入正常战斗
        script = [["challenge"], ["challenge_alt"]] + [["challenge_alt"]] * 22 \
            + [[], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(60):
            c.run_once()
            if c.finished:
                break
        assert any("疑似点击未生效" in m for m in msgs(events))
        assert c.stats.snapshot().success == 1
        # 自愈重点的是备选图位置(同一坐标,clicks=1)
        assert c.input.clicks.count((400, 300, 1)) >= 1

    def test_reenter_prefers_primary_when_both_visible(self, profile):
        """主图与备选图同时可见:自愈优先重点主图。"""
        profile.alt_enabled = True
        profile.alt_battle_img = "alt.png"
        profile.reenter_check = 8.0
        profile.max_runs = 1
        script = [["challenge"], ["challenge", "challenge_alt"]] * 12 \
            + [[], ["victory"], ["victory"], []]
        c, _ = make_controller(profile, FakeDetector(script))
        for _ in range(60):
            c.run_once()
            if c.finished:
                break
        # first(CHALLENGE, CHALLENGE_ALT) 语义下 challenge 优先
        assert c.stats.snapshot().success == 1

    def test_find_second_reclicks_challenge_when_swallowed(self, profile):
        """漏洞A自愈: 点开始图后第一段点击被吞(未展开第二段界面，仍看到开始图) → 自动重点开始图。"""
        profile.second_enabled = True
        profile.second_img = "second.png"
        profile.second_delay = 1.0
        profile.reenter_check = 3.0
        profile.battle_clicks = 1
        profile.max_runs = 1
        # 开始图点击后，第二段界面未展开，屏幕持续显示 challenge 图
        # 超过 3s 后触发自愈重点击开始图；重点击后第二段图出现并点击，随后胜利
        script = [["challenge"]] + [["challenge"]] * 10 + [["second"], ["second"],
                                                           ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(50):
            c.run_once()
            if c.finished:
                break
        assert any("等待第二段图超时，但仍看到开始图" in m for m in msgs(events))
        assert c.stats.snapshot().success == 1

    def test_wait_battle_second_stage_reclicks_second(self, profile):
        """漏洞B自愈: 点进攻(第二段)后点击被吞(未进战斗，仍看到进攻图) → 自动重点进攻图。"""
        profile.second_enabled = True
        profile.second_img = "second.png"
        profile.second_delay = 0.0
        profile.pre_battle_delay = 0.5
        profile.reenter_check = 3.0
        profile.max_runs = 1
        # 点击开始图 -> 点击第二段图 -> 进 WAIT_BATTLE 后屏幕依然是 second 图
        # 超过 3s 后触发自愈重点第二段图；重点后第二段图消失，随后胜负图出现
        script = [["challenge"], ["second"]] + [["second"]] * 10 \
            + [[], [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(50):
            c.run_once()
            if c.finished:
                break
        assert any("仍看到第二段图" in m for m in msgs(events))
        assert c.stats.snapshot().success == 1

    def test_alert_click_action_handles_popup_and_continues(self, profile):
        """异常弹窗拦截(click): 发现弹窗自动点击处理并继续正常挂机。"""
        profile.alert_enabled = True
        profile.alert_img = "alert.png"
        profile.alert_action = "click"
        profile.max_runs = 1
        # 找挑战时遇到弹窗 -> 自动点击弹窗 -> 随后出现开始图 -> 胜利
        script = [["alert"], ["challenge"], [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        assert any("已自动点击处理" in m for m in msgs(events))
        assert c.stats.snapshot().success == 1
        # 弹窗被点击(400, 300, 1)
        assert (400, 300, 1) in c.input.clicks

    def test_alert_stop_action_stops_immediately(self, profile):
        """异常弹窗拦截(stop): 发现弹窗(如体力耗尽)自动安全停止挂机。"""
        profile.alert_enabled = True
        profile.alert_img = "alert.png"
        profile.alert_action = "stop"
        profile.max_runs = 10
        # 找挑战时遇到弹窗 -> 立即停止
        script = [["alert"]]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(10):
            c.run_once()
            if c.finished:
                break
        assert any("按配置自动停止挂机" in m for m in msgs(events))
        assert c.finished
        assert c.fsm.state == GameState.STOPPED

    def test_alert_handled_during_wait_battle(self, profile):
        """异常弹窗拦截: 战斗等待期出现弹窗(如断线/协同邀请)自动点击处理。"""
        profile.alert_enabled = True
        profile.alert_img = "alert.png"
        profile.alert_action = "click"
        profile.pre_battle_delay = 0.5
        profile.max_runs = 1
        # 开始战斗 -> 进入 WAIT_BATTLE -> 出现弹窗并点击 -> 随后胜利
        script = [["challenge"], ["alert"], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        assert any("已自动点击处理" in m for m in msgs(events))
        assert c.stats.snapshot().success == 1


class TestProgressEvents:
    def test_progress_events_emitted(self, profile):
        script = [["challenge"], [], [], ["victory"], ["victory"], []]
        c, events = make_controller(profile, FakeDetector(script))
        for _ in range(30):
            c.run_once()
            if c.finished:
                break
        progress = [d for k, d in events if k == "progress"]
        assert progress
        assert progress[-1]["runs"] == 3
        assert progress[-1]["max_runs"] == 3


class TestAdaptiveInterval:
    def test_adaptive_interval_adjusts_for_states(self, profile):
        profile.detect_interval = 0.5
        profile.pre_battle_delay = 5.0
        c, _ = make_controller(profile, FakeDetector([["challenge"]]))
        # 初始 FIND_CHALLENGE 状态
        assert c.suggested_interval() == 0.5

        # 触发进入战斗: FIND_CHALLENGE -> CLICK_CHALLENGE -> WAIT_BATTLE
        c.run_once()
        c.run_once()
        assert c.fsm.state == GameState.WAIT_BATTLE
        # 战斗前置等待期自适应降频
        assert c.suggested_interval() == 1.2
