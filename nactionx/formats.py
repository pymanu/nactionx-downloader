"""Selección de formatos y etiquetas de calidad."""

LOSSY_AUDIO = ('mp3', 'm4a', 'opus')
AUDIO_BYTES_PER_SECOND = {'wav': 192_000, 'flac': 105_000}  # PCM 48 kHz estéreo 16 bit; FLAC ≈55 %


def fix_combo(container, codec):
    """WEBM solo admite VP9/AV1: H.264 dentro de WEBM hace fallar la unión con ffmpeg."""
    if container == 'webm' and codec == 'h264':
        return 'vp9'
    return codec


def video_selection(quality, container, codec, progressive=False):
    """Resolución y fps siempre por delante; el códec y la extensión solo desempatan.
    (Con la extensión delante, un 1080p MP4 le ganaba a un 2160p WEBM.)

    `progressive`: la plataforma sirve el vídeo y el audio ya unidos (Instagram, TikTok). Ahí se pide
    primero el archivo completo, porque no existen pistas separadas que combinar.
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
    fmt = 'bv*+ba/b'
    if container == 'webm':
        fmt = 'bv*[vcodec~="^(vp0?9|av0?1)"]+ba[acodec~="^(opus|vorbis)"]/bv*+ba/b'
    return {'format': fmt, 'format_sort': sort, 'merge_output_format': container}


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
