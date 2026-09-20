# Onmyoji AutoBot V1.0 Agent 开发执行任务书

## 总规则

- 一次只执行一个 Task
- 不要一次性生成整个项目
- 每个 Task 必须可运行
- 每个核心模块必须有测试
- 不随意修改已确认接口
- 完成后报告 Created / Modified / Test / Known Issues

---

# Phase 0：初始化

## Task 001：创建项目结构

验收：

- 目录创建完成
- Python Import 正常

## Task 002：创建 requirements.txt

验收：

- 依赖明确
- 可安装

## Task 003：创建 pyproject.toml

验收：

- pytest 可运行
- Ruff 配置完成

---

# Phase 1：GUI

## Task 004：MainWindow

验收：

- GUI 可启动
- 不连接真实自动化

## Task 005：WindowSelector

验收：

- 有刷新按钮
- 有窗口列表

## Task 006：ControlPanel

验收：

- START
- PAUSE
- RESUME
- STOP

---

# Phase 2：窗口

## Task 007：WindowInfo

验收：

- dataclass
- Type Hint

## Task 008：WindowManager

验收：

- 可扫描窗口
- 可验证窗口

## Task 009：WindowManager Tests

验收：

- pytest 通过

---

# Phase 3：截图

## Task 010：CaptureBackend

## Task 011：ScreenCapture

## Task 012：Image Validation

## Task 013：Debug Screenshot

验收：

- 可保存截图
- 图像 shape 正确
- 图像类型正确

---

# Phase 4：Vision

## Task 014：MatchResult

## Task 015：TemplateRegistry

## Task 016：TemplateMatcher

## Task 017：ROI

## Task 018：ScreenDetector

## Task 019：Vision Tests

---

# Phase 5：FSM

## Task 020：GameState

## Task 021：ScreenType

## Task 022：Transition Table

## Task 023：StateMachine

## Task 024：Invalid Transition

## Task 025：State Tests

---

# Phase 6：Input

## Task 026：InputBackend

## Task 027：InputController

## Task 028：CoordinateMapper

## Task 029：MouseBackend

## Task 030：Input Mock Tests

---

# Phase 7：Automation

## Task 031：AutomationSettings

## Task 032：StatisticsModel

## Task 033：Action Base

## Task 034：ActionFactory

## Task 035：AutomationController

## Task 036：run_once

## Task 037：Mock Integration Test

---

# Phase 8：Worker

## Task 038：AutomationWorker

## Task 039：Signals

## Task 040：Pause

## Task 041：Resume

## Task 042：Stop

## Task 043：GUI Integration

---

# Phase 9：Statistics

## Task 044：Statistics

## Task 045：Snapshot

## Task 046：GUI Statistics

---

# Phase 10：Error

## Task 047：BattleTimeout

## Task 048：UnknownScreen

## Task 049：WindowLost

## Task 050：Debug Error Capture

## Task 051：Pause On Error

---

# 每个 Task 完成报告模板

```text
Task:
Completed:

Created Files:
- 

Modified Files:
- 

Tests:
- 

Result:
PASS / FAIL

Known Issues:
- 

Next Task:
-
```
