# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('gspread')
hiddenimports += collect_submodules('google.auth')
hiddenimports += collect_submodules('google.oauth2')


a = Analysis(
    ['run_tracker.py'],
    pathex=['.'],
    binaries=[],
    # картинки скриншотов событий: сайт раздаёт их по /img/..., окно грузит их же
    datas=[('app/web/static', 'app/web/static'),
           # иконка окна (панель задач): без неё панель берёт иконку exe из
           # кэша Windows и после автообновления показывает иконку прошлой версии
           ('assets/SKYHELPER.ico', 'assets')],
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
    a.binaries,
    a.datas,
    [],
    name='SKYHELPER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # собственная иконка (монограмма SH): без неё Windows подставляет логотип Python
    icon='assets/SKYHELPER.ico',
)
