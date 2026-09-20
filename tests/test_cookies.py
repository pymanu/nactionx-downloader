"""Subir un cookies.txt: lo único que sirve cuando la app se usa desde otra máquina."""
import http.client
import json
import os
import stat

import pytest

from nactionx import api, cookies, manager as manager_mod, settings
from nactionx.settings import SettingsError

CAMPOS = ['.youtube.com', 'TRUE', '/', 'TRUE', '2000000000', 'SID', 'valor']
LINEA = '\t'.join(CAMPOS)
SOLO_HTTPONLY = cookies.HTTPONLY + '\t'.join(['.youtube.com', 'TRUE', '/', 'TRUE', '2000000000', 'HSID', 'otro'])


@pytest.fixture
def datos_en(tmp_path, monkeypatch):
    monkeypatch.setattr(cookies.paths, 'data_dir', lambda: tmp_path)
    return tmp_path


# ------------------------------------------------------------------ formato
def test_the_netscape_header_is_added_when_the_export_lacks_it():
    """Sin esa primera línea yt-dlp lanza LoadError, y varias extensiones exportan sin ella."""
    salida = cookies.clean(LINEA)
    assert salida.splitlines()[0] == cookies.HEADER
    assert LINEA in salida


def test_an_existing_header_is_not_duplicated():
    assert cookies.clean(f'{cookies.HEADER}\n{LINEA}').count('Netscape HTTP Cookie File') == 1


def test_httponly_lines_count_as_cookies():
    """Empiezan por # pero no son comentarios: un archivo solo con ellas es válido."""
    assert SOLO_HTTPONLY in cookies.clean(SOLO_HTTPONLY)


def test_windows_line_endings_survive():
    assert cookies.clean(f'{LINEA}\r\n').splitlines()[-1] == LINEA


@pytest.mark.parametrize('texto', ['', '   \n\n', '# solo comentarios\n', 'esto no es un cookies.txt'])
def test_rubbish_is_rejected(texto):
    with pytest.raises(SettingsError):
        cookies.clean(texto)


def test_a_huge_file_is_rejected():
    with pytest.raises(SettingsError):
        cookies.clean(LINEA + '\n' + 'x' * (cookies.MAX_BYTES + 1))


# ------------------------------------------------------------------ escritura
def test_yt_dlp_can_load_what_we_save(datos_en):
    """Lo que importa no es que el formato me parezca bien: es que el motor lo acepte."""
    from yt_dlp.cookies import YoutubeDLCookieJar

    ruta = cookies.save(LINEA)          # sin cabecera: el caso que fallaba
    jar = YoutubeDLCookieJar(str(ruta))
    jar.load()
    assert len(jar) == 1


@pytest.mark.skipif(os.name == 'nt', reason='los permisos POSIX no aplican en Windows')
def test_the_file_is_not_readable_by_other_users(datos_en):
    """Es una sesión iniciada, y el servidor puede tener más cuentas."""
    assert stat.S_IMODE(os.stat(cookies.save(LINEA)).st_mode) == 0o600


def test_discard_only_removes_our_own_copy(datos_en):
    propio = cookies.save(LINEA)
    ajeno = datos_en / 'elegido-por-el-usuario.txt'
    ajeno.write_text(LINEA, encoding='utf-8')

    assert cookies.discard(str(ajeno)) is False
    assert ajeno.exists(), 'un archivo del disco del usuario nunca se borra'
    assert cookies.discard(str(propio)) is True
    assert not propio.exists()


# ------------------------------------------------------------------ API
class _FakeComponents:
    def status(self):
        return {'ytdlp': 'test', 'issues': [], 'update': {}}


def _server(tmp_path):
    store = settings.Settings(tmp_path / 'settings.json')
    store.update({'folder': str(tmp_path / 'dl')})
    queue = manager_mod.Manager(store, _FakeComponents(), data_dir=tmp_path, runner=lambda job, m: 0,
                                collection_check=lambda url: False, notifier=lambda t, b: None,
                                autostart=False)
    srv = api.ApiServer(queue, store, _FakeComponents())
    srv.start()
    return srv


def _post(srv, path, body):
    conn = http.client.HTTPConnection('127.0.0.1', srv.port, timeout=5)
    conn.request('POST', path, body=json.dumps(body),
                 headers={'Host': f'127.0.0.1:{srv.port}', 'Content-Type': 'application/json',
                          'X-NactionX-Token': srv.token})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data or b'{}')


def test_uploading_points_the_engine_at_the_saved_file(datos_en):
    srv = _server(datos_en)
    try:
        code, data = _post(srv, '/api/cookies', {'text': LINEA})
        assert code == 200
        guardado = data['settings']['cookies_file']
        assert guardado == str(cookies.store_path())
        assert os.path.isfile(guardado)
    finally:
        srv.stop()


def test_a_bad_upload_leaves_the_settings_alone(datos_en):
    srv = _server(datos_en)
    try:
        code, data = _post(srv, '/api/cookies', {'text': 'esto no es un cookies.txt'})
        assert code == 400
        assert 'formato' in data['error'].lower()
        assert srv.settings.get('cookies_file') == ''
    finally:
        srv.stop()


def test_clearing_removes_the_uploaded_copy(datos_en):
    """Dejar una sesión iniciada en disco tras pulsar «Quitar» sería una fuga silenciosa."""
    srv = _server(datos_en)
    try:
        _post(srv, '/api/cookies', {'text': LINEA})
        assert cookies.store_path().exists()
        code, data = _post(srv, '/api/cookies-clear', {})
        assert code == 200
        assert data['settings']['cookies_file'] == ''
        assert not cookies.store_path().exists()
    finally:
        srv.stop()
