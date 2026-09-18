# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: NactionX Downloader para Windows (carpeta + .exe) y macOS (.app)."""
import os
import platform
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from nactionx import APP_NAME, __version__  # noqa: E402

IS_WIN, IS_MAC = sys.platform == 'win32', sys.platform == 'darwin'
PLATFORM = 'windows' if IS_WIN else 'macos' if IS_MAC else 'linux'
ARCH = os.environ.get('NACTIONX_ARCH') or {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower(), 'x64')
BIN_DIR = Path(os.environ.get('NACTIONX_BIN_ROOT') or ROOT / 'packaging' / 'bin') / f'{PLATFORM}-{ARCH}'
if not BIN_DIR.is_dir():
    raise SystemExit(f'Faltan FFmpeg/Deno en {BIN_DIR}. Ejecuta: python packaging/fetch_components.py')

binaries = [(str(p), 'bin') for p in sorted(BIN_DIR.iterdir()) if p.is_file()]
datas = [
    (str(ROOT / 'nactionx' / 'web'), 'nactionx/web'),
    (str(ROOT / 'THIRD_PARTY_NOTICES.md'), '.'),
]
datas += collect_data_files('yt_dlp_ejs') + copy_metadata('yt-dlp') + copy_metadata('yt-dlp-ejs')

# Módulos de la biblioteca estándar que versiones futuras de yt-dlp podrían usar al actualizarse desde la app
STDLIB_EXTRA = ['asyncio', 'concurrent', 'email', 'encodings', 'html', 'http', 'importlib', 'json', 'urllib', 'xml',
                'sqlite3', 'ctypes']
hiddenimports = collect_submodules('yt_dlp') + collect_submodules('yt_dlp_ejs')
for package in STDLIB_EXTRA:
    hiddenimports += collect_submodules(package)
hiddenimports += ['psutil', 'certifi', 'brotli', 'mutagen', 'Cryptodome', 'websockets', 'requests', 'urllib3',
                  'bz2', 'lzma', 'gzip', 'zipfile', 'tarfile', 'hmac', 'secrets', 'uuid', 'netrc', 'getpass',
                  'unicodedata', 'shlex', 'difflib', 'statistics', 'decimal', 'fractions', 'queue', 'selectors',
                  'webbrowser', 'mimetypes', 'dataclasses', 'contextvars', 'graphlib', 'string', 'textwrap']

a = Analysis(
    [str(ROOT / 'packaging' / 'launcher.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['tkinter', '_tkinter', 'pytest', '_pytest', 'PIL', 'numpy', 'matplotlib', 'IPython'],
    noarchive=False,
)
# PyInstaller analiza las dependencias de ffmpeg.exe y copia sus DLL también en la raíz (≈180 MB duplicados).
# ffmpeg las carga desde su propia carpeta bin/, así que las copias de la raíz sobran.
BUNDLED = {p.name.lower() for p in BIN_DIR.iterdir()}
a.binaries = [entry for entry in a.binaries
              if not ('/' not in entry[0].replace('\\', '/') and entry[0].lower() in BUNDLED)]
pyz = PYZ(a.pure)

version_file = None
if IS_WIN:
    parts = tuple(int(x) for x in (__version__.split('.') + ['0'] * 4)[:4])
    version_file = Path(workpath) / 'version_info.txt'
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('0C0A04B0', [
      StringStruct('CompanyName', 'NactionX'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('LegalCopyright', 'NactionX'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])])
  ]
)''', encoding='utf-8')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / 'packaging' / 'icons' / ('icon.ico' if IS_WIN else 'icon.icns')),
    version=str(version_file) if version_file else None,
    upx=False,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=str(ROOT / 'packaging' / 'icons' / 'icon.icns'),
        bundle_identifier='com.nactionx.downloader',
        version=__version__,
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'LSMinimumSystemVersion': '11.0',
            'NSHighResolutionCapable': True,
            'LSApplicationCategoryType': 'public.app-category.utilities',
            'NSHumanReadableCopyright': 'NactionX',
        },
    )
