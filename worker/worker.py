"""AutomationWorker：后台线程驱动 AutomationController（TDD Phase 8）。

- pause：不再执行 run_once，但线程存活、可即时恢复；
- resume / stop：通过 Event 唤醒，pause 中的等待也是可中断的；
- 控制器每拍内部都不长阻塞，因此暂停/停止响应延迟 <= 一个检测间隔。
"""
from __future__ import annotations

import threading
import traceback
from typing import Callable, Optional

from controller.automation import AutomationController
from core.models import BattleProfile
from state.machine import GameState


class AutomationWorker:
    """持有控制器并按间隔驱动。回调均在工作线程调用，GUI 侧自行线程安全。"""

    def __init__(self, controller: AutomationController,
                 on_finished: Optional[Callable[[str], None]] = None) -> None:
        self.controller = controller
        self.on_finished = on_finished or (lambda reason: None)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._resume = threading.Event()

    # ---- 控制 ----

    def start(self, profile: BattleProfile) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.controller.start(profile)
        self._stop.clear()
        self._pause.clear()
        self._resume.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self._thread and self._thread.is_alive():
            self._pause.set()
            self._resume.clear()

    def resume(self) -> None:
        self._pause.clear()
        self._resume.set()

    def stop(self) -> None:
        self._stop.set()
        self._resume.set()  # 从 pause 等待中唤醒

    def join(self, timeout: float = 5.0) -> None:
        if self._thread:
            self._thread.join(timeout)

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---- 线程体 ----

    def _run(self) -> None:
        c = self.controller
        reason = "finished"
        try:
            while not self._stop.is_set():
                if self._pause.is_set():
                    if self._resume.wait(timeout=1.0):
                        if not self._stop.is_set():
                            c.on_event("log", {"message": "▶ 已恢复运行"})
                    continue
                try:
                    c.run_once()
                except Exception:
                    c.on_event("log", {
                        "message": f"❌ 执行出错:\n{traceback.format_exc()}"})
                    c.stats.increment_error()
                    break
                if c.finished:
                    if c.fsm.state == GameState.ERROR:
                        reason = "error"
                    break
                self._stop.wait(c.profile.detect_interval)
            if self._pause.is_set():
                c.on_event("log", {"message": "⏹ 已在暂停状态下停止"})
        finally:
            if c.fsm.state != GameState.STOPPED:
                c.fsm.transition_to(GameState.STOPPED)
                c.on_event("state", {"state": c.fsm.state})
            self.on_finished(reason)
