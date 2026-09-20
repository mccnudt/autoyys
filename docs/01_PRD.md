# Onmyoji AutoBot V1.0 产品需求文档（PRD）

## 1. 项目概述

开发一款 Windows 桌面 GUI 自动化工具，用于对指定游戏窗口进行状态识别和流程自动化。

核心目标：

- 用户选择目标窗口
- 获取目标窗口画面
- 识别挑战/战斗/结算等状态
- 根据有限状态机执行流程
- 提供开始、暂停、恢复、停止
- 显示运行状态、日志和统计数据

## 2. V1.0 功能范围

### 2.1 窗口管理

- 扫描 Windows 窗口
- 用户选择目标窗口
- 保存 HWND
- 检测窗口是否失效
- 获取客户区尺寸

### 2.2 画面识别

V1.0 使用 OpenCV 模板匹配。

支持识别：

- CHALLENGE
- BATTLE
- VICTORY
- FAILURE
- SETTLEMENT
- UNKNOWN
- ERROR

### 2.3 自动化流程

基础流程：

IDLE
↓
FIND_CHALLENGE
↓
CLICK_CHALLENGE
↓
WAIT_BATTLE
↓
CHECK_RESULT
↓
SETTLEMENT
↓
FIND_CHALLENGE

### 2.4 GUI

包含：

- WindowSelector
- SettingsPanel
- StatusPanel
- ControlPanel
- LogPanel
- Screenshot Preview（调试）

### 2.5 控制功能

- START
- PAUSE
- RESUME
- STOP

### 2.6 统计

- 总运行次数
- 成功次数
- 失败次数
- 超时次数
- 错误次数
- 运行时间

## 3. 非功能需求

### 稳定性

- 窗口丢失后停止
- 长时间 UNKNOWN 后暂停
- 战斗超时后进入错误状态
- 保存调试截图

### 性能

建议检测间隔：

0.5～1.0 秒

优先优化：

1. ROI
2. Template Cache
3. Image Resize

### 可维护性

- 模块化
- Type Hint
- 配置文件
- Logging
- pytest
- Dependency Injection

## 4. V1.0 不包含

- OCR 作为核心依赖
- AI 深度学习识别
- 多窗口完整调度
- 云端同步
- 历史数据库
- GPU 推理

## 5. 验收标准

- GUI 可启动
- 可选择窗口
- 可获取窗口画面
- 模板识别可测试
- FSM 可测试
- Worker 不阻塞 GUI
- 可暂停/恢复/停止
- 有日志
- 有 Debug 截图
- 有核心 pytest
