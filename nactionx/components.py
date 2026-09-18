"""Componentes externos: FFmpeg, FFprobe, motor JavaScript (Deno/Node) y el motor yt-dlp actualizable.

yt-dlp se puede actualizar sin reinstalar la app: se descargan los paquetes oficiales (wheels) de PyPI,
se verifica su SHA-256 y, al arrancar, se importan desde ellos por delante de la versión incluida.
"""
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.request

from . import __version__, log, paths, platform_utils, storage

logger = log.get('components')

OVERLAY_PACKAGES = ('yt_dlp', 'yt_dlp_ejs')
USER_AGENT = f'NactionX-Downloader/{__version__}'
BUNDLED_YTDLP_FALLBACK = '2026.08.19'


# ------------------------------------------------------------------ versión incluida y superposición
def _version_key(text):
    return tuple(int(n) for n in re.findall(r'\d+', str(text or '0')))


def bundled_ytdlp_version():
    try:
        import importlib.metadata
        return importlib.metadata.version('yt-dlp')
    except Exception:
        try:
            from . import _build
            return _build.YTDLP_VERSION
        except Exception:
            return BUNDLED_YTDLP_FALLBACK


def overlay_meta_path():
    return paths.sub_dir('components') / 'ytdlp.json'


def overlay_wheel_dir():
    folder = paths.sub_dir('components') / 'python'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class _OverlayFinder(importlib.abc.MetaPathFinder):
    """Resuelve yt_dlp y yt_dlp_ejs desde los wheels actualizados antes que desde la copia congelada."""

    def __init__(self, roots):
        self.roots = [str(r) for r in roots]

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.partition('.')[0]
        if top not in OVERLAY_PACKAGES:
            return None
        if '.' not in fullname:
            return importlib.machinery.PathFinder.find_spec(fullname, self.roots)
        parent = sys.modules.get(fullname.rpartition('.')[0])
        search = getattr(parent, '__path__', None)
        return importlib.machinery.PathFinder.find_spec(fullname, list(search)) if search else None


_overlay_version = None


def apply_overlay():
    """Llamar ANTES de importar yt_dlp. Devuelve la versión superpuesta o None."""
    global _overlay_version
    meta = storage.read_json(overlay_meta_path(), {})
    if not meta or meta.get('disabled'):
        return None
    wheels = [overlay_wheel_dir() / name for name in meta.get('wheels', [])]
    if not wheels or not all(w.exists() for w in wheels):
        return None
    if _version_key(meta.get('version')) <= _version_key(bundled_ytdlp_version()):
        return None
    sys.meta_path.insert(0, _OverlayFinder(wheels))
    _overlay_version = meta.get('version')
    logger.info('Usando yt-dlp actualizado %s', _overlay_version)
    return _overlay_version


def disable_overlay(reason):
    meta = storage.read_json(overlay_meta_path(), {})
    meta.update({'disabled': True, 'disabled_reason': str(reason)[:500], 'disabled_at': time.time()})
    storage.write_json(overlay_meta_path(), meta)
    logger.error('Actualización de yt-dlp desactivada: %s', reason)


def verify_ytdlp():
    """Comprueba que el motor importado funciona de verdad (evita quedarse sin motor tras una actualización)."""
    import yt_dlp
    from yt_dlp.extractor import gen_extractor_classes
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}):
        pass
    if len(list(gen_extractor_classes())) < 100:
        raise RuntimeError('El motor no cargó sus extractores')
    return yt_dlp.version.__version__


# ------------------------------------------------------------------ binarios
def _find_binary(name):
    exe = f'{name}.exe' if platform_utils.IS_WIN else name
    for folder in paths.bin_dirs():
        candidate = folder / exe
        if candidate.is_file():
            return str(candidate), 'incluido'
    found = shutil.which(name)
    return (found, 'sistema') if found else (None, None)


def _first_line(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=15, **platform_utils.popen_kwargs())
        return (out.stdout or out.stderr).decode('utf-8', 'replace').strip().splitlines()[0]
    except Exception:
        return ''


