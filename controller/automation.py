"""AutomationController：FSM 驱动的通用模板战斗（TDD Phase 7）。

设计：run_once() 是一拍（一个检测-决策-执行周期），由 Worker 按
detect_interval 反复调用。所有等待（前置动画/结算缓冲/拟人化休息）
都是"时间戳 + 提前返回"，不阻塞线程 —— 因此暂停/停止永远即时生效。

YYSGUI 移植的行为：
- 点击 3 连击 + 随机偏移（在 InputController 内）
- 战斗超时点击自定义屏幕坐标（后台模式自动转客户区坐标）
- 每 N 次休息 M 秒（N/M 取自范围字符串的随机值）
- 找不到开始图 error_action=continue/stop
"""
from __future__ import annotations

import random
import time
from typing import Callable, Optional

from core.errors import AutoBotError, BattleTimeout, CaptureFailed, WindowLost
from core.models import BattleProfile, ScreenType, Statistics
from debug.debug_manager import DebugManager
from input.controller import InputController
from state.machine import GameState, StateMachine
from vision.capture import ScreenCapture
from vision.detector import ScreenDetector
from window.manager import WindowManager

EventType = str


class AutomationController:
    """一次挂机会话的控制器。每次 start() 绑定一份 profile 重新开始。"""

    CONFIRM_WAIT = 15.0          # 结算确认图最长等待（秒）
    RESULT_CLICK_BUFFER = (2.0, 3.5)  # 结算点击后到下一轮的随机缓冲
    TIMEOUT_BUFFER = 3.0         # 超时点击后的载入缓冲（秒）

    def __init__(self, window_manager: WindowManager,
                 capture: ScreenCapture, detector: ScreenDetector,
                 input_controller: InputController, statistics: Statistics,
                 debug: DebugManager,
                 on_event: Optional[Callable[[EventType, dict], None]] = None,
                 hwnd: Optional[int] = None,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self.wm = window_manager
        self.capture = capture
        self.detector = detector
        self.input = input_controller
        self.stats = statistics
        self.debug = debug
        self.hwnd = hwnd
        self.on_event = on_event or (lambda kind, data: None)
        self._clock = clock or time.time  # 测试可注入虚拟时钟

        self.fsm = StateMachine()
        self.profile: Optional[BattleProfile] = None

        # 每拍上下文
        self._click_target: Optional[tuple] = None
        self._battle_started_at = 0.0
        self._result_pos: Optional[tuple] = None
        self._settlement_at = 0.0
        self._result_clicked = False
        self._confirm_clicked = False
        self._rest_until = 0.0
        self._rest_announced = False
        self._capture_fail_streak = 0
        self._finished = False
        self._state_entered_at = 0.0  # 当前状态进入时间（找图超时计时用）
        self._find_reactivated = False  # 找图超时是否已点击过激活坐标
        self._timeout_at = 0.0
        self._shikigami_clicked = False
        self._last_scroll_at = 0.0  # 上次滚动/拖拽时间（找图期间周期触发）
        self._dungeon_round = 0     # 副本轮数(入口-结束外层循环计数)
        self._end_clicked = False   # 结束图是否已点击(本拍缓冲用)
        self._end_clicked_at = 0.0
        self._result_seen = False   # 胜负图连续两拍确认(防动画假命中)
        self._reentered_count = 0   # 本场战斗"重点开始图"次数(防无限自愈)
        self._exclude_all_logged = False  # 候选全部排除时的日志节流标记

    # ---- 生命周期 ----

    def start(self, profile: BattleProfile) -> None:
        if profile.team_role in ("单人", "队长") and not profile.battle_img:
            raise AutoBotError("未设置战斗开始图，无法运行")
        self.profile = profile
        self.stats.reset()
        self.fsm.reset()
        self._reset_context()
        self._dungeon_round = 0  # 副本轮数(入口-结束循环计数)
        if profile.team_role == "队员":
            self._goto(GameState.WAIT_TEAM)
            self._log(f"▶ 开始挂机[队员模式] - {profile.name}，目标 {profile.max_runs} 次"
                      f"（{'后台' if self.input.is_background else '前台'}模式，等待发车）")
        elif profile.entry_enabled and profile.entry_img:
            self._goto(GameState.FIND_ENTRY)
            self._log(f"▶ 开始挂机 - {profile.name}，目标 {profile.max_runs} 次"
                      f"（{'后台' if self.input.is_background else '前台'}模式）")
        else:
            self._goto(GameState.FIND_CHALLENGE)
            self._log(f"▶ 开始挂机 - {profile.name}，目标 {profile.max_runs} 次"
                      f"（{'后台' if self.input.is_background else '前台'}模式）")

    def _reset_context(self) -> None:
        self._click_target = None
        self._battle_started_at = 0.0
        self._timeout_at = 0.0
        self._state_entered_at = 0.0  # 当前状态进入时间（找图超时计时用）
        self._find_reactivated = False  # 找图超时是否已点击过激活坐标
        self._shikigami_clicked = False
        self._result_pos = None
        self._settlement_at = 0.0
        self._result_clicked = False
        self._confirm_clicked = False
        self._rest_until = 0.0
        self._rest_announced = False
        self._capture_fail_streak = 0
        self._finished = False
        self._dungeon_round = 0
        self._end_clicked = False
        self._end_clicked_at = 0.0
        self._result_seen = False
        self._reentered_count = 0
        self._minimized_logged = False
        self._exclude_all_logged = False
        self._chest_clicked_count = 0

    @property
    def finished(self) -> bool:
        return self._finished or self.fsm.state in (
            GameState.STOPPED, GameState.ERROR)

    def suggested_interval(self) -> float:
        """根据当前状态与运行阶段提供自适应检测心跳(节约多开 CPU/GPU 占用)。"""
        if not self.profile:
            return 0.5
        base = self.profile.detect_interval
        if not getattr(self.profile, "adaptive_interval", True) or base < 0.2:
            return base
        st = self.fsm.state
        now = self._clock()
        # 1. 拟人化休息期间: 直接休眠至休息结束或最长 1.0 秒
        if now < self._rest_until:
            return min(1.0, max(base, self._rest_until - now))
        # 2. 战斗等待期: 动画前置等待(pre_battle_delay)或刚进战斗阶段自适应降频
        if st == GameState.WAIT_BATTLE:
            elapsed = now - self._battle_started_at
            if elapsed < self.profile.pre_battle_delay:
                return max(base * 2.5, 1.2)
            elif elapsed < 10.0 and self.profile.battle_timeout > 15.0:
                return max(base * 2.0, 1.0)
            return max(base * 2.0, 1.0)
        # 3. 找入口/找二段界面展开等待期: 适度降频
        elif st in (GameState.FIND_ENTRY, GameState.FIND_ENTRY2):
            delay = (self.profile.entry_delay if st == GameState.FIND_ENTRY
                     else self.profile.entry2_delay)
            if now - self._state_entered_at < delay:
                return max(base, 0.8)
        elif st == GameState.FIND_SECOND:
            if now - self._state_entered_at < self.profile.second_delay:
                return max(base, 0.8)
        # 4. 点击后小缓冲期: 等待画面切换，不必高频轮询
        elif st in (GameState.CLICK_CHALLENGE, GameState.CLICK_SECOND,
                    GameState.CLICK_ENTRY, GameState.CLICK_ENTRY2,
                    GameState.CLICK_END):
            return max(base, 0.5)
        return base

    # ---- 事件 ----

    def _log(self, msg: str) -> None:
        self.on_event("log", {"message": msg})

    def _emit_state(self) -> None:
        self.on_event("state", {"state": self.fsm.state})

    def _goto(self, target: GameState) -> None:
        """统一状态切换：记录进入时间戳；进入找图状态时重置找图计时/激活标记/滚动计时。"""
        self.fsm.transition_to(target)
        self._state_entered_at = self._clock()
        if target in (GameState.FIND_CHALLENGE, GameState.FIND_SECOND,
                      GameState.FIND_ENTRY, GameState.FIND_ENTRY2,
                      GameState.WAIT_TEAM):
            self._find_reactivated = False
            self._last_scroll_at = self._state_entered_at
        self._minimized_logged = False
        self._emit_state()

    def _emit_progress(self) -> None:
        p = self.profile
        self.on_event("progress", {
            "runs": self.stats.snapshot().total_runs,
            "max_runs": p.max_runs if p else 0,
            "stats": self.stats.snapshot(),
        })

    def _error(self, exc: AutoBotError) -> None:
        """统一错误处理：Log -> Debug截图 -> 按策略暂停或继续（TDD 第7节）。"""
        self.stats.increment_error()
        self._log(f"❌ {exc}")
        img = None
        try:
            img = self.capture.capture(self.hwnd) if self.hwnd else None
        except Exception:
            pass
        self.debug.save_error(img, exc)
        self._log(
            f"   已保存错误现场，{self.debug.describe_image(img) if img is not None else '截图失败'}")
        if isinstance(exc, WindowLost) or (
                self.profile and self.profile.error_action == "stop"):
            self._goto(GameState.ERROR)
        else:
            self._log("（continue 模式：跳过本次，继续尝试）")

    # ---- 主循环的一拍 ----

    def run_once(self) -> None:
        """执行一个检测-决策-执行周期（TDD 第 5 节 run_once 流程）。"""
        if self.profile is None or self.finished:
            return
        state = self.fsm.state
        try:
            # 1. 验证窗口
            if self.hwnd and not self.wm.is_window_valid(self.hwnd):
                raise WindowLost("绑定的游戏窗口已丢失（关闭/崩溃）")
            if self.hwnd and self.wm.is_window_minimized(self.hwnd):
                if not self._minimized_logged:
                    self._log("⚠ 窗口已最小化：后台挂机支持遮挡但不支持最小化，"
                              "恢复窗口(不遮挡也没关系)后自动继续")
                    self._minimized_logged = True
                return  # 静默等待恢复,不计错误
            # 2. 截图 + 3. 有效性校验（内部抛 CaptureFailed）
            img = self.capture.capture(self.hwnd)
            self._capture_fail_streak = 0
        except WindowLost as e:
            self._error(e)
            return
        except CaptureFailed as e:
            self._on_capture_failed(e)
            return
        except Exception as e:  # 截图层未知异常
            self._error(AutoBotError(f"截图异常: {e}"))
            return

        # 4. 按状态检测
        if state == GameState.FIND_ENTRY:
            self._tick_find_entry(img, which=1)
        elif state == GameState.CLICK_ENTRY:
            self._tick_click_entry(which=1)
        elif state == GameState.FIND_ENTRY2:
            self._tick_find_entry(img, which=2)
        elif state == GameState.CLICK_ENTRY2:
            self._tick_click_entry(which=2)
        elif state == GameState.FIND_CHALLENGE:
            self._tick_find_challenge(img)
        elif state == GameState.CLICK_CHALLENGE:
            self._tick_click_challenge()
        elif state == GameState.FIND_SECOND:
            self._tick_find_second(img)
        elif state == GameState.CLICK_SECOND:
            self._tick_click_second()
        elif state == GameState.WAIT_BATTLE:
            self._tick_wait_battle(img)
        elif state == GameState.TIMEOUT_HANDLED:
            self._tick_timeout_handled()
        elif state == GameState.SETTLEMENT:
            self._tick_settlement(img)
        elif state == GameState.CLICK_END:
            self._tick_click_end()
        elif state == GameState.WAIT_TEAM:
            self._tick_wait_team(img)

    # ---- 各状态处理 ----

    def _tick_find_entry(self, img, which: int) -> None:
        """副本入口图查找(which=1/2)。与 second 同款:delay 等待→检测→转点击。"""
        now = self._clock()
        delay = (self.profile.entry_delay if which == 1
                 else self.profile.entry2_delay)
        if now - self._state_entered_at < delay:
            return
        st = ScreenType.ENTRY if which == 1 else ScreenType.ENTRY2
        label = f"入口图{which}"
        types = [st]
        if self.profile.alert_enabled and self.profile.alert_img:
            types.append(ScreenType.ALERT)
        res = self.detector.detect(img, self.profile, types,
                                   strategy=self.profile.match_strategy)
        if self._handle_alert_if_present(img, res):
            return
        m = res.first(st)
        if m is not None:
            self._click_target = m.center
            self._goto(GameState.CLICK_ENTRY if which == 1
                       else GameState.CLICK_ENTRY2)
            return
        self._maybe_scroll(now)
        self._find_timeout_common(img, now, label)

    def _tick_click_entry(self, which: int) -> None:
        pos = getattr(self, "_click_target", None)
        if pos:
            self.input.click(pos[0], pos[1], clicks=1)
        if which == 1:
            self._log("已点击入口图1，等待界面载入...")
            if self.profile.entry2_enabled and self.profile.entry2_img:
                self._goto(GameState.FIND_ENTRY2)
            else:
                self._chest_clicked_count = 0
                self._goto(GameState.FIND_CHALLENGE)
        else:
            self._log("已点击入口图2，进入副本，等待界面载入...")
            self._chest_clicked_count = 0
            self._goto(GameState.FIND_CHALLENGE)

    def _tick_click_end(self) -> None:
        """副本结束图:第一拍点击,缓冲后回到入口段(下一轮副本)。"""
        now = self._clock()
        if not self._end_clicked:
            pos = getattr(self, "_click_target", None)
            if pos:
                self.input.click(pos[0], pos[1], clicks=1)
            self._end_clicked = True
            self._end_clicked_at = now
            return
        if now - self._end_clicked_at < self.profile.end_delay:
            return
        self._dungeon_round += 1
        runs = self.stats.snapshot().total_runs
        self._log(f"🏁 副本一轮完成(第{self._dungeon_round}轮, 累计{runs}场)，重新进入")
        if self.profile.entry_enabled and self.profile.entry_img:
            self._goto(GameState.FIND_ENTRY)
        else:
            self._goto(GameState.FIND_CHALLENGE)

    def _tick_find_challenge(self, img) -> None:
        # 拟人化休息窗口（休息期间冻结找图计时，休息不占超时额度）
        now = self._clock()
        if now < self._rest_until:
            if not self._rest_announced:
                self._log(f"😪 休息 {self._rest_until - now:.0f} 秒...")
                self._rest_announced = True
            self._state_entered_at = now
            return
        self._rest_announced = False

        # 达到目标次数 -> 完成
        runs = self.stats.snapshot().total_runs
        if runs >= self.profile.max_runs:
            self._log(f"✅ 挂机完成！共 {runs} 次")
            self._finished = True
            self._goto(GameState.STOPPED)
            return

        # 主开始图 + 备选开始图(勾选启用)，任一命中即点那张;
        # 启用结束图时顺带检测,挑战优先(同屏时先打完这场再出副本)
        types = [ScreenType.CHALLENGE]
        if self.profile.alt_enabled and self.profile.alt_battle_img:
            types.append(ScreenType.CHALLENGE_ALT)
        if self.profile.end_enabled and self.profile.end_img:
            types.append(ScreenType.END)
        if self.profile.alert_enabled and self.profile.alert_img:
            types.append(ScreenType.ALERT)
        res = self.detector.detect(img, self.profile, types,
                                   strategy=self.profile.match_strategy)
        if self._handle_alert_if_present(img, res):
            return
        # 挑战目标优先级：若开启备选图且开启 Boss 优先，先看 CHALLENGE_ALT (首领 Boss)
        if self.profile.boss_priority and self.profile.alt_enabled and self.profile.alt_battle_img:
            m = res.first(ScreenType.CHALLENGE_ALT, ScreenType.CHALLENGE)
        else:
            m = res.first(ScreenType.CHALLENGE, ScreenType.CHALLENGE_ALT)
        if m is not None:
            if getattr(res, "excluded_count", 0) > 0:
                self._log(f"🛡 已根据排除标记跳过 {res.excluded_count} 个已失败目标")
            self._exclude_all_logged = False
            nxt = self.fsm.update(detected=True, has_result=False,
                                  timed_out=False)
            if nxt != self.fsm.state:
                self._click_target = m.center
                self._goto(nxt)
            return
        if getattr(res, "excluded_count", 0) > 0:
            if not getattr(self, "_exclude_all_logged", False):
                self._log(f"🛡 当前可见的 {res.excluded_count} 个候选目标均包含排除标记，已全部跳过")
                self._exclude_all_logged = True

        # 通关小纸人/宝箱贪婪拾取拦截器:
        # 当场景中没有小怪可打了(击杀 Boss 结算后)，且开启了小纸人拾取且未达当轮上限
        if (self.profile.chest_enabled and self.profile.chest_img
                and self._chest_clicked_count < self.profile.chest_max_clicks):
            chests = self.detector.matcher.find_all(
                img, self.profile.chest_img, self.profile.chest_threshold)
            valid_chests = [c for c in chests if c.matched and c.center]
            if valid_chests:
                target = valid_chests[0]
                self.input.click(target.center[0], target.center[1], clicks=1)
                self._chest_clicked_count += 1
                self._log(f"🎁 拾取通关小纸人/宝箱 ({target.center[0]}, {target.center[1]}) "
                          f"[第 {self._chest_clicked_count}/{self.profile.chest_max_clicks} 只]")
                self._state_entered_at = now
                return

        # 只有在小纸人全部拾取完毕或未配置时，才允许响应结束图退出副本
        if res.end is not None and res.end.matched:
            self._click_target = res.end.center
            self._goto(GameState.CLICK_END)
            return

        # 找不到图:按配置周期性滚轮/拖拽查找
        self._maybe_scroll(now)

        # 找图超时：先点击激活坐标重新激活一次，仍找不到则停止
        self._find_timeout_common(img, now, "战斗开始图")

    def _tick_wait_team(self, img) -> None:
        """队员等待组队发车/战斗：非阻塞被动响应 + 容错兜底。

        - 游戏内若勾选「默认自动接受邀请」，队员会自动秒准备，无需强制任何按钮；
        - 若出现异常弹窗（如体力不足），安全响应；
        - 若配置了邀请图/准备图且界面恰好出现，顺手点击作为兜底；
        - 一旦检测到式神战斗或胜负/结算图，平滑无缝接入 WAIT_BATTLE 或 SETTLEMENT；
        - 看门狗超时(team_timeout)仅作为长期掉线告警，不干扰正常轮转。
        """
        now = self._clock()
        # 拟人化休息窗口
        if now < self._rest_until:
            if not self._rest_announced:
                self._log(f"😪 休息 {self._rest_until - now:.0f} 秒...")
                self._rest_announced = True
            self._state_entered_at = now
            return
        self._rest_announced = False

        # 达到目标次数 -> 完成
        runs = self.stats.snapshot().total_runs
        if runs >= self.profile.max_runs:
            self._log(f"✅ 挂机完成！共 {runs} 次")
            self._finished = True
            self._goto(GameState.STOPPED)
            return

        types = [ScreenType.VICTORY, ScreenType.FAILURE]
        if self.profile.confirm_img:
            types.append(ScreenType.SETTLEMENT)
        if self.profile.shikigami_enabled and self.profile.shikigami_img:
            types.append(ScreenType.SHIKIGAMI)
        if self.profile.alert_enabled and self.profile.alert_img:
            types.append(ScreenType.ALERT)
        if self.profile.invite_enabled and self.profile.invite_img:
            types.append(ScreenType.INVITE)
        if self.profile.ready_enabled and self.profile.ready_img:
            types.append(ScreenType.READY)

        res = self.detector.detect(img, self.profile, types)
        if self._handle_alert_if_present(img, res):
            return

        # 1. 战斗已结束/结算中（直达结算）
        m = res.first(ScreenType.VICTORY, ScreenType.FAILURE)
        if m is not None:
            if not self._result_seen:
                self._result_seen = True
                return
            if m.screen_type == ScreenType.VICTORY:
                self.stats.increment_run()
                self.stats.increment_success()
                self._log("🏆 检测到战斗胜利，进入结算")
            else:
                self.stats.increment_run()
                self.stats.increment_failure()
                self._log("☠ 检测到战斗失败，进入结算")
            self._result_pos = m.center
            self._settlement_at = now
            self._result_clicked = False
            self._confirm_clicked = False
            self._result_seen = False
            self._shikigami_clicked = False
            self._goto(GameState.SETTLEMENT)
            return
        self._result_seen = False

        if res.settlement and res.settlement.matched:
            self._log("🏁 检测到结算画面，进入结算")
            self._settlement_at = now
            self._result_clicked = False
            self._confirm_clicked = False
            self._result_seen = False
            self._shikigami_clicked = False
            self._goto(GameState.SETTLEMENT)
            return

        # 2. 战斗已开始（检测到式神绿标）
        if res.shikigami and res.shikigami.matched:
            self._log("⚔ 检测到式神，已进入战斗！")
            self._battle_started_at = now
            if not self._shikigami_clicked:
                self.input.click(res.shikigami.center[0], res.shikigami.center[1], clicks=1)
                self._shikigami_clicked = True
            self._goto(GameState.WAIT_BATTLE)
            return

        # 3. 容错备用：检测到邀请弹窗
        if res.invite and res.invite.matched:
            pos = res.invite.center
            self.input.click(pos[0], pos[1], clicks=1)
            self._log(f"🤝 队员检测到组队邀请，已点击接受 ({pos[0]}, {pos[1]})")
            self._state_entered_at = now
            return

        # 4. 容错备用：检测到准备按钮
        if res.ready and res.ready.matched:
            pos = res.ready.center
            self.input.click(pos[0], pos[1], clicks=1)
            self._log(f"👊 队员检测到准备按钮，已点击准备 ({pos[0]}, {pos[1]})")
            self._state_entered_at = now
            return

        # 5. 看门狗超时：等待发车超长时间无任何动静（如队长掉线/散队）
        tt = self.profile.team_timeout
        if tt > 0 and now - self._state_entered_at > tt:
            self._log(f"⚠ 等待发车超时 (已等待超 {tt:.0f} 秒无任何响应)")
            if self.profile.error_action == "stop":
                self.debug.save_error(img, AutoBotError("等待发车超时停止"))
                self._goto(GameState.ERROR)
            else:
                self._state_entered_at = now  # 重置看门狗，继续等待下一拍

    def _handle_alert_if_present(self, img, res) -> bool:
        """若检测到通用异常弹窗(如体力耗尽/网络断线/协同邀请),按配置处理并返回 True。"""
        if not (self.profile.alert_enabled and res.alert is not None and res.alert.matched):
            return False
        pos = res.alert.center
        if self.profile.alert_action == "stop":
            self._log("🛑 检测到异常弹窗（如体力耗尽/验证码），按配置自动停止挂机并触发警报")
            self.debug.save_error(img, AutoBotError("检测到异常弹窗，按配置停止"))
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass
            self._goto(GameState.STOPPED)
            self._finished = True
            return True
        else:
            self.input.click(pos[0], pos[1], clicks=1)
            self._log(f"🔔 检测到异常弹窗，已自动点击处理 ({pos[0]}, {pos[1]})")
            # 重置找图状态与战斗计时窗口，避免由于弹窗阻断而导致超时
            now = self._clock()
            self._state_entered_at = now
            self._battle_started_at = now
            return True

    def _find_timeout_common(self, img, now: float, label: str) -> None:
        """找图状态(FIND_CHALLENGE/FIND_SECOND)共用的超时-激活-停止逻辑。"""
        ft = self.profile.find_timeout
        if not (ft and ft > 0 and now - self._state_entered_at > ft):
            return
        coord = self.profile.find_timeout_click
        if not self._find_reactivated and coord:
            cx, cy = self.input.screen_to_client(coord[0], coord[1])
            self.input.click(cx, cy, clicks=1)
            self._find_reactivated = True
            self._state_entered_at = now  # 重新开一个计时窗口
            self._log(f"⚠ {ft:.0f}秒未找到{label}，"
                      f"已点击激活坐标 ({cx}, {cy}) 重新激活")
        else:
            reason = (f"重新激活后仍未找到{label}" if coord else
                      f"{ft:.0f}秒未找到{label}（未设置激活坐标）")
            self.stats.increment_error()
            self._log(f"❌ {reason}，自动停止")
            self.debug.save_error(img, AutoBotError(reason))
            self._log("   已保存错误现场")
            self._goto(GameState.ERROR)

    def _maybe_scroll(self, now: float) -> None:
        """找不到图时按配置周期性滚轮/拖拽(结界突破式列表查找)。"""
        p = self.profile
        if not (p.scroll_enabled and p.scroll_mode in ("滚轮", "拖拽")):
            return
        if now - self._last_scroll_at < p.scroll_interval:
            return
        self._last_scroll_at = now
        try:
            if p.scroll_mode == "滚轮":
                cx = cy = None
                if self.hwnd:
                    x, y, w, h = self.wm.get_client_rect(self.hwnd)
                    cx, cy = x + w // 2, y + h // 2  # 窗口中心(屏幕坐标)
                self.input.scroll(cx, cy, p.scroll_ticks)
                self._log(f"   已滚动滚轮 {p.scroll_ticks} 格(查找中)")
            else:
                if p.drag_from and p.drag_to:
                    self.input.drag(p.drag_from[0], p.drag_from[1],
                                    p.drag_to[0], p.drag_to[1])
                    self._log("   已执行拖拽滑动(查找中)")
                else:
                    self._log("⚠ 拖拽模式未设置起点/终点坐标")
        except Exception as e:
            self._log(f"⚠ 滚动/拖拽执行失败: {e}")

    def _tick_click_challenge(self) -> None:
        pos = getattr(self, "_click_target", None)
        if pos:
            self.input.click(pos[0], pos[1], clicks=self.profile.battle_clicks)
        self.stats.increment_run()
        self._battle_started_at = self._clock()
        self._shikigami_clicked = False  # 每场战斗重置式神点击标记
        self._result_seen = False
        self._reentered_count = 0
        self._log(f"第 {self.stats.snapshot().total_runs} 次: 进入战斗，等待结果...")
        if self.profile.second_enabled and self.profile.second_img:
            self._goto(GameState.FIND_SECOND)
        else:
            self._goto(GameState.WAIT_BATTLE)
        self._emit_progress()

    def _tick_find_second(self, img) -> None:
        """第二段图(如结界突破"进攻")查找:找到单击一次进战斗。"""
        now = self._clock()
        # 点完第一段后先等界面展开(second_delay),避免在过渡动画里误点
        if now - self._state_entered_at < self.profile.second_delay:
            return
        if now < self._rest_until:
            self._state_entered_at = now
            return

        check_reenter = self.profile.reenter_check > 0
        types = [ScreenType.SECOND]
        if check_reenter:
            types.append(ScreenType.CHALLENGE)
            if self.profile.alt_enabled and self.profile.alt_battle_img:
                types.append(ScreenType.CHALLENGE_ALT)
        if self.profile.alert_enabled and self.profile.alert_img:
            types.append(ScreenType.ALERT)

        res = self.detector.detect(img, self.profile, types,
                                   strategy=self.profile.match_strategy)
        if self._handle_alert_if_present(img, res):
            return
        m = res.first(ScreenType.SECOND)
        if m is not None:
            self._click_target = m.center
            self._goto(GameState.CLICK_SECOND)
            return

        # 漏洞A自愈: 第一段点击被吞判定(未看到第二段图, 但仍能看到开始图)
        seen_challenge = res.challenge if (res.challenge is not None
                                           and res.challenge.matched) else \
            (res.challenge_alt if (res.challenge_alt is not None
                                   and res.challenge_alt.matched) else None)
        rc = max(self.profile.reenter_check, self.profile.second_delay)
        if check_reenter and seen_challenge is not None \
                and now - self._state_entered_at > rc:
            self._reentered_count += 1
            if self._reentered_count <= 3:
                self._log(f"⚠ 等待第二段图超时，但仍看到开始图，疑似第一段点击被吞，"
                          f"重新点击开始图(第{self._reentered_count}次)")
                self.input.click(seen_challenge.center[0], seen_challenge.center[1],
                                 clicks=self.profile.battle_clicks)
            else:
                self._log(f"⚠ 已重点开始图{self._reentered_count - 1}次仍未展开第二段，"
                          f"疑似界面异常，保存现场")
                self.debug.save_error(img, AutoBotError("反复重点开始图仍未展开第二段界面"))
            self._state_entered_at = now
            return

        self._maybe_scroll(now)
        self._find_timeout_common(img, now, "第二段图(进攻)")

    def _tick_click_second(self) -> None:
        pos = getattr(self, "_click_target", None)
        if pos:
            self.input.click(pos[0], pos[1], clicks=1)
        self._battle_started_at = self._clock()
        self._shikigami_clicked = False
        self._result_seen = False
        self._reentered_count = 0
        self._log("   已点击第二段按钮(如进攻)")
        self._goto(GameState.WAIT_BATTLE)

    def _tick_wait_battle(self, img) -> None:
        now = self._clock()
        if now - self._battle_started_at < self.profile.pre_battle_delay:
            return
        # 检测:胜负 + (启用时)式神 + 开始图/第二段图(用于"没进战斗"判定) + (启用时)异常弹窗
        want_shikigami = (self.profile.shikigami_enabled
                          and self.profile.shikigami_img
                          and not self._shikigami_clicked)
        types = [ScreenType.VICTORY, ScreenType.FAILURE]
        if want_shikigami:
            types.append(ScreenType.SHIKIGAMI)
        check_reenter = self.profile.reenter_check > 0
        if check_reenter:
            types.append(ScreenType.CHALLENGE)
            if self.profile.alt_enabled and self.profile.alt_battle_img:
                types.append(ScreenType.CHALLENGE_ALT)
            if self.profile.second_enabled and self.profile.second_img:
                types.append(ScreenType.SECOND)
        if self.profile.alert_enabled and self.profile.alert_img:
            types.append(ScreenType.ALERT)
        res = self.detector.detect(img, self.profile, types)
        m = res.first(ScreenType.VICTORY, ScreenType.FAILURE)
        if m is not None:
            # 两拍确认:胜负图连续两拍都命中才处理,防动画中截获假命中
            if not self._result_seen:
                self._result_seen = True
                return
            if m.screen_type == ScreenType.VICTORY:
                self.stats.increment_success()
                self._log("   ⚔ 胜利")
            else:
                self.stats.increment_failure()
                self._log("   💀 失败")
            self._result_pos = m.center
            self._settlement_at = now
            self._result_clicked = False
            self._confirm_clicked = False
            self._result_seen = False
            self._goto(GameState.SETTLEMENT)
            return
        self._result_seen = False
        if want_shikigami and res.shikigami is not None \
                and res.shikigami.matched:
            pos = res.shikigami.center
            self.input.click(pos[0], pos[1], clicks=1)
            self._shikigami_clicked = True
            self._log(f"   已点击式神 ({pos[0]}, {pos[1]})")
            return
        if self._handle_alert_if_present(img, res):
            return
        # "没进战斗"自愈:等了 reenter_check 秒仍能看到第二段图或开始图
        # (a) 若为两段战斗且仍看到第二段图(如进攻) → 进攻点击未生效,重点第二段图
        # (b) 若仍看到开始图(主图或备选图) → 开始图点击未生效,重点开始图
        rc = self.profile.reenter_check
        seen_second = (res.second if (self.profile.second_enabled
                                      and res.second is not None
                                      and res.second.matched) else None)
        seen_challenge = res.challenge if (res.challenge is not None
                                           and res.challenge.matched) else \
            (res.challenge_alt if (res.challenge_alt is not None
                                   and res.challenge_alt.matched) else None)
        if check_reenter and (seen_second is not None or seen_challenge is not None) \
                and now - self._battle_started_at > rc:
            self._reentered_count += 1
            if seen_second is not None:
                if self._reentered_count <= 3:
                    self._log(f"⚠ 进战斗{rc:.0f}秒后仍看到第二段图(进攻)，疑似点击未生效，"
                              f"重新点击第二段图(第{self._reentered_count}次)")
                    self.input.click(
                        seen_second.center[0], seen_second.center[1], clicks=1)
                else:
                    self._log(f"⚠ 已重点第二段图{self._reentered_count - 1}次仍未进入战斗，"
                              f"疑似界面异常，保存现场")
                    self.debug.save_error(
                        img, AutoBotError("反复重点第二段图仍未进战斗"))
            else:
                if self._reentered_count <= 3:
                    self._log(f"⚠ 进战斗{rc:.0f}秒后仍看到开始图，疑似点击未生效，"
                              f"重新点击开始图(第{self._reentered_count}次)")
                    self.input.click(seen_challenge.center[0], seen_challenge.center[1],
                                     clicks=self.profile.battle_clicks)
                else:
                    self._log(f"⚠ 已重点开始图{self._reentered_count - 1}次仍未进入，"
                              f"疑似界面异常，保存现场")
                    self.debug.save_error(
                        img, AutoBotError("反复重点开始图仍未进战斗"))
            self._battle_started_at = now  # 重新计时,给下一轮自愈机会
            return
        bt = self.profile.battle_timeout
        if bt and bt > 0 and now - self._battle_started_at > bt:
            self.stats.increment_timeout()
            self.stats.increment_error()
            exc = BattleTimeout(
                f"战斗超时({bt:.0f}s)，未出现胜负结果")
            self._log(f"⚠ {exc}")
            self.debug.save_error(img, exc)
            if self.profile.error_action == "stop":
                self._goto(GameState.ERROR)
                return
            # continue：点击自定义超时坐标（屏幕坐标 -> 客户区）
            tc = self.profile.timeout_click
            if tc:
                cx, cy = self.input.screen_to_client(tc[0], tc[1])
                self.input.click(cx, cy, clicks=1)
                self._log(f"   已点击超时坐标 ({cx}, {cy})")
            self._timeout_at = self._clock()
            self._goto(GameState.TIMEOUT_HANDLED)
            return
        # 看门狗:battle_timeout=0(不限时)时的兜底,超长无动静→按错误处理
        wd = self.profile.watchdog_timeout
        if (wd and wd > 0 and now - self._battle_started_at > wd
                and not (bt and bt > 0)):
            self.stats.increment_error()
            exc = AutoBotError(
                f"看门狗: {wd:.0f}秒无任何动静(未出现胜负图也未超时)，疑似卡死")
            self._log(f"❌ {exc}")
            self.debug.save_error(img, exc)
            self._log("   已保存错误现场")
            if self.profile.error_action == "stop":
                self._goto(GameState.ERROR)
            else:
                # continue:点超时坐标(如有)后回到找挑战,尽量把流程拉回来
                tc = self.profile.timeout_click
                if tc:
                    cx, cy = self.input.screen_to_client(tc[0], tc[1])
                    self.input.click(cx, cy, clicks=1)
                    self._log(f"   已点击超时坐标 ({cx}, {cy})")
                self._timeout_at = self._clock()
                self._goto(GameState.TIMEOUT_HANDLED)

    def _tick_timeout_handled(self) -> None:
        # 超时点击后给游戏一段载入缓冲再回到找挑战/等待发车
        if self._clock() - self._timeout_at > self.TIMEOUT_BUFFER:
            if self.profile and self.profile.team_role == "队员":
                self._goto(GameState.WAIT_TEAM)
            else:
                self._goto(GameState.FIND_CHALLENGE)

    def _tick_settlement(self, img) -> None:
        now = self._clock()
        if not self._result_clicked:
            if self._result_pos:
                self.input.click(self._result_pos[0], self._result_pos[1],
                                 clicks=3)
            self._result_clicked = True
            self._settlement_at = now
            return
        # 可选：结算确认图
        if self.profile.confirm_img and not self._confirm_clicked:
            if now - self._settlement_at < 1.0:
                return
            res = self.detector.detect(img, self.profile,
                                       [ScreenType.SETTLEMENT])
            m = res.first(ScreenType.SETTLEMENT)
            if m is not None:
                self.input.click(m.center[0], m.center[1], clicks=3)
                self._confirm_clicked = True
                self._log("   已点击结算确认")
                self._settlement_at = now
                return
            if now - self._settlement_at > self.CONFIRM_WAIT:
                self._confirm_clicked = True  # 放弃确认，继续下一轮
                self._log("   未出现结算确认图，跳过")
        # 缓冲后进入下一轮；按节奏插入拟人化休息
        if now - self._settlement_at < random.uniform(*self.RESULT_CLICK_BUFFER):
            return
        self._maybe_rest()
        if self.profile and self.profile.team_role == "队员":
            self._goto(GameState.WAIT_TEAM)
        else:
            self._goto(GameState.FIND_CHALLENGE)

    def _maybe_rest(self) -> None:
        p = self.profile
        runs = self.stats.snapshot().total_runs
        n = _random_from_range(p.rest_every)
        if n and runs > 0 and runs % n == 0 and runs < p.max_runs:
            rt = _random_from_range(p.rest_seconds, default=5)
            self._rest_until = self._clock() + rt
            self._rest_announced = False

    def _on_capture_failed(self, exc: CaptureFailed) -> None:
        self._capture_fail_streak += 1
        if self._capture_fail_streak == 1:
            self._log(f"⚠ 截图失败: {exc}")
        if self._capture_fail_streak in (6, 60, 600):
            self._log(f"⚠ 截图持续失败 x{self._capture_fail_streak}，"
                      f"GDI对象={DebugManager.gdi_object_count()}")
        if self._capture_fail_streak >= 6 and self._capture_fail_streak % 60 == 6:
            self._log("（若长时间无法恢复，请检查窗口是否最小化/关闭）")
        if self.profile and self.profile.error_action == "stop" \
                and self._capture_fail_streak >= 12:
            self._error(exc)


def _random_from_range(range_str: str, default: Optional[int] = None) -> Optional[int]:
    """解析 "8-12" 并返回随机整数；无效返回 default。"""
    try:
        a, b = str(range_str).split("-")
        a, b = int(a), int(b)
        if a <= b:
            return random.randint(a, b)
    except Exception:
        pass
    return default
