"""Aviso de versión nueva de la app.

Las descargas se publican en un repositorio de GitHub público aparte del código, para que esta
comprobación no necesite ninguna credencial dentro de la app: pedirle a GitHub la última publicación
de un repositorio privado exigiría llevar un token incrustado, y un token incrustado no es secreto.

La app no se actualiza sola: avisa, enseña las novedades y abre la descarga que le toca a este
sistema (instalador .exe en Windows, .dmg de la arquitectura correcta en macOS).
"""
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from . import APP_NAME, __version__, log, paths, storage

logger = log.get('updates')

REPO = 'pymanu/nactionx-downloader-releases'
LATEST_API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPO}/releases/latest'
MIN_INTERVAL = 6 * 3600  # no preguntar a GitHub más de una vez cada seis horas
TIMEOUT = 15


def version_tuple(text):
    """'v1.10.2' -> (1, 10, 2). Compara por números, así que la 1.10 va después de la 1.9."""
    numbers = re.findall(r'\d+', str(text or ''))[:4]
    return tuple(int(n) for n in numbers) if numbers else (0,)


def is_newer(candidate, current=None):
    return version_tuple(candidate) > version_tuple(current or __version__)


def asset_pattern():
    """Qué archivo de la publicación le corresponde a este ordenador."""
    if sys.platform == 'win32':
        return re.compile(r'Windows-x64-Setup\.exe$', re.I)
    if sys.platform == 'darwin':
        return re.compile(r'macOS-' + re.escape(paths.arch_tag()) + r'\.dmg$', re.I)
    return None


def pick_asset(assets):
    pattern = asset_pattern()
    if not pattern:
        return None
    for asset in assets or []:
        name = str(asset.get('name') or '')
        if pattern.search(name):
            return {'name': name, 'url': asset.get('browser_download_url') or '',
                    'size': int(asset.get('size') or 0)}
    return None


def trim_notes(text, limit=700):
    """Las notas de la publicación en texto plano, sin encabezados de Markdown ni enlaces sueltos."""
    lines = []
    for line in str(text or '').splitlines():
        line = re.sub(r'^\s*#+\s*', '', line).strip()
        line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
        if line and not line.startswith('<!--'):
            lines.append(line)
    notes = '\n'.join(lines)
    return notes[:limit].rstrip() + ('…' if len(notes) > limit else '')


def fetch_latest():
    request = urllib.request.Request(LATEST_API, headers={
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': f'{APP_NAME}/{__version__}',
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


class AppUpdates:
    """Estado del aviso de versión, compartido entre la interfaz y la comprobación de fondo."""

    def __init__(self, path=None):
        self.path = path or paths.data_dir() / 'app_update.json'
        self._lock = threading.RLock()
        stored = storage.read_json(self.path, {}) or {}
        self.checked_at = float(stored.get('checked_at') or 0)
        found = stored.get('found') or {}
        # Una versión guardada que ya se ha instalado deja de ser noticia.
        self.found = found if found.get('version') and is_newer(found['version']) else {}
        self.state = 'available' if self.found else 'idle'
        self.error = ''

    # ------------------------------------------------------------ estado para la interfaz
    def status(self):
        with self._lock:
            data = {'state': self.state, 'current': __version__, 'page': RELEASES_PAGE,
                    'checked_at': self.checked_at, 'message': self._message()}
            data.update(self.found or {})
            if self.error:
                data['error'] = self.error
            return data

    def _message(self):
        if self.state == 'checking':
            return 'Buscando una versión nueva…'
        if self.state == 'available':
            return f'Hay una versión nueva: {self.found.get("version")} (tienes la {__version__}).'
        if self.state == 'error':
            return self.error or 'No se pudo comprobar si hay una versión nueva.'
        if self.state == 'current':
            return f'Tienes la última versión ({__version__}).'
        return f'Versión {__version__}.'

    def _save(self):
        storage.write_json(self.path, {'checked_at': self.checked_at, 'found': self.found})

    # ------------------------------------------------------------ comprobación
    def check(self, force=True):
        with self._lock:
            if self.state == 'checking':
                return self.status()
            if not force and time.time() - self.checked_at < MIN_INTERVAL:
                return self.status()
            self.state, self.error = 'checking', ''
        try:
            release = fetch_latest()
        except urllib.error.HTTPError as e:
            # 404 mientras todavía no se ha publicado nada: no es un fallo que merezca alarmar.
            reason = ('Todavía no hay ninguna versión publicada.' if e.code == 404
                      else f'GitHub respondió {e.code} al comprobar la versión.')
            return self._finish_error(reason, e)
        except Exception as e:
            return self._finish_error('No se pudo conectar con GitHub para comprobar la versión.', e)

        version = str(release.get('tag_name') or release.get('name') or '').lstrip('vV')
        with self._lock:
            self.checked_at = time.time()
            if version and is_newer(version):
                self.found = {
                    'version': version,
                    'name': str(release.get('name') or f'Versión {version}'),
                    'notes': trim_notes(release.get('body')),
                    'url': str(release.get('html_url') or RELEASES_PAGE),
                    'published': str(release.get('published_at') or ''),
                    'asset': pick_asset(release.get('assets')),
                }
                self.state = 'available'
                logger.info('Versión nueva disponible: %s', version)
            else:
                self.found, self.state = {}, 'current'
            self._save()
            return self.status()

    def _finish_error(self, message, exception):
        logger.warning('Comprobación de versión fallida: %s', exception)
        with self._lock:
            # Si ya se conocía una versión nueva, el fallo de red no debe borrar el aviso.
            self.state = 'available' if self.found else 'error'
            self.error = message
            return self.status()

    def check_in_background(self, force=False):
        threading.Thread(target=self.check, args=(force,), daemon=True, name='app-update').start()

    def open_download(self):
        """Abre en el navegador el archivo que toca, o la página de la publicación si no hay uno."""
        with self._lock:
            found = dict(self.found or {})
        asset = found.get('asset') or {}
        target = asset.get('url') or found.get('url') or RELEASES_PAGE
        webbrowser.open(target)
        return {'ok': True, 'url': target}
