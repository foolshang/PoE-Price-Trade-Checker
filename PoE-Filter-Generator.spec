# -*- mode: python ; coding: utf-8 -*-
# Standalone Filter Generator. Only stdlib + tkinter are needed (verified by an
# import scan of filter_service/filter_window/config/hub_client/...), so the
# checker-only dependencies (tray, OCR/WinRT) are excluded.
datas = [('poe_price_trade/assets/icon.ico', 'poe_price_trade/assets')]
binaries = []
hiddenimports = []


a = Analysis(
    ['run_filtergen.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pystray', 'PIL', 'winrt'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PoE-Filter-Generator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='poe_price_trade/assets/icon.ico',
)
