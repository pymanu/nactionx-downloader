"""Ventana nativa (pywebview), instancia única, cierre ordenado y reinicio."""
import json
import os
import threading
import time
import urllib.request
import webbrowser

from . import APP_NAME, log, paths, platform_utils, storage

logger = log.get('desktop')


# ------------------------------------------------------------------ instancia única
def instance_path():
    return paths.data_dir() / 'instance.json'


def existing_instance():
    info = storage.read_json(instance_path(), None)
    if not info or not platform_utils.pid_alive(info.get('pid', 0)) or info.get('pid') == os.getpid():
        return None
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{info["port"]}/api/ping')
        with urllib.request.urlopen(request, timeout=2) as response:
            if APP_NAME.encode() in response.read():
                return info
    except Exception:
        return None
    return None


def activate_instance(info):
    try:
        request = urllib.request.Request(
            f'http://127.0.0.1:{info["port"]}/api/app/focus', data=b'{}', method='POST',
            headers={'X-NactionX-Token': info['token'], 'Content-Type': 'application/json'})
        urllib.request.urlopen(request, timeout=3).read()
        return True
    except Exception as e:
        logger.warning('No se pudo activar la instancia existente: %s', e)
        return False


# ------------------------------------------------------------------ puente con la interfaz
class Bridge:
    """Métodos llamados desde la interfaz (window.pywebview.api). Los atributos privados no se exponen."""

    def __init__(self):
        self._window = None

    def pick_folder(self, initial=''):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial or '')
        return result[0] if result else ''

    def pick_file(self, initial=''):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=initial or '',
                                                 file_types=('Cookies (*.txt)', 'Todos los archivos (*.*)'))
        return result[0] if result else ''


class DesktopController:
    """Lo que la API puede pedir a la ventana: diálogos, traer al frente, reiniciar y salir."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.window = None
        self.restart_requested = False
        self.force_close = False

    def pick_folder(self, initial):
        return self.bridge.pick_folder(initial)

    def pick_file(self, initial):
        return self.bridge.pick_file(initial)

    def focus(self):
        window = self.window
        if not window:
            return
        try:
            window.restore()
        except Exception:
            pass
        window.show()
        window.on_top = True
        time.sleep(0.25)
        window.on_top = False

    def restart(self):
        self.restart_requested = True
        self.quit()

    def quit(self):
        self.force_close = True
        threading.Timer(0.3, lambda: self.window and self.window.destroy()).start()


# ------------------------------------------------------------------ arranque
def run(args, settings, components, manager_cls, api_cls, migrate):
    platform_utils.set_app_user_model_id()
    other = existing_instance()
    if other:
        logger.info('Ya hay una instancia abierta (pid %s): se trae al frente', other['pid'])
        activate_instance(other)
        return 0

    manager = manager_cls(settings, components)
    try:
        migrate(settings, manager)
    except Exception:
        logger.exception('Falló la migración del prototipo')

    bridge = Bridge()
    controller = None if args.browser else DesktopController(bridge)
    server = api_cls(manager, settings, components, desktop=controller)
    server.start()
    storage.write_json(instance_path(), {'pid': os.getpid(), 'port': server.port, 'token': server.token})

    try:
        if args.browser:
            print(f'{APP_NAME} en modo navegador: {server.app_url}', flush=True)
            if not args.no_open:
                webbrowser.open(server.app_url)
            while True:
                time.sleep(3600)
        return _run_window(args, manager, server, bridge, controller)
    except KeyboardInterrupt:
        return 0
    finally:
        manager.shutdown()
        server.stop()
        try:
            if (storage.read_json(instance_path(), {}) or {}).get('pid') == os.getpid():
                instance_path().unlink()
        except OSError:
            pass
        if controller and controller.restart_requested:
            platform_utils.spawn_relaunch()


def _run_window(args, manager, server, bridge, controller):
    import webview

    window = webview.create_window(
        APP_NAME, server.app_url, js_api=bridge, width=1380, height=900, min_size=(1040, 680),
        background_color='#090a0e', text_select=True)
    bridge._window = window
    controller.window = window

    def on_closing():
        if controller.force_close:
            return True
        active = manager.active_count()
        if not active:
            return True
        plural = 'descarga activa' if active == 1 else 'descargas activas'
        return bool(window.create_confirmation_dialog(
            'Hay descargas en curso',
            f'Tienes {active} {plural}. Si cierras, se pausarán y continuarán solas la próxima vez que abras '
            f'{APP_NAME}.\n\n¿Cerrar de todos modos?'))

    window.events.closing += on_closing
    options = {'private_mode': False, 'storage_path': str(paths.sub_dir('webview')), 'debug': args.debug}
    if platform_utils.IS_WIN:
        # WinForms solo acepta .ico: un PNG hace fallar System.Drawing.Icon y cierra la app
        options['gui'] = 'edgechromium'
        ico = paths.web_dir() / 'icon.ico'
        if ico.exists():
            options['icon'] = str(ico)
    elif not platform_utils.IS_MAC:
        icon = paths.web_dir() / 'icon.png'
        options['icon'] = str(icon) if icon.exists() else None
    try:
        webview.start(**options)
    except Exception:
        logger.exception('No se pudo abrir la ventana')
        if platform_utils.IS_WIN:
            platform_utils.message_box(
                APP_NAME, 'NactionX Downloader necesita Microsoft Edge WebView2 Runtime, que no está instalado en este equipo.\n\n'
                          'Se abrirá la página oficial de Microsoft para instalarlo. Después, vuelve a abrir la app.')
            webbrowser.open('https://go.microsoft.com/fwlink/p/?LinkId=2124703')
        raise
    return 0
