"""Motor de descarga sobre yt-dlp: análisis de enlaces y ejecución de una descarga."""
import glob
import os
import re
import subprocess
import time

import yt_dlp
from yt_dlp.postprocessor import PostProcessor, get_postprocessor
from yt_dlp.utils import parse_bytes, parse_duration

from . import errors, formats, log, names, platform_utils, sites
from .errors import FriendlyError

logger = log.get('engine')

PP_NAMES = {
    'Merger': 'Uniendo vídeo y audio', 'FFmpegMerger': 'Uniendo vídeo y audio',
    'ExtractAudio': 'Convirtiendo audio', 'FFmpegExtractAudio': 'Convirtiendo audio',
    'EmbedThumbnail': 'Incrustando carátula', 'ThumbnailsConvertor': 'Preparando carátula',
    'FFmpegThumbnailsConvertor': 'Preparando carátula', 'Metadata': 'Escribiendo metadatos',
    'FFmpegMetadata': 'Escribiendo metadatos', 'EmbedSubtitle': 'Incrustando subtítulos',
    'FFmpegEmbedSubtitle': 'Incrustando subtítulos', 'SubtitlesConvertor': 'Convirtiendo subtítulos',
    'FFmpegSubtitlesConvertor': 'Convirtiendo subtítulos', 'SponsorBlock': 'Consultando SponsorBlock',
    'ModifyChapters': 'Quitando segmentos', 'MoveFiles': 'Finalizando', 'MoveFilesAfterDownload': 'Finalizando',
    'FixupM3u8': 'Reparando', 'FixupStretched': 'Reparando', 'FixupDuplicateMoov': 'Reparando',
    'Trim': 'Recortando fragmento',
}
LIVE_STATES = ('is_live', 'is_upcoming')


class Stop(Exception):
    """Pausa o cancelación pedida por el usuario."""


def yt_thumb(video_id):
    return f'https://i.ytimg.com/vi/{video_id}/mqdefault.jpg' if video_id else ''


normalize_url = sites.normalize_url
looks_like_collection = sites.looks_like_collection


class YtdlpLogger:
    """Canaliza los mensajes de yt-dlp al registro de la descarga en lugar de perderlos."""

    def __init__(self, sink=None):
        self.sink = sink
        self.last_error = ''

    def _emit(self, level, msg):
        msg = errors.clean(msg)
        if self.sink:
            self.sink(level, msg)

    def debug(self, msg):
        if msg.startswith('[debug]'):
            return
        self._emit('info', msg)

    def info(self, msg):
        self._emit('info', msg)

    def warning(self, msg):
        self._emit('warning', msg)
        logger.debug('yt-dlp: %s', msg)

    def error(self, msg):
        self.last_error = errors.clean(msg)
        self._emit('error', msg)


def base_opts(settings, components, sink=None):
    opts = {
        'quiet': True,
        'no_warnings': False,
        'noprogress': True,
        'color': {'stdout': 'no_color', 'stderr': 'no_color'},
        'socket_timeout': 30,
        'logger': YtdlpLogger(sink),
    }
    if components.ffmpeg_location():
        opts['ffmpeg_location'] = components.ffmpeg_location()
    runtimes = components.js_runtimes()
    if runtimes:
        opts['js_runtimes'] = runtimes
    if settings.get('cookies_file'):
        opts['cookiefile'] = settings['cookies_file']
    elif settings.get('cookies_browser'):
        opts['cookiesfrombrowser'] = (settings['cookies_browser'],)
    if settings.get('proxy'):
        opts['proxy'] = settings['proxy']
    return opts


