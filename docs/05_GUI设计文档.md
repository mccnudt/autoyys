# Onmyoji AutoBot V1.0 GUI 设计文档

## 1. 主窗口

建议：

- 默认 1200 × 800
- 最小 1000 × 700
- Dark Theme

## 2. 布局

```text
┌──────────────────────────────────────────────┐
│              Onmyoji AutoBot                 │
├───────────────────┬──────────────────────────┤
│ 窗口选择          │ 当前状态                 │
│                   │                          │
│ 设置              │ 统计信息                 │
├───────────────────┴──────────────────────────┤
│ START   PAUSE   RESUME   STOP                │
├──────────────────────────────────────────────┤
│ Debug Screenshot Preview                     │
├──────────────────────────────────────────────┤
│ Log                                          │
│                                              │
└──────────────────────────────────────────────┘
```

## 3. WindowSelector

控件：

- Refresh Button
- ComboBox
- Window Info

## 4. SettingsPanel

- Max Runs
- Battle Timeout
- Detect Interval
- Template Threshold
- Auto Settlement
- Pause On Error

## 5. StatusPanel

显示：

- Current State
- Current Screen
- Window Status
- Automation Status

## 6. StatisticsPanel

显示：

- Total Runs
- Success
- Failure
- Timeout
- Error
- Runtime

## 7. ControlPanel

按钮状态：

### IDLE

START：Enabled

### RUNNING

PAUSE：Enabled
STOP：Enabled

### PAUSED

RESUME：Enabled
STOP：Enabled

### ERROR

STOP：Enabled

## 8. LogPanel

使用 QPlainTextEdit。

最大行数：

1000

超过后删除旧日志。

## 9. Preview

Debug 模式下显示截图。

刷新频率：

最多每秒一次。