class Components:
    def __init__(self):
        self.ffmpeg, self.ffmpeg_source = _find_binary('ffmpeg')
        self.ffprobe, _ = _find_binary('ffprobe')
        self.deno, self.deno_source = _find_binary('deno')
        self.node, self.node_source = (None, None) if self.deno else _find_binary('node')
        self.versions = {}
        self.update = {'state': 'idle', 'message': '', 'latest': None, 'checked_at': None}
        self._lock = threading.Lock()
        threading.Thread(target=self._probe_versions, daemon=True, name='versions').start()

    # -- para yt-dlp
    def ffmpeg_location(self):
        return os.path.dirname(self.ffmpeg) if self.ffmpeg else None

    def js_runtimes(self):
        if self.deno:
            return {'deno': {'path': self.deno}}
        if self.node:
            return {'node': {'path': self.node}}
        return {}

    def _probe_versions(self):
        versions = {}
        if self.ffmpeg:
            match = re.search(r'ffmpeg version (\S+)', _first_line([self.ffmpeg, '-version']))
            versions['ffmpeg'] = match.group(1) if match else 'desconocida'
        if self.deno:
            match = re.search(r'deno (\S+)', _first_line([self.deno, '--version']))
            versions['deno'] = match.group(1) if match else 'desconocida'
        elif self.node:
            versions['node'] = _first_line([self.node, '--version']).lstrip('v')
        self.versions.update(versions)

    def status(self):
        import yt_dlp
        try:
            import yt_dlp_ejs
            ejs = getattr(yt_dlp_ejs, 'version', '')
            ejs = getattr(ejs, 'version', ejs) if not isinstance(ejs, str) else ejs
        except Exception:
            ejs = ''
        issues = []
        if not self.ffmpeg:
            issues.append('No se encontró FFmpeg: no se podrán unir vídeo y audio ni convertir formatos.')
        elif not self.ffprobe:
            issues.append('No se encontró FFprobe: la carátula y SponsorBlock pueden fallar.')
        if not (self.deno or self.node):
            issues.append('No hay motor JavaScript (Deno): YouTube ofrecerá menos calidades.')
        if not ejs:
            issues.append('Falta el componente yt-dlp-ejs: YouTube ofrecerá menos calidades.')
        return {
            'ytdlp': yt_dlp.version.__version__,
            'ytdlp_source': 'actualizado' if _overlay_version else 'incluido',
            'ejs': str(ejs),
            'ffmpeg': self.versions.get('ffmpeg', 'sí' if self.ffmpeg else ''),
            'ffmpeg_source': self.ffmpeg_source or '',
            'js_runtime': 'Deno' if self.deno else ('Node.js' if self.node else ''),
            'js_version': self.versions.get('deno') or self.versions.get('node') or '',
            'js_source': self.deno_source or self.node_source or '',
            'python': sys.version.split()[0],
            'issues': issues,
            'update': dict(self.update),
        }

    # -- actualización del motor
    def _open(self, url, timeout=30):
        context = ssl.create_default_context()
        try:
            import certifi
            context.load_verify_locations(certifi.where())
        except Exception:
            pass
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        return urllib.request.urlopen(request, timeout=timeout, context=context)

    def _pypi(self, project, version=None):
        url = f'https://pypi.org/pypi/{project}/{version}/json' if version else f'https://pypi.org/pypi/{project}/json'
        with self._open(url) as response:
            return json.load(response)

    @staticmethod
    def _wheel(release):
        for item in release.get('urls', []):
            if item.get('packagetype') == 'bdist_wheel' and item.get('filename', '').endswith('-py3-none-any.whl'):
                return item
        raise RuntimeError('No se encontró un paquete compatible en PyPI')

    def check_update(self):
        import yt_dlp
        with self._lock:
            self.update.update(state='checking', message='Buscando actualizaciones…')
        try:
            latest = self._pypi('yt-dlp')['info']['version']
            current = yt_dlp.version.__version__
            available = _version_key(latest) > _version_key(current)
            self.update.update(state='available' if available else 'current', latest=latest, checked_at=time.time(),
                               message=f'Hay una versión nueva del motor: {latest}' if available
                               else f'El motor está al día ({current})')
        except Exception as e:
            logger.warning('No se pudo comprobar la actualización: %s', e)
            self.update.update(state='error', message='No se pudo comprobar si hay actualizaciones (¿sin conexión?)')
        return dict(self.update)

    def _download_verified(self, item, dest_dir):
        target = dest_dir / item['filename']
        partial = dest_dir / (item['filename'] + '.download')
        digest = hashlib.sha256()
        with self._open(item['url'], timeout=120) as response, open(partial, 'wb') as out:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != item['digests']['sha256']:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f'La verificación SHA-256 de {item["filename"]} no coincide')
        os.replace(partial, target)
        return target.name

    def install_update(self):
        with self._lock:
            if self.update.get('state') == 'installing':
                return dict(self.update)
            self.update.update(state='installing', message='Descargando la nueva versión del motor…')
        try:
            data = self._pypi('yt-dlp')
            version = data['info']['version']
            import yt_dlp
            if _version_key(version) <= _version_key(yt_dlp.version.__version__):
                self.update.update(state='current', latest=version, message=f'El motor ya está al día ({yt_dlp.version.__version__})')
                return dict(self.update)
            wheels_dir = overlay_wheel_dir()
            names = [self._download_verified(self._wheel(data), wheels_dir)]
            ejs_req = next((r for r in data['info'].get('requires_dist') or [] if r.startswith('yt-dlp-ejs')), '')
            match = re.search(r'==\s*([\w.]+)', ejs_req)
            ejs_release = self._pypi('yt-dlp-ejs', match.group(1)) if match else self._pypi('yt-dlp-ejs')
            names.append(self._download_verified(self._wheel(ejs_release), wheels_dir))
            storage.write_json(overlay_meta_path(), {'version': version, 'wheels': names, 'installed_at': time.time()})
            for old in wheels_dir.glob('*.whl'):
                if old.name not in names:
                    old.unlink(missing_ok=True)
            self.update.update(state='restart', latest=version,
                               message=f'Motor {version} instalado. Reinicia la app para usarlo.')
        except Exception as e:
            logger.exception('Falló la actualización del motor')
            self.update.update(state='error', message=f'No se pudo actualizar el motor: {e}')
        return dict(self.update)
