"""Nombres de archivo: limpieza para Windows/macOS, nombres únicos y renombrado seguro."""
import glob
import os
import re

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MEDIA_EXT = re.compile(r'\.(mp4|mkv|webm|mov|avi|m4v|mp3|m4a|aac|opus|ogg|flac|wav)$', re.I)
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)$', re.I)
TEMP_SUFFIXES = ('.part', '.ytdl')


def clean_filename(text, limit=180):
    """Nombre elegido por el usuario -> nombre válido, sin extensión multimedia."""
    name = MEDIA_EXT.sub('', str(text or '').strip())
    name = INVALID_CHARS.sub('', name).strip(' .')
    if RESERVED.match(name):
        name = '_' + name
    return name[:limit].rstrip(' .')


def folder_name(text, fallback='Playlist'):
    """Nombre de subcarpeta (playlist, canal): sustituye caracteres no válidos."""
    name = INVALID_CHARS.sub('_', str(text or '')).strip(' .')
    if RESERVED.match(name):
        name = '_' + name
    return name[:120].rstrip(' .') or fallback


def unique_base(folder, name, ext_pattern='.*', taken=(), ignore=''):
    """Devuelve 'nombre', 'nombre (2)', 'nombre (3)'... sin chocar con archivos existentes
    (los temporales de una descarga a medias no cuentan) ni con nombres reservados por otras descargas."""
    ignore = os.path.normcase(ignore) if ignore else ''
    taken = {t.lower() for t in taken}

    def busy(candidate):
        if candidate.lower() in taken:
            return True
        pattern = os.path.join(glob.escape(str(folder)), glob.escape(candidate) + ext_pattern)
        for path in glob.glob(pattern):
            if path.endswith(TEMP_SUFFIXES) or (ignore and os.path.normcase(path) == ignore):
                continue
            return True
        return False

    candidate, n = name, 2
    while busy(candidate):
        candidate = f'{name} ({n})'
        n += 1
    return candidate


class RenameError(ValueError):
    pass


def rename_file(path, name):
    """Renombra conservando la extensión. Nunca sobrescribe: añade (2), (3)... si hace falta."""
    folder = os.path.dirname(path)
    base, ext = os.path.splitext(os.path.basename(path))
    if base == name:
        return path
    if base.lower() == name.lower():
        target = name
    else:
        target = unique_base(folder, name, glob.escape(ext), ignore=path)
    new_path = os.path.join(folder, target + ext)
    try:
        os.rename(path, new_path)
    except PermissionError:
        raise RenameError('El archivo está en uso (¿abierto en un reproductor?). Ciérralo e inténtalo de nuevo')
    except FileNotFoundError:
        raise RenameError('El archivo ya no existe en disco')
    return new_path
