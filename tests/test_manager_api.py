import http.client
import json
import threading
import time

import pytest

from nactionx import api, manager as manager_mod, paths, settings


class FakeComponents:
    def status(self):
        return {'ytdlp': 'test', 'issues': [], 'update': {}}


def wait_for(predicate, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def make(tmp_path, runner, autostart=True, notes=None, concurrency=2):
    store = settings.Settings(tmp_path / 'settings.json')
    store.update({'folder': str(tmp_path / 'dl'), 'concurrency': concurrency})
    notes = notes if notes is not None else []
    m = manager_mod.Manager(store, FakeComponents(), data_dir=tmp_path, runner=runner,
                            collection_check=lambda url: False, notifier=lambda t, b: notes.append((t, b)),
                            autostart=autostart)
    return m, store, notes


def status_of(m, job_id):
    return next(j for j in m.jobs if j['id'] == job_id)['status']


def blocking_runner(release):
    def run(job, m):
        while not release.is_set():
            if m.flag(job['id']):
                raise RuntimeError('stop')
            time.sleep(0.01)
        return 123
    return run


# ------------------------------------------------------------------ cola
def test_duplicates_are_detected(tmp_path):
    m, _, _ = make(tmp_path, blocking_runner(threading.Event()), autostart=False)
    first = m.add([{'url': 'https://www.youtube.com/watch?v=jNQXAC9IVRw'}], {})
    again = m.add([{'url': 'https://youtu.be/jNQXAC9IVRw'}, {'url': 'https://example.com/otro'}], {})
    assert first == {'added': 1, 'duplicates': 0} and again == {'added': 1, 'duplicates': 1}
    audio = m.add([{'url': 'https://youtu.be/jNQXAC9IVRw'}], {'mode': 'audio'})
    assert audio['added'] == 1, 'el mismo vídeo en audio no es un duplicado'


def test_concurrency_limit_and_completion(tmp_path):
    release = threading.Event()
    m, _, notes = make(tmp_path, blocking_runner(release))
    m.add([{'url': f'https://example.com/{i}'} for i in range(3)], {})
    assert wait_for(lambda: m.active_count() == 2)
    time.sleep(0.2)
    assert m.active_count() == 2
    release.set()
    assert wait_for(lambda: all(j['status'] == 'done' for j in m.jobs))
    assert wait_for(lambda: len(notes) == 1)
    assert notes[0][0] == '3 descargas completadas', 'B10: una sola notificación resumen'
    m.shutdown(timeout=1)


def test_network_errors_are_retried_automatically(tmp_path):
    calls = []

    def flaky(job, m):
        calls.append(1)
        if len(calls) == 1:
            raise OSError('<urlopen error [Errno 11001] getaddrinfo failed>')
        return 50

    m, _, _ = make(tmp_path, flaky)
    job_id = m.jobs[0]['id'] if m.jobs else None
    m.add([{'url': 'https://example.com/red'}], {})
    job = m.jobs[0]
    assert wait_for(lambda: job['retries'] == 1)
    assert job['status'] == 'queued' and job['retry_at'] > time.time() and 'conexión' in job['error']
    job['retry_at'] = time.time()
    m.touch()
    assert wait_for(lambda: job['status'] == 'done')
    assert job_id is None and len(calls) == 2
    m.shutdown(timeout=1)


def test_permanent_errors_are_not_retried(tmp_path):
    def broken(job, m):
        raise RuntimeError('ERROR: [youtube] x: This video is unavailable')

    m, _, notes = make(tmp_path, broken)
    m.add([{'url': 'https://example.com/roto'}], {})
    job = m.jobs[0]
    assert wait_for(lambda: job['status'] == 'error')
    assert job['retries'] == 0 and job['error_kind'] == 'unavailable'
    assert wait_for(lambda: notes and notes[0][0] == 'Descargas con error')
    m.shutdown(timeout=1)


def test_pause_all_persists_and_resume_only_global(tmp_path):
    """B08 y B09."""
    release = threading.Event()
    m, store, _ = make(tmp_path, blocking_runner(release), concurrency=1)
    m.add([{'url': 'https://example.com/a'}, {'url': 'https://example.com/b'}], {})
    a, b = m.jobs
    m.job_action(b['id'], 'pause')
    assert wait_for(lambda: a['status'] == 'downloading' or a['status'] == 'starting')
    m.queue_action('pause_all')
    assert wait_for(lambda: a['status'] == 'paused')
    assert a['paused_by'] == 'global' and b['paused_by'] == 'user'
    m.save()
    reloaded = manager_mod.Manager(store, FakeComponents(), data_dir=tmp_path, runner=blocking_runner(release),
                                   collection_check=lambda u: False, notifier=lambda t, b: None, autostart=False)
    assert reloaded.paused is True
    reloaded.queue_action('resume_all')
    ra, rb = reloaded.jobs
    assert ra['status'] == 'queued' and rb['status'] == 'paused'
    release.set()
    m.shutdown(timeout=1)


def test_cancel_resets_progress(tmp_path):
    m, _, _ = make(tmp_path, blocking_runner(threading.Event()))
    m.add([{'url': 'https://example.com/c'}], {})
    job = m.jobs[0]
    assert wait_for(lambda: job['status'] == 'starting')
    job['progress'] = 40.0
    m.job_action(job['id'], 'cancel')
    assert wait_for(lambda: job['status'] == 'canceled')
    assert job['progress'] == 0.0
    m.shutdown(timeout=1)


def test_state_revisions_are_incremental(tmp_path):
    """B03: sin cambios no se reenvía la cola."""
    m, _, _ = make(tmp_path, blocking_runner(threading.Event()), autostart=False)
    m.add([{'url': 'https://example.com/s'}], {})
    full = m.state()
    assert len(full['jobs']) == 1
    same = m.state(full['srev'], full['prev'])
    assert same.get('unchanged') and 'jobs' not in same
    m.jobs[0]['status'] = 'downloading'
    m.bump_progress()
    partial = m.state(full['srev'], full['prev'])
    assert 'progress' in partial and 'jobs' not in partial


def test_rename_completed_file(tmp_path):
    def producer(job, m):
        folder = tmp_path / 'dl'
        folder.mkdir(exist_ok=True)
        path = folder / 'Original.mp4'
        path.write_text('video')
        job['filepath'] = str(path)
        return 5

    m, _, _ = make(tmp_path, producer)
    m.add([{'url': 'https://example.com/r'}], {})
    job = m.jobs[0]
    assert wait_for(lambda: job['status'] == 'done')
    result = m.rename(job['id'], 'Mi nombre: final?')
    assert result['applied'] == 'now' and result['path'].endswith('Mi nombre final.mp4')
    assert (tmp_path / 'dl' / 'Mi nombre final.mp4').exists() and m.history[0]['filepath'] == result['path']
    with pytest.raises(ValueError):
        m.rename(job['id'], '???')
    m.shutdown(timeout=1)


def test_corrupt_queue_file_does_not_crash(tmp_path):
    (tmp_path / 'queue.json').write_text('{esto no es json', encoding='utf-8')
    m, _, _ = make(tmp_path, blocking_runner(threading.Event()), autostart=False)
    assert m.jobs == []


def test_legacy_migration(tmp_path, monkeypatch):
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    (legacy / 'settings.json').write_text(json.dumps({'folder': str(tmp_path / 'viejo'), 'concurrency': 4,
                                                      'app_window': True}), encoding='utf-8')
    (legacy / 'history.json').write_text(json.dumps([{'id': 'h1', 'title': 'Antiguo', 'finished': 1}]), encoding='utf-8')
    (legacy / 'queue.json').write_text(json.dumps([
        {'id': 'd1', 'url': 'https://example.com/hecho', 'status': 'done', 'options': {}},
        {'id': 'q1', 'url': 'https://example.com/pendiente', 'status': 'queued', 'options': {'mode': 'audio'}},
    ]), encoding='utf-8')
    monkeypatch.setattr(paths, 'legacy_data_dirs', lambda: [legacy])
    m, store, _ = make(tmp_path, blocking_runner(threading.Event()), autostart=False)
    result = manager_mod.migrate_legacy(store, m, marker_dir=tmp_path)
    assert result['settings'] == 2 and result['history'] == 1 and result['queue'] == 1
    assert store.get('concurrency') == 4 and m.jobs[0]['status'] == 'paused' and m.jobs[0]['options']['mode'] == 'audio'
    assert manager_mod.migrate_legacy(store, m, marker_dir=tmp_path) is None


# ------------------------------------------------------------------ API
@pytest.fixture
def server(tmp_path):
    m, store, _ = make(tmp_path, blocking_runner(threading.Event()), autostart=False)
    srv = api.ApiServer(m, store, FakeComponents())
    srv.start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None, token=True, host=None):
    conn = http.client.HTTPConnection('127.0.0.1', srv.port, timeout=5)
    headers = {'Host': host or f'127.0.0.1:{srv.port}', 'Content-Type': 'application/json'}
    if token:
        headers['X-NactionX-Token'] = srv.token
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_api_requires_token(server):
    """D03."""
    assert request(server, 'GET', '/api/state', token=False)[0] == 401
    assert request(server, 'POST', '/api/queue', {'action': 'clear_all'}, token=False)[0] == 403
    assert request(server, 'GET', '/api/state')[0] == 200
    assert request(server, 'GET', '/api/ping', token=False)[0] == 200


def test_api_rejects_foreign_host(server):
    assert request(server, 'GET', '/api/state', host='evil.example:80')[0] == 403
    assert request(server, 'GET', '/', host='evil.example')[0] == 403


def test_api_serves_interface_and_validates_input(server):
    status, body = request(server, 'GET', '/', token=False)
    assert status == 200 and b'NactionX Downloader' in body
    status, body = request(server, 'POST', '/api/settings', {'values': {'concurrency': 'abc'}})
    assert status == 400 and 'número' in json.loads(body)['error']
    status, body = request(server, 'POST', '/api/add', {'items': [{'url': 'https://example.com/v'}], 'options': {'container': 'exe'}})
    assert status == 400
    status, body = request(server, 'POST', '/api/add', {'items': [{'url': 'https://example.com/v'}], 'options': {}})
    assert status == 200 and json.loads(body)['added'] == 1
    status, body = request(server, 'POST', '/api/open', {'path': 'C:\\Windows\\notepad.exe', 'mode': 'file'})
    assert status == 403, 'solo se abren archivos descargados por la app'
