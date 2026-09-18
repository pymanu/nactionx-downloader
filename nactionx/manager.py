"""Cola de descargas: planificación, estados, persistencia, historial y notificaciones."""
import collections
import os
import re
import threading
import time
import uuid
from pathlib import Path

from . import errors, log, names, paths, platform_utils, settings as settings_mod, storage

logger = log.get('manager')

ACTIVE = ('starting', 'downloading', 'processing')
PENDING = ('queued', 'paused')
RETRY_DELAYS = (15, 45, 120)
HISTORY_LIMIT = 1000
PROGRESS_KEYS = ('progress', 'speed', 'eta', 'downloaded', 'total')
PRIVATE_KEYS = ('outname_for', 'outdir')

JOB_DEFAULTS = {
    'id': '', 'url': '', 'title': '', 'thumbnail': '', 'uploader': '', 'duration': None,
    'status': 'queued', 'phase': '', 'progress': 0.0, 'speed': 0, 'eta': None, 'downloaded': 0, 'total': 0,
    'filepath': '', 'filesize': 0, 'error': '', 'error_detail': '', 'error_kind': '', 'note': '',
    'format_label': '', 'subfolder': '', 'custom_name': '', 'outname': '', 'outname_for': '', 'outdir': '',
    'options': {}, 'created': 0.0, 'finished': None, 'paused_by': '', 'retries': 0, 'retry_at': 0.0,
}
URL_RE = re.compile(r'https?://[^\s<>"\']+')
YOUTUBE_ID = re.compile(r'(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})')


def media_key(url):
    match = YOUTUBE_ID.search(url or '')
    return f'yt:{match.group(1)}' if match else (url or '').strip().rstrip('/')


def new_job(item, options, subfolder=''):
    job = dict(JOB_DEFAULTS)
    job.update({
        'id': uuid.uuid4().hex[:12], 'url': item['url'].strip(), 'title': item.get('title') or item['url'],
        'thumbnail': item.get('thumbnail') or '', 'uploader': item.get('uploader') or '',
        'duration': item.get('duration'), 'subfolder': subfolder or '',
        'custom_name': names.clean_filename(item.get('filename')), 'options': dict(options), 'created': time.time(),
    })
    return job


def run_download(job, manager):
    from . import engine
    download = engine.Download(job, manager)
    try:
        return download.run()
    except BaseException:
        if manager.flag(job['id']) == 'cancel':
            download.cleanup()
        raise


def expand_collection(url, settings, components):
    from . import engine
    return engine.expand_collection(url, settings, components)


def is_collection(url):
    from . import engine
    return engine.looks_like_collection(url)


