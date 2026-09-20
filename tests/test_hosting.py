"""Lo que hace falta para servir la app desde un servidor detrás de un proxy."""
import os
import threading

from nactionx import api, manager as manager_mod, settings
from nactionx.__main__ import parse_args


class _FakeComponents:
    def status(self):
        return {'ytdlp': 'test', 'issues': [], 'update': {}}


def _server(tmp_path, **kwargs):
    store = settings.Settings(tmp_path / 'settings.json')
    store.update({'folder': str(tmp_path / 'dl')})
    queue = manager_mod.Manager(store, _FakeComponents(), data_dir=tmp_path, runner=lambda job, m: 0,
                                collection_check=lambda url: False, notifier=lambda t, b: None,
                                autostart=False)
    return api.ApiServer(queue, store, _FakeComponents(), **kwargs)


def test_stopping_a_server_that_never_started_does_not_hang(tmp_path):
    """`shutdown()` espera a que serve_forever confirme; sin start() esa confirmación no llega nunca."""
    server = _server(tmp_path)
    hecho = threading.Event()
    threading.Thread(target=lambda: (server.stop(), hecho.set()), daemon=True).start()
    assert hecho.wait(10), 'stop() se quedó colgado'


def test_port_is_random_by_default(tmp_path):
    server = _server(tmp_path)
    try:
        assert server.port > 0
    finally:
        server.stop()


def test_a_fixed_port_can_be_requested(tmp_path):
    """Un proxy necesita saber a qué puerto hablar; el puerto al azar no le sirve."""
    libre = _server(tmp_path / 'a')
    numero = libre.port
    libre.stop()
    server = _server(tmp_path / 'b', port=numero)
    try:
        assert server.port == numero
    finally:
        server.stop()


def test_port_argument_reaches_the_parser():
    assert parse_args([]).port == 0
    assert parse_args(['--browser', '--port', '8090']).port == 8090


def test_token_is_random_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv('NACTIONX_TOKEN', raising=False)
    a, b = _server(tmp_path / 'a'), _server(tmp_path / 'b')
    try:
        assert a.token != b.token and len(a.token) >= 20
    finally:
        a.stop()
        b.stop()


def test_token_can_be_fixed_for_a_hosted_instance(tmp_path, monkeypatch):
    """Sin esto, la dirección de la app cambia en cada reinicio y el marcador deja de valer."""
    monkeypatch.setenv('NACTIONX_TOKEN', 'un-token-estable-de-pruebas')
    server = _server(tmp_path)
    try:
        assert server.token == 'un-token-estable-de-pruebas'
        assert server.app_url.endswith('#t=un-token-estable-de-pruebas')
    finally:
        server.stop()


def test_it_only_listens_on_loopback(tmp_path):
    """Nunca debe escuchar en 0.0.0.0: quien la exponga tiene que hacerlo con un proxy delante."""
    server = _server(tmp_path)
    try:
        assert server.host == '127.0.0.1'
        assert os.environ.get('NACTIONX_HOST') is None  # no existe forma de cambiarlo por entorno
    finally:
        server.stop()
