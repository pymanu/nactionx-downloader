"""Rutas de la app: recursos empaquetados, datos del usuario y carpetas del sistema."""
import os
import platform
import sys
from pathlib import Path

from . import APP_NAME

PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


def platform_tag():
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    return 'linux'


def arch_tag():
    machine = platform.machine().lower()
    return {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine, machine)


def resource_root():
    return Path(getattr(sys, '_MEIPASS', PROJECT_DIR))


def web_dir():
    return resource_root() / 'nactionx' / 'web' if is_frozen() else PKG_DIR / 'web'


def is_portable_runtime():
    """Distribución de Windows sobre el Python oficial firmado (runtime/ + app/), compatible con Smart App Control."""
    return not is_frozen() and (PROJECT_DIR / 'bin').is_dir() and Path(sys.executable).parent.name.lower() == 'runtime'


def bin_dirs():
    """Carpetas donde buscar ffmpeg, ffprobe y deno incluidos con la app."""
    if is_frozen():
        candidates = [resource_root() / 'bin']
    else:
        base = PROJECT_DIR / 'packaging' / 'bin'
        candidates = [PROJECT_DIR / 'bin', base / f'{platform_tag()}-{arch_tag()}', base / platform_tag()]
    return [d for d in candidates if d.is_dir()]


_data_dir = None


def data_dir():
    global _data_dir
    if _data_dir is None:
        override = os.environ.get('NACTIONX_DATA_DIR')
        if override:
            path = Path(override)
        elif sys.platform == 'win32':
            path = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / APP_NAME
        elif sys.platform == 'darwin':
            path = Path.home() / 'Library' / 'Application Support' / APP_NAME
        else:
            path = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'nactionx-downloader'
        path.mkdir(parents=True, exist_ok=True)
        _data_dir = path
    return _data_dir


def sub_dir(name):
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _windows_known_folder(guid_text):
    import ctypes
    import uuid
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                    ('Data4', ctypes.c_ubyte * 8)]

    u = uuid.UUID(guid_text)
    guid = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    out = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_wchar_p)]
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return out.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def downloads_dir():
    if sys.platform == 'win32':
        try:
            found = _windows_known_folder('374DE290-123F-4565-9164-39C4925E467B')
            if found:
                return Path(found)
        except Exception:
            pass
    return Path.home() / 'Downloads'


def default_download_folder():
    return str(downloads_dir() / APP_NAME)


def legacy_data_dirs():
    """Carpetas de datos del prototipo «Descargador», para migrar ajustes, cola e historial."""
    home = Path.home()
    desktops = [home / 'OneDrive' / 'Desktop', home / 'OneDrive' / 'Escritorio', home / 'Desktop', home / 'Escritorio']
    for var in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        if os.environ.get(var):
            desktops += [Path(os.environ[var]) / 'Desktop', Path(os.environ[var]) / 'Escritorio']
    found, seen = [], set()
    for desk in desktops:
        for sub in ('data', 'legacy/data'):
            candidate = desk / 'descargador' / sub
            key = os.path.normcase(str(candidate))
            if key in seen:
                continue
            seen.add(key)
            if (candidate / 'settings.json').exists() or (candidate / 'history.json').exists():
                found.append(candidate)
    return found