class Manager:
    def __init__(self, settings, components, data_dir=None, runner=None, expander=None, collection_check=None,
                 notifier=None, autostart=True):
        self.settings = settings
        self.components = components
        base = Path(data_dir or paths.data_dir())
        self.queue_path, self.history_path = base / 'queue.json', base / 'history.json'
        self.runner = runner or run_download
        self.expander = expander or expand_collection
        self.is_collection = collection_check or is_collection
        self.notifier = notifier or platform_utils.notify
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self.flags = {}
        self.logs = {}
        self.srev, self.prev = 1, 1
        self.dirty = False
        self.stopped = False
        self.batch = {'done': [], 'failed': []}
        self._load()
        if autostart:
            self.start()

    # ------------------------------------------------------------ persistencia
    def _load(self):
        raw = storage.read_json(self.queue_path, {})
        if isinstance(raw, list):
            raw = {'jobs': raw}
        self.paused = bool(raw.get('paused'))
        self.jobs = []
        for stored in raw.get('jobs') or []:
            job = {**JOB_DEFAULTS, **{k: v for k, v in stored.items() if k in JOB_DEFAULTS}}
            if not job['id'] or not job['url']:
                continue
            if job['status'] in ACTIVE or (job['status'] == 'paused' and job['paused_by'] == 'shutdown'):
                job['status'], job['paused_by'] = 'queued', ''
            job['speed'], job['eta'] = 0, None
            self.jobs.append(job)
        self.history = list(storage.read_json(self.history_path, []))[:HISTORY_LIMIT]

    def save(self):
        with self.lock:
            data = {'version': 1, 'paused': self.paused, 'jobs': [dict(j) for j in self.jobs]}
            history = list(self.history[:HISTORY_LIMIT])
            self.dirty = False
        storage.write_json(self.queue_path, data)
        storage.write_json(self.history_path, history)

    def _saver(self):
        while not self.stopped:
            time.sleep(1.5)
            if self.dirty:
                self.save()

    # ------------------------------------------------------------ contexto para el motor
    def touch(self):
        with self.lock:
            self.srev += 1
            self.dirty = True
            self.cv.notify_all()

    def bump_progress(self):
        self.prev += 1

    def flag(self, job_id):
        return self.flags.get(job_id)

    def settings_snapshot(self):
        return self.settings.snapshot()

    def log(self, job_id, level, message):
        entries = self.logs.get(job_id)
        if entries is None:
            entries = self.logs.setdefault(job_id, collections.deque(maxlen=400))
        entries.append((time.time(), level, message))

    def reserve_name(self, job, folder, name):
        with self.lock:
            taken = {x['outname'] for x in self.jobs
                     if x is not job and x['outname'] and x['status'] not in ('done', 'canceled')
                     and os.path.normcase(x['outdir']) == os.path.normcase(folder)}
            return names.unique_base(folder, name, taken=taken)

    # ------------------------------------------------------------ planificador
    def start(self):
        threading.Thread(target=self._scheduler, daemon=True, name='scheduler').start()
        threading.Thread(target=self._saver, daemon=True, name='saver').start()

    def _scheduler(self):
        while not self.stopped:
            with self.cv:
                wait = 2.0
                if not self.paused:
                    limit = self.settings.get('concurrency')
                    running = sum(1 for j in self.jobs if j['status'] in ACTIVE)
                    now = time.time()
                    for job in self.jobs:
                        if running >= limit:
                            break
                        if job['status'] != 'queued':
                            continue
                        if job['retry_at'] and job['retry_at'] > now:
                            wait = min(wait, job['retry_at'] - now)
                            continue
                        self._start(job)
                        running += 1
                self.cv.wait(timeout=max(0.05, wait))

    def _start(self, job):
        job.update(status='starting', phase='Obteniendo información', speed=0, eta=None, retry_at=0.0)
        self.log(job['id'], 'info', f'Inicio: {job["url"]}')
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f'job-{job["id"]}').start()
        self.touch()

    def _run(self, job):
        job_id = job['id']
        try:
            if self.is_collection(job['url']):
                self._expand(job)
                return
            size = self.runner(job, self)
            with self.lock:
                if self.flags.get(job_id):
                    raise engine_stop()
                job.update(status='done', progress=100.0, phase=job['note'] or 'Completado', speed=0, eta=None,
                           filesize=size or job['total'], finished=time.time(), error='', error_detail='',
                           error_kind='', retries=0, retry_at=0.0)
                if job in self.jobs:
                    self._add_history(job)
                self.batch['done'].append(job['custom_name'] or job['title'])
                self.log(job_id, 'info', f'Completado: {job["filepath"]}')
        except BaseException as exc:
            with self.lock:
                flag = self.flags.get(job_id)
                if flag:
                    self._apply_flag(job, flag)
                else:
                    self._fail(job, exc)
        finally:
            with self.lock:
                self.flags.pop(job_id, None)
                job['speed'], job['eta'] = 0, None
                self.touch()
                self._notify_if_idle()

    def _apply_flag(self, job, flag):
        if flag == 'cancel':
            job.update(status='canceled', phase='', progress=0.0, downloaded=0, outname='', outname_for='', paused_by='')
            self.log(job['id'], 'info', 'Cancelada por el usuario')
        else:
            job.update(status='paused', phase='', paused_by={'pause': 'user', 'pause_global': 'global'}.get(flag, 'shutdown'))
            self.log(job['id'], 'info', 'Pausada')

    def _fail(self, job, exc):
        message, kind, detail = errors.explain(exc)
        entries = self.logs.get(job['id'])
        if not entries or entries[-1][2] != (detail or message):
            self.log(job['id'], 'error', detail or message)
        if kind in errors.RETRYABLE and job['retries'] < len(RETRY_DELAYS):
            delay = RETRY_DELAYS[job['retries']] * (2 if kind == 'ratelimit' else 1)
            job['retries'] += 1
            job.update(status='queued', retry_at=time.time() + delay, error=message, error_detail=detail,
                       error_kind=kind, phase=f'Reintento {job["retries"]} de {len(RETRY_DELAYS)}')
            logger.info('Reintento %s de %s en %ss: %s', job['retries'], job['url'], delay, detail[:200])
            return
        job.update(status='error', phase='', error=message, error_detail=detail, error_kind=kind)
        self.batch['failed'].append(job['custom_name'] or job['title'])
        logger.warning('Descarga fallida %s: %s', job['url'], detail[:300])

    def _expand(self, job):
        snapshot = self.settings.snapshot()
        title, entries = self.expander(job['url'], snapshot, self.components)
        subfolder = names.folder_name(title) if snapshot.get('playlist_subfolder') else ''
        created = [new_job(item, job['options'], subfolder) for item in entries if item.get('url') and not item.get('live')]
        if not created:
            raise errors.FriendlyError('La lista no contiene vídeos descargables.', 'unavailable')
        with self.lock:
            index = self.jobs.index(job) if job in self.jobs else len(self.jobs)
            if job in self.jobs:
                self.jobs.remove(job)
            self.jobs[index:index] = created
            self.logs.pop(job['id'], None)

    def _add_history(self, job):
        entry = {k: job[k] for k in ('id', 'url', 'title', 'thumbnail', 'uploader', 'duration', 'filepath', 'filesize',
                                     'format_label', 'finished', 'custom_name')}
        entry['mode'] = job['options'].get('mode')
        self.history = [h for h in self.history if h.get('id') != job['id']]
        self.history.insert(0, entry)
        del self.history[HISTORY_LIMIT:]

    def _notify_if_idle(self):
        if any(j['status'] in ACTIVE or j['status'] == 'queued' for j in self.jobs):
            return
        done, failed = self.batch['done'], self.batch['failed']
        if not done and not failed:
            return
        self.batch = {'done': [], 'failed': []}
        if not self.settings.get('notify'):
            return
        if len(done) == 1 and not failed:
            title, body = 'Descarga completada', done[0]
        elif done:
            title = f'{len(done)} descargas completadas'
            body = f'{len(failed)} con error' if failed else 'Todo listo en tu carpeta de destino'
        else:
            title, body = 'Descargas con error', f'{len(failed)} no se pudieron completar'
        self.notifier(title, body)

    # ------------------------------------------------------------ acciones
    def add(self, items, options, subfolder='', top=False):
        opts = settings_mod.job_options(options, self.settings.snapshot())
        with self.lock:
            busy = {(media_key(j['url']), j['options'].get('mode'), j['options'].get('start'), j['options'].get('end'))
                    for j in self.jobs if j['status'] in ACTIVE or j['status'] in PENDING}
            created, duplicates = [], 0
            for item in items or []:
                if not item.get('url'):
                    continue
                key = (media_key(item['url']), opts['mode'], opts['start'], opts['end'])
                if key in busy:
                    duplicates += 1
                    continue
                busy.add(key)
                created.append(new_job(item, opts, subfolder))
            if top:
                index = next((i for i, j in enumerate(self.jobs) if j['status'] not in ACTIVE), len(self.jobs))
                self.jobs[index:index] = created
            else:
                self.jobs.extend(created)
            if created:
                self.touch()
        return {'added': len(created), 'duplicates': duplicates}

    def add_urls(self, text, options, top=False):
        urls = list(dict.fromkeys(URL_RE.findall(text or '')))
        return self.add([{'url': u, 'title': u} for u in urls], options, '', top)

    def job_action(self, job_id, action):
        with self.lock:
            job = next((j for j in self.jobs if j['id'] == job_id), None)
            if not job:
                return False
            status = job['status']
            if action == 'pause':
                if status in ACTIVE:
                    self.flags[job_id] = 'pause'
                elif status == 'queued':
                    job.update(status='paused', paused_by='user')
            elif action == 'resume':
                if status in ('paused', 'canceled', 'error'):
                    job.update(status='queued', paused_by='', error='', error_detail='', error_kind='', retries=0, retry_at=0.0)
            elif action == 'cancel':
                if status in ACTIVE:
                    self.flags[job_id] = 'cancel'
                elif status in PENDING:
                    job.update(status='canceled', paused_by='', retry_at=0.0)
            elif action == 'retry':
                if status in ('error', 'canceled', 'done', 'paused'):
                    job.update(status='queued', error='', error_detail='', error_kind='', progress=0.0, phase='',
                               note='', retries=0, retry_at=0.0, paused_by='')
                    if status in ('canceled', 'done'):
                        job.update(outname='', outname_for='', filepath='')
            elif action == 'remove':
                if status in ACTIVE:
                    self.flags[job_id] = 'cancel'
                self.jobs.remove(job)
                self.logs.pop(job_id, None)
            elif action in ('top', 'bottom', 'up', 'down'):
                index = self.jobs.index(job)
                self.jobs.pop(index)
                target = {'top': 0, 'bottom': len(self.jobs), 'up': max(0, index - 1),
                          'down': min(len(self.jobs), index + 1)}[action]
                self.jobs.insert(target, job)
            else:
                return False
            self.touch()
            return True

    def queue_action(self, action):
        with self.lock:
            if action == 'pause_all':
                self.paused = True
                for job in self.jobs:
                    if job['status'] in ACTIVE:
                        self.flags[job['id']] = 'pause_global'
            elif action == 'resume_all':
                self.paused = False
                for job in self.jobs:
                    if job['status'] == 'paused' and job['paused_by'] in ('global', 'shutdown'):
                        job.update(status='queued', paused_by='')
            elif action == 'clear_done':
                self.jobs = [j for j in self.jobs if j['status'] not in ('done', 'canceled')]
            elif action == 'retry_failed':
                for job in self.jobs:
                    previous = job['status']
                    if previous in ('error', 'canceled'):
                        job.update(status='queued', error='', error_detail='', error_kind='', progress=0.0, phase='',
                                   retries=0, retry_at=0.0, paused_by='')
                        if previous == 'canceled':
                            job.update(outname='', outname_for='')
            elif action == 'cancel_all':
                for job in self.jobs:
                    if job['status'] in ACTIVE:
                        self.flags[job['id']] = 'cancel'
                    elif job['status'] in PENDING:
                        job.update(status='canceled', paused_by='', retry_at=0.0)
            elif action == 'clear_all':
                for job in self.jobs:
                    if job['status'] in ACTIVE:
                        self.flags[job['id']] = 'cancel'
                self.jobs = []
                self.logs.clear()
            else:
                return False
            self.touch()
            return True

    def reorder(self, ids):
        with self.lock:
            position = {job_id: i for i, job_id in enumerate(ids or [])}
            self.jobs.sort(key=lambda j: position.get(j['id'], len(position)))
            self.touch()

    def rename(self, job_id, name):
        name = names.clean_filename(name)
        if not name:
            raise ValueError('Escribe un nombre válido')
        with self.lock:
            job = next((j for j in self.jobs if j['id'] == job_id), None)
            entry = next((h for h in self.history if h.get('id') == job_id), None)
            if job and job['status'] != 'done':
                job['custom_name'] = name
                if job['status'] in ('queued', 'canceled') and not job['downloaded']:
                    job.update(outname='', outname_for='')
                self.touch()
                later = job['status'] in ACTIVE or bool(job['outname'])
                return {'applied': 'later' if later else 'start', 'name': name}
            path = (job or entry or {}).get('filepath')
        if not path or not os.path.isfile(path):
            raise ValueError('El archivo ya no existe en disco')
        new_path = names.rename_file(path, name)
        final_name = os.path.splitext(os.path.basename(new_path))[0]
        with self.lock:
            for record in (job, entry):
                if record:
                    record['filepath'], record['custom_name'] = new_path, final_name
            self.touch()
        return {'applied': 'now', 'path': new_path, 'name': final_name}

    # ------------------------------------------------------------ consultas
    def _public(self, job):
        return {k: v for k, v in job.items() if k not in PRIVATE_KEYS}

    def state(self, srev=None, prev=None):
        with self.lock:
            base = {'srev': self.srev, 'prev': self.prev, 'paused': self.paused}
            if srev == self.srev:
                if prev == self.prev:
                    return {**base, 'unchanged': True}
                progress = {j['id']: {k: j[k] for k in PROGRESS_KEYS} for j in self.jobs if j['status'] in ACTIVE}
                return {**base, 'progress': progress}
            return {**base, 'jobs': [self._public(j) for j in self.jobs]}

    def job_log(self, job_id):
        return [{'t': t, 'level': level, 'msg': msg} for t, level, msg in list(self.logs.get(job_id) or [])]

    def history_list(self):
        with self.lock:
            return list(self.history)

    def history_action(self, action, job_id=None):
        with self.lock:
            if action == 'clear':
                self.history = []
            elif action == 'remove':
                self.history = [h for h in self.history if h.get('id') != job_id]
            self.touch()

    def known_paths(self):
        with self.lock:
            return {j['filepath'] for j in self.jobs if j['filepath']} | {h.get('filepath') for h in self.history if h.get('filepath')}

    def active_count(self):
        with self.lock:
            return sum(1 for j in self.jobs if j['status'] in ACTIVE)

    # ------------------------------------------------------------ migración del prototipo
    def import_history(self, entries):
        with self.lock:
            known = {h.get('id') for h in self.history}
            added = [h for h in entries or [] if isinstance(h, dict) and h.get('id') and h['id'] not in known]
            self.history = sorted(self.history + added, key=lambda h: h.get('finished') or 0, reverse=True)[:HISTORY_LIMIT]
            self.touch()
            return len(added)

    def import_jobs(self, stored_jobs):
        snapshot = self.settings.snapshot()
        imported = 0
        with self.lock:
            known = {j['id'] for j in self.jobs}
            for stored in stored_jobs or []:
                if not isinstance(stored, dict) or not stored.get('url') or stored.get('id') in known:
                    continue
                try:
                    options = settings_mod.job_options(stored.get('options') or {}, snapshot)
                except ValueError:
                    options = settings_mod.job_options({}, snapshot)
                job = {**JOB_DEFAULTS, **{k: v for k, v in stored.items() if k in JOB_DEFAULTS}, 'options': options}
                job.update(status='paused', paused_by='user', speed=0, eta=None, error='', retries=0, retry_at=0.0)
                self.jobs.append(job)
                imported += 1
            if imported:
                self.touch()
        return imported

    # ------------------------------------------------------------ cierre ordenado
    def shutdown(self, timeout=8.0):
        with self.lock:
            active = [j for j in self.jobs if j['status'] in ACTIVE]
            for job in active:
                self.flags[job['id']] = 'shutdown'
            self.touch()
        deadline = time.time() + timeout
        while active and time.time() < deadline:
            if not any(j['status'] in ACTIVE for j in active):
                break
            time.sleep(0.1)
        killed = platform_utils.kill_children()
        with self.lock:
            for job in self.jobs:
                if job['status'] in ACTIVE:
                    job.update(status='queued', speed=0, eta=None)
            self.stopped = True
            self.cv.notify_all()
        self.save()
        logger.info('Cola guardada al cerrar (%s activas, %s procesos cerrados)', len(active), killed)


def engine_stop():
    from .engine import Stop
    return Stop()


def migrate_legacy(settings, manager, marker_dir=None):
    """Importa ajustes, historial y cola pendiente del prototipo «Descargador» una sola vez."""
    marker = Path(marker_dir or paths.data_dir()) / 'migration.json'
    if marker.exists():
        return None
    result = {'source': '', 'settings': 0, 'history': 0, 'queue': 0}
    sources = paths.legacy_data_dirs()
    if sources:
        source = sources[0]
        legacy_settings = storage.read_json(source / 'settings.json', {}) or {}
        result['settings'] = len(settings.replace_all(legacy_settings))
        result['history'] = manager.import_history(storage.read_json(source / 'history.json', []))
        legacy_queue = storage.read_json(source / 'queue.json', [])
        if isinstance(legacy_queue, dict):
            legacy_queue = legacy_queue.get('jobs', [])
        result['queue'] = manager.import_jobs([j for j in legacy_queue if j.get('status') != 'done'])
        result['source'] = str(source)
        logger.info('Migración del prototipo: %s', result)
    storage.write_json(marker, {'done_at': time.time(), **result})
    return result