# ------------------------------------------------------------------ análisis
def entry_item(entry):
    video_id = entry.get('id')
    url = entry.get('url') or entry.get('webpage_url') or ''
    extractor = (entry.get('ie_key') or entry.get('extractor_key') or entry.get('extractor') or '').lower()
    is_youtube = extractor.startswith('youtube') or 'youtube.com' in url or 'youtu.be' in url
    if not url.startswith('http') and video_id:
        # En las listas planas algunas plataformas devuelven solo el identificador.
        if is_youtube:
            url = f'https://www.youtube.com/watch?v={video_id}'
        elif extractor.startswith('tiktok'):
            user = entry.get('uploader') or entry.get('channel') or ''
            url = f'https://www.tiktok.com/@{user.lstrip("@")}/video/{video_id}' if user else url
        elif extractor.startswith('instagram'):
            url = f'https://www.instagram.com/p/{video_id}/'
    thumb = ''
    if is_youtube and video_id:
        thumb = yt_thumb(video_id)
    else:
        for t in reversed(entry.get('thumbnails') or []):
            if t.get('url'):
                thumb = t['url']
                break
        thumb = thumb or entry.get('thumbnail') or ''
    return {
        'id': video_id, 'url': url, 'title': entry.get('title') or url,
        'duration': entry.get('duration'), 'uploader': entry.get('channel') or entry.get('uploader') or '',
        'thumbnail': thumb, 'live': entry.get('live_status') in LIVE_STATES,
    }


COLLECTION_HELP = {
    sites.INSTAGRAM: 'Instagram no deja listar un perfil entero sin sesión iniciada. Pega el enlace de la '
                     'publicación concreta, o configura las cookies en Ajustes → Cuenta y red.',
    sites.TIKTOK: 'TikTok no deja listar un perfil entero desde fuera de su aplicación. Abre el vídeo que '
                  'quieras en TikTok y pega su enlace: los vídeos sueltos sí se descargan.',
}


def extract(ydl, url, collection=False):
    """Extrae la información del enlace, explicando el caso en el que más gente se atasca: pegar el
    perfil de Instagram o TikTok en lugar de la publicación."""
    try:
        return ydl.extract_info(url, download=False)
    except Exception as e:
        help_text = COLLECTION_HELP.get(sites.platform_of(url)) if collection else None
        if help_text:
            raise FriendlyError(help_text, 'unsupported', errors.clean(e)) from e
        raise


def analyze(query, want_playlist, settings, components):
    query = query.strip()
    if not query:
        raise FriendlyError('Escribe un enlace o algo que buscar', 'unsupported')
    opts = base_opts(settings, components)
    if not re.match(r'^https?://', query, re.I):
        opts['extract_flat'] = 'in_playlist'
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f'ytsearch25:{query}', download=False)
        return {'type': 'search', 'title': f'Resultados para «{query}»', 'query': query,
                'entries': [entry_item(e) for e in info.get('entries') or []]}

    url = normalize_url(query)
    opts.update(sites.request_options(url))
    collection = bool(want_playlist or looks_like_collection(url))
    if collection:
        if want_playlist:
            match = re.search(r'[?&]list=([\w-]+)', url)
            if match:
                url = f'https://www.youtube.com/playlist?list={match.group(1)}'
        opts['extract_flat'] = 'in_playlist'
    else:
        opts['noplaylist'] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = extract(ydl, url, collection)

    if info.get('_type') == 'playlist' or info.get('entries') is not None:
        entries = [entry_item(e) for e in (info.get('entries') or []) if e]
        return {'type': 'playlist', 'title': info.get('title') or 'Playlist',
                'uploader': info.get('channel') or info.get('uploader') or '',
                'url': info.get('webpage_url') or url, 'entries': entries}

    qualities, audio_size = formats.summarize(info)
    return {
        'type': 'video', 'id': info.get('id'), 'url': info.get('webpage_url') or url, 'title': info.get('title'),
        'uploader': info.get('channel') or info.get('uploader') or '', 'duration': info.get('duration') or 0,
        'view_count': info.get('view_count'), 'upload_date': info.get('upload_date'),
        'thumbnail': info.get('thumbnail') or (yt_thumb(info.get('id')) if 'youtube' in url else ''),
        'live_status': info.get('live_status') or ('is_live' if info.get('is_live') else ''),
        'release_timestamp': info.get('release_timestamp'),
        'qualities': qualities, 'audio_size': audio_size, 'audio_tracks': formats.audio_tracks(info),
        'chapters': len(info.get('chapters') or []),
        'subtitles': sorted((info.get('subtitles') or {}).keys())[:40],
        'has_playlist': 'list=' in query and ('youtube' in query or 'youtu.be' in query),
        'extractor': info.get('extractor_key'),
        'platform': sites.platform_of(url), 'platform_label': sites.label_of(url),
    }


