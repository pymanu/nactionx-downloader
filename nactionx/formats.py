"""Selección de formatos y etiquetas de calidad."""
import re

LOSSY_AUDIO = ('mp3', 'm4a', 'opus')
AUDIO_BYTES_PER_SECOND = {'wav': 192_000, 'flac': 105_000}  # PCM 48 kHz estéreo 16 bit; FLAC ≈55 %


def fix_combo(container, codec):
    """WEBM solo admite VP9/AV1: H.264 dentro de WEBM hace fallar la unión con ffmpeg."""
    if container == 'webm' and codec == 'h264':
        return 'vp9'
    return codec


def audio_filter(audio_track):
    """Filtro de yt-dlp para quedarse con una pista de audio concreta, o cadena vacía."""
    return f'[language={audio_track}]' if audio_track else ''


def video_selection(quality, container, codec, progressive=False, audio_track=''):
    """Resolución y fps siempre por delante; el códec y la extensión solo desempatan.
    (Con la extensión delante, un 1080p MP4 le ganaba a un 2160p WEBM.)

    `progressive`: la plataforma sirve el vídeo y el audio ya unidos (Instagram, TikTok). Ahí se pide
    primero el archivo completo, porque no existen pistas separadas que combinar.

    `audio_track`: código de idioma de la pista elegida. Va delante como alternativa propia, nunca
    sustituyendo al selector normal: si ese vídeo no tiene esa pista, se cae al comportamiento de
    siempre en lugar de fallar.
    """
    codec = fix_combo(container, codec)
    quality = str(quality or 'best')
    sort = [f'res:{quality}' if quality.isdigit() else 'res', 'fps']
    if codec in ('h264', 'vp9', 'av01'):
        sort.append(f'vcodec:{codec}')
    if container == 'mp4':
        sort.append('ext:mp4:m4a')
    elif container == 'webm':
        sort.append('ext:webm:webm')
    if progressive:
        return {'format': 'b/bv*+ba', 'format_sort': sort, 'merge_output_format': container}
    lang = audio_filter(audio_track)
    if container == 'webm':
        # El audio debe seguir siendo Opus o Vorbis: WEBM no admite AAC y la unión fallaría.
        fmt = 'bv*[vcodec~="^(vp0?9|av0?1)"]+ba[acodec~="^(opus|vorbis)"]/bv*+ba/b'
        if lang:
            fmt = f'bv*[vcodec~="^(vp0?9|av0?1)"]+ba{lang}[acodec~="^(opus|vorbis)"]/{fmt}'
    else:
        fmt = 'bv*+ba/b'
        if lang:
            fmt = f'bv*+ba{lang}/{fmt}'
    return {'format': fmt, 'format_sort': sort, 'merge_output_format': container}


def audio_only_selection(audio_track=''):
    """Selector para el modo «solo audio»."""
    lang = audio_filter(audio_track)
    return f'ba{lang}/ba/b' if lang else 'ba/b'


# Nombres en español de los idiomas que más aparecen en las pistas de YouTube. Para el resto se usa
# lo que diga yt-dlp (en inglés) antes que enseñar un código suelto como «zh-Hant».
LANGUAGE_NAMES = {
    'es': 'Español', 'en': 'Inglés', 'pt': 'Portugués', 'fr': 'Francés', 'de': 'Alemán', 'it': 'Italiano',
    'ja': 'Japonés', 'ko': 'Coreano', 'zh': 'Chino', 'ru': 'Ruso', 'ar': 'Árabe', 'hi': 'Hindi',
    'nl': 'Neerlandés', 'pl': 'Polaco', 'tr': 'Turco', 'id': 'Indonesio', 'vi': 'Vietnamita',
    'th': 'Tailandés', 'sv': 'Sueco', 'da': 'Danés', 'no': 'Noruego', 'fi': 'Finés', 'el': 'Griego',
    'he': 'Hebreo', 'cs': 'Checo', 'hu': 'Húngaro', 'ro': 'Rumano', 'uk': 'Ucraniano', 'bn': 'Bengalí',
    'ta': 'Tamil', 'te': 'Telugu', 'ml': 'Malayalam', 'ms': 'Malayo', 'fil': 'Filipino', 'ca': 'Catalán',
    'eu': 'Euskera', 'gl': 'Gallego',
}
REGION_NAMES = {
    'latin america': 'Latinoamérica', 'spain': 'España', 'brazil': 'Brasil', 'portugal': 'Portugal',
    'united states': 'EE. UU.', 'united kingdom': 'Reino Unido', 'mexico': 'México', 'canada': 'Canadá',
    'france': 'Francia', 'germany': 'Alemania', 'india': 'India', 'japan': 'Japón',
    'traditional': 'tradicional', 'simplified': 'simplificado',
    # Códigos sueltos: aparecen cuando no hay format_note del que sacar el nombre, por ejemplo al
    # construir el nombre del archivo a partir de la pista guardada en el trabajo.
    '419': 'Latinoamérica', 'hans': 'simplificado', 'hant': 'tradicional', 'br': 'Brasil',
    'mx': 'México', 'us': 'EE. UU.', 'gb': 'Reino Unido', 'es': 'España', 'ar': 'Argentina',
}
# format_note de YouTube: «Spanish (Latin America) original (default), medium». Sobra la calidad final
# y las marcas de pista original, que se muestran aparte.
NOTE_TAIL = re.compile(r',\s*(?:low|medium|high|ultralow)\s*$', re.I)
NOTE_MARKS = re.compile(r'\s*\b(?:original|default)\b\s*', re.I)


