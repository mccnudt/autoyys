"""数据模型：窗口、匹配结果、画面识别结果、战斗配置、统计。"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


# ---------- 窗口 ----------

@dataclass
class WindowInfo:
    hwnd: int
    title: str
    width: int
    height: int


# ---------- 视觉 ----------

@dataclass
class MatchResult:
    """一次模板匹配的结果。center 为截图坐标系（客户区）中心点。"""
    screen_type: "ScreenType"
    center: Tuple[int, int]
    score: float

    @property
    def matched(self) -> bool:
        return self.center is not None


class ScreenType(Enum):
    ENTRY = "entry"                # 副本入口图1(如探索开始)
    ENTRY2 = "entry2"              # 副本入口图2(可选,如副本图标)
    END = "end"                    # 副本结束图(如探索结束)
    CHALLENGE = "challenge"        # 战斗开始图
    CHALLENGE_ALT = "challenge_alt"  # 备选开始图
    SECOND = "second"              # 第二段图(如结界突破的"进攻")
    VICTORY = "victory"            # 胜利图
    FAILURE = "failure"            # 失败图
    SETTLEMENT = "settlement"      # 结算确认图
    SHIKIGAMI = "shikigami"        # 战斗中的式神（进入战斗后点击）
    ALERT = "alert"                # 通用异常弹窗（体力不足/重连/邀请）
    EXCLUDE = "exclude"            # 排除图片(如结界失败标记)
    INVITE = "invite"              # 接受组队邀请
    READY = "ready"                # 组队准备按钮
    CHEST = "chest"                # 通关小纸人/宝箱
    NONE = "none"


@dataclass
class ScreenResult:
    """一帧截图中，各关注模板的检测结果（未检测的类型为 None）。

    注意:字段名必须与 ScreenType 的枚举值一致(first() 按枚举值取属性)。
    """
    entry: Optional[MatchResult] = None
    entry2: Optional[MatchResult] = None
    end: Optional[MatchResult] = None
    challenge: Optional[MatchResult] = None
    challenge_alt: Optional[MatchResult] = None
    second: Optional[MatchResult] = None
    victory: Optional[MatchResult] = None
    failure: Optional[MatchResult] = None
    settlement: Optional[MatchResult] = None
    shikigami: Optional[MatchResult] = None
    alert: Optional[MatchResult] = None
    exclude: Optional[MatchResult] = None
    invite: Optional[MatchResult] = None
    ready: Optional[MatchResult] = None
    chest: Optional[MatchResult] = None
    excluded_count: int = 0

    def first(self, *types: ScreenType) -> Optional[MatchResult]:
        """按给定优先级返回第一个匹配成功的结果。"""
        for t in types:
            r = getattr(self, t.value)
            if r is not None and r.matched:
                return r
        return None


# ---------- 战斗配置（YYSGUI「通用模板」配置的模型化） ----------

@dataclass
class BattleProfile:
    """一次通用模板挂机的完整配置，可序列化为 JSON 保存/加载。"""
    name: str = "默认"
    battle_img: str = ""
    victory_img: str = ""
    defeat_img: str = ""
    confirm_img: str = ""          # 结算确认图，可留空
    battle_threshold: float = 0.8
    victory_threshold: float = 0.8
    defeat_threshold: float = 0.7
    confirm_threshold: float = 0.8
    shikigami_enabled: bool = False  # 进入战斗后自动点击式神
    shikigami_img: str = ""
    shikigami_threshold: float = 0.8
    alt_enabled: bool = False      # 备选开始图:与主开始图任一命中即点(可用于首领Boss)
    alt_battle_img: str = ""
    alt_battle_threshold: float = 0.8
    boss_priority: bool = True     # 优先挑战首领Boss(若配置了备选图且同屏出现)
    second_enabled: bool = False   # 第二段图:点完开始图后再找它点击(如"进攻")
    second_img: str = ""
    second_threshold: float = 0.8
    second_delay: float = 3.0      # 点完第一段后等待界面展开的秒数,再找第二段图
    scroll_enabled: bool = False   # 找不到图时自动滚动/拖拽
    scroll_mode: str = "滚轮"      # 滚轮 | 拖拽
    scroll_ticks: int = -3         # 滚轮格数(负=向下)
    drag_from: Optional[Tuple[int, int]] = None   # 拖拽起点(屏幕坐标)
    drag_to: Optional[Tuple[int, int]] = None     # 拖拽终点(屏幕坐标)
    scroll_interval: float = 5.0   # 找不到图时每隔 N 秒滚动一次
    entry_enabled: bool = False    # 副本入口图1:每轮副本开始前点击
    entry_img: str = ""
    entry_threshold: float = 0.7
    entry_delay: float = 3.0       # 点完入口图1后等界面载入的秒数
    entry2_enabled: bool = False   # 副本入口图2(可选):入口图1之后顺序点击
    entry2_img: str = ""
    entry2_threshold: float = 0.7
    entry2_delay: float = 3.0
    end_enabled: bool = False      # 副本结束图:识别到则点击并回到入口段
    end_img: str = ""
    end_threshold: float = 0.7
    end_delay: float = 2.0         # 点完结束图后的小缓冲(回到找入口)
    chest_enabled: bool = False    # 拾取通关小纸人/宝箱(如困28击败首领后随机出现的1-3只小纸人)
    chest_img: str = ""            # 小纸人/宝箱图片路径
    chest_threshold: float = 0.7   # 小纸人匹配阈值
    chest_max_clicks: int = 3      # 单轮最多拾取小纸人数量(通常为1-3只)
    alert_enabled: bool = False    # 通用异常弹窗拦截(体力不足/断线/邀请)
    alert_img: str = ""            # 弹窗按钮图片(如确定/取消/X)
    alert_threshold: float = 0.8
    alert_action: str = "click"    # click | stop
    exclude_enabled: bool = False  # 排除图片过滤(如结界失败标记)
    exclude_img: str = ""          # 排除图路径
    exclude_threshold: float = 0.8  # 排除图匹配阈值
    exclude_distance: float = 120.0  # 关联距离(像素)，在此距离内的开始图将被排除跳过
    max_runs: int = 100
    battle_timeout: float = 60.0   # WAIT_BATTLE 最长等待(秒),0=不限,一直等胜负图
    pre_battle_delay: float = 1.2  # 进入战斗后的动画前置等待（秒，默认1.2秒极速进入检测）
    timeout_click: Optional[Tuple[int, int]] = None  # 超时点击的屏幕坐标
    battle_clicks: int = 3         # 开始图点击次数(1-3;点一次开界面的场景设1)
    match_strategy: str = "最高分"  # 多目标策略: 最高分 | 最上面 | 最左边
    reenter_check: float = 8.0     # 进入战斗后等 N 秒仍见开始图→判定没进战斗,重点开始图(0=关闭)
    watchdog_timeout: float = 600.0  # 看门狗:整个 WAIT_BATTLE 无任何动静超 N 秒→现场截图+按错误处理(0=关闭)
    find_timeout: float = 100.0    # FIND_CHALLENGE 最长找图秒数，0=不启用
    find_timeout_click: Optional[Tuple[int, int]] = None  # 找图超时的"激活点击"屏幕坐标
    rest_every: str = "8-12"       # 每多少次休息一次（范围字符串）
    rest_seconds: str = "5-10"     # 休息时长（范围字符串）
    error_action: str = "continue"  # continue | stop
    run_mode: str = "后台"         # 前台 | 后台
    window_keyword: str = ""       # 后台窗口标题关键词
    detect_interval: float = 0.5   # 检测间隔（秒）
    adaptive_interval: bool = True  # 自适应心跳: 战斗期间自动放宽间隔降低 CPU 占用
    team_role: str = "单人"        # 单人 | 队长 | 队员
    invite_enabled: bool = False   # 队员备用兜底: 识别并点击接受邀请
    invite_img: str = ""
    invite_threshold: float = 0.8
    ready_enabled: bool = False    # 队员备用兜底: 识别并点击准备按钮
    ready_img: str = ""
    ready_threshold: float = 0.8
    team_timeout: float = 300.0    # 队员等待发车看门狗超时(秒),0=不限

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["timeout_click"] = list(self.timeout_click) if self.timeout_click else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BattleProfile":
        known = {f for f in cls.__dataclass_fields__}
        d = {k: v for k, v in d.items() if k in known}
        # 所有 Optional[(x,y)] 坐标字段:JSON 反序列化后是 list,统一转回 tuple
        for key in ("timeout_click", "find_timeout_click",
                    "drag_from", "drag_to"):
            tc = d.get(key)
            if isinstance(tc, (list, tuple)) and len(tc) == 2:
                d[key] = (int(tc[0]), int(tc[1]))
            else:
                d[key] = None
        return cls(**d)

    # ---- 校验(集中在此,GUI 只负责展示;返回 (错误列表, 警告列表)) ----

    def validate(self, image_exists=os.path.exists) -> tuple:
        errors, warnings = [], []
        # 战斗开始图：单人与队长模式为必填；队员模式非必填（支持游戏内自动接受发车）
        if self.team_role in ("单人", "队长"):
            if not self.battle_img:
                errors.append("请先设置战斗开始图")
            elif not image_exists(self.battle_img):
                errors.append(f"战斗开始图不存在: {self.battle_img}")
        elif self.battle_img and not image_exists(self.battle_img):
            errors.append(f"战斗开始图不存在: {self.battle_img}")
        # 勾选项必须提供有效图片
        for label, en, img in (
                ("进入战斗后点击式神", "shikigami_enabled", "shikigami_img"),
                ("备选开始图", "alt_enabled", "alt_battle_img"),
                ("第二段图", "second_enabled", "second_img"),
                ("入口图1", "entry_enabled", "entry_img"),
                ("入口图2", "entry2_enabled", "entry2_img"),
                ("副本结束图", "end_enabled", "end_img"),
                ("异常弹窗处理", "alert_enabled", "alert_img"),
                ("排除图片过滤", "exclude_enabled", "exclude_img"),
                ("接受组队邀请", "invite_enabled", "invite_img"),
                ("组队准备按钮", "ready_enabled", "ready_img"),
                ("拾取通关小纸人/宝箱", "chest_enabled", "chest_img")):
            if getattr(self, en):
                img_path = getattr(self, img)
                if not img_path:
                    errors.append(f"勾选了「{label}」但未设置图片")
                elif not image_exists(img_path):
                    errors.append(f"「{label}」图片不存在: {img_path}")
        # 拖拽滚动需要起止坐标
        if self.scroll_enabled and self.scroll_mode == "拖拽" \
                and not (self.drag_from and self.drag_to):
            warnings.append("滚动方式为拖拽但未设置起点/终点，滚动将不执行")
        # 启用找图超时但没激活坐标
        if self.find_timeout > 0 and not self.find_timeout_click:
            warnings.append("已启用找图超时但未设置激活坐标，超时后将直接停止")
        return errors, warnings


# ---------- 统计 ----------

@dataclass
class StatisticsModel:
    total_runs: int = 0
    success: int = 0
    failure: int = 0
    timeout: int = 0
    error: int = 0
    started_at: float = field(default_factory=time.time)

    @property
    def runtime_seconds(self) -> float:
        return time.time() - self.started_at


class Statistics:
    """运行统计（对应 API 文档 Statistics 接口）。线程内使用，由 Worker 独占。"""

    def __init__(self) -> None:
        self._m = StatisticsModel()

    def increment_run(self) -> None:
        self._m.total_runs += 1

    def increment_success(self) -> None:
        self._m.success += 1

    def increment_failure(self) -> None:
        self._m.failure += 1

    def increment_timeout(self) -> None:
        self._m.timeout += 1

    def increment_error(self) -> None:
        self._m.error += 1

    def snapshot(self) -> StatisticsModel:
        return StatisticsModel(
            total_runs=self._m.total_runs,
            success=self._m.success,
            failure=self._m.failure,
            timeout=self._m.timeout,
            error=self._m.error,
            started_at=self._m.started_at,
        )

    def reset(self) -> None:
        self._m = StatisticsModel()
