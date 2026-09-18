"""Ajustes con esquema de validación: ningún valor inválido llega al motor ni a la cola."""
import os
import re
import sys
import threading

from . import log, paths, storage

logger = log.get('settings')

QUALITIES = ('best', '4320', '2160', '1440', '1080', '720', '480', '360', '240', '144')
CONTAINERS = ('mp4', 'mkv', 'webm')
CODECS = ('auto', 'h264', 'vp9', 'av01')
AUDIO_FORMATS = ('mp3', 'm4a', 'opus', 'flac', 'wav', 'original')
BITRATES = ('320', '256', '192', '128')
RATE_LIMITS = ('', '500K', '1M', '2M', '5M', '10M', '20M')
BROWSERS = ('', 'firefox', 'chrome', 'edge', 'brave', 'opera', 'vivaldi', 'chromium', 'safari')

JOB_OPTION_KEYS = ('folder', 'mode', 'quality', 'container', 'codec', 'audio_format', 'audio_bitrate', 'subtitles',
                   'sub_langs', 'auto_subs', 'embed_subs', 'embed_thumbnail', 'embed_metadata', 'sponsorblock',
                   'template')


class SettingsError(ValueError):
    pass


def defaults():
    return {
        'folder': paths.default_download_folder(),
        'concurrency': 2,
        'mode': 'video',
        'quality': 'best',
        'container': 'mp4',
        # QuickTime no reproduce VP9 y solo reproduce AV1 en Mac recientes: en macOS se prioriza H.264
        'codec': 'h264' if sys.platform == 'darwin' else 'auto',
        'audio_format': 'mp3',
        'audio_bitrate': '320',
        'subtitles': False,
        'sub_langs': 'es,en',
        'auto_subs': True,
        'embed_subs': True,
        'embed_thumbnail': True,
        'embed_metadata': True,
        'sponsorblock': False,
        'playlist_subfolder': True,
        'template': '%(title)s.%(ext)s',
        'rate_limit': '',
        'cookies_browser': '',
        'cookies_file': '',
        'proxy': '',
        'auto_add': False,
        'clipboard': True,
        'notify': True,
        'check_updates': True,
    }


def _bool(value):
    if isinstance(value, bool):
        return value
    if value in (0, 1, '0', '1', 'true', 'false', 'True', 'False'):
        return str(value).lower() in ('1', 'true')
    raise SettingsError('Valor de sí/no no válido')


def _choice(options, label):
    def check(value):
        value = '' if value is None else str(value)
        if value not in options:
            raise SettingsError(f'{label}: valor no válido')
        return value
    return check


