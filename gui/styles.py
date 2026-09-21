"""GUI 统一样式与设计系统规范常量（PEP 8 & Clean Code）。"""
from __future__ import annotations

# 调色盘规范
COLOR_STATUS_RUNNING = "#2e7d32"    # 运行中/就绪：稳重绿
COLOR_STATUS_WAITING = "#f57c00"    # 等待发车/过渡：暖琥珀色
COLOR_STATUS_ERROR = "#d32f2f"      # 错误/异常：警示红
COLOR_STATUS_IDLE = "#757575"       # 空闲/未开始：柔和灰
COLOR_TIP_INFO = "#0066cc"          # 提示与建议：信息蓝
COLOR_MUTED = "gray"                # 弱化次要文字

# 字体规范（支持跨 DPI 清晰呈现）
FONT_BODY = ("", 9)
FONT_BODY_BOLD = ("", 9, "bold")
FONT_TITLE = ("", 10, "bold")
FONT_SMALL = ("", 8)
FONT_LOG = ("Consolas", 9)