def language_label(code, note=''):
    """Nombre legible de una pista: «Español», «Español (Latinoamérica)» o lo que diga yt-dlp."""
    code = str(code or '')
    clean = NOTE_MARKS.sub(' ', NOTE_TAIL.sub('', str(note or '')))
    clean = re.sub(r'\(\s*\)', '', clean)
    # Ojo: aquí no se puede quitar «)» de los extremos, o «Spanish (Latin America)» pierde el cierre
    # y la región deja de reconocerse.
    clean = re.sub(r'\s{2,}', ' ', clean).strip(' ,')
    base, _, region = code.partition('-')
    name = LANGUAGE_NAMES.get(base.lower())
    if not name:
        return clean or code or 'Desconocido'
    # El nombre en inglés trae la región entre paréntesis, y distingue doblajes: se conserva.
    detail = re.search(r'\(([^)]+)\)', clean)
    extra = detail.group(1).strip() if detail else region
    if not extra:
        return name
    return f'{name} ({REGION_NAMES.get(extra.lower(), extra)})'


def audio_tracks(info):
    """Pistas de audio de distintos idiomas, la original primero.

    Solo YouTube publica varias en la práctica. Devuelve lista vacía cuando no hay nada que elegir,
    que es lo que la interfaz usa para no enseñar el selector.
    """
    found = {}
    for fmt in info.get('formats') or []:
        if fmt.get('acodec') in (None, 'none') or fmt.get('vcodec') not in (None, 'none'):
            continue
        code = fmt.get('language')
        if not code:
            continue
        track = found.setdefault(code, {'value': code, 'label': '', 'original': False, 'note': ''})
        if fmt.get('language_preference') == 10:
            track['original'] = True
        if not track['note']:
            track['note'] = fmt.get('format_note') or ''
    if len(found) < 2:
        return []
    for code, track in found.items():
        track['label'] = language_label(code, track.pop('note'))
    return sorted(found.values(), key=lambda t: (not t['original'], t['label'].lower()))


def short_side(fmt):
    width, height = fmt.get('width'), fmt.get('height')
    if width and height:
        return min(width, height)
    return height


def quality_label(side, fps):
    fps = int(round(fps or 0))
    return f'{side}p{fps if fps > 30 else ""}'


def estimate_size(fmt, duration):
    size = fmt.get('filesize') or fmt.get('filesize_approx')
    if not size and fmt.get('tbr') and duration:
        size = fmt['tbr'] * duration * 125
    return int(size or 0)


def summarize(info):
    """Calidades disponibles (agrupadas por dimensión menor) y tamaño del mejor audio."""
    duration = info.get('duration') or 0
    formats = info.get('formats') or []
    audio = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')]
    best_audio = max(audio, key=lambda f: f.get('abr') or f.get('tbr') or 0, default=None)
    audio_size = estimate_size(best_audio, duration) if best_audio else 0
    best = {}
    for f in formats:
        side = short_side(f)
        if not side or f.get('vcodec') in (None, 'none'):
            continue
        key = (round(f.get('fps') or 30), (f.get('dynamic_range') or 'SDR') != 'SDR', f.get('tbr') or 0)
        current = best.get(side)
        if current is None or key > current[0]:
            best[side] = (key, f)
    qualities = []
    for side in sorted(best, reverse=True):
        (_, hdr, _), f = best[side]
        size = estimate_size(f, duration)
        if f.get('acodec') in (None, 'none'):
            size += audio_size
        qualities.append({'value': str(side), 'label': quality_label(side, f.get('fps')), 'hdr': hdr, 'size': size})
    return qualities, audio_size


def estimate_audio(audio_format, bitrate, duration, source_size):
    if not duration:
        return source_size
    if audio_format in LOSSY_AUDIO:
        return int(int(bitrate or 192) * duration * 125)
    if audio_format in AUDIO_BYTES_PER_SECOND:
        return int(AUDIO_BYTES_PER_SECOND[audio_format] * duration)
    return source_size