def _concurrency(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise SettingsError('Descargas simultáneas: debe ser un número')
    return max(1, min(8, number))


def _quality(value):
    value = str(value or '')
    if value in QUALITIES or (value.isdigit() and 100 <= int(value) <= 8640):
        return value
    raise SettingsError('Calidad no válida')


def _folder(value):
    value = str(value or '').strip()
    if not value:
        raise SettingsError('Elige una carpeta de destino')
    value = os.path.normpath(os.path.expanduser(value))
    if not os.path.isabs(value):
        raise SettingsError('La carpeta de destino debe ser una ruta completa')
    return value


def _sub_langs(value):
    value = str(value or '').strip()
    if not re.fullmatch(r'[\w\-.,*|^$ ]{1,120}', value):
        raise SettingsError('Idiomas de subtítulos no válidos (ejemplo: es,en)')
    return value


def validate_template(value):
    value = str(value or '').strip()
    if not value or len(value) > 300:
        raise SettingsError('La plantilla de nombre está vacía o es demasiado larga')
    if '%(ext)s' not in value:
        raise SettingsError('La plantilla debe incluir %(ext)s para conservar la extensión')
    if os.path.isabs(value) or value.startswith(('/', '\\')) or re.search(r'(^|[\\/])\.\.([\\/]|$)', value):
        raise SettingsError('La plantilla no puede salir de la carpeta de destino')
    import yt_dlp
    problem = yt_dlp.YoutubeDL.validate_outtmpl(value)
    if problem:
        raise SettingsError(f'Plantilla de nombre no válida: {problem}')
    return value


def _proxy(value):
    value = str(value or '').strip()
    if value and not re.fullmatch(r'(https?|socks4a?|socks5h?)://\S+', value):
        raise SettingsError('Proxy no válido (ejemplo: http://127.0.0.1:8080 o socks5://host:1080)')
    return value


def _cookies_file(value):
    value = str(value or '').strip()
    if value and not os.path.isfile(value):
        raise SettingsError('El archivo de cookies no existe')
    return value


VALIDATORS = {
    'folder': _folder,
    'concurrency': _concurrency,
    'mode': _choice(('video', 'audio'), 'Tipo'),
    'quality': _quality,
    'container': _choice(CONTAINERS, 'Formato'),
    'codec': _choice(CODECS, 'Códec'),
    'audio_format': _choice(AUDIO_FORMATS, 'Formato de audio'),
    'audio_bitrate': _choice(BITRATES, 'Bitrate'),
    'subtitles': _bool,
    'sub_langs': _sub_langs,
    'auto_subs': _bool,
    'embed_subs': _bool,
    'embed_thumbnail': _bool,
    'embed_metadata': _bool,
    'sponsorblock': _bool,
    'playlist_subfolder': _bool,
    'template': validate_template,
    'rate_limit': _choice(RATE_LIMITS, 'Límite de velocidad'),
    'cookies_browser': _choice(BROWSERS, 'Navegador'),
    'cookies_file': _cookies_file,
    'proxy': _proxy,
    'auto_add': _bool,
    'clipboard': _bool,
    'notify': _bool,
    'check_updates': _bool,
}


def validate(partial):
    """Valida un diccionario parcial. Ignora claves desconocidas; lanza SettingsError con un mensaje claro."""
    clean = {}
    for key, value in (partial or {}).items():
        if key in VALIDATORS:
            clean[key] = VALIDATORS[key](value)
    return clean


def parse_trim(start, end):
    """Valida el recorte opcional. Devuelve (inicio, fin) como texto normalizado o vacío."""
    from yt_dlp.utils import parse_duration
    start, end = str(start or '').strip(), str(end or '').strip()
    s = parse_duration(start) if start else None
    e = parse_duration(end) if end else None
    if start and s is None:
        raise SettingsError('Inicio del recorte no válido (ejemplo: 1:30)')
    if end and e is None:
        raise SettingsError('Fin del recorte no válido (ejemplo: 2:45)')
    if s is not None and e is not None and e <= s:
        raise SettingsError('El fin del recorte debe ser posterior al inicio')
    return start, end


def job_options(requested, current):
    """Opciones de una descarga: lo que pide la interfaz, validado, con los ajustes actuales como base."""
    requested = requested or {}
    merged = {key: requested.get(key, current.get(key)) for key in JOB_OPTION_KEYS}
    options = {**{k: current[k] for k in JOB_OPTION_KEYS}, **validate(merged)}
    options['start'], options['end'] = parse_trim(requested.get('start'), requested.get('end'))
    return options


class Settings:
    def __init__(self, path=None):
        self.path = path or paths.data_dir() / 'settings.json'
        self._lock = threading.RLock()
        self.data = defaults()
        stored = storage.read_json(self.path, {})
        for key, value in (stored or {}).items():
            if key not in VALIDATORS:
                continue
            try:
                self.data.update(validate({key: value}))
            except SettingsError as e:
                logger.warning('Ajuste %s descartado: %s', key, e)
        self.revision = 0

    def get(self, key):
        with self._lock:
            return self.data[key]

    def snapshot(self):
        with self._lock:
            return dict(self.data)

    def update(self, partial):
        clean = validate(partial)
        with self._lock:
            self.data.update(clean)
            self.revision += 1
            storage.write_json(self.path, self.data)
            return dict(self.data)

    def replace_all(self, values):
        """Usado por la migración: aplica solo los valores válidos."""
        applied = {}
        for key, value in (values or {}).items():
            try:
                applied.update(validate({key: value}))
            except SettingsError:
                continue
        if applied:
            self.update(applied)
        return applied
