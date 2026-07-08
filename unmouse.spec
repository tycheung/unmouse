# PyInstaller spec for unmouse — run: poetry run pyinstaller unmouse.spec --noconfirm
from pathlib import Path

block_cipher = None

repo_root = Path(SPECPATH)
src_path = str(repo_root / "src")

a = Analysis(
    [str(repo_root / "src" / "unmouse" / "__main__.py")],
    pathex=[src_path],
    binaries=[],
    datas=[
        (str(repo_root / "assets" / "gestures"), "assets/gestures"),
        (str(repo_root / "assets" / "ui"), "assets/ui"),
        (str(repo_root / "assets" / "icon.ico"), "assets"),
    ],
    hiddenimports=[
        "mediapipe",
        "pydantic_settings",
        "webview",
        "pystray",
        "uiautomation",
        "mss",
        "keyboard",
        "eyeGestures",
        "cv2",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "unmouse.main",
        "unmouse.launcher.panel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter.test"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="unmouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(repo_root / "assets" / "icon.ico"),
    onefile=True,
)
