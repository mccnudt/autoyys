# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：build_venv\Scripts\pyinstaller autobot.spec --noconfirm
# exe 文件名带版本号（读 VERSION 文件），升级版本不会覆盖旧 exe。
# 模板图片作为数据文件打入，运行时解压到 _MEIPASS；配置/日志写在 exe 旁边。

import os

with open(os.path.join(os.getcwd(), "VERSION"), encoding="utf-8") as f:
    APP_VERSION = f.read().strip()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('VERSION', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'OnmyojiAutoBot_v{APP_VERSION}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