def expand_collection(url, settings, components):
    opts = base_opts(settings, components)
    opts.update(sites.request_options(url))
    opts['extract_flat'] = 'in_playlist'
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = extract(ydl, normalize_url(url), collection=True)
    return info.get('title') or 'Playlist', [entry_item(e) for e in (info.get('entries') or []) if e]


# ------------------------------------------------------------------ recorte
class TrimPP(PostProcessor):
    """Recorta el archivo ya descargado. Pedir rangos a ffmpeg por HTTP es lentísimo con YouTube
    y no se puede cancelar; así se descarga a velocidad normal y el corte es exacto."""
    AUDIO_CODECS = {'.mp3': 'libmp3lame', '.m4a': 'aac', '.aac': 'aac', '.opus': 'libopus', '.ogg': 'libvorbis',
                    '.webm': 'libopus', '.flac': 'flac', '.wav': 'pcm_s16le'}

    def __init__(self, downloader, start=None, end=None, bitrate='320', should_stop=None, ffmpeg=None):
        super().__init__(downloader)
        self.start, self.end, self.bitrate = start, end, bitrate
        self.should_stop, self.ffmpeg = should_stop, ffmpeg

    def run(self, info):
        path = info.get('filepath')
        if not path or not os.path.exists(path):
            return [], info
        root, ext = os.path.splitext(path)
        ext = ext.lower()
        out = f'{root}.recorte{ext}'
        args = [self.ffmpeg or 'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
        if self.start:
            args += ['-ss', str(self.start)]
        args += ['-i', path]
        if self.end:
            args += ['-t', str(max(0.1, self.end - (self.start or 0)))]
        is_audio = info.get('vcodec') in (None, 'none') or ext in ('.mp3', '.m4a', '.aac', '.opus', '.ogg', '.flac', '.wav')
        if is_audio:
            codec = self.AUDIO_CODECS.get(ext, 'aac')
            args += ['-map', '0:a:0', '-vn', '-c:a', codec]
            if codec in ('libmp3lame', 'aac', 'libopus', 'libvorbis'):
                args += ['-b:a', f'{self.bitrate or 192}k']
        elif ext == '.webm':
            args += ['-map', '0:v:0', '-map', '0:a?', '-c:v', 'libvpx-vp9', '-deadline', 'realtime', '-cpu-used', '8',
                     '-crf', '30', '-b:v', '0', '-c:a', 'libopus']
        else:
            args += ['-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                     '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k']
            if ext in ('.mp4', '.m4v', '.mov'):
                args += ['-movflags', '+faststart']
        args.append(out)
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **platform_utils.popen_kwargs())
        while proc.poll() is None:
            if self.should_stop and self.should_stop():
                proc.kill()
                proc.wait()
                if os.path.exists(out):
                    os.remove(out)
                raise Stop()
            time.sleep(0.25)
        if proc.returncode != 0:
            err = (proc.stderr.read() or b'').decode('utf-8', 'replace')[-400:]
            if os.path.exists(out):
                os.remove(out)
            raise FriendlyError('No se pudo recortar el fragmento. Prueba con otro formato.', 'format', err.strip())
        os.replace(out, path)
        return [], info


# ------------------------------------------------------------------ descarga
def mmss(seconds):
    return f'{int(seconds // 60):02d}m{int(seconds % 60):02d}s' if seconds is not None else 'fin'


class Download:
    """Ejecuta una descarga. `ctx` es el gestor de la cola (flags, avisos de cambios, registro)."""

    def __init__(self, job, ctx):
        self.job, self.ctx = job, ctx
        self.settings = ctx.settings_snapshot()
        self.components = ctx.components
        self.tmpfiles = set()
        self.parts = {'ids': [], 'sizes': [], 'started': False}
        self.finals = {}

    # -- utilidades
    def stopping(self):
        return self.ctx.flag(self.job['id'])

    def set(self, structural=False, **fields):
        job, changed = self.job, False
        for key, value in fields.items():
            if job.get(key) != value:
                job[key] = value
                changed = True
        if changed:
            (self.ctx.touch if structural else self.ctx.bump_progress)()

    def sink(self, level, msg):
        self.ctx.log(self.job['id'], level, msg)
        if 'has already been downloaded' in msg:
            self.job['note'] = 'El archivo ya existía'
        elif 'has already been recorded in the archive' in msg:
            self.job['note'] = 'Ya descargado antes'

    def folder(self):
        options = self.job['options']
        folder = options.get('folder') or self.settings['folder']
        if self.job.get('subfolder'):
            folder = os.path.join(folder, names.folder_name(self.job['subfolder']))
        return folder

    # -- construcción de opciones
    def output_template(self, folder):
        job, options = self.job, self.job['options']
        template = options.get('template') or '%(title)s.%(ext)s'
        start, end = parse_duration(options.get('start') or ''), parse_duration(options.get('end') or '')
        if job.get('custom_name') and not job.get('outname'):
            job['outname'] = self.ctx.reserve_name(job, folder, job['custom_name'])
            job['outname_for'] = job['custom_name']
            job['outdir'] = folder
        if job.get('outname'):
            template = job['outname'].replace('%', '%%') + '.%(ext)s'
        else:
            suffix = f' (recorte {mmss(start or 0)}-{mmss(end)})' if start or end else ''
            # Sin esto, el mismo vídeo en dos idiomas daba «Vídeo.mp4» y «Vídeo (2).mp4», indistinguibles.
            if options.get('audio_track'):
                suffix += f' ({formats.language_label(options["audio_track"])})'
            if suffix:
                template = (template[:-len('.%(ext)s')] + suffix + '.%(ext)s') if template.endswith('.%(ext)s') else template + suffix
        # Solo la plantilla: la carpeta va en 'paths'. Si la carpeta formara parte de la plantilla, el límite de
        # longitud de yt-dlp se aplicaría a la ruta entera y cortaría el nombre (y el sufijo de recorte).
        return template

    def build(self, folder):
        job, options = self.job, self.job['options']
        opts = base_opts(self.settings, self.components, self.sink)
        opts.update({
            'paths': {'home': folder},
            'outtmpl': {'default': self.output_template(folder)},
            'noplaylist': True, 'continuedl': True, 'retries': 10, 'fragment_retries': 10,
            'concurrent_fragment_downloads': 4, 'windowsfilenames': True, 'trim_file_name': 150,
            'overwrites': False, 'progress_hooks': [self.progress_hook], 'postprocessor_hooks': [self.pp_hook],
        })
        opts.update(sites.request_options(job['url']))
        if self.settings.get('rate_limit'):
            opts['ratelimit'] = parse_bytes(self.settings['rate_limit'])

        mode = options.get('mode') or 'video'
        container = options.get('container') or 'mp4'
        audio_format = options.get('audio_format') or 'mp3'
        start, end = parse_duration(options.get('start') or ''), parse_duration(options.get('end') or '')
        trimming = bool(start or end)
        pps = []
        if options.get('sponsorblock') and not trimming:
            categories = ['sponsor', 'selfpromo', 'interaction']
            pps.append({'key': 'SponsorBlock', 'categories': categories, 'when': 'after_filter'})
            pps.append({'key': 'ModifyChapters', 'remove_sponsor_segments': categories})
        track = options.get('audio_track') or ''
        if mode == 'audio':
            opts['format'] = formats.audio_only_selection(track)
            if audio_format != 'original':
                lossy = audio_format in formats.LOSSY_AUDIO
                pps.append({'key': 'FFmpegExtractAudio', 'preferredcodec': audio_format,
                            'preferredquality': str(options.get('audio_bitrate') or '320') if lossy else '0'})
        else:
            opts.update(formats.video_selection(options.get('quality'), container, options.get('codec'),
                                                progressive=sites.progressive(job['url']), audio_track=track))
        if trimming:
            pps.append({'key': 'Trim', 'start': start, 'end': end, 'bitrate': options.get('audio_bitrate') or '320'})
        if mode == 'video' and options.get('subtitles') and not trimming:
            opts['writesubtitles'] = True
            opts['writeautomaticsub'] = bool(options.get('auto_subs'))
            opts['subtitleslangs'] = [s.strip() for s in (options.get('sub_langs') or 'es,en').split(',') if s.strip()]
            if options.get('embed_subs'):
                pps.append({'key': 'FFmpegEmbedSubtitle', 'already_have_subtitle': False})
            else:
                pps.append({'key': 'FFmpegSubtitlesConvertor', 'format': 'srt', 'when': 'before_dl'})
        if options.get('embed_metadata', True):
            pps.append({'key': 'FFmpegMetadata', 'add_chapters': True, 'add_metadata': True})
        can_thumb = not ((mode == 'video' and container == 'webm') or (mode == 'audio' and audio_format in ('wav', 'original')))
        if options.get('embed_thumbnail', True) and can_thumb:
            opts['writethumbnail'] = True
            pps.append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg', 'when': 'before_dl'})
            pps.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
        return opts, pps, mode, container, audio_format

    def attach(self, ydl, pps):
        for spec in pps:
            spec = dict(spec)
            when = spec.pop('when', 'post_process')
            key = spec.pop('key')
            if key == 'Trim':
                instance = TrimPP(ydl, should_stop=lambda: bool(self.stopping()), ffmpeg=self.components.ffmpeg, **spec)
            else:
                instance = get_postprocessor(key)(ydl, **spec)
            ydl.add_post_processor(instance, when=when)

    # -- ganchos de progreso
    def progress_hook(self, d):
        if self.stopping():
            raise Stop()
        job, parts = self.job, self.parts
        if d.get('tmpfilename'):
            self.tmpfiles.add(d['tmpfilename'])
        info = d.get('info_dict') or {}
        format_id = info.get('format_id')
        idx = parts['ids'].index(format_id) if format_id in parts['ids'] else 0
        count = max(1, len(parts['ids']))
        if d['status'] == 'downloading':
            parts['started'] = True
            done = d.get('downloaded_bytes') or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            sizes = list(parts['sizes'])
            if total and idx < len(sizes):
                sizes[idx] = total
            full, before = sum(sizes), sum(sizes[:idx])
            if full > 0:
                pct = (before + done) / full * 100
            elif total:
                pct = (idx + done / total) / count * 100
            else:
                pct = job['progress']
            phase = 'Descargando'
            if count > 1:
                phase = ('Descargando audio' if info.get('vcodec') == 'none' else 'Descargando vídeo') + f' ({idx + 1}/{count})'
            self.set(structural=True, status='downloading', phase=phase)
            self.set(progress=round(min(pct, 99.9), 1), speed=int(d.get('speed') or 0), eta=d.get('eta'),
                     downloaded=int(before + done), total=int(full or total))
        elif d['status'] == 'finished':
            if idx < len(parts['sizes']) and d.get('total_bytes'):
                parts['sizes'][idx] = d['total_bytes']
            if idx >= count - 1:
                self.set(progress=99.9, speed=0, eta=None)

    def pp_hook(self, d):
        if self.stopping():
            raise Stop()
        name = d.get('postprocessor') or ''
        if d['status'] == 'started':
            self.set(structural=True, status='processing', phase=PP_NAMES.get(name, 'Procesando'))
            self.set(speed=0, eta=None)
        elif d['status'] == 'finished':
            if not self.parts['started']:
                # Postprocesos previos a la descarga (carátula, SponsorBlock): volver a «descargando»
                self.set(structural=True, status='downloading', phase='Conectando')
            path = (d.get('info_dict') or {}).get('filepath')
            if path:
                self.job['filepath'] = path

    # -- ejecución
    def run(self):
        job, ctx = self.job, self.ctx
        folder = self.folder()
        try:
            platform_utils.ensure_writable(folder)
        except OSError as e:
            message, kind, detail = errors.explain(e)
            raise FriendlyError(message if kind == 'permission' else 'No se puede escribir en la carpeta de destino. Elige otra carpeta.', 'permission', detail)
        opts, pps, mode, container, audio_format = self.build(folder)
        with yt_dlp.YoutubeDL(opts) as ydl:
            self.attach(ydl, pps)
            info = ydl.extract_info(job['url'], download=False)
            if self.stopping():
                raise Stop()
            if info.get('_type') == 'playlist' or info.get('entries') is not None:
                raise FriendlyError('El enlace es una lista. Analízalo para elegir los vídeos.', 'unsupported')
            live = info.get('live_status') or ('is_live' if info.get('is_live') else '')
            if live == 'is_live':
                raise FriendlyError('Es un directo en curso. Podrás descargarlo cuando termine la emisión.', 'live')
            if live == 'is_upcoming':
                raise FriendlyError('El estreno o directo todavía no ha empezado.', 'live')

            base = os.path.splitext(ydl.prepare_filename(info))[0]
            self.tmpfiles.add('base:' + base)
            produced = {container} if mode == 'video' else ({audio_format} if audio_format != 'original' else set())
            for ext in (produced | {info.get('ext') or ''}) - {''}:
                candidate = f'{base}.{ext}'
                self.finals[candidate] = os.path.exists(candidate)

            requested = info.get('requested_formats') or [info]
            duration = info.get('duration') or 0
            self.parts['ids'] = [f.get('format_id') for f in requested]
            self.parts['sizes'] = [formats.estimate_size(f, duration) for f in requested]
            total = sum(self.parts['sizes'])
            if mode == 'audio':
                bitrate = job['options'].get('audio_bitrate')
                label = audio_format.upper() + (f' · {bitrate} kbps' if audio_format in formats.LOSSY_AUDIO else '')
            else:
                video = next((f for f in requested if f.get('vcodec') not in (None, 'none')), info)
                side = formats.short_side(video)
                codec = (video.get('vcodec') or '').split('.')[0]
                codec = {'avc1': 'H.264', 'av01': 'AV1', 'vp09': 'VP9', 'vp9': 'VP9', 'hev1': 'HEVC', 'hvc1': 'HEVC'}.get(codec, codec.upper())
                label = ' · '.join(x for x in [container.upper(), formats.quality_label(side, video.get('fps')) if side else '', codec] if x)
            if job['options'].get('audio_track'):
                # Del formato que se ha elegido de verdad, no del que se pidió: si el vídeo no tenía esa
                # pista, el selector cae en la de siempre y la etiqueta debe decir la verdad.
                chosen = next((f for f in requested if f.get('acodec') not in (None, 'none')), {})
                if chosen.get('language'):
                    label += ' · ' + formats.language_label(chosen['language'], chosen.get('format_note'))
            self.set(structural=True, title=info.get('title') or job['title'],
                     uploader=info.get('channel') or info.get('uploader') or job['uploader'],
                     duration=info.get('duration') or job['duration'],
                     thumbnail=job['thumbnail'] or (yt_thumb(info.get('id')) if str(info.get('extractor_key', '')).startswith('Youtube')
                                                    else info.get('thumbnail')) or '',
                     format_label=label, total=total)

            free = platform_utils.folder_info(folder).get('free')
            if total and free is not None and free < total * 1.05 + 50 * 1024 * 1024:
                raise FriendlyError(
                    f'No hay espacio suficiente en el disco: hacen falta unos {total / 1024 ** 3:.1f} GB y quedan '
                    f'{free / 1024 ** 3:.1f} GB libres.', 'disk')

            self.set(structural=True, status='downloading', phase='Conectando')
            ydl.process_ie_result(info, download=True)
            if not job['filepath']:
                downloads = info.get('requested_downloads') or []
                job['filepath'] = (downloads[-1].get('filepath') if downloads else '') or ''
        if self.stopping():
            raise Stop()
        if job.get('custom_name') and job['custom_name'] != job.get('outname_for') and job['filepath'] \
                and os.path.exists(job['filepath']):
            try:
                job['filepath'] = names.rename_file(job['filepath'], job['custom_name'])
            except names.RenameError as e:
                job['note'] = f'No se pudo renombrar: {e}'
        size = os.path.getsize(job['filepath']) if job['filepath'] and os.path.exists(job['filepath']) else 0
        return size

    def cleanup(self):
        """Tras cancelar: borra temporales y cualquier archivo final creado por esta descarga."""
        temp_ext = ('.part', '.ytdl', '.jpg', '.webp', '.png', '.vtt', '.srt', '.temp', '.recorte')
        candidates = set()
        for item in self.tmpfiles:
            if item.startswith('base:'):
                base = item[5:]
                for path in glob.glob(glob.escape(base) + '.*'):
                    rest = path[len(base):].lower()
                    if rest.endswith(temp_ext) or re.match(r'^\.f[\w-]+\.', rest) or '.part' in rest or '.recorte' in rest:
                        candidates.add(path)
            else:
                candidates |= {item, item + '.part', item + '.ytdl'} | set(glob.glob(glob.escape(item) + '.part*'))
        for final, existed_before in self.finals.items():
            if not existed_before:
                candidates.add(final)
        for path in candidates:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
