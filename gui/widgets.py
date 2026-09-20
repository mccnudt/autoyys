"""GUI 公共工具：路径解析、全屏截图框选、坐标拾取。"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

import pyautogui

if getattr(sys, "frozen", False):
    # 打包后：可写数据(配置/日志)放 exe 旁边，只读资源(模板图)在 _MEIPASS
    APP_ROOT = os.path.dirname(sys.executable)
    RESOURCE_ROOT = getattr(sys, "_MEIPASS", APP_ROOT)
else:
    APP_ROOT = RESOURCE_ROOT = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))


def resolve_image(name: str) -> str:
    """图片路径解析：绝对路径直返；相对名依次找 资源目录/数据目录/工作目录。"""
    if not name:
        return ""
    if os.path.isabs(name) and os.path.exists(name):
        return name
    for base in (RESOURCE_ROOT, APP_ROOT, os.curdir):
        cand = os.path.join(base, name)
        if os.path.exists(cand):
            return os.path.abspath(cand)
    return name


def crop_screen(root: tk.Misc) -> Optional[Tuple[int, int, int, int]]:
    """冻结当前屏幕供框选区域，返回 (x, y, w, h)；取消返回 None。"""
    from PIL import Image, ImageTk

    screen_img = pyautogui.screenshot()
    screen_w, screen_h = screen_img.size
    bg = ImageTk.PhotoImage(screen_img)

    overlay = tk.Toplevel(root.winfo_toplevel())
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)
    overlay.configure(cursor="cross")
    overlay.focus_force()
    canvas = tk.Canvas(overlay, highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    canvas.create_image(0, 0, image=bg, anchor=tk.NW)
    canvas.bg_img = bg  # 防止被垃圾回收
    canvas.create_text(screen_w // 2, 40,
                       text="按住鼠标左键拖拽框选图片区域，Esc 取消",
                       fill="yellow", font=("Microsoft YaHei", 14))

    press = [None, None]
    region = [None]
    rect_id = [None]

    def on_press(e):
        press[0], press[1] = e.x_root, e.y_root

    def on_drag(e):
        if press[0] is None:
            return
        x1, y1 = min(press[0], e.x_root), min(press[1], e.y_root)
        x2, y2 = max(press[0], e.x_root), max(press[1], e.y_root)
        if rect_id[0]:
            canvas.delete(rect_id[0])
        rect_id[0] = canvas.create_rectangle(x1, y1, x2, y2, outline="red", width=2)

    def on_release(e):
        if press[0] is not None:
            x1, y1 = min(press[0], e.x_root), min(press[1], e.y_root)
            x2, y2 = max(press[0], e.x_root), max(press[1], e.y_root)
            if x2 - x1 > 5 and y2 - y1 > 5:
                region[0] = (x1, y1, x2 - x1, y2 - y1)
        press[0] = press[1] = None
        overlay.destroy()

    canvas.bind("<Button-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    overlay.bind("<Escape>", lambda e: overlay.destroy())
    overlay.wait_window()
    return region[0]


def pick_screen_coord(root: tk.Misc) -> Optional[Tuple[int, int]]:
    """全屏点击取坐标（截图为背景，避免黑屏），返回 (x, y)；Esc 取消。"""
    from PIL import Image, ImageTk

    screen_img = pyautogui.screenshot()
    bg = ImageTk.PhotoImage(screen_img)
    overlay = tk.Toplevel(root.winfo_toplevel())
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)
    overlay.configure(cursor="cross")
    overlay.focus_force()
    canvas = tk.Canvas(overlay, highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    canvas.create_image(0, 0, image=bg, anchor=tk.NW)
    canvas.bg_img = bg
    canvas.create_text(overlay.winfo_screenwidth() // 2,
                       overlay.winfo_screenheight() // 2,
                       text="点击屏幕任意位置取坐标（Esc 取消）",
                       fill="yellow", font=("Microsoft YaHei", 16))
    result = [None]

    def on_click(e):
        result[0] = (e.x_root, e.y_root)
        overlay.destroy()

    canvas.bind("<Button-1>", on_click)
    overlay.bind("<Escape>", lambda e: overlay.destroy())
    overlay.wait_window()
    return result[0]


def snapshot_region(root: tk.Misc, save_path: str,
                    minimize_win: tk.Misc) -> Optional[str]:
    """最小化窗口 -> 框选 -> 截图保存 -> 恢复。返回保存路径或 None。"""
    minimize_win.iconify()
    minimize_win.update_idletasks()
    time.sleep(0.3)
    try:
        region = crop_screen(root)
    finally:
        minimize_win.deiconify()
        minimize_win.lift()
    if region is None:
        return None
    pyautogui.screenshot(region=region).save(save_path)
    return save_path


def update_img_preview(path: str, label: tk.Label,
                       empty_text: str = "无预览") -> None:
    """在 Label 上显示所选图片缩略图；无效时显示占位文字。"""
    path = (path or "").strip()
    try:
        from PIL import Image, ImageTk
        if not path or not os.path.exists(path):
            raise FileNotFoundError(path)
        img = Image.open(path)
        img.thumbnail((96, 60))
        photo = ImageTk.PhotoImage(img)
        label.config(image=photo, text="")
        label.image = photo
    except Exception:
        label.config(image="", text=empty_text)


def make_image_row(parent, label_text: str, path_var: tk.StringVar,
                   conf_var: tk.StringVar, on_crop, tab_tag: str = "") -> tk.Label:
    """一行：标签+路径+浏览+截图+置信度+预览。返回预览 Label。"""
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(row, text=label_text, width=16, font=("", 9)).pack(side=tk.LEFT)
    ttk.Entry(row, textvariable=path_var, font=("", 9)).pack(
        side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))

    def browse():
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title=f"选择{label_text}",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")])
        if path:
            path_var.set(path)
            update_img_preview(path, preview)

    def crop():
        path = on_crop()
        if path:
            path_var.set(path)
            update_img_preview(path, preview)

    ttk.Button(row, text="浏览", command=browse, width=6).pack(side=tk.LEFT)
    ttk.Button(row, text="截图", command=crop, width=6).pack(
        side=tk.LEFT, padx=(5, 0))
    ttk.Label(row, text="置信度:", font=("", 8)).pack(side=tk.LEFT, padx=(10, 2))
    ttk.Entry(row, textvariable=conf_var, width=4, font=("", 9)).pack(side=tk.LEFT)
    pf = tk.Frame(row, width=80, height=50, bg="#e8e8e8",
                  relief=tk.SUNKEN, bd=1)
    pf.pack(side=tk.LEFT, padx=(8, 0))
    pf.pack_propagate(False)
    preview = tk.Label(pf, bg="#e8e8e8", fg="#888888", text="无", font=("", 8))
    preview.pack(fill=tk.BOTH, expand=True)
    update_img_preview(path_var.get(), preview)
    return preview
