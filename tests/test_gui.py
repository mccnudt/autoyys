"""GUI 冒烟测试：验证 Tkinter 界面组件、事件绑定、多标签页生命周期（防 UI 回调缺失）。"""
import tkinter as tk
import pytest
from gui.app import App


@pytest.fixture
def gui_app():
    root = tk.Tk()
    root.withdraw()  # 无头隐藏窗口，避免弹出干扰
    app = App(root)
    yield app, root
    try:
        root.destroy()
    except Exception:
        pass


def test_gui_initialization(gui_app):
    app, _ = gui_app
    assert len(app.tabs) >= 1
    tab = app.tabs[0]
    assert hasattr(tab, "_on_run_mode_changed")
    assert hasattr(tab, "_on_team_role_changed")
    assert hasattr(tab, "apply_remark")
    assert hasattr(tab, "_set_window_remark")
    assert hasattr(tab, "_make_image_row")
    assert hasattr(tab, "_previews")
    assert "battle" in tab._previews


def test_gui_mode_and_role_switching(gui_app):
    app, _ = gui_app
    tab = app.tabs[0]

    # 1. 运行模式切换
    tab._vars["run_mode"].set("前台")
    tab._on_run_mode_changed()
    assert "前台" in tab._vars["run_mode"].get()

    tab._vars["run_mode"].set("后台")
    tab._on_run_mode_changed()
    assert "后台" in tab._vars["run_mode"].get()

    # 2. 角色切换与提示文字联动
    for role, expected_kw in [("队员", "免填开始图"), ("队长", "主动点击"), ("单人", "全流程")]:
        tab._vars["team_role"].set(role)
        tab._on_team_role_changed()
        assert expected_kw in tab.role_tip_lbl.cget("text")

    # 3. 模板加载联动
    names = tab.profiles.list_names()
    assert len(names) > 0
    for name in names:
        tab._vars["template"].set(name)
        tab._load_profile()
        assert tab._to_profile() is not None


def test_gui_tab_lifecycle(gui_app):
    app, _ = gui_app
    assert len(app.tabs) == 1
    t2 = app.new_tab()
    assert len(app.tabs) == 2
    assert t2.tab_id == 2

    app.close_tab(t2)
    assert len(app.tabs) == 1
