"""API local (solo 127.0.0.1) que usa la interfaz. Protegida con token por sesión y comprobación de Host."""
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import APP_NAME, __version__, errors, log, paths, platform_utils
from .settings import SettingsError

logger = log.get('api')

STATIC = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/app.css': 'app.css',
          '/icon.svg': 'icon.svg'}
URL_RE = re.compile(r'https?://[^\s<>"\']+')


class ApiServer:
    def __init__(self, manager, settings, components, host='127.0.0.1', port=0, desktop=None):
        self.manager, self.settings, self.components = manager, settings, components
        self.token = secrets.token_urlsafe(24)
        self.desktop = desktop  # objeto con pick_folder/pick_file/focus/restart/quit cuando hay ventana nativa
        server = self

        class Handler(RequestHandler):
            app = server

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self.host, self.port = self.httpd.server_address[:2]
        self.thread = None

    @property
    def url(self):
        return f'http://{self.host}:{self.port}/'

    @property
    def app_url(self):
        return f'{self.url}#t={self.token}'

    def start(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name='api')
        self.thread.start()
        logger.info('API en %s', self.url)

    def stop(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass


class RequestHandler(BaseHTTPRequestHandler):
    app = None
    server_version = 'NactionX'
    sys_version = ''

    def log_message(self, fmt, *args):
        pass

    # -- respuestas
    def send(self, code, body=b'', content_type='application/json; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json(self, data, code=200):
        self.send(code, json.dumps(data, ensure_ascii=False))

    def fail(self, message, code=400, kind='other', detail=''):
        self.json({'error': message, 'kind': kind, 'detail': detail}, code)

    # -- seguridad
    def host_ok(self):
        port = self.app.port
        return self.headers.get('Host', '') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def token_ok(self):
        supplied = self.headers.get('X-NactionX-Token', '')
        return bool(supplied) and secrets.compare_digest(supplied, self.app.token)

    # -- enrutado
    def do_GET(self):
        if not self.host_ok():
            return self.send(403, 'forbidden', 'text/plain')
        parsed = urlparse(self.path)
        if parsed.path in STATIC:
            return self.static(STATIC[parsed.path])
        if not parsed.path.startswith('/api/'):
            return self.send(404, 'not found', 'text/plain')
        if parsed.path == '/api/ping':
            return self.json({'ok': True, 'app': APP_NAME})
        if not self.token_ok():
            return self.fail('No autorizado', 401)
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        try:
            return self.route_get(parsed.path, query)
        except Exception as e:
            return self.error(e)

    def do_POST(self):
        if not self.host_ok() or not self.token_ok():
            return self.send(403, 'forbidden', 'text/plain')
        length = min(int(self.headers.get('Content-Length') or 0), 5 * 1024 * 1024)
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.fail('Petición no válida')
        try:
            return self.route_post(urlparse(self.path).path, body)
        except Exception as e:
            return self.error(e)

    def error(self, exc):
        if isinstance(exc, (SettingsError, ValueError)) and not isinstance(exc, errors.FriendlyError):
            return self.fail(str(exc), 400, 'validation')
        message, kind, detail = errors.explain(exc)
        if kind == 'other':
            logger.exception('Error en la API')
        return self.fail(message, 400, kind, detail)

    def static(self, name):
        path = paths.web_dir() / name
        try:
            data = path.read_bytes()
        except OSError:
            return self.send(404, 'not found', 'text/plain')
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        if content_type.startswith(('text/', 'application/javascript')) or name.endswith('.svg'):
            content_type += '; charset=utf-8'
        csp = ("default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        return self.send(200, data, content_type, {'Content-Security-Policy': csp})

    # -- GET
    def route_get(self, path, q):
        app, manager = self.app, self.app.manager
        if path == '/api/bootstrap':
            return self.json({
                'app': {'name': APP_NAME, 'version': __version__, 'platform': sys.platform,
                        'desktop': app.desktop is not None, 'data_dir': str(paths.data_dir()),
                        'portable': paths.is_portable_runtime()},
                'settings': app.settings.snapshot(),
                'components': app.components.status(),
                'folder': platform_utils.folder_info(app.settings.get('folder')),
            })
        if path == '/api/state':
            srev = int(q['srev']) if q.get('srev', '').isdigit() else None
            prev = int(q['prev']) if q.get('prev', '').isdigit() else None
            return self.json(manager.state(srev, prev))
        if path == '/api/history':
            return self.json({'history': manager.history_list()})
        if path == '/api/job-log':
            return self.json({'log': manager.job_log(q.get('id', ''))})
        if path == '/api/clipboard':
            urls = list(dict.fromkeys(URL_RE.findall(platform_utils.read_clipboard() or '')))[:20]
            return self.json({'urls': urls})
        if path == '/api/folder-info':
            return self.json(platform_utils.folder_info(q.get('path') or app.settings.get('folder')))
        if path == '/api/components':
            return self.json(app.components.status())
        return self.fail('Ruta desconocida', 404)

    # -- POST
    def route_post(self, path, b):
        app, manager = self.app, self.app.manager
        if path == '/api/info':
            from . import engine
            return self.json(engine.analyze(str(b.get('query') or ''), bool(b.get('playlist')),
                                            app.settings.snapshot(), app.components))
        if path == '/api/add':
            items = [i for i in (b.get('items') or []) if isinstance(i, dict)]
            return self.json(manager.add(items, b.get('options') or {}, str(b.get('subfolder') or ''), bool(b.get('top'))))
        if path == '/api/add-urls':
            return self.json(manager.add_urls(str(b.get('text') or ''), b.get('options') or {}, bool(b.get('top'))))
        if path == '/api/job':
            return self.json({'ok': manager.job_action(str(b.get('id')), str(b.get('action')))})
        if path == '/api/rename':
            return self.json(manager.rename(str(b.get('id')), b.get('name')))
        if path == '/api/reorder':
            return self.json({'ok': manager.reorder([str(i) for i in b.get('ids') or []]) or True})
        if path == '/api/queue':
            return self.json({'ok': manager.queue_action(str(b.get('action')))})
        if path == '/api/settings':
            updated = app.settings.update(b.get('values') or {})
            return self.json({'settings': updated, 'folder': platform_utils.folder_info(updated['folder'])})
        if path == '/api/history':
            manager.history_action(str(b.get('action')), b.get('id'))
            return self.json({'ok': True})
        if path == '/api/open':
            return self.open_path(b)
        if path == '/api/pick-folder':
            if app.desktop:
                return self.json({'path': app.desktop.pick_folder(b.get('initial') or app.settings.get('folder'))})
            return self.fail('El selector de carpetas solo está disponible en la app de escritorio', 400)
        if path == '/api/pick-file':
            if app.desktop:
                return self.json({'path': app.desktop.pick_file(b.get('initial') or '')})
            return self.fail('El selector de archivos solo está disponible en la app de escritorio', 400)
        if path == '/api/components/check':
            return self.json(app.components.check_update())
        if path == '/api/components/update':
            threading.Thread(target=app.components.install_update, daemon=True, name='update').start()
            return self.json({'ok': True})
        if path == '/api/app/restart':
            if app.desktop:
                app.desktop.restart()
                return self.json({'ok': True})
            return self.fail('Reinicia el proceso manualmente', 400)
        if path == '/api/app/quit':
            if app.desktop:
                app.desktop.quit()
                return self.json({'ok': True})
            return self.fail('No disponible', 400)
        if path == '/api/app/shortcuts':
            return self.json({'links': platform_utils.create_shortcuts()})
        if path == '/api/app/focus':
            if app.desktop:
                app.desktop.focus()
            return self.json({'ok': True})
        return self.fail('Ruta desconocida', 404)

    def open_path(self, b):
        app, mode, path = self.app, b.get('mode'), str(b.get('path') or '')
        if mode in ('file', 'reveal'):
            if path not in app.manager.known_paths():
                return self.fail('Ese archivo no pertenece a tus descargas', 403)
            if not os.path.isfile(path):
                return self.fail('El archivo ya no existe en disco', 404)
            (platform_utils.open_path if mode == 'file' else platform_utils.reveal)(path)
            return self.json({'ok': True})
        if mode == 'logs':
            platform_utils.open_path(str(paths.sub_dir('logs')))
            return self.json({'ok': True})
        if mode == 'notices':
            notices = paths.resource_root() / 'THIRD_PARTY_NOTICES.md'
            if not notices.exists():
                return self.fail('No se encontró el archivo de licencias', 404)
            platform_utils.open_path(str(notices))
            return self.json({'ok': True})
        if mode == 'folder':
            folder = path or app.settings.get('folder')
            if not os.path.isabs(folder):
                return self.fail('Carpeta no válida')
            os.makedirs(folder, exist_ok=True)
            platform_utils.open_path(folder)
            return self.json({'ok': True})
        return self.fail('Acción no válida')
