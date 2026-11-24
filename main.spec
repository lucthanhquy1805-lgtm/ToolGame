# -*- mode: python ; coding: utf-8 -*-
# Rebuilt spec (the original was not in the shipped build).
# Build:  .venv\Scripts\pyinstaller --noconfirm main.spec
# Output: dist\main\  (onedir). Ship the whole folder; main.exe needs _internal\.
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from lineage_auto.hunt_maps import pyinstaller_onnx_datas  # noqa: E402

datas = [
    ("hp_template.png", "."),
    (os.path.join("lineage_auto", "data"), os.path.join("lineage_auto", "data")),
]
if os.path.exists("mp_template.png"):
    datas.append(("mp_template.png", "."))
datas += pyinstaller_onnx_datas("model")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["onnxruntime", "win32timezone"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="main",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    uac_admin=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="main")
