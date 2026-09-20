"""BotTab：单个挂机标签页 = 一套独立 控制器/Worker/统计/日志（自定 Phase 12）。"""
from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional

from controller.automation import AutomationController
from core.models import BattleProfile, Statistics
from debug.debug_manager import DebugManager
from input.controller import InputController
from profiles.manager import ProfileManager
from vision.capture import ScreenCapture
from vision.detector import ScreenDetector
from window.manager import WindowManager
from worker.worker import AutomationWorker

from . import widgets
from .widgets import APP_ROOT, resolve_image

STATE_TEXT = {
    "idle": "空闲", "find_challenge": "寻找挑战", "click_challenge": "点击挑战",
    "find_second": "寻找二段", "click_second": "点击二段",
    "wait_battle": "战斗中", "settlement": "结算中",
    "timeout_handled": "超时处理", "error": "错误", "stopped": "已停止",
    "find_entry": "寻找入口", "click_entry": "点击入口",
    "find_entry2": "寻找入口2", "click_entry2": "点击入口2",
    "click_end": "副本收尾",
    "wait_team": "等待发车",
}


class BotTab(ttk.Frame):
    """一个标签页承载一次完整挂机会话。tab_id 从 1 开始。"""

    def __init__(self, notebook: ttk.Notebook, app, tab_id: int) -> None:
        super().__init__(notebook)
        self.app = app
        self.tab_id = tab_id
        self.win = self.winfo_toplevel()
        self._ftag = "" if tab_id == 1 else f"_t{tab_id}"

        self.wm = WindowManager()
        self.capture = ScreenCapture()
        self.detector = ScreenDetector()
        self.stats = Statistics()
        self.debug = DebugManager(os.path.join(APP_ROOT, "logs"))
        self.profiles = ProfileManager(os.path.join(APP_ROOT, "profiles"))
        self.input = InputController()
        self._load_remarks()
        self.worker: Optional[AutomationWorker] = None
        self._paused = False
        self._last_stats = None
        self._max_runs = 0

        self._build_vars()
        self._build_ui()
        self._load_initial_profile()

    # ---------- 变量 ----------

    # ---- 配置字段表驱动(加字段只改这里;类型: str|int|float|bool|img|clicks|coord) ----
    # coord 的 var 键是前缀,实际变量为 {前缀}_x / {前缀}_y
    _FIELD_SPECS = [
        ("battle_img", "battle_img", "img"),
        ("victory_img", "victory_img", "img"),
        ("defeat_img", "defeat_img", "img"),
        ("confirm_img", "confirm_img", "img"),
        ("battle_threshold", "battle_conf", "float"),
        ("victory_threshold", "victory_conf", "float"),
        ("defeat_threshold", "defeat_conf", "float"),
        ("confirm_threshold", "confirm_conf", "float"),
        ("shikigami_enabled", "shikigami_enabled", "bool"),
        ("shikigami_img", "shikigami_img", "img"),
        ("shikigami_threshold", "shikigami_conf", "float"),
        ("alt_enabled", "alt_enabled", "bool"),
        ("alt_battle_img", "alt_battle_img", "img"),
        ("alt_battle_threshold", "alt_battle_conf", "float"),
        ("second_enabled", "second_enabled", "bool"),
        ("second_img", "second_img", "img"),
        ("second_threshold", "second_conf", "float"),
        ("second_delay", "second_delay", "float"),
        ("scroll_enabled", "scroll_enabled", "bool"),
        ("scroll_mode", "scroll_mode", "str"),
        ("scroll_ticks", "scroll_ticks", "int"),
        ("scroll_interval", "scroll_interval", "float"),
        ("entry_enabled", "entry_enabled", "bool"),
        ("entry_img", "entry_img", "img"),
        ("entry_threshold", "entry_conf", "float"),
        ("entry_delay", "entry_delay", "float"),
        ("entry2_enabled", "entry2_enabled", "bool"),
        ("entry2_img", "entry2_img", "img"),
        ("entry2_threshold", "entry2_conf", "float"),
        ("entry2_delay", "entry2_delay", "float"),
        ("end_enabled", "end_enabled", "bool"),
        ("end_img", "end_img", "img"),
        ("end_threshold", "end_conf", "float"),
        ("find_timeout", "find_timeout", "float"),
        ("find_timeout_click", "find", "coord"),
        ("reenter_check", "reenter_check", "float"),
        ("watchdog_timeout", "watchdog_timeout", "float"),
        ("max_runs", "max_runs", "int"),
        ("battle_timeout", "battle_timeout", "int"),
        ("timeout_click", "timeout", "coord"),
        ("battle_clicks", "battle_clicks", "clicks"),
        ("match_strategy", "match_strategy", "str"),
        ("rest_every", "rest_every", "str"),
        ("rest_seconds", "rest_seconds", "str"),
        ("error_action", "error_action", "str"),
        ("run_mode", "run_mode", "str"),
        ("window_keyword", "window_keyword", "str"),
        ("drag_from", "drag_from", "coord"),
        ("drag_to", "drag_to", "coord"),
        ("alert_enabled", "alert_enabled", "bool"),
        ("alert_img", "alert_img", "img"),
        ("alert_threshold", "alert_conf", "float"),
        ("alert_action", "alert_action", "str"),
        ("exclude_enabled", "exclude_enabled", "bool"),
        ("exclude_img", "exclude_img", "img"),
        ("exclude_threshold", "exclude_conf", "float"),
        ("exclude_distance", "exclude_dist", "float"),
        ("team_role", "team_role", "str"),
        ("invite_enabled", "invite_enabled", "bool"),
        ("invite_img", "invite_img", "img"),
        ("invite_threshold", "invite_conf", "float"),
        ("ready_enabled", "ready_enabled", "bool"),
        ("ready_img", "ready_img", "img"),
        ("ready_threshold", "ready_conf", "float"),
        ("team_timeout", "team_timeout", "float"),
    ]
    # var 默认值覆盖:profile 默认 None/空时,UI 仍给合理初始值
    _VAR_DEFAULT_OVERRIDES = {
        "window_keyword": "阳师",
        "team_role": "单人",
        "timeout": (800, 450),  # 超时点击坐标的 UI 默认
    }

    @staticmethod
    def _fmt_num(v) -> str:
        """数值显示:整数值去掉 .0(3.0 -> '3'),其余原样。"""
        if isinstance(v, (int, float)) and not isinstance(v, bool)                 and v == int(v):
            return str(int(v))
        return str(v)

    @staticmethod
    def _to_int(var, default):
        try:
            return int(var.get())
        except ValueError:
            return default

    @staticmethod
    def _to_float(var, default):
        try:
            return float(var.get())
        except ValueError:
            return default

    def _build_vars(self) -> None:
        v = self._vars = {}
        v["template"] = tk.StringVar()
        v["template_name"] = tk.StringVar()
        v["window"] = tk.StringVar()
        v["window_remark"] = tk.StringVar()
        defaults = BattleProfile()
        for attr, key, kind in self._FIELD_SPECS:
            val = self._VAR_DEFAULT_OVERRIDES.get(key, getattr(defaults, attr))
            if kind == "bool":
                v[key] = tk.BooleanVar(value=bool(val))
            elif kind == "coord":
                val = self._VAR_DEFAULT_OVERRIDES.get(key) or val
                if val:
                    v[f"{key}_x"] = tk.StringVar(value=str(val[0]))
                    v[f"{key}_y"] = tk.StringVar(value=str(val[1]))
                else:
                    v[f"{key}_x"] = tk.StringVar()
                    v[f"{key}_y"] = tk.StringVar()
            else:
                v[key] = tk.StringVar(value=self._fmt_num(val))
        self._window_list = []

    def _to_profile(self) -> BattleProfile:
        """界面 -> BattleProfile:全部字段由 _FIELD_SPECS 表驱动。"""
        v = self._vars
        defaults = BattleProfile()
        kwargs = {}
        for attr, key, kind in self._FIELD_SPECS:
            if kind == "bool":
                kwargs[attr] = bool(v[key].get())
            elif kind == "coord":
                xs = v[f"{key}_x"].get().strip()
                ys = v[f"{key}_y"].get().strip()
                try:
                    kwargs[attr] = (int(xs), int(ys)) if xs and ys else None
                except ValueError:
                    kwargs[attr] = None
            elif kind == "img":
                kwargs[attr] = resolve_image(v[key].get().strip())
            elif kind == "int":
                kwargs[attr] = self._to_int(v[key],
                                            getattr(defaults, attr))
            elif kind == "clicks":
                kwargs[attr] = max(1, min(3, self._to_int(v[key], 3)))
            elif kind == "float":
                kwargs[attr] = self._to_float(v[key],
                                              getattr(defaults, attr))
            else:
                kwargs[attr] = v[key].get()
        return BattleProfile(**kwargs)

    def _from_profile(self, p: BattleProfile) -> None:
        """BattleProfile -> 界面:全部字段由 _FIELD_SPECS 表驱动。"""
        v = self._vars
        for attr, key, kind in self._FIELD_SPECS:
            val = getattr(p, attr)
            if kind == "bool":
                v[key].set(bool(val))
            elif kind == "coord":
                if val:
                    v[f"{key}_x"].set(str(val[0]))
                    v[f"{key}_y"].set(str(val[1]))
                else:
                    v[f"{key}_x"].set("")
                    v[f"{key}_y"].set("")
            elif kind in ("int", "float", "clicks"):
                v[key].set(self._fmt_num(val))
            elif kind == "str":
                # 空值时回退到默认覆盖(如 window_keyword='阳师',空关键词无法刷新)
                v[key].set(val or self._VAR_DEFAULT_OVERRIDES.get(key, ""))
            else:
                v[key].set(val)
        for key, label in self._previews.items():
            widgets.update_img_preview(v[f"{key}_img"].get(), label)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        # 结构:上方设置区(内容超高时滚轮滚动) + 下方固定的 控制/状态/日志
        outer = ttk.Frame(self, padding="5")
        outer.pack(fill=tk.BOTH, expand=True)
        fixed = ttk.Frame(outer)          # 底部固定区
        fixed.pack(side=tk.BOTTOM, fill=tk.X)
        settings_area = ttk.Frame(outer)  # 顶部滚动区
        settings_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(settings_area, highlightthickness=0)
        self._settings_canvas = canvas
        vbar = ttk.Scrollbar(settings_area, orient=tk.VERTICAL,
                             command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        main = ttk.Frame(canvas, padding="8")
        canvas.create_window((0, 0), window=main, anchor="nw", tags="inner")
        main.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("inner", width=e.width))
        canvas.bind_all("<MouseWheel>", self._on_settings_wheel)

        # ===== 模板管理(最前,不折叠——决定整个配置区内容) =====
        tm = ttk.Frame(main)
        tm.pack(fill=tk.X, pady=(0, 8))
        trow = ttk.Frame(tm)
        trow.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(trow, text="模板:", font=("", 9)).pack(side=tk.LEFT)
        self.template_combo = ttk.Combobox(
            trow, textvariable=self._vars["template"], width=14,
            state="readonly", font=("", 9))
        self.template_combo.pack(side=tk.LEFT, padx=(5, 10))
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)
        ttk.Button(trow, text="加载", command=self._load_profile, width=6
                   ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(trow, text="另存为:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(trow, textvariable=self._vars["template_name"], width=10,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Button(trow, text="保存", command=self._save_profile, width=6
                   ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(trow, text="删除", command=self._delete_profile, width=6
                   ).pack(side=tk.LEFT)


        # ===== 运行模式 =====
        mf = ttk.LabelFrame(main, text="运行模式", padding="8")
        mf.pack(fill=tk.X, pady=(0, 8))
        mfc = self._make_collapsible(mf, default_open=True)
        ttk.Label(mfc, text="模式:", font=("", 9)).pack(side=tk.LEFT)
        self.run_mode_combo = ttk.Combobox(
            mfc, textvariable=self._vars["run_mode"], width=6,
            state="readonly", font=("", 9))
        self.run_mode_combo["values"] = ["前台", "后台"]
        self.run_mode_combo.pack(side=tk.LEFT, padx=(4, 16))
        ttk.Label(mfc, text="窗口标题关键词:", font=("", 9)).pack(side=tk.LEFT)
        self.keyword_entry = ttk.Entry(
            mfc, textvariable=self._vars["window_keyword"], width=10, font=("", 9))
        self.keyword_entry.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Button(mfc, text="刷新窗口", command=self.refresh_windows, width=8
                   ).pack(side=tk.LEFT, padx=(2, 8))
        self.window_combo = ttk.Combobox(
            mfc, textvariable=self._vars["window"], width=30,
            state="readonly", font=("", 8))
        self.window_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.window_combo.bind("<<ComboboxSelected>>", self._on_window_selected)
        ttk.Label(mfc, text="备注:", font=("", 9)).pack(side=tk.LEFT)
        remark_entry = ttk.Entry(mfc, textvariable=self._vars["window_remark"],
                                 width=8, font=("", 9))
        remark_entry.pack(side=tk.LEFT, padx=(4, 2))
        remark_entry.bind("<Return>", lambda e: self.apply_remark())
        ttk.Button(mfc, text="标记", command=self.apply_remark, width=5
                   ).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(mfc, text="测试", command=self._test_backend, width=6
                   ).pack(side=tk.LEFT)
        ttk.Label(mfc, text="(测试=存截图到logs/并向窗口中心发一次后台点击)",
                  foreground="gray", font=("", 8)).pack(side=tk.LEFT, padx=(6, 0))

        # ===== 控制 =====

        # ===== 1.【基础】核心战斗目标 =====
        basic_lf = ttk.LabelFrame(main, text="【基础】核心战斗目标", padding="8")
        basic_lf.pack(fill=tk.X, pady=(0, 8))
        basic_c = self._make_collapsible(basic_lf, default_open=True)

        self._previews = {}
        # 运行模式选择行
        role_row = ttk.Frame(basic_c)
        role_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(role_row, text="运行模式:", font=("", 9, "bold")).pack(side=tk.LEFT)
        role_combo = ttk.Combobox(role_row, textvariable=self._vars["team_role"],
                                  width=8, state="readonly", font=("", 9))
        role_combo["values"] = ["单人", "队长", "队员"]
        role_combo.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(role_row, text="💡 队员模式：被动等待发车，自动结算，免填开始图；队长/单人需配置开始图",
                  foreground="#0066cc", font=("", 8)).pack(side=tk.LEFT)

        # 核心4图 (每行都是标准统一的图片控件行)
        self._previews["battle"] = widgets.make_image_row(
            basic_c, "战斗开始图:", self._vars["battle_img"], self._vars["battle_conf"],
            lambda: self._crop_to("battle"))
        self._previews["victory"] = widgets.make_image_row(
            basic_c, "胜利结算图:", self._vars["victory_img"], self._vars["victory_conf"],
            lambda: self._crop_to("victory"))
        self._previews["defeat"] = widgets.make_image_row(
            basic_c, "失败结算图:", self._vars["defeat_img"], self._vars["defeat_conf"],
            lambda: self._crop_to("defeat"))
        self._previews["confirm"] = widgets.make_image_row(
            basic_c, "结算确认图(可选):", self._vars["confirm_img"],
            self._vars["confirm_conf"], lambda: self._crop_to("confirm"))

        # 运行目标与匹配策略行
        brow = ttk.Frame(basic_c)
        brow.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(brow, text="次数上限:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(brow, textvariable=self._vars["max_runs"], width=6,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 6))
        ttk.Label(brow, text="0=不限", foreground="gray", font=("", 8)).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(brow, text="开始图点击次数:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(brow, textvariable=self._vars["battle_clicks"], width=3,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(brow, text="同图多个时点:", font=("", 9)).pack(side=tk.LEFT)
        strat = ttk.Combobox(brow, textvariable=self._vars["match_strategy"],
                             width=8, state="readonly", font=("", 9))
        strat["values"] = ["最高分", "最上面", "最左边"]
        strat.pack(side=tk.LEFT, padx=(4, 0))

        # ===== 2.【进阶】组队协同与特定副本 =====
        adv_lf = ttk.LabelFrame(main, text="【进阶】组队协同与特定副本", padding="8")
        adv_lf.pack(fill=tk.X, pady=(0, 8))
        adv_c = self._make_collapsible(adv_lf, default_open=False)

        ttk.Label(adv_c, text="包含组队被动兜底、结界突破防误点过滤、双阶段进入图及式神绿标",
                  foreground="gray", font=("", 8)).pack(anchor=tk.W, pady=(0, 4))

        self._previews["invite"], _ = self._checkbox_image_row(
            adv_c, "接受组队邀请(队员兜底):", self._vars["invite_enabled"],
            self._vars["invite_img"], self._vars["invite_conf"], "invite")
        self._previews["ready"], _ = self._checkbox_image_row(
            adv_c, "组队准备按钮(队员兜底):", self._vars["ready_enabled"],
            self._vars["ready_img"], self._vars["ready_conf"], "ready")

        pv_exc, excrow = self._checkbox_image_row(
            adv_c, "排除过滤图片(如突破失败):", self._vars["exclude_enabled"],
            self._vars["exclude_img"], self._vars["exclude_conf"], "exclude")
        self._previews["exclude"] = pv_exc
        ttk.Label(excrow, text="关联间距(px):", font=("", 9)).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Entry(excrow, textvariable=self._vars["exclude_dist"], width=5,
                  font=("", 9)).pack(side=tk.LEFT)

        self._previews["alt_battle"], _ = self._checkbox_image_row(
            adv_c, "备选开始图(任一命中即点):", self._vars["alt_enabled"],
            self._vars["alt_battle_img"], self._vars["alt_battle_conf"], "alt_battle")

        self._previews["second"], s2row = self._checkbox_image_row(
            adv_c, "第二段图(如进攻):", self._vars["second_enabled"],
            self._vars["second_img"], self._vars["second_conf"], "second")
        ttk.Label(s2row, text="二段前等待(秒):", font=("", 9)).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Entry(s2row, textvariable=self._vars["second_delay"], width=4,
                  font=("", 9)).pack(side=tk.LEFT)

        self._previews["shikigami"], _ = self._checkbox_image_row(
            adv_c, "进入战斗点击式神(绿标):", self._vars["shikigami_enabled"],
            self._vars["shikigami_img"], self._vars["shikigami_conf"], "shikigami")

        # ===== 3.【安全】异常拦截与自愈闭环 =====
        heal_lf = ttk.LabelFrame(main, text="【安全】异常拦截与自愈闭环", padding="8")
        heal_lf.pack(fill=tk.X, pady=(0, 8))
        heal_c = self._make_collapsible(heal_lf, default_open=False)

        # 弹窗拦截
        pv_alert, altrow = self._checkbox_image_row(
            heal_c, "异常弹窗拦截(如体力不足):", self._vars["alert_enabled"],
            self._vars["alert_img"], self._vars["alert_conf"], "alert")
        self._previews["alert"] = pv_alert
        ttk.Label(altrow, text="动作:", font=("", 9)).pack(side=tk.LEFT, padx=(8, 2))
        alert_act = ttk.Combobox(altrow, textvariable=self._vars["alert_action"],
                                 width=6, state="readonly", font=("", 9))
        alert_act["values"] = ["click", "stop"]
        alert_act.pack(side=tk.LEFT)

        # 进战斗重试 + 看门狗
        arow = ttk.Frame(heal_c)
        arow.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(arow, text="进战斗重试等待(秒):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(arow, textvariable=self._vars["reenter_check"], width=4,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(arow, text="点开始后未进入自动重点(0=关)",
                  foreground="gray", font=("", 8)).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(arow, text="战斗看门狗(秒):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(arow, textvariable=self._vars["watchdog_timeout"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(arow, text="无动静超时保护(0=关)",
                  foreground="gray", font=("", 8)).pack(side=tk.LEFT)

        # 战斗超时设置 + 独立行：超时脱离点击坐标 (彻底解决溢出！)
        trow = ttk.Frame(heal_c)
        trow.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(trow, text="战斗超时(秒):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(trow, textvariable=self._vars["battle_timeout"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(trow, text="0=不限", foreground="gray", font=("", 8)).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(trow, text="超时脱离点击坐标:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(trow, textvariable=self._vars["timeout_x"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(trow, text=",", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(trow, textvariable=self._vars["timeout_y"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(trow, text="截取坐标", command=self._pick_coord, width=8
                   ).pack(side=tk.LEFT, padx=(4, 0))

        # 找图超时与激活坐标
        frow = ttk.Frame(heal_c)
        frow.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(frow, text="找图超时(秒):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(frow, textvariable=self._vars["find_timeout"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(frow, text="0=关", foreground="gray", font=("", 8)).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(frow, text="激活点击坐标:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(frow, textvariable=self._vars["find_x"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(frow, text=",", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(frow, textvariable=self._vars["find_y"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(frow, text="截取坐标", command=self._pick_find_coord, width=8
                   ).pack(side=tk.LEFT, padx=(4, 0))

        # 找不到开始图动作
        erow = ttk.Frame(heal_c)
        erow.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(erow, text="找不到开始图时的动作:", font=("", 9)).pack(side=tk.LEFT)
        err = ttk.Combobox(erow, textvariable=self._vars["error_action"],
                           width=10, state="readonly", font=("", 9))
        err["values"] = ["continue", "stop"]
        err.pack(side=tk.LEFT, padx=(4, 6))
        ttk.Label(erow, text="continue=继续寻找重试，stop=安全停止挂机",
                  foreground="gray", font=("", 8)).pack(side=tk.LEFT)

        # ===== 4.【辅助】拟人防封与列表滚动 =====
        aux_lf = ttk.LabelFrame(main, text="【辅助】拟人防封与列表滚动", padding="8")
        aux_lf.pack(fill=tk.X, pady=(0, 8))
        aux_c = self._make_collapsible(aux_lf, default_open=False)

        # 拟人休息
        rrow = ttk.Frame(aux_c)
        rrow.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(rrow, text="每(N次)休息:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(rrow, textvariable=self._vars["rest_every"], width=7,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(rrow, text="如 8-12", foreground="gray", font=("", 8)
                  ).pack(side=tk.LEFT, padx=(2, 16))
        ttk.Label(rrow, text="休息时长(秒):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(rrow, textvariable=self._vars["rest_seconds"], width=7,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(rrow, text="如 5-10", foreground="gray", font=("", 8)
                  ).pack(side=tk.LEFT, padx=(2, 0))

        # 滚动查找
        scrow1 = ttk.Frame(aux_c)
        scrow1.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(scrow1, text="找不到图时自动滚动:",
                        variable=self._vars["scroll_enabled"]).pack(side=tk.LEFT)
        mode = ttk.Combobox(scrow1, textvariable=self._vars["scroll_mode"],
                            width=6, state="readonly", font=("", 9))
        mode["values"] = ["滚轮", "拖拽"]
        mode.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(scrow1, text="滚轮格数(负=向下):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(scrow1, textvariable=self._vars["scroll_ticks"], width=4,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(scrow1, text="滚动间隔(秒):", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(scrow1, textvariable=self._vars["scroll_interval"], width=4,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 0))

        # 拖拽坐标行
        scrow2 = ttk.Frame(aux_c)
        scrow2.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(scrow2, text="拖拽起点:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(scrow2, textvariable=self._vars["drag_from_x"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(scrow2, text=",", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(scrow2, textvariable=self._vars["drag_from_y"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(scrow2, text="截取起点", command=lambda:
                   self._pick_into("drag_from_x", "drag_from_y"),
                   width=8).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(scrow2, text="拖拽终点:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(scrow2, textvariable=self._vars["drag_to_x"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(scrow2, text=",", font=("", 9)).pack(side=tk.LEFT)
        ttk.Entry(scrow2, textvariable=self._vars["drag_to_y"], width=5,
                  font=("", 9)).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(scrow2, text="截取终点", command=lambda:
                   self._pick_into("drag_to_x", "drag_to_y"),
                   width=8).pack(side=tk.LEFT, padx=(4, 0))

        # ===== 5.【循环】副本外层循环(可选,双层循环如困难28探索) =====
        df = ttk.LabelFrame(main, text="【循环】副本外层循环(可选)", padding="8")
        df.pack(fill=tk.X, pady=(0, 8))
        dfc = self._make_collapsible(df, default_open=False)
        ttk.Label(dfc, text="流程: 入口图1[→入口图2] → 开始图循环战斗 → 识别到结束图后点击并重新进入",
                  foreground="gray", font=("", 8)).pack(anchor=tk.W, pady=(0, 4))

        pv, erow = self._checkbox_image_row(
            dfc, "入口图1(如探索开始):", self._vars["entry_enabled"],
            self._vars["entry_img"], self._vars["entry_conf"], "entry")
        self._previews["entry"] = pv
        ttk.Label(erow, text="点击后等待(秒):", font=("", 8)).pack(
            side=tk.LEFT, padx=(8, 2))
        ttk.Entry(erow, textvariable=self._vars["entry_delay"], width=3,
                  font=("", 9)).pack(side=tk.LEFT)

        pv, e2row = self._checkbox_image_row(
            dfc, "入口图2(可选,顺序点击):", self._vars["entry2_enabled"],
            self._vars["entry2_img"], self._vars["entry2_conf"], "entry2")
        self._previews["entry2"] = pv
        ttk.Label(e2row, text="点击后等待(秒):", font=("", 8)).pack(
            side=tk.LEFT, padx=(8, 2))
        ttk.Entry(e2row, textvariable=self._vars["entry2_delay"], width=3,
                  font=("", 9)).pack(side=tk.LEFT)

        pv, endrow = self._checkbox_image_row(
            dfc, "副本结束图(识别到则点击并重新进入):", self._vars["end_enabled"],
            self._vars["end_img"], self._vars["end_conf"], "end")
        self._previews["end"] = pv

        # ===== 控制按钮(固定区,不随设置区滚动) =====
        bf = ttk.Frame(fixed)
        bf.pack(fill=tk.X, pady=(0, 8))
        self.start_btn = ttk.Button(bf, text="▶ 开始", command=self.start, width=10)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.pause_btn = ttk.Button(bf, text="⏸ 暂停", command=self.pause,
                                    state=tk.DISABLED, width=10)
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.resume_btn = ttk.Button(bf, text="⏵ 恢复", command=self.resume,
                                     state=tk.DISABLED, width=10)
        self.resume_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn = ttk.Button(bf, text="■ 停止", command=self.stop,
                                   state=tk.DISABLED, width=10)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="✕ 关闭本页",
                   command=self.request_close, width=10).pack(side=tk.LEFT)

        # ===== 状态 + 统计(固定区) =====
        sf = ttk.LabelFrame(fixed, text="状态 / 统计", padding="8")
        sf.pack(fill=tk.X, pady=(0, 8))
        srow1 = ttk.Frame(sf)
        srow1.pack(fill=tk.X)
        ttk.Label(srow1, text="状态:", font=("", 10)).pack(side=tk.LEFT)
        self.state_label = ttk.Label(srow1, text="空闲", foreground="gray",
                                     font=("", 10))
        self.state_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(srow1, text="进度:", font=("", 10)).pack(side=tk.LEFT)
        self.progress_label = ttk.Label(srow1, text="0/0", font=("", 10))
        self.progress_label.pack(side=tk.LEFT, padx=(5, 10))
        self.progress_bar = ttk.Progressbar(srow1, length=220,
                                            mode="determinate")
        self.progress_bar.pack(side=tk.LEFT)

        srow2 = ttk.Frame(sf)
        srow2.pack(fill=tk.X, pady=(4, 0))
        self.stats_label = ttk.Label(srow2, text=self._stats_text(None),
                                     foreground="#555555", font=("", 9))
        self.stats_label.pack(side=tk.LEFT)

        # 流程点管线:当前环节高亮(状态可视化)
        self._flow_stages = [("entry1", "入口1"), ("entry2", "入口2"),
                             ("team", "等待发车"),
                             ("challenge", "开始图"), ("second", "二段"),
                             ("battle", "战斗"), ("settle", "结算"),
                             ("end", "收尾")]
        self._flow_labels = {}
        self._flow_enabled = set()  # start() 时按 profile 填充
        flowrow = ttk.Frame(sf)
        flowrow.pack(fill=tk.X, pady=(2, 0))
        self._build_flow_row(flowrow)

        # ===== 日志(固定区) =====
        logf = ttk.LabelFrame(fixed, text="运行日志", padding="8")
        logf.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(logf, height=10, wrap=tk.WORD,
                                font=("Consolas", 9))
        scroll = ttk.Scrollbar(logf, orient=tk.VERTICAL,
                               command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log("标签页已就绪，选择模板后点「开始」")

    # ---------- 配置 <-> 界面 ----------

    def _load_initial_profile(self) -> None:
        self.refresh_profile_list()
        last = self.profiles.load_last()
        if last is not None:
            self._from_profile(last)
            self.log("已加载上次运行配置")
        elif self.template_combo["values"]:
            self.template_combo.current(0)
            self._load_profile()

    # ---------- 模板管理 ----------

    def refresh_profile_list(self) -> None:
        self.template_combo["values"] = self.profiles.list_names()

    def _on_template_selected(self, _event=None) -> None:
        self._load_profile()

    def _load_profile(self) -> None:
        name = self._vars["template"].get()
        if not name:
            return
        p = self.profiles.load(name)
        if p is None:
            self.log(f"加载模板失败: {name}")
            return
        self._from_profile(p)
        self.log(f"已加载模板: {name}")

    def _save_profile(self) -> None:
        name = self._vars["template_name"].get().strip() \
            or self._vars["template"].get().strip()
        if not name:
            self.log("请先在\"另存为\"填写模板名")
            return
        p = self._to_profile()
        p.name = name
        self.profiles.save(p)
        self.refresh_profile_list()
        self._vars["template"].set(name)
        self.log(f"模板已保存: {name}")

    def _delete_profile(self) -> None:
        name = self._vars["template"].get().strip()
        if not name:
            return
        if self.profiles.delete(name):
            self.log(f"已删除模板: {name}")
            self.refresh_profile_list()
            names = self.template_combo["values"]
            if names:
                self.template_combo.current(0)
                self._load_profile()
        else:
            self.log(f"模板 {name} 无文件可删（可能是预置模板）")

    # ---------- 截图/坐标 ----------

    def _crop_to(self, key: str) -> Optional[str]:
        """框选截图保存为 {模板名}_{字段}.png,同名覆盖=更新该槽位图片。

        - 跨模板不会互相影响(文件名含模板名);
        - 同模板同槽位重新截图直接覆盖旧图(旧图已无引用,覆盖即清理);
        - 模板引擎按 mtime 缓存,覆盖后自动重载;
        - 截图后若"另存为"改成别的名字,图片保持原文件名,引用依然有效。
        """
        import re
        name = (self._vars["template_name"].get().strip()
                or self._vars["template"].get().strip() or "未命名")
        safe = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "未命名"
        path = os.path.join(APP_ROOT, "templates", f"{safe}_{key}.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        saved = widgets.snapshot_region(self, path, self.win)
        if saved is None:
            self.log("截图已取消")
            return None
        self.log(f"已截图保存: {saved}")
        return saved

    def _make_collapsible(self, frame: ttk.LabelFrame,
                          default_open: bool = True) -> ttk.Frame:
        """把 LabelFrame 变成可折叠:标题行点击切换内容区显隐。

        返回 content 容器——该区的子控件应 pack 进它而不是 frame 本身。
        必须在向 frame 添加任何子控件之前调用。
        """
        title = frame.cget("text")
        frame.config(text="")
        state = {"open": default_open}

        title_lbl = tk.Label(
            frame, text=f"{'▼' if default_open else '▶'} {title}",
            cursor="hand2", font=("", 9, "bold"), anchor="w")
        title_lbl.pack(fill=tk.X)

        content = ttk.Frame(frame)
        content.pack(fill=tk.X)

        def _toggle(_event=None):
            state["open"] = not state["open"]
            title_lbl.config(text=f"{'▼' if state['open'] else '▶'} {title}")
            if state["open"]:
                content.pack(fill=tk.X)
            else:
                content.pack_forget()

        title_lbl.bind("<Button-1>", _toggle)
        frame._content = content
        return content

    def _checkbox_image_row(self, parent, label, enabled_var, img_var,
                            conf_var, crop_key):
        """勾选式图片行:勾选启用 + 路径/浏览/截图/置信度/预览。返回预览 Label。"""
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(row, text=label, variable=enabled_var).pack(
            side=tk.LEFT)
        ttk.Entry(row, textvariable=img_var, font=("", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 5))

        def _browse():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title=f"选择{label.strip(':')}",
                filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp"),
                           ("所有文件", "*.*")])
            if path:
                img_var.set(path)
                widgets.update_img_preview(path, preview)

        def _crop():
            path = self._crop_to(crop_key)
            if path:
                img_var.set(path)
                widgets.update_img_preview(path, preview)

        ttk.Button(row, text="浏览", command=_browse, width=6).pack(side=tk.LEFT)
        ttk.Button(row, text="截图", command=_crop, width=6).pack(
            side=tk.LEFT, padx=(5, 0))
        ttk.Label(row, text="置信度:", font=("", 8)).pack(
            side=tk.LEFT, padx=(10, 2))
        ttk.Entry(row, textvariable=conf_var, width=4, font=("", 9)).pack(
            side=tk.LEFT)
        pf = tk.Frame(row, width=80, height=50, bg="#e8e8e8",
                      relief=tk.SUNKEN, bd=1)
        pf.pack(side=tk.LEFT, padx=(8, 0))
        pf.pack_propagate(False)
        preview = tk.Label(pf, bg="#e8e8e8", fg="#888888", text="无",
                           font=("", 8))
        preview.pack(fill=tk.BOTH, expand=True)
        return preview, row

    def _on_settings_wheel(self, event) -> None:
        """设置区滚轮滚动(bind_all 全局绑定,仅作用于当前选中的标签页)。"""
        try:
            if self.app.notebook.select() != str(self):
                return
            self._settings_canvas.yview_scroll(
                int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _pick_coord(self) -> None:
        pos = widgets.pick_screen_coord(self)
        if pos:
            self._vars["timeout_x"].set(str(pos[0]))
            self._vars["timeout_y"].set(str(pos[1]))
            self.log(f"已截取坐标: {pos}")

    def _pick_find_coord(self) -> None:
        """全屏点选"激活点击坐标"(找图超时后的重新激活点击位置)。"""
        pos = widgets.pick_screen_coord(self)
        if pos:
            self._vars["find_x"].set(str(pos[0]))
            self._vars["find_y"].set(str(pos[1]))
            self.log(f"已截取激活坐标: {pos}")

    def _pick_into(self, x_key: str, y_key: str) -> None:
        """全屏点选坐标写入指定的两个 StringVar。"""
        pos = widgets.pick_screen_coord(self)
        if pos:
            self._vars[x_key].set(str(pos[0]))
            self._vars[y_key].set(str(pos[1]))
            self.log(f"已截取坐标: {pos}")

    # ---------- 窗口选择 ----------

    # ---- 窗口备注(按标题持久化到 window_remarks.json,跨会话生效) ----

    REMARKS_PATH = os.path.join(APP_ROOT, "window_remarks.json")

    def _load_remarks(self) -> None:
        import json
        try:
            with open(self.REMARKS_PATH, "r", encoding="utf-8") as f:
                self._remarks = json.load(f)
        except (OSError, ValueError):
            self._remarks = {}

    def _save_remarks(self) -> None:
        import json
        try:
            with open(self.REMARKS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._remarks, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _window_text(w, remark: str = "") -> str:
        base = f"HWND={w.hwnd} {w.title} ({w.width}x{w.height})"
        return f"{base} 【{remark}】" if remark else base

    def apply_remark(self) -> None:
        """给当前选中的窗口设置/清除备注(清空输入框=清除)。"""
        idx = self.window_combo.current()
        if not (0 <= idx < len(self._window_list)):
            self.log("未选中窗口，无法备注")
            return
        w = self._window_list[idx]
        remark = self._vars["window_remark"].get().strip()
        if remark:
            self._remarks[w.title] = remark
        else:
            self._remarks.pop(w.title, None)
        self._save_remarks()
        self.window_combo["values"] = [
            self._window_text(x, self._remarks.get(x.title, ""))
            if i != idx else self._window_text(w, remark)
            for i, x in enumerate(self._window_list)]
        self.log(f"窗口备注已{'设置' if remark else '清除'}: "
                 f"「{w.title}」→ {remark or '(无)'}")

    def _on_window_selected(self, _event=None) -> None:
        idx = self.window_combo.current()
        if 0 <= idx < len(self._window_list):
            self._vars["window_remark"].set(
                self._remarks.get(self._window_list[idx].title, ""))

    def refresh_windows(self) -> None:
        kw = self._vars["window_keyword"].get().strip()
        if not kw:
            self.log("请先填写窗口标题关键词")
            return
        self._window_list = self.wm.get_windows(kw)
        if not self._window_list:
            self.log(f"未找到标题含'{kw}'的窗口")
            self.window_combo["values"] = []
            return
        self.window_combo["values"] = [
            self._window_text(w, self._remarks.get(w.title, ""))
            for w in self._window_list]
        self.window_combo.current(0)
        self._on_window_selected()
        self.log(f"找到 {len(self._window_list)} 个窗口")

    def _selected_hwnd(self) -> Optional[int]:
        idx = self.window_combo.current()
        if 0 <= idx < len(self._window_list):
            return self._window_list[idx].hwnd
        kw = self._vars["window_keyword"].get().strip()
        ws = self.wm.get_windows(kw) if kw else []
        return ws[0].hwnd if ws else None

    def _calibrate_scale(self, hwnd: int) -> None:
        """测量 DPI 缩放比例并应用到截图与点击坐标。"""
        sx, sy = self.capture.calibrate(hwnd)
        if self.input.backend is not None:
            self.input.backend.coord_scale = (sx, sy)
        if (sx, sy) != (1.0, 1.0):
            self.log(f"检测到 DPI 缩放差异 ({sx:.2f}, {sy:.2f})："
                     f"后台截图将自动缩放到屏幕尺寸，点击坐标自动折算")

    def _test_backend(self) -> None:
        hwnd = self._selected_hwnd()
        if not hwnd:
            self.log("未选中窗口，请先「刷新窗口」并选择")
            return
        info = self.wm.get_window(hwnd)
        if info:
            self.log(f"测试目标: HWND={hwnd} 「{info.title}」 "
                     f"客户区 {info.width}x{info.height}")
        try:
            img = self.capture.capture(hwnd)
        except Exception as e:
            self.log(f"截图失败: {e}（窗口最小化？）")
            return
        path = os.path.join(APP_ROOT, "logs", f"test_backend{self._ftag}.png")
        import cv2
        cv2.imwrite(path, img)
        self.log(f"已存客户区截图: {path}（黑图/不是游戏画面=截图环节有问题）")

        # ===== 前台/后台对照：定位 DPI 缩放或画面内容差异 =====
        try:
            import numpy as np
            import pyautogui
            x, y, w, h = self.wm.get_client_rect(hwnd)
            shot = pyautogui.screenshot(region=(x, y, w, h))
            fg = cv2.cvtColor(np.array(shot.convert("RGB")),
                              cv2.COLOR_RGB2BGR)
            fg_path = os.path.join(APP_ROOT, "logs",
                                   f"test_fg_region{self._ftag}.png")
            cv2.imwrite(fg_path, fg)
            self.log(f"前台对照截图: {fg_path}（同一时刻屏幕上该窗口区域的画面）")
            if fg.shape[:2] != img.shape[:2]:
                self.log(f"⚠⚠ 尺寸不一致: PrintWindow={img.shape[1]}x{img.shape[0]}"
                         f" vs 屏幕={fg.shape[1]}x{fg.shape[0]}"
                         f" —— 存在 DPI/缩放差异，这就是后台识别失配的原因")
                scaled = cv2.resize(img, (fg.shape[1], fg.shape[0]))
                self._log_template_scores(scaled, prof, suffix="(缩放后)")
            else:
                diff = float(np.abs(img.astype(int) - fg.astype(int)).mean())
                self.log(f"两种截图尺寸一致，平均像素差 {diff:.1f}"
                         f"（>30 = 画面内容不同：旧帧/硬件叠加层问题）")
        except Exception as e:
            self.log(f"前台对照截图失败: {e}")

        # 各模板在该客户区截图上的最高匹配分：判断识别环节
        self._log_template_scores(img, prof)
        self.input.bind(hwnd, screen_to_client=lambda x, y:
                        self.capture.screen_to_client(hwnd, x, y))
        w, h = self.capture.client_size(hwnd)
        self.input.click(w // 2, h // 2, clicks=1)
        self.log(f"已向窗口中心 ({w // 2}, {h // 2}) 发后台点击，切到游戏验证响应"
                 f"；GDI对象={DebugManager.gdi_object_count()}")

    def _log_template_scores(self, img, prof, suffix="") -> None:
        checks = (("战斗开始", prof.battle_img, prof.battle_threshold),
                  ("胜利", prof.victory_img, prof.victory_threshold),
                  ("失败", prof.defeat_img, prof.defeat_threshold),
                  ("结算确认", prof.confirm_img, prof.confirm_threshold),
                  ("式神", prof.shikigami_img, prof.shikigami_threshold))
        for label, path_, thr in checks:
            if not path_:
                continue
            m = self.detector.matcher.find(img, path_, 0.0)
            mark = "✓" if m.score >= thr else "✗"
            self.log(f"   {mark} {label}{suffix}: 最高分 {m.score:.3f} / 阈值 {thr}")

    # ---------- 启动/控制 ----------

    def start(self) -> None:
        if self.worker and self.worker.is_alive:
            return
        profile = self._to_profile()
        # 校验集中在 profile.validate();GUI 只负责展示
        errors, warnings = profile.validate()
        for e in errors:
            self.log(f"错误: {e}")
        for w in warnings:
            self.log(f"提示: {w}")
        # 可选图：填了但文件不存在大概率是路径笔误，提醒但不阻断
        for label, key in (("胜利图", "victory_img"),
                           ("失败图", "defeat_img"),
                           ("结算确认图", "confirm_img")):
            p = getattr(profile, key)
            if p and not os.path.exists(p):
                self.log(f"⚠ {label}文件不存在，该步检测将永远不命中: {p}")
        if errors:
            return
        self._max_runs = profile.max_runs

        hwnd = None
        if profile.run_mode == "后台":
            hwnd = self._selected_hwnd()
            if not hwnd:
                self.log("错误: 后台模式需要先「刷新窗口」并选择一个窗口")
                return
            self.input.bind(
                hwnd, screen_to_client=lambda x, y:
                self.capture.screen_to_client(hwnd, x, y))
            self._calibrate_scale(hwnd)
            info = self.wm.get_window(hwnd)
            if info:
                self.log(f"后台模式: 已绑定窗口 HWND={hwnd} "
                         f"「{info.title}」 客户区 {info.width}x{info.height}"
                         f"（请确认这是游戏窗口）")
        else:
            self.input.bind(None)
            self.capture.scale = (1.0, 1.0)

        self.stats = Statistics()
        self.debug = DebugManager(os.path.join(APP_ROOT, "logs"))
        controller = AutomationController(
            self.wm, self.capture, self.detector, self.input, self.stats,
            self.debug, on_event=self._on_event, hwnd=hwnd)
        self.worker = AutomationWorker(
            controller, on_finished=self._on_finished)
        self.worker.start(profile)
        self.profiles.save_last(profile)
        self._refresh_flow_enabled(profile)
        self._paused = False
        self._set_ui_running(True)
        self._schedule_stats_clock()

    def pause(self) -> None:
        if self.worker and self.worker.is_alive:
            self.worker.pause()
            self._paused = True
            self.pause_btn.config(state=tk.DISABLED)
            self.resume_btn.config(state=tk.NORMAL)
            self.state_label.config(text="已暂停", foreground="orange")
            self.log("⏸ 已暂停")

    def resume(self) -> None:
        if self.worker and self.worker.is_alive:
            self.worker.resume()
            self._paused = False
            self.resume_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)

    def stop(self) -> None:
        if self.worker and self.worker.is_alive:
            self.worker.stop()
            self.log("⏹ 正在停止...")

    def request_close(self) -> None:
        if self.worker and self.worker.is_alive:
            self.worker.stop()
        self.app.close_tab(self)

    # ---------- Worker事件 -> UI ----------

    def _after(self, fn) -> None:
        try:
            self.after(0, fn)
        except Exception:
            pass  # 标签页已销毁，丢弃

    def _on_event(self, kind: str, data: dict) -> None:
        self._after(lambda: self._handle_event(kind, data))

    # ---- 流程点管线 ----

    _FLOW_STATE_MAP = {
        "find_entry": "entry1", "click_entry": "entry1",
        "find_entry2": "entry2", "click_entry2": "entry2",
        "find_challenge": "challenge", "click_challenge": "challenge",
        "timeout_handled": "challenge",
        "wait_team": "team",
        "find_second": "second", "click_second": "second",
        "wait_battle": "battle",
        "settlement": "settle", "click_end": "end",
    }

    def _build_flow_row(self, parent) -> None:
        """流程点管线一行:阶段名用箭头连接,当前环节高亮。"""
        for i, (key, label) in enumerate(self._flow_stages):
            if i:
                ttk.Label(parent, text="→", foreground="#bbbbbb",
                          font=("", 8)).pack(side=tk.LEFT)
            lbl = tk.Label(parent, text=label, fg="#aaaaaa", bg="#f0f0f0",
                           font=("", 9))
            lbl.pack(side=tk.LEFT, padx=2)
            self._flow_labels[key] = lbl

    def _update_flow(self, state_value: str) -> None:
        """按当前状态高亮对应环节;未启用的环节淡显。"""
        cur = self._FLOW_STATE_MAP.get(state_value)
        for key, lbl in self._flow_labels.items():
            enabled = key in self._flow_enabled
            if key == cur:
                lbl.config(fg="#0a7d18", font=("", 9, "bold"))
            elif not enabled:
                lbl.config(fg="#dddddd", font=("", 9))
            else:
                lbl.config(fg="#666666", font=("", 9))

    def _refresh_flow_enabled(self, profile) -> None:
        """按 profile 决定哪些环节参与显示(start 时调用)。"""
        self._flow_enabled = {
            "challenge", "battle", "settle",
            "team" if profile.team_role == "队员" else None,
            "entry1" if profile.entry_enabled else None,
            "entry2" if (profile.entry_enabled and profile.entry2_enabled)
            else None,
            "second" if profile.second_enabled else None,
            "end" if profile.end_enabled else None,
        } - {None}
        self._update_flow("idle")

    def _handle_event(self, kind: str, data: dict) -> None:
        if kind == "log":
            self.log(data["message"])
        elif kind == "state":
            st_val = data["state"].value
            color = "#0a7d18"
            if st_val in ("idle", "stopped"):
                color = "gray"
            elif st_val == "error":
                color = "red"
            elif st_val == "wait_team":
                color = "#d97706"
            self.state_label.config(
                text=STATE_TEXT.get(st_val, st_val),
                foreground=color)
            self._update_flow(st_val)
            self._set_tab_title()
        elif kind == "progress":
            runs, max_runs = data["runs"], data["max_runs"]
            self._max_runs = max_runs
            self.progress_label.config(text=f"{runs}/{max_runs}")
            if max_runs:
                self.progress_bar["value"] = runs / max_runs * 100
            self._last_stats = data["stats"]
            self.stats_label.config(text=self._stats_text(data["stats"]))
            self._set_tab_title()

    def _on_finished(self, reason: str) -> None:
        self._after(lambda: self._finish_ui(reason))

    def _finish_ui(self, reason: str) -> None:
        if reason == "error":
            self.log("⏹ 因错误停止")
        elif reason == "finished":
            self.log("✅ 已达到目标次数，挂机完成")
        else:
            self.log("⏹ 已停止挂机")
        self._set_ui_running(False)
        self._set_tab_title()

    def _stats_text(self, s) -> str:
        if s is None:
            return "总计 0 | 成功 0 | 失败 0 | 超时 0 | 错误 0 | 运行 0秒"
        return (f"总计 {s.total_runs} | 成功 {s.success} | 失败 {s.failure}"
                f" | 超时 {s.timeout} | 错误 {s.error}"
                f" | 运行 {s.runtime_seconds:.0f}秒")

    def _schedule_stats_clock(self) -> None:
        """运行期间每秒刷新一次时长显示。"""
        def tick():
            if not (self.worker and self.worker.is_alive):
                return
            if self._last_stats is not None:
                self.stats_label.config(text=self._stats_text(self._last_stats))
            try:
                self.after(1000, tick)
            except Exception:
                pass  # 标签页已销毁
        self._after(tick)

    # ---------- UI状态 ----------

    def _set_ui_running(self, running: bool) -> None:
        st = tk.DISABLED if running else tk.NORMAL
        self.start_btn.config(state=st)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.pause_btn.config(
            state=tk.NORMAL if running and not self._paused else tk.DISABLED)
        self.resume_btn.config(
            state=tk.NORMAL if running and self._paused else tk.DISABLED)
        self.template_combo.config(state=st)
        self.keyword_entry.config(state=st)
        self.run_mode_combo.config(state=st)
        self.state_label.config(
            text="运行中" if running else "空闲",
            foreground="green" if running else "gray")

    def _set_tab_title(self) -> None:
        try:
            running = self.worker is not None and self.worker.is_alive
            s = self._last_stats
            if running and s is not None:
                text = f"页{self.tab_id} ● {s.total_runs}/{self._max_runs}"
            else:
                text = f"页{self.tab_id}"
            self.app.notebook.tab(self, text=text)
        except Exception:
            pass

    # ---------- 日志 ----------

    def log(self, message: str) -> None:
        ts = time.strftime("%H:%M:%S")

        def _append():
            try:
                self.log_text.insert(tk.END, f"[{ts}] {message}\n")
                if int(self.log_text.index("end-1c").split(".")[0]) > 1000:
                    self.log_text.delete("1.0", "200.0")
                self.log_text.see(tk.END)
            except Exception:
                pass
        self._after(_append)
