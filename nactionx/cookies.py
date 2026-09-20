"""Guardar el cookies.txt que llega desde la interfaz.

En la app de escritorio el archivo se elige con un diálogo del sistema y el motor lo lee de donde
esté. Cuando la app se sirve desde un servidor, el navegador y el archivo están en máquinas
distintas: escribir una ruta no vale de nada, hay que subir el contenido y guardarlo aquí.
"""
import os
import re

from . import log, paths
from .settings import SettingsError

logger = log.get('cookies')

# yt-dlp rechaza el archivo si la primera línea no es esta: MozillaCookieJar comprueba la cabecera y
# lanza LoadError con un mensaje que no dice qué hacer. Varias extensiones exportan sin ella, así que
# se añade cuando falta en vez de dar un error que el usuario no puede arreglar.
HEADER = '# Netscape HTTP Cookie File'
MAGIC = re.compile(r'#( Netscape)? HTTP Cookie File')
# Las cookies marcadas HttpOnly se guardan con este prefijo: parecen comentarios pero son registros.
HTTPONLY = '#HttpOnly_'
FIELDS = 7
MAX_BYTES = 1024 * 1024

FORMAT_HELP = ('El archivo no tiene el formato Netscape que necesita el motor. Expórtalo con una '
               'extensión de cookies.txt del navegador; no vale escribirlo a mano.')


def store_path():
    return paths.data_dir() / 'cookies.txt'


def is_managed(path):
    """¿Es la copia que guarda la app? Solo esa puede borrarse al quitar las cookies."""
    if not path:
        return False
    return os.path.normcase(os.path.abspath(str(path))) == os.path.normcase(str(store_path()))


def _is_record(line):
    stripped = line.strip()
    return bool(stripped) and (not stripped.startswith('#') or stripped.startswith(HTTPONLY))


def clean(text):
    """Valida el contenido subido y devuelve el texto exacto que hay que escribir."""
    text = (text or '').lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').strip('\n')
    if not text.strip():
        raise SettingsError('El archivo de cookies está vacío')
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise SettingsError('El archivo de cookies es demasiado grande: no parece un cookies.txt')
    lines = text.split('\n')
    records = [line for line in lines if _is_record(line)]
    if not records:
        raise SettingsError('El archivo no contiene ninguna cookie')
    if any(len(line.split('\t')) < FIELDS for line in records):
        raise SettingsError(FORMAT_HELP)
    if not MAGIC.match(lines[0]):
        text = f'{HEADER}\n{text}'
    return text + '\n'


def save(text):
    """Escribe el cookies.txt en la carpeta de datos y devuelve su ruta."""
    data = clean(text)
    path = store_path()
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(data)
    try:
        # es una sesión iniciada: en un servidor no debe poder leerla otro usuario de la máquina
        os.chmod(path, 0o600)
    except OSError as e:
        logger.warning('No se pudieron restringir los permisos de %s: %s', path, e)
    logger.info('Cookies guardadas (%d bytes)', len(data))
    return path


def discard(path):
    """Borra la copia de la app. Nunca toca un archivo que eligiera el usuario en su disco."""
    if not is_managed(path):
        return False
    try:
        os.remove(path)
        logger.info('Copia de cookies borrada')
        return True
    except OSError:
        return False
