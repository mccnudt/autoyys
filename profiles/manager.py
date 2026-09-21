"""ProfileManager：战斗配置（BattleProfile）的保存/加载/删除/预置。

对应 YYSGUI 的"通用模板管理"功能（文档未覆盖的自定 Phase 11）：
- 预置模板（魂11通用/御灵通用/业原火通用/活动通用）首次运行自动生成；
- 用户配置保存为 profiles/<名称>.json；
- last_profile.json 记录上次运行配置，启动时自动恢复。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from core.models import BattleProfile

# YYSGUI 预置模板原样移植（字段名按新模型映射）
PRESET_PROFILES: Dict[str, dict] = {
    "魂11通用": {
        "battle_img": "templates/hun11tz.png", "victory_img": "templates/victory.png",
        "defeat_img": "templates/failure.png", "confirm_img": "templates/jiesuan.png",
        "battle_threshold": 0.8, "victory_threshold": 0.8,
        "defeat_threshold": 0.7, "confirm_threshold": 0.8,
        "max_runs": 100, "battle_timeout": 60,
        "rest_every": "8-12", "rest_seconds": "5-10",
        "error_action": "continue"},
    "御灵通用": {
        "battle_img": "templates/tz.png", "victory_img": "templates/victory.png",
        "defeat_img": "templates/failure.png", "confirm_img": "templates/jiesuan.png",
        "battle_threshold": 0.8, "victory_threshold": 0.8,
        "defeat_threshold": 0.7, "confirm_threshold": 0.8,
        "max_runs": 50, "battle_timeout": 60,
        "rest_every": "4-6", "rest_seconds": "3-5",
        "error_action": "stop"},
    "业原火通用": {
        "battle_img": "templates/tz.png", "victory_img": "templates/victory.png",
        "defeat_img": "templates/failure.png", "confirm_img": "templates/jiesuan.png",
        "battle_threshold": 0.7, "victory_threshold": 0.6,
        "defeat_threshold": 0.7, "confirm_threshold": 0.8,
        "max_runs": 80, "battle_timeout": 60,
        "rest_every": "6-10", "rest_seconds": "3-7",
        "error_action": "continue"},
    "活动通用": {
        "battle_img": "templates/pata.png", "victory_img": "templates/final.png",
        "defeat_img": "templates/failure.png", "confirm_img": "templates/jiesuan.png",
        "battle_threshold": 0.8, "victory_threshold": 0.8,
        "defeat_threshold": 0.7, "confirm_threshold": 0.8,
        "max_runs": 50, "battle_timeout": 60,
        "rest_every": "5-8", "rest_seconds": "3-6",
        "error_action": "continue"},
    "结界突破通用": {
        "battle_img": "templates/tupo1.png",
        "second_enabled": True, "second_img": "templates/jingongjiejie.png",
        "victory_img": "templates/victory.png",
        "defeat_img": "templates/failure.png",
        "confirm_img": "templates/jiesuan.png",
        "battle_threshold": 0.8, "second_threshold": 0.8,
        "victory_threshold": 0.8, "defeat_threshold": 0.7,
        "confirm_threshold": 0.8,
        "battle_clicks": 1, "match_strategy": "最上面",
        "max_runs": 30, "battle_timeout": 0,
        "rest_every": "5-8", "rest_seconds": "3-6",
        "error_action": "continue"},
    "困难28通用": {
        "battle_img": "templates/tansuo.png",
        "entry_enabled": True, "entry_img": "templates/kun28.png",
        "entry_threshold": 0.7, "entry_delay": 3,
        "entry2_enabled": True, "entry2_img": "templates/tansuokaishi.png",
        "entry2_threshold": 0.7, "entry2_delay": 3,
        "end_enabled": True, "end_img": "templates/tansuojieshu.png",
        "end_threshold": 0.7,
        "victory_img": "templates/victory.png",
        "defeat_img": "templates/failure.png",
        "confirm_img": "templates/jiesuan.png",
        "battle_threshold": 0.8, "victory_threshold": 0.8,
        "defeat_threshold": 0.7, "confirm_threshold": 0.8,
        "max_runs": 100, "battle_timeout": 60,
        "rest_every": "10-15", "rest_seconds": "3-6",
        "error_action": "continue"},
}


class ProfileManager:

    def __init__(self, profile_dir: str) -> None:
        self.dir = profile_dir
        os.makedirs(self.dir, exist_ok=True)
        self._init_presets()

    # ---- 预置 ----

    def _init_presets(self, overwrite: bool = False) -> None:
        """首次运行初始化预置模板；若文件已存在则不强制覆盖，保护用户的微调配置。"""
        for name, d in PRESET_PROFILES.items():
            path = self.path_of(name)
            if overwrite or not os.path.exists(path):
                self.save(BattleProfile.from_dict({**d, "name": name}))

    # ---- CRUD ----

    def list_names(self) -> List[str]:
        """预置模板按定义顺序在前（文件删除后仍可用，load 有内置兜底），
        用户模板按名称序在后。"""
        try:
            files = [f[:-5] for f in os.listdir(self.dir)
                     if f.endswith(".json") and f != "last_profile.json"]
        except OSError:
            files = []
        return list(PRESET_PROFILES) + sorted(
            f for f in files if f not in PRESET_PROFILES)

    def path_of(self, name: str) -> str:
        return os.path.join(self.dir, f"{name}.json")

    def load(self, name: str) -> Optional[BattleProfile]:
        path = self.path_of(name)
        if not os.path.exists(path):
            preset = PRESET_PROFILES.get(name)
            return BattleProfile.from_dict({**preset, "name": name}) if preset else None
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return BattleProfile.from_dict(d)
        except (OSError, ValueError):
            return None

    def save(self, profile: BattleProfile) -> str:
        path = self.path_of(profile.name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    def delete(self, name: str) -> bool:
        path = self.path_of(name)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    # ---- 上次运行配置 ----

    @property
    def last_path(self) -> str:
        return os.path.join(self.dir, "last_profile.json")

    def save_last(self, profile: BattleProfile) -> None:
        try:
            with open(self.last_path, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_last(self) -> Optional[BattleProfile]:
        try:
            with open(self.last_path, "r", encoding="utf-8") as f:
                return BattleProfile.from_dict(json.load(f))
        except (OSError, ValueError):
            return None
