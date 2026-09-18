"""Todo lo que depende del sistema operativo (Windows, macOS, Linux) está aquí."""
import base64
import os
import shutil
import subprocess
import sys
import threading
import time
from xml.sax.saxutils import escape

from . import APP_ID, APP_NAME, log, paths

logger = log.get('platform')

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def popen_kwargs():
    """Evita ventanas de consola en Windows. En macOS/Linux, creationflags no existe."""
    return {'creationflags': CREATE_NO_WINDOW} if IS_WIN else {}


# ------------------------------------------------------------------ archivos y carpetas
def open_path(path):
    if IS_WIN:
        os.startfile(path)
    elif IS_MAC:
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def reveal(path):
    """Muestra el archivo seleccionado en el Explorador / Finder."""
    if IS_WIN:
        subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
    elif IS_MAC:
        subprocess.Popen(['open', '-R', path])
    else:
        subprocess.Popen(['xdg-open', os.path.dirname(path)])


def folder_info(path):
    info = {'path': path, 'exists': os.path.isdir(path), 'writable': False, 'free': None, 'cloud': cloud_provider(path)}
    probe = path
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if probe and os.path.isdir(probe):
        try:
            info['free'] = shutil.disk_usage(probe).free
        except OSError:
            pass
        info['writable'] = os.access(probe, os.W_OK)
    return info


def ensure_writable(folder):
    os.makedirs(folder, exist_ok=True)
    probe = os.path.join(folder, f'.nactionx-{os.getpid()}-{threading.get_ident()}.tmp')
    with open(probe, 'w') as f:
        f.write('ok')
    os.remove(probe)


def cloud_provider(path):
    """Detecta carpetas sincronizadas con la nube (subidas continuas, archivos bloqueados)."""
    norm = os.path.normcase(os.path.abspath(path or ''))
    for var in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        root = os.environ.get(var)
        if root and norm.startswith(os.path.normcase(os.path.abspath(root))):
            return 'OneDrive'
    parts = norm.replace('\\', '/').split('/')
    lowered = [p.lower() for p in parts]
    if any(p.startswith('onedrive') for p in lowered):
        return 'OneDrive'
    if 'dropbox' in lowered:
        return 'Dropbox'
    if 'google drive' in lowered or 'googledrive' in lowered or 'my drive' in lowered:
        return 'Google Drive'
    if 'mobile documents' in lowered or 'icloud drive' in lowered:
        return 'iCloud Drive'
    if 'cloudstorage' in lowered:
        return 'la nube'
    return ''


# ------------------------------------------------------------------ portapapeles
def _clipboard_windows():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    cf_unicodetext = 13
    if not user32.IsClipboardFormatAvailable(cf_unicodetext):
        return ''
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return ''
    try:
        handle = user32.GetClipboardData(cf_unicodetext)
        if not handle:
            return ''
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ''
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def read_clipboard():
    try:
        if IS_WIN:
            return _clipboard_windows()
        if IS_MAC:
            out = subprocess.run(['pbpaste'], capture_output=True, timeout=2)
            return out.stdout.decode('utf-8', 'replace')
        for cmd in (['wl-paste', '--no-newline'], ['xclip', '-selection', 'clipboard', '-o'], ['xsel', '-ob']):
            if shutil.which(cmd[0]):
                out = subprocess.run(cmd, capture_output=True, timeout=2)
                return out.stdout.decode('utf-8', 'replace')
    except Exception as e:
        logger.debug('Portapapeles no disponible: %s', e)
    return ''


