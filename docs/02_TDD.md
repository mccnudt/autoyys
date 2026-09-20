# Onmyoji AutoBot V1.0 技术设计文档（TDD）

## 1. 技术栈

- Python 3.11+
- PySide6
- OpenCV
- numpy
- pywin32
- pytest

## 2. 分层架构

Presentation Layer
↓
Application Layer
↓
Domain Layer
↓
Infrastructure Layer

核心链路：

GUI
↓
AutomationController
↓
StateMachine
↓
ScreenDetector
↓
TemplateMatcher
↓
ScreenCapture
↓
Window

输入：

Action
↓
InputController
↓
InputBackend

## 3. 推荐目录

```text
OnmyojiAutoBot/
├── main.py
├── requirements.txt
├── pyproject.toml
├── config/
├── gui/
├── core/
├── state/
├── models/
├── vision/
├── input/
├── window/
├── logger/
├── debug/
├── templates/
├── logs/
└── tests/
```

## 4. 核心模块

### WindowManager

职责：

- get_windows()
- get_window()
- is_window_valid()
- get_client_rect()

### ScreenCapture

接口：

```python
capture(hwnd: int) -> np.ndarray
```

输出：

BGR numpy.ndarray

### TemplateMatcher

职责：

- 加载模板
- 缓存模板
- ROI
- 阈值判断
- 返回 MatchResult

### ScreenDetector

输入：

Screenshot

输出：

ScreenResult

### StateMachine

负责：

- 当前状态
- 状态转换
- 非法转换验证
- Reset

### InputController

统一输入接口。

具体 Backend 独立实现。

### AutomationController

核心方法：

```python
start()
pause()
resume()
stop()
run_once()
```

## 5. run_once 流程

1. Validate Window
2. Capture
3. Validate Image
4. Detect
5. Update StateMachine
6. Get Action
7. Execute Action
8. Update Statistics
9. Emit Event

## 6. Worker

使用 QThread。

GUI 通过 Signal 接收：

- status_changed
- log_message
- statistics_changed
- error_occurred
- screenshot_updated

## 7. 错误处理

错误：

- WindowLost
- CaptureFailed
- BattleTimeout
- UnknownScreen
- InvalidTransition

处理：

Log
↓
Debug Screenshot
↓
Pause

## 8. 测试

使用 pytest + Mock。

Mock：

- Capture
- Detector
- Input

禁止核心测试依赖真实游戏窗口。

## 9. 开发阶段

Phase 0：项目初始化
Phase 1：GUI Skeleton
Phase 2：WindowManager
Phase 3：Screen Capture
Phase 4：Vision
Phase 5：StateMachine
Phase 6：Input
Phase 7：AutomationController
Phase 8：Worker
Phase 9：Statistics
Phase 10：Error Handling
