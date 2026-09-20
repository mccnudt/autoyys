"""Worker 与 ProfileManager 测试（Phase 8/11）。"""
import json
import os
import time

from core.models import BattleProfile, Statistics
from profiles.manager import PRESET_PROFILES, ProfileManager
from worker.worker import AutomationWorker

from .conftest import (FakeCapture, FakeDebug, FakeDetector, FakeInput,
                       FakeWM)


class TestProfileManager:

    def test_presets_created_on_first_run(self, tmp_path):
        pm = ProfileManager(str(tmp_path))
        names = pm.list_names()
        for n in PRESET_PROFILES:
            assert n in names

    def test_save_load_roundtrip(self, tmp_path):
        pm = ProfileManager(str(tmp_path))
        p = BattleProfile(name="我的配置", battle_img="a.png",
                          max_runs=42, timeout_click=(10, 20),
                          rest_every="3-5")
        pm.save(p)
        loaded = pm.load("我的配置")
        assert loaded is not None
        assert loaded.battle_img == "a.png"
        assert loaded.max_runs == 42
        assert loaded.timeout_click == (10, 20)
        assert loaded.rest_every == "3-5"

    def test_delete(self, tmp_path):
        pm = ProfileManager(str(tmp_path))
        pm.save(BattleProfile(name="临时", battle_img="x.png"))
        assert pm.delete("临时")
        assert "临时" not in pm.list_names()

    def test_last_profile_roundtrip(self, tmp_path):
        pm = ProfileManager(str(tmp_path))
        pm.save_last(BattleProfile(name="last", max_runs=7))
        got = pm.load_last()
        assert got is not None and got.max_runs == 7

    def test_load_falls_back_to_preset(self, tmp_path):
        pm = ProfileManager(str(tmp_path))
        os.remove(pm.path_of("魂11通用"))
        p = pm.load("魂11通用")
        assert p is not None and p.battle_img == "templates/hun11tz.png"

    def test_load_missing_returns_none(self, tmp_path):
        pm = ProfileManager(str(tmp_path))
        assert pm.load("不存在的名字") is None

    def test_unknown_fields_ignored(self, tmp_path):
        # 向后兼容：旧配置多余字段不炸
        pm = ProfileManager(str(tmp_path))
        path = pm.path_of("带新字段")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"name": "带新字段", "battle_img": "b.png",
                       "future_field": 123}, f)
        p = pm.load("带新字段")
        assert p is not None and p.battle_img == "b.png"


class TestWorker:

    def _make(self, profile, script):
        from controller.automation import AutomationController

        events = []
        c = AutomationController(
            FakeWM(), FakeCapture(), FakeDetector(script), FakeInput(),
            Statistics(), FakeDebug(),
            on_event=lambda k, d: events.append((k, d)), hwnd=1)
        c.RESULT_CLICK_BUFFER = (0, 0)
        finished = []
        w = AutomationWorker(c, on_finished=lambda r: finished.append(r))
        return w, c, finished

    def test_run_to_completion(self):
        profile = BattleProfile(
            name="w", battle_img="b.png", max_runs=2,
            pre_battle_delay=0, detect_interval=0.01, battle_timeout=5)
        script = [["challenge"], [], ["victory"], ["victory"], []]
        w, c, finished = self._make(profile, script)
        w.start(profile)
        w.join(timeout=10)
        assert not w.is_alive
        assert finished == ["finished"]
        assert c.stats.snapshot().total_runs == 2

    def test_stop_interrupts(self):
        profile = BattleProfile(
            name="w", battle_img="b.png", max_runs=1000,
            pre_battle_delay=0, detect_interval=0.01, battle_timeout=5)
        script = [[]]  # 永远找不到挑战 -> 一直跑
        w, c, finished = self._make(profile, script)
        w.start(profile)
        time.sleep(0.2)
        assert w.is_alive
        w.stop()
        w.join(timeout=5)
        assert not w.is_alive
        assert finished == ["finished"]
        assert c.fsm.state.value == "stopped"

    def test_pause_and_resume(self):
        profile = BattleProfile(
            name="w", battle_img="b.png", max_runs=2,
            pre_battle_delay=0, detect_interval=0.01, battle_timeout=5)
        script = [["challenge"], [], ["victory"], ["victory"], []]
        w, c, _ = self._make(profile, script)
        w.start(profile)
        time.sleep(0.1)
        w.pause()
        time.sleep(0.1)
        calls_frozen = c.detector.i  # 暂停后不再推进
        time.sleep(0.2)
        assert c.detector.i == calls_frozen
        w.resume()
        w.join(timeout=10)
        assert finished_or_done(w)

    def test_error_stops_worker(self):
        profile = BattleProfile(
            name="w", battle_img="b.png", max_runs=5, error_action="stop",
            pre_battle_delay=0, detect_interval=0.01, battle_timeout=5)
        # 窗口立即失效 -> ERROR
        class DeadWM(FakeWM):
            def is_window_valid(self, hwnd):
                return False

        from controller.automation import AutomationController
        c = AutomationController(
            DeadWM(), FakeCapture(), FakeDetector([]), FakeInput(),
            Statistics(), FakeDebug(), on_event=lambda k, d: None, hwnd=1)
        finished = []
        w = AutomationWorker(c, on_finished=lambda r: finished.append(r))
        w.start(profile)
        w.join(timeout=5)
        assert finished == ["error"]


def finished_or_done(w):
    return not w.is_alive