# ------------------------------------------------------------------ notificaciones nativas
POWERSHELL_AUMID = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
TOAST_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:NX_TOAST_XML)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:NX_TOAST_APPID).Show($toast)
'''


def _register_toast_app_id():
    """Registra el AppUserModelID para que las notificaciones muestren el nombre y el icono de la app."""
    try:
        import winreg
        icon = paths.web_dir() / 'icon.png'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\AppUserModelId\{APP_ID}') as key:
            winreg.SetValueEx(key, 'DisplayName', 0, winreg.REG_SZ, APP_NAME)
            if icon.exists():
                winreg.SetValueEx(key, 'IconUri', 0, winreg.REG_SZ, str(icon))
            winreg.SetValueEx(key, 'ShowInSettings', 0, winreg.REG_DWORD, 1)
        return True
    except Exception as e:
        logger.debug('No se pudo registrar el AppUserModelID: %s', e)
        return False


def notify(title, body):
    def run():
        try:
            if IS_WIN:
                xml = ('<toast><visual><binding template="ToastGeneric">'
                       f'<text>{escape(title)}</text><text>{escape(body)}</text>'
                       '</binding></visual></toast>')
                env = dict(os.environ, NX_TOAST_XML=xml,
                           NX_TOAST_APPID=APP_ID if _register_toast_app_id() else POWERSHELL_AUMID)
                encoded = base64.b64encode(TOAST_SCRIPT.encode('utf-16-le')).decode('ascii')
                subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                '-EncodedCommand', encoded], env=env, timeout=20, capture_output=True, **popen_kwargs())
            elif IS_MAC:
                subprocess.run(['osascript', '-e', 'on run argv', '-e',
                                'display notification (item 2 of argv) with title (item 1 of argv)', '-e', 'end run',
                                title, body], timeout=10, capture_output=True)
            elif shutil.which('notify-send'):
                subprocess.run(['notify-send', title, body], timeout=10, capture_output=True)
        except Exception as e:
            logger.debug('No se pudo mostrar la notificación: %s', e)
    threading.Thread(target=run, daemon=True, name='notify').start()


SHORTCUT_SCRIPT = r'''
$shell = New-Object -ComObject WScript.Shell
foreach ($path in $env:NX_LINKS.Split('|')) {
  $link = $shell.CreateShortcut($path)
  $link.TargetPath = $env:NX_TARGET
  $link.Arguments = '-m nactionx'
  $link.WorkingDirectory = $env:NX_WORKDIR
  $link.IconLocation = $env:NX_ICON + ',0'
  $link.Description = $env:NX_NAME
  $link.Save()
}
'''


def create_shortcuts():
    """Accesos directos en el escritorio y el menú Inicio para la versión portable de Windows."""
    if not IS_WIN:
        raise RuntimeError('Solo disponible en Windows')
    runtime = os.path.dirname(sys.executable)
    target = os.path.join(runtime, 'pythonw.exe')
    if not os.path.exists(target):
        raise RuntimeError('No se encontró pythonw.exe junto a la app')
    desktop = paths._windows_known_folder('B4BFCC3A-DB2C-424C-B029-7FE99A87C641')
    programs = paths._windows_known_folder('A77F5D77-2E2B-44C3-A6A2-ABA601054A51')
    links = [os.path.join(folder, f'{APP_NAME}.lnk') for folder in (desktop, programs) if folder]
    env = dict(os.environ, NX_LINKS='|'.join(links), NX_TARGET=target, NX_WORKDIR=str(paths.PROJECT_DIR),
               NX_ICON=str(paths.web_dir() / 'icon.ico'), NX_NAME=APP_NAME)
    encoded = base64.b64encode(SHORTCUT_SCRIPT.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-EncodedCommand', encoded], env=env, capture_output=True, timeout=30, **popen_kwargs())
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace')[-300:] or 'No se pudieron crear los accesos directos')
    return links


def message_box(title, text):
    """Aviso nativo bloqueante, para errores de arranque cuando la interfaz no puede abrirse."""
    try:
        if IS_WIN:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
        elif IS_MAC:
            subprocess.run(['osascript', '-e', 'on run argv', '-e',
                            'display alert (item 1 of argv) message (item 2 of argv) as critical', '-e', 'end run',
                            title, text], timeout=300)
    except Exception:
        pass


# ------------------------------------------------------------------ procesos
def set_app_user_model_id():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def wait_for_exit(pid, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline and pid_alive(pid):
        time.sleep(0.2)


def kill_children(timeout=3):
    """Termina procesos hijos que sigan vivos (ffmpeg, deno) para no dejar archivos bloqueados."""
    try:
        import psutil
        children = psutil.Process(os.getpid()).children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(children, timeout=timeout)
        for child in alive:
            try:
                child.kill()
            except psutil.Error:
                pass
        return len(children)
    except Exception as e:
        logger.warning('No se pudieron cerrar los procesos hijos: %s', e)
        return 0


def relaunch_command():
    if paths.is_frozen():
        return [sys.executable]
    return [sys.executable, '-m', 'nactionx']


def spawn_relaunch(extra_args=()):
    cmd = relaunch_command() + ['--wait-pid', str(os.getpid()), *extra_args]
    kwargs = {'close_fds': True, 'cwd': str(paths.PROJECT_DIR if not paths.is_frozen() else os.path.dirname(sys.executable))}
    if IS_WIN:
        kwargs['creationflags'] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    logger.info('Reiniciando: %s', cmd)
    subprocess.Popen(cmd, **kwargs)
