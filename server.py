#!/usr/bin/env python3
"""Descargador: gestor de descargas local (YouTube y +1000 sitios) basado en yt-dlp.

Sin dependencias web externas: servidor HTTP de la libreria estandar + yt-dlp + ffmpeg.
Arranque: doble clic en "Abrir Descargador" o `python server.py`.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
os.makedirs(DATA, exist_ok=True)
HOST, PORT = '127.0.0.1', 8765
URL = f'http://{HOST}:{PORT}/'
SETTINGS_FILE = os.path.join(DATA, 'settings.json')
QUEUE_FILE = os.path.join(DATA, 'queue.json')
HISTORY_FILE = os.path.join(DATA, 'history.json')
LOG_FILE = os.path.join(DATA, 'server.log')

# Con pythonw no hay consola: redirigir la salida a un log.
if sys.stdout is None or sys.stderr is None:
    _log = open(LOG_FILE, 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = _log

import yt_dlp  # noqa: E402
from yt_dlp.postprocessor import PostProcessor, get_postprocessor  # noqa: E402
from yt_dlp.utils import parse_bytes, parse_duration  # noqa: E402

FFMPEG = shutil.which('ffmpeg')
NODE = shutil.which('node')
DENO = shutil.which('deno')

DEFAULTS = {
    'folder': os.path.join(os.path.expanduser('~'), 'Downloads', 'Descargador'),
    'concurrency': 2,
    'mode': 'video',
    'quality': 'best',
    'container': 'mp4',
    'codec': 'auto',
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
    'auto_add': False,
    'clipboard': True,
    'notify': True,
    'app_window': True,
}
OPTION_KEYS = ['folder', 'mode', 'quality', 'container', 'codec', 'audio_format', 'audio_bitrate', 'subtitles',
               'sub_langs', 'auto_subs', 'embed_subs', 'embed_thumbnail', 'embed_metadata', 'sponsorblock',
               'template', 'start', 'end']
ACTIVE = ('starting', 'downloading', 'processing')
ANSI = re.compile(r'\x1b\[[0-9;]*m')
PP_NAMES = {
    'Merger': 'Uniendo vídeo y audio', 'FFmpegMerger': 'Uniendo vídeo y audio',
    'ExtractAudio': 'Convirtiendo audio', 'FFmpegExtractAudio': 'Convirtiendo audio',
    'EmbedThumbnail': 'Incrustando miniatura', 'ThumbnailsConvertor': 'Preparando miniatura',
    'FFmpegThumbnailsConvertor': 'Preparando miniatura', 'Metadata': 'Escribiendo metadatos',
    'FFmpegMetadata': 'Escribiendo metadatos', 'EmbedSubtitle': 'Incrustando subtítulos',
    'FFmpegEmbedSubtitle': 'Incrustando subtítulos', 'SubtitlesConvertor': 'Convirtiendo subtítulos',
    'SponsorBlock': 'Consultando SponsorBlock', 'ModifyChapters': 'Eliminando segmentos',
    'MoveFiles': 'Finalizando', 'MoveFilesAfterDownload': 'Finalizando', 'FixupM3u8': 'Reparando',
    'Trim': 'Recortando fragmento',
}
NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- utilidades
def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def clean_error(msg):
    msg = ANSI.sub('', str(msg or '')).strip()
    msg = re.sub(r'^(ERROR:\s*)+', '', msg)
    msg = re.sub(r'^\[[\w:]+\]\s*[\w-]+:\s*', '', msg)
    return msg[:500] or 'Error desconocido'


def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(s or '')).strip(' .')
    return s[:120] or 'Playlist'


MEDIA_EXT = re.compile(r'\.(mp4|mkv|webm|mov|avi|mp3|m4a|aac|opus|ogg|flac|wav)$', re.I)


def clean_filename(s):
    """Nombre elegido por el usuario -> nombre válido en Windows, sin extensión."""
    s = MEDIA_EXT.sub('', str(s or '').strip())
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', s).strip(' .')
    if s.upper() in ('CON', 'PRN', 'AUX', 'NUL') or re.fullmatch(r'(COM|LPT)\d', s.upper()):
        s = '_' + s
    return s[:180]


def rename_file(path, name):
    folder = os.path.dirname(path)
    base, ext = os.path.splitext(os.path.basename(path))
    if base == name:
        return path
    target = name if base.lower() == name.lower() else unique_base(folder, name, glob.escape(ext), ignore=path)
    new = os.path.join(folder, target + ext)
    try:
        os.rename(path, new)
    except PermissionError:
        raise ValueError('El archivo está en uso (¿abierto en un reproductor?). Ciérralo e inténtalo de nuevo')
    return new


def unique_base(folder, name, ext_pattern='.*', taken=(), ignore=''):
    """Evita chocar con un archivo existente o con otra descarga de la cola:
    'nombre', 'nombre (2)', 'nombre (3)'..."""
    ignore = os.path.normcase(ignore)

    def busy(c):
        if c.lower() in taken:
            return True
        for p in glob.glob(os.path.join(glob.escape(folder), glob.escape(c) + ext_pattern)):
            if not p.endswith(('.part', '.ytdl')) and os.path.normcase(p) != ignore:
                return True
        return False

    cand, n = name, 2
    while busy(cand):
        cand = f'{name} ({n})'
        n += 1
    return cand


def yt_thumb(vid):
    return f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg' if vid else ''


settings = {**DEFAULTS, **read_json(SETTINGS_FILE, {})}
settings_lock = threading.Lock()


def save_settings():
    with settings_lock:
        write_json(SETTINGS_FILE, settings)


def base_opts():
    o = {
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'color': {'stdout': 'no_color', 'stderr': 'no_color'},
    }
    if FFMPEG:
        o['ffmpeg_location'] = os.path.dirname(FFMPEG)
    runtimes = {}
    if DENO:
        runtimes['deno'] = {}
    if NODE:
        runtimes['node'] = {}
    if runtimes:
        o['js_runtimes'] = runtimes
    if settings.get('cookies_browser'):
        o['cookiesfrombrowser'] = (settings['cookies_browser'],)
    return o


def normalize_url(q):
    q = q.strip()
    # Canal sin pestaña -> pestaña de vídeos
    if re.match(r'^https?://(www\.|m\.)?youtube\.com/(@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+)/?$', q):
        q = q.rstrip('/') + '/videos'
    return q


def looks_like_collection(url):
    return bool(re.search(r'youtube\.com/(playlist\?|@|channel/|c/|user/)', url)) or (
        'list=' in url and 'v=' not in url and 'youtu.be/' not in url)


def entry_item(e):
    vid = e.get('id')
    url = e.get('url') or e.get('webpage_url') or ''
    if (not url.startswith('http')) and vid:
        url = f'https://www.youtube.com/watch?v={vid}'
    thumbs = e.get('thumbnails') or []
    thumb = ''
    if 'youtube' in (e.get('ie_key') or e.get('extractor') or 'youtube').lower() and vid:
        thumb = yt_thumb(vid)
    elif thumbs:
        thumb = thumbs[-1].get('url', '')
    return {
        'id': vid, 'url': url, 'title': e.get('title') or url,
        'duration': e.get('duration'), 'uploader': e.get('channel') or e.get('uploader') or '',
        'thumbnail': thumb,
    }


def fmt_size(f, duration):
    s = f.get('filesize') or f.get('filesize_approx')
    if not s and f.get('tbr') and duration:
        s = f['tbr'] * duration * 125
    return int(s or 0)


def analyze(query, want_playlist=False):
    query = query.strip()
    is_url = bool(re.match(r'^https?://', query))
    o = base_opts()
    if not is_url:
        o['extract_flat'] = 'in_playlist'
        with yt_dlp.YoutubeDL(o) as ydl:
            info = ydl.extract_info(f'ytsearch25:{query}', download=False)
        return {'type': 'search', 'title': f'Resultados para “{query}”',
                'entries': [entry_item(e) for e in info.get('entries') or []]}

    url = normalize_url(query)
    if want_playlist or looks_like_collection(url):
        if want_playlist:
            m = re.search(r'[?&]list=([\w-]+)', url)
            if m:
                url = f'https://www.youtube.com/playlist?list={m.group(1)}'
        o['extract_flat'] = 'in_playlist'
    else:
        o['noplaylist'] = True
    with yt_dlp.YoutubeDL(o) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get('_type') == 'playlist' or info.get('entries') is not None:
        entries = [entry_item(e) for e in (info.get('entries') or []) if e]
        return {'type': 'playlist', 'title': info.get('title') or 'Playlist',
                'uploader': info.get('channel') or info.get('uploader') or '',
                'url': info.get('webpage_url') or url, 'entries': entries}

    duration = info.get('duration') or 0
    formats = info.get('formats') or []
    audio = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')]
    best_audio = max(audio, key=lambda f: (f.get('abr') or f.get('tbr') or 0), default=None)
    audio_size = fmt_size(best_audio, duration) if best_audio else 0
    by_height = {}
    for f in formats:
        h = f.get('height')
        if not h or f.get('vcodec') in (None, 'none'):
            continue
        key = (h, f.get('fps') or 30)
        cur = by_height.get(h)
        if cur is None or key[1] > (cur.get('fps') or 30) or (
                key[1] == (cur.get('fps') or 30) and (f.get('tbr') or 0) > (cur.get('tbr') or 0)):
            by_height[h] = f
    qualities = []
    for h in sorted(by_height, reverse=True):
        f = by_height[h]
        fps = int(f.get('fps') or 0)
        size = fmt_size(f, duration)
        if f.get('acodec') in (None, 'none'):
            size += audio_size
        qualities.append({
            'height': h, 'fps': fps,
            'label': f'{h}p{fps if fps > 30 else ""}',
            'hdr': (f.get('dynamic_range') or 'SDR') != 'SDR',
            'size': size,
        })
    webpage = info.get('webpage_url') or url
    has_list = 'list=' in query and 'youtube' in query
    return {
        'type': 'video', 'id': info.get('id'), 'url': webpage, 'title': info.get('title'),
        'uploader': info.get('channel') or info.get('uploader') or '', 'duration': duration,
        'view_count': info.get('view_count'), 'upload_date': info.get('upload_date'),
        'thumbnail': info.get('thumbnail') or yt_thumb(info.get('id')),
        'is_live': bool(info.get('is_live')), 'qualities': qualities, 'audio_size': audio_size,
        'chapters': len(info.get('chapters') or []),
        'subtitles': sorted((info.get('subtitles') or {}).keys())[:40],
        'has_playlist': has_list, 'extractor': info.get('extractor_key'),
    }


# ---------------------------------------------------------------- gestor de cola
class Stop(Exception):
    pass


class TrimPP(PostProcessor):
    """Recorta el archivo ya descargado. Descargar entero y cortar en local es mucho más
    rápido con YouTube que pedir rangos a ffmpeg por HTTP, y además se puede cancelar."""
    AUDIO_CODECS = {'.mp3': 'libmp3lame', '.m4a': 'aac', '.aac': 'aac', '.opus': 'libopus', '.ogg': 'libvorbis',
                    '.webm': 'libopus', '.flac': 'flac', '.wav': 'pcm_s16le'}

    def __init__(self, downloader, start=None, end=None, bitrate='320', job=None, mgr=None):
        super().__init__(downloader)
        self.start, self.end, self.bitrate, self.job, self.mgr = start, end, bitrate, job, mgr

    def run(self, info):
        path = info.get('filepath')
        if not path or not os.path.exists(path):
            return [], info
        root, ext = os.path.splitext(path)
        ext = ext.lower()
        out = root + '.recorte' + ext
        args = [FFMPEG or 'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
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
            if ext == '.mp4':
                args += ['-movflags', '+faststart']
        args.append(out)
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        while proc.poll() is None:
            if self.mgr and self.job and self.mgr.flags.get(self.job['id']):
                proc.kill()
                proc.wait()
                if os.path.exists(out):
                    os.remove(out)
                raise Stop()
            time.sleep(0.25)
        if proc.returncode != 0:
            err = (proc.stderr.read() or b'').decode('utf-8', 'replace')[-300:]
            if os.path.exists(out):
                os.remove(out)
            raise RuntimeError(f'No se pudo recortar: {err.strip() or proc.returncode}')
        os.replace(out, path)
        return [], info


class JobLogger:
    def __init__(self, job):
        self.job = job

    def debug(self, msg):
        if 'has already been downloaded' in msg:
            self.job['note'] = 'El archivo ya existía'

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.job['error'] = clean_error(msg)


def new_job(item, options, subfolder=''):
    return {
        'id': uuid.uuid4().hex[:12], 'url': item['url'], 'title': item.get('title') or item['url'],
        'thumbnail': item.get('thumbnail') or '', 'uploader': item.get('uploader') or '',
        'duration': item.get('duration'), 'status': 'queued', 'phase': '', 'progress': 0.0,
        'speed': 0, 'eta': None, 'downloaded': 0, 'total': 0, 'filepath': '', 'filesize': 0,
        'error': '', 'note': '', 'format_label': '', 'subfolder': subfolder,
        'custom_name': clean_filename(item.get('filename')), 'outname': '',
        'options': options, 'created': time.time(), 'finished': None,
    }


class Manager:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = read_json(QUEUE_FILE, [])
        for j in self.jobs:
            if j.get('status') in ACTIVE:
                j['status'] = 'queued'
            j['speed'], j['eta'] = 0, None
        self.history = read_json(HISTORY_FILE, [])
        self.paused = False
        self.flags = {}
        self.dirty = True
        self.last_save = 0
        self.update_status = ''
        threading.Thread(target=self.loop, daemon=True).start()

    # -- persistencia
    def save(self):
        with self.lock:
            write_json(QUEUE_FILE, self.jobs)
            write_json(HISTORY_FILE, self.history[:1000])
            self.dirty = False
            self.last_save = time.time()

    def find(self, jid):
        return next((j for j in self.jobs if j['id'] == jid), None)

    # -- planificador
    def loop(self):
        while True:
            try:
                with self.lock:
                    if not self.paused:
                        limit = max(1, min(8, int(settings.get('concurrency') or 2)))
                        running = sum(1 for j in self.jobs if j['status'] in ACTIVE)
                        for j in self.jobs:
                            if running >= limit:
                                break
                            if j['status'] == 'queued':
                                j['status'] = 'starting'
                                j['phase'] = 'Obteniendo información'
                                running += 1
                                threading.Thread(target=self.run_job, args=(j,), daemon=True).start()
                    if self.dirty and time.time() - self.last_save > 2:
                        self.save()
            except Exception:
                traceback.print_exc()
            time.sleep(0.3)

    def add(self, items, options, subfolder='', top=False):
        opts = {k: options.get(k, settings.get(k)) for k in OPTION_KEYS}
        jobs = [new_job(it, dict(opts), subfolder) for it in items if it.get('url')]
        with self.lock:
            if top:
                idx = next((i for i, j in enumerate(self.jobs) if j['status'] not in ACTIVE), len(self.jobs))
                self.jobs[idx:idx] = jobs
            else:
                self.jobs.extend(jobs)
            self.dirty = True
        return len(jobs)

    # -- ejecucion de una descarga
    def build_opts(self, job, parts, tmpfiles):
        op = job['options']
        folder = op.get('folder') or settings['folder']
        if job.get('subfolder'):
            folder = os.path.join(folder, safe_name(job['subfolder']))
        os.makedirs(folder, exist_ok=True)
        template = op.get('template') or DEFAULTS['template']
        t_start, t_end = parse_duration(op.get('start') or ''), parse_duration(op.get('end') or '')
        job.setdefault('custom_name', '')
        job.setdefault('outname', '')
        if job['custom_name'] and not job['outname']:
            # Se fija al empezar para que una pausa pueda reanudar el mismo .part,
            # y se reserva para que dos descargas simultáneas no compartan nombre.
            with self.lock:
                taken = {x['outname'].lower() for x in self.jobs if x is not job and x.get('outname')
                         and os.path.normcase(x.get('outdir', '')) == os.path.normcase(folder)
                         and x['status'] not in ('done', 'canceled')}
                job['outname'] = unique_base(folder, job['custom_name'], taken=taken)
                job['outname_for'] = job['custom_name']
                job['outdir'] = folder
        if job['outname']:
            template = job['outname'].replace('%', '%%') + '.%(ext)s'
        elif t_start or t_end:
            # Un recorte nunca debe pisar la versión completa del mismo vídeo
            def mmss(t):
                return f'{int(t // 60):02d}m{int(t % 60):02d}s' if t is not None else 'fin'
            suffix = f' (recorte {mmss(t_start or 0)}-{mmss(t_end)})'
            template = template[:-len('.%(ext)s')] + suffix + '.%(ext)s' if template.endswith('.%(ext)s') else template + suffix
        o = base_opts()
        o.update({
            'outtmpl': {'default': os.path.join(folder.replace('%', '%%'), template)},
            'noplaylist': True, 'continuedl': True, 'retries': 10, 'fragment_retries': 10,
            'concurrent_fragment_downloads': 4, 'windowsfilenames': True, 'trim_file_name': 180,
            'overwrites': False, 'logger': JobLogger(job),
        })
        rl = parse_bytes(settings.get('rate_limit') or '') if settings.get('rate_limit') else None
        if rl:
            o['ratelimit'] = rl
        jid = job['id']

        def hook(d):
            if self.flags.get(jid):
                raise Stop()
            if d.get('tmpfilename'):
                tmpfiles.add(d['tmpfilename'])
            fid = (d.get('info_dict') or {}).get('format_id')
            idx = parts['ids'].index(fid) if fid in parts['ids'] else 0
            n = max(1, len(parts['ids']))
            if d['status'] == 'downloading':
                parts['started'] = True
                done = d.get('downloaded_bytes') or 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                sizes = list(parts['sizes'])
                if total and idx < len(sizes):
                    sizes[idx] = total
                full = sum(sizes)
                before = sum(sizes[:idx])
                if full > 0:
                    pct = (before + done) / full * 100
                elif total:
                    pct = (idx + done / total) / n * 100
                else:
                    pct = job['progress']
                job['status'] = 'downloading'
                label = ''
                if n > 1:
                    kind = (d.get('info_dict') or {}).get('vcodec')
                    label = 'Descargando audio' if kind == 'none' else 'Descargando vídeo'
                    label += f' ({idx + 1}/{n})'
                job['phase'] = label or 'Descargando'
                job['progress'] = round(min(pct, 99.9), 1)
                job['speed'] = int(d.get('speed') or 0)
                job['eta'] = d.get('eta')
                job['downloaded'] = int(before + done)
                job['total'] = int(full or total)
            elif d['status'] == 'finished':
                if idx < len(parts['sizes']) and d.get('total_bytes'):
                    parts['sizes'][idx] = d['total_bytes']
                if idx >= n - 1:
                    job['progress'] = 99.9
                    job['speed'], job['eta'] = 0, None

        def pphook(d):
            name = d.get('postprocessor') or ''
            if self.flags.get(jid):
                raise Stop()
            if d['status'] == 'finished' and not parts.get('started'):
                # Postprocesos previos a la descarga (miniatura, SponsorBlock...): volver a "descargando"
                job['status'] = 'downloading'
                job['phase'] = 'Conectando'
            if d['status'] == 'started':
                job['status'] = 'processing'
                job['phase'] = PP_NAMES.get(name, 'Procesando')
                job['speed'], job['eta'] = 0, None
            elif d['status'] == 'finished':
                fp = (d.get('info_dict') or {}).get('filepath')
                if fp:
                    job['filepath'] = fp

        o['progress_hooks'] = [hook]
        o['postprocessor_hooks'] = [pphook]

        pps = []
        mode = op.get('mode') or 'video'
        container = op.get('container') or 'mp4'
        audio_format = op.get('audio_format') or 'mp3'
        start, end = parse_duration(op.get('start') or ''), parse_duration(op.get('end') or '')
        trimming = bool(start or end)
        if op.get('sponsorblock') and not trimming:
            cats = ['sponsor', 'selfpromo', 'interaction']
            pps.append({'key': 'SponsorBlock', 'categories': cats, 'when': 'after_filter'})
            pps.append({'key': 'ModifyChapters', 'remove_sponsor_segments': cats})
        if mode == 'audio':
            o['format'] = 'ba/b'
            if audio_format != 'original':
                lossy = audio_format in ('mp3', 'm4a', 'aac', 'opus')
                pps.append({'key': 'FFmpegExtractAudio', 'preferredcodec': audio_format,
                            'preferredquality': str(op.get('audio_bitrate') or '320') if lossy else '0'})
        else:
            sort = []
            q = str(op.get('quality') or 'best')
            if q.isdigit():
                sort.append(f'res:{q}')
            codec = op.get('codec') or 'auto'
            if codec in ('h264', 'vp9', 'av01'):
                sort.append(f'vcodec:{codec}')
            if container == 'mp4':
                sort.append('ext:mp4:m4a')
            elif container == 'webm':
                sort.append('ext:webm:webm')
            o['format'] = 'bv*+ba/b'
            if sort:
                o['format_sort'] = sort
            o['merge_output_format'] = container
        if trimming:
            pps.append({'key': 'Trim', 'start': start, 'end': end, 'bitrate': op.get('audio_bitrate') or '320'})
        if mode == 'video':
            if op.get('subtitles') and not trimming:
                o['writesubtitles'] = True
                o['writeautomaticsub'] = bool(op.get('auto_subs'))
                o['subtitleslangs'] = [s.strip() for s in (op.get('sub_langs') or 'es,en').split(',') if s.strip()]
                if op.get('embed_subs'):
                    pps.append({'key': 'FFmpegEmbedSubtitle', 'already_have_subtitle': False})
                else:
                    pps.append({'key': 'FFmpegSubtitlesConvertor', 'format': 'srt', 'when': 'before_dl'})
        if op.get('embed_metadata', True):
            pps.append({'key': 'FFmpegMetadata', 'add_chapters': True, 'add_metadata': True})
        can_thumb = not ((mode == 'video' and container == 'webm') or (mode == 'audio' and audio_format in ('wav', 'original')))
        if op.get('embed_thumbnail', True) and can_thumb:
            o['writethumbnail'] = True
            pps.append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg', 'when': 'before_dl'})
            pps.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
        return o, pps, mode, container, audio_format

    def attach_pps(self, ydl, pps, job):
        # Se añaden a mano (y en orden) para poder intercalar el recorte propio.
        for pp in pps:
            pp = dict(pp)
            when = pp.pop('when', 'post_process')
            key = pp.pop('key')
            if key == 'Trim':
                inst = TrimPP(ydl, job=job, mgr=self, **pp)
            else:
                inst = get_postprocessor(key)(ydl, **pp)
            ydl.add_post_processor(inst, when=when)

    def expand_collection(self, job):
        o = base_opts()
        o['extract_flat'] = 'in_playlist'
        with yt_dlp.YoutubeDL(o) as ydl:
            info = ydl.extract_info(normalize_url(job['url']), download=False)
        entries = [entry_item(e) for e in (info.get('entries') or []) if e]
        sub = safe_name(info.get('title')) if settings.get('playlist_subfolder') else ''
        new = [new_job(it, dict(job['options']), sub) for it in entries]
        with self.lock:
            idx = self.jobs.index(job) if job in self.jobs else len(self.jobs)
            if job in self.jobs:
                self.jobs.remove(job)
            self.jobs[idx:idx] = new
            self.dirty = True

    def run_job(self, job):
        jid = job['id']
        tmpfiles = set()
        parts = {'ids': [], 'sizes': []}
        job.update({'error': '', 'note': '', 'speed': 0, 'eta': None})
        try:
            if looks_like_collection(job['url']):
                self.expand_collection(job)
                return
            o, pps, mode, container, audio_format = self.build_opts(job, parts, tmpfiles)
            with yt_dlp.YoutubeDL(o) as ydl:
                self.attach_pps(ydl, pps, job)
                info = ydl.extract_info(job['url'], download=False)
                if self.flags.get(jid):
                    raise Stop()
                if info.get('_type') == 'playlist':
                    raise RuntimeError('El enlace es una lista; analízalo para elegir los vídeos')
                try:
                    tmpfiles.add('base:' + os.path.splitext(ydl.prepare_filename(info))[0])
                except Exception:
                    pass
                job['title'] = info.get('title') or job['title']
                job['uploader'] = info.get('channel') or info.get('uploader') or job['uploader']
                job['duration'] = info.get('duration') or job['duration']
                job['thumbnail'] = job['thumbnail'] or info.get('thumbnail') or ''
                reqs = info.get('requested_formats') or [info]
                dur = info.get('duration') or 0
                parts['ids'] = [f.get('format_id') for f in reqs]
                parts['sizes'] = [fmt_size(f, dur) for f in reqs]
                job['total'] = sum(parts['sizes'])
                if mode == 'audio':
                    br = job['options'].get('audio_bitrate')
                    job['format_label'] = audio_format.upper() + (
                        f' · {br} kbps' if audio_format in ('mp3', 'm4a', 'aac', 'opus') else '')
                else:
                    vf = next((f for f in reqs if f.get('vcodec') not in (None, 'none')), info)
                    h, fps = vf.get('height'), int(vf.get('fps') or 0)
                    vc = (vf.get('vcodec') or '').split('.')[0].replace('avc1', 'H.264').replace('av01', 'AV1').upper()
                    job['format_label'] = ' · '.join(x for x in [
                        container.upper(), f'{h}p{fps if fps > 30 else ""}' if h else '', vc] if x)
                job['status'] = 'downloading'
                job['phase'] = 'Conectando'
                ydl.process_ie_result(info, download=True)
                if not job['filepath']:
                    rd = info.get('requested_downloads') or []
                    job['filepath'] = (rd[-1].get('filepath') if rd else '') or ''
            if self.flags.get(jid):
                raise Stop()
            # Nombre cambiado mientras se descargaba: aplicarlo ahora
            if job.get('custom_name') and job['custom_name'] != job.get('outname_for', job.get('outname')) and job['filepath'] \
                    and os.path.exists(job['filepath']):
                try:
                    job['filepath'] = rename_file(job['filepath'], job['custom_name'])
                except OSError as e:
                    job['note'] = f'No se pudo renombrar: {e.strerror or e}'
            size = 0
            if job['filepath'] and os.path.exists(job['filepath']):
                size = os.path.getsize(job['filepath'])
            job.update({'status': 'done', 'progress': 100.0, 'phase': job['note'] or 'Completado', 'speed': 0,
                        'eta': None, 'filesize': size or job['total'], 'finished': time.time()})
            with self.lock:
                self.history.insert(0, {k: job[k] for k in (
                    'id', 'url', 'title', 'thumbnail', 'uploader', 'duration', 'filepath', 'filesize',
                    'format_label', 'finished', 'custom_name')} | {'mode': job['options'].get('mode')})
        except Exception as e:
            flag = self.flags.get(jid)
            if flag:
                job['status'] = 'paused' if flag == 'pause' else 'canceled'
                job['phase'] = ''
                if flag == 'cancel':
                    self.cleanup(tmpfiles)
                    job['progress'] = 0.0
                    job['downloaded'] = 0
            else:
                job['error'] = job.get('error') or clean_error(e)
                job['status'] = 'error'
                job['phase'] = ''
                traceback.print_exc()
        finally:
            job['speed'], job['eta'] = 0, None
            self.flags.pop(jid, None)
            with self.lock:
                self.dirty = True

    @staticmethod
    def cleanup(tmpfiles):
        """Borra solo restos temporales de una descarga cancelada, nunca archivos completos previos."""
        temp_ext = ('.part', '.ytdl', '.jpg', '.webp', '.png', '.vtt', '.srt', '.temp')
        candidates = set()
        for t in tmpfiles:
            if t.startswith('base:'):
                base = t[5:]
                for p in glob.glob(glob.escape(base) + '.*'):
                    rest = p[len(base):]
                    if rest.lower().endswith(temp_ext) or re.match(r'^\.f[\w-]+\.', rest) or '.part' in rest:
                        candidates.add(p)
            else:
                candidates |= {t + '.part', t + '.ytdl'} | set(glob.glob(glob.escape(t) + '.part*'))
        for p in candidates:
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass

    # -- acciones
    def job_action(self, jid, action):
        with self.lock:
            j = self.find(jid)
            if not j:
                return
            st = j['status']
            if action == 'pause':
                if st in ACTIVE:
                    self.flags[jid] = 'pause'
                elif st == 'queued':
                    j['status'] = 'paused'
            elif action == 'resume':
                if st in ('paused', 'canceled', 'error'):
                    j['status'] = 'queued'
                    j['error'] = ''
            elif action == 'cancel':
                if st in ACTIVE:
                    self.flags[jid] = 'cancel'
                elif st in ('queued', 'paused'):
                    j['status'] = 'canceled'
            elif action == 'retry':
                if st in ('error', 'canceled', 'done', 'paused'):
                    j.update({'status': 'queued', 'error': '', 'progress': 0.0, 'phase': '', 'note': ''})
                    if st in ('canceled', 'done'):
                        j['outname'] = j['outname_for'] = ''
            elif action == 'remove':
                if st in ACTIVE:
                    self.flags[jid] = 'cancel'
                self.jobs.remove(j)
            elif action in ('top', 'bottom', 'up', 'down'):
                i = self.jobs.index(j)
                self.jobs.pop(i)
                ni = {'top': 0, 'bottom': len(self.jobs), 'up': max(0, i - 1), 'down': min(len(self.jobs), i + 1)}[action]
                self.jobs.insert(ni, j)
            self.dirty = True

    def rename(self, jid, name):
        name = clean_filename(name)
        if not name:
            raise ValueError('Escribe un nombre válido')
        with self.lock:
            j = self.find(jid)
            h = next((x for x in self.history if x.get('id') == jid), None)
            if j and j['status'] != 'done':
                j['custom_name'] = name
                if j['status'] in ('queued', 'canceled'):
                    j['outname'] = j['outname_for'] = ''
                self.dirty = True
                later = j['status'] in ACTIVE or bool(j.get('outname'))
                return {'applied': 'later' if later else 'start', 'name': name}
            path = (j or h or {}).get('filepath')
        if not path or not os.path.isfile(path):
            raise ValueError('El archivo ya no existe en disco')
        new = rename_file(path, name)
        with self.lock:
            for rec in (j, h):
                if rec:
                    rec['filepath'] = new
                    rec['custom_name'] = os.path.splitext(os.path.basename(new))[0]
            self.dirty = True
        return {'applied': 'now', 'path': new, 'name': os.path.splitext(os.path.basename(new))[0]}

    def reorder(self, ids):
        with self.lock:
            pos = {jid: i for i, jid in enumerate(ids)}
            self.jobs.sort(key=lambda j: pos.get(j['id'], len(ids)))
            self.dirty = True

    def queue_action(self, action):
        with self.lock:
            if action == 'pause_all':
                self.paused = True
                for j in self.jobs:
                    if j['status'] in ACTIVE:
                        self.flags[j['id']] = 'pause'
            elif action == 'resume_all':
                self.paused = False
                for j in self.jobs:
                    if j['status'] == 'paused':
                        j['status'] = 'queued'
            elif action == 'clear_done':
                self.jobs = [j for j in self.jobs if j['status'] not in ('done', 'canceled')]
            elif action == 'retry_failed':
                for j in self.jobs:
                    if j['status'] in ('error', 'canceled'):
                        j.update({'status': 'queued', 'error': '', 'progress': 0.0, 'phase': ''})
            elif action == 'cancel_all':
                for j in self.jobs:
                    if j['status'] in ACTIVE:
                        self.flags[j['id']] = 'cancel'
                    elif j['status'] in ('queued', 'paused'):
                        j['status'] = 'canceled'
            elif action == 'clear_all':
                for j in self.jobs:
                    if j['status'] in ACTIVE:
                        self.flags[j['id']] = 'cancel'
                self.jobs = []
            self.dirty = True

    def state(self):
        with self.lock:
            for _ in range(3):
                try:
                    return json.dumps({
                        'jobs': self.jobs, 'paused': self.paused, 'settings': settings,
                        'version': yt_dlp.version.__version__, 'ffmpeg': bool(FFMPEG),
                        'update_status': self.update_status,
                    }, ensure_ascii=False)
                except RuntimeError:
                    time.sleep(0.01)
        return '{}'


manager = None
httpd = None


def update_ytdlp():
    manager.update_status = 'Actualizando yt-dlp…'
    try:
        r = subprocess.run([python_console(), '-m', 'pip', 'install', '-U', 'yt-dlp[default]'],
                           capture_output=True, text=True, creationflags=0x08000000, timeout=600)
        if r.returncode == 0:
            manager.update_status = 'yt-dlp actualizado. Reinicia el servidor para aplicar.'
        else:
            manager.update_status = 'Error al actualizar: ' + (r.stderr or r.stdout)[-300:]
    except Exception as e:
        manager.update_status = f'Error al actualizar: {e}'


def python_console():
    exe = sys.executable
    if exe.lower().endswith('pythonw.exe'):
        alt = exe[:-len('pythonw.exe')] + 'python.exe'
        if os.path.exists(alt):
            return alt
    return exe


def pick_folder(initial):
    code = (
        "import sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        "p = filedialog.askdirectory(initialdir=sys.argv[1], title='Selecciona la carpeta de destino', parent=r)\n"
        "sys.stdout.write(p or '')\n"
    )
    r = subprocess.run([sys.executable, '-c', code, initial or os.path.expanduser('~')],
                       capture_output=True, text=True, creationflags=0x08000000)
    p = (r.stdout or '').strip()
    return os.path.normpath(p) if p else ''


def known_paths():
    with manager.lock:
        return {j.get('filepath') for j in manager.jobs} | {h.get('filepath') for h in manager.history}


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code=200, body=b'', ctype='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False))

    def host_ok(self):
        return self.headers.get('Host', '') in (f'{HOST}:{PORT}', f'localhost:{PORT}')

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, 'forbidden', 'text/plain')
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            with open(os.path.join(BASE, 'index.html'), 'rb') as f:
                return self.send(200, f.read(), 'text/html; charset=utf-8')
        if path == '/api/ping':
            return self.json({'ok': True, 'app': 'descargador'})
        if path == '/api/state':
            return self.send(200, manager.state())
        if path == '/api/history':
            with manager.lock:
                return self.json({'history': manager.history})
        return self.send(404, 'not found', 'text/plain')

    def do_POST(self):
        # Protección frente a peticiones de otras webs (CSRF / DNS rebinding)
        if not self.host_ok() or self.headers.get('X-Descargador') != '1':
            return self.send(403, 'forbidden', 'text/plain')
        length = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            body = {}
        path = urlparse(self.path).path
        try:
            return self.route(path, body)
        except Exception as e:
            traceback.print_exc()
            return self.json({'error': clean_error(e)}, 400)

    def route(self, path, b):
        if path == '/api/info':
            return self.json(analyze(b.get('query', ''), bool(b.get('playlist'))))
        if path == '/api/add':
            n = manager.add(b.get('items') or [], b.get('options') or {}, b.get('subfolder') or '', bool(b.get('top')))
            return self.json({'added': n})
        if path == '/api/add-urls':
            urls = re.findall(r'https?://[^\s<>"\']+', b.get('text') or '')
            seen, items = set(), []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    items.append({'url': u, 'title': u})
            n = manager.add(items, b.get('options') or {}, '', bool(b.get('top')))
            return self.json({'added': n})
        if path == '/api/job':
            manager.job_action(b.get('id'), b.get('action'))
            return self.json({'ok': True})
        if path == '/api/rename':
            return self.json(manager.rename(b.get('id'), b.get('name')))
        if path == '/api/reorder':
            manager.reorder(b.get('ids') or [])
            return self.json({'ok': True})
        if path == '/api/queue':
            manager.queue_action(b.get('action'))
            return self.json({'ok': True})
        if path == '/api/settings':
            with settings_lock:
                for k, v in (b or {}).items():
                    if k in DEFAULTS:
                        settings[k] = v
            save_settings()
            return self.json({'settings': settings})
        if path == '/api/pick-folder':
            return self.json({'path': pick_folder(b.get('initial') or settings['folder'])})
        if path == '/api/open':
            p = b.get('path') or ''
            if b.get('mode') == 'file':
                if p in known_paths() and os.path.isfile(p):
                    os.startfile(p)
                    return self.json({'ok': True})
                return self.json({'error': 'El archivo ya no existe'}, 404)
            if b.get('mode') == 'select' and p in known_paths() and os.path.isfile(p):
                subprocess.Popen(['explorer', '/select,', p])
                return self.json({'ok': True})
            folder = p if os.path.isdir(p) else os.path.dirname(p)
            if b.get('mode') == 'app':
                folder = BASE
            if folder and not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
            if folder and os.path.isdir(folder):
                os.startfile(folder)
                return self.json({'ok': True})
            return self.json({'error': 'Carpeta no encontrada'}, 404)
        if path == '/api/history':
            with manager.lock:
                if b.get('action') == 'clear':
                    manager.history = []
                elif b.get('action') == 'remove':
                    manager.history = [h for h in manager.history if h.get('id') != b.get('id')]
                manager.dirty = True
            return self.json({'ok': True})
        if path == '/api/update-ytdlp':
            threading.Thread(target=update_ytdlp, daemon=True).start()
            return self.json({'ok': True})
        if path == '/api/restart':
            threading.Thread(target=restart, daemon=True).start()
            return self.json({'ok': True})
        if path == '/api/shutdown':
            threading.Thread(target=shutdown, daemon=True).start()
            return self.json({'ok': True})
        return self.json({'error': 'ruta desconocida'}, 404)


def shutdown():
    time.sleep(0.3)
    manager.save()
    os._exit(0)


def restart():
    time.sleep(0.3)
    manager.save()
    subprocess.Popen([sys.executable, os.path.join(BASE, 'server.py'), '--restart'], cwd=BASE,
                     creationflags=0x00000008 | 0x08000000)
    os._exit(0)


def ping():
    try:
        with urlopen(URL + 'api/ping', timeout=1.5) as r:
            return b'descargador' in r.read()
    except Exception:
        return False


def open_window():
    if settings.get('app_window', True):
        cands = [
            os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
        ]
        for c in cands:
            if os.path.exists(c):
                subprocess.Popen([c, f'--app={URL}', '--window-size=1460,940'])
                return
    webbrowser.open(URL)


def main():
    global manager, httpd
    is_restart = '--restart' in sys.argv
    no_browser = is_restart or '--no-browser' in sys.argv
    if not is_restart and ping():
        open_window()
        return
    for _ in range(60):
        try:
            httpd = ThreadingHTTPServer((HOST, PORT), Handler)
            break
        except OSError:
            if not is_restart and ping():
                open_window()
                return
            time.sleep(0.25)
    if httpd is None:
        print('No se pudo abrir el puerto', PORT)
        return
    httpd.daemon_threads = True
    manager = Manager()
    print(f'Descargador en {URL}  (yt-dlp {yt_dlp.version.__version__}, ffmpeg: {FFMPEG})')
    if not no_browser:
        threading.Timer(0.4, open_window).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        manager.save()


if __name__ == '__main__':
    main()
