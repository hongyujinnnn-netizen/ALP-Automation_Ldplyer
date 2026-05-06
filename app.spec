# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


datas = [
    ("assets", "assets"),
]
binaries = []
hiddenimports = [
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
]

tmp_ret = collect_all("uiautomator2")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# uiautomator2 loads these files at runtime through importlib.resources.
# Keep them under uiautomator2/assets so "assets/u2.jar" resolves in frozen builds.
datas += collect_data_files(
    "uiautomator2",
    includes=["assets/*", "ext/htmlreport/assets/*"],
)
hiddenimports += collect_submodules("uiautomator2")


a = Analysis(
    ["Alp_Automation.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ALP-Automation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ALP-Automation",
)
