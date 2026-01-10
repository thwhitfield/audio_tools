# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Audio Tools Streamlit app.

Build with: pyinstaller AudioTools.spec --clean
"""

import glob
import sys
from pathlib import Path

block_cipher = None

# Get the app directory (where this spec file is)
app_dir = Path(SPECPATH)
project_root = app_dir.parent

# Check for icon file
icon_path = app_dir / 'icon.icns'
icon_file = str(icon_path) if icon_path.exists() else None

# Collect rubberband binaries
binaries_dir = app_dir / 'binaries'
rubberband_binaries = []
if binaries_dir.exists():
    for binary in binaries_dir.glob('*'):
        if binary.is_file():
            # Put all binaries in a 'bin' subdirectory
            rubberband_binaries.append((str(binary), 'bin'))

a = Analysis(
    ['run_app.py'],
    pathex=[str(project_root)],
    binaries=rubberband_binaries,
    datas=[
        # Include the main streamlit app
        ('main.py', '.'),
        # Include the audio_tools package
        (str(project_root / 'audio_tools'), 'audio_tools'),
        # Streamlit config
        ('.streamlit', '.streamlit'),
    ],
    hiddenimports=[
        'streamlit',
        'streamlit.runtime.scriptrunner.magic_funcs',
        'pydub',
        'gtts',
        'audio_tools',
        'audio_tools.process',
        'audio_tools.podcast_search',
        'static_ffmpeg',
        'pyrubberband',
        'numpy',
        'feedparser',
        'sgmllib3k',
        'requests',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AudioTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=True,  # Important for macOS
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AudioTools',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='Audio Tools.app',
    icon=icon_file,
    bundle_identifier='com.audiotools.app',
    info_plist={
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'Audio Tools',
        'NSHighResolutionCapable': True,
    },
)
