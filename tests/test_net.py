import ssl
import sys

import pytest

from nactionx import components, net, updates


@pytest.fixture(autouse=True)
def _fresh_context(monkeypatch):
    """El contexto se cachea a propósito: cada test parte de cero."""
    monkeypatch.setattr(net, '_context', None)
    monkeypatch.setattr(net, '_source', '')


def test_context_loads_a_certificate_bundle():
    """Sin certificados cargados a mano, macOS falla con CERTIFICATE_VERIFY_FAILED en todo."""
    context = net.context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.cert_store_stats()['x509_ca'] > 0
    assert net.source() == 'certifi'


def test_context_is_reused():
    assert net.context() is net.context()


class _SinCA:
    """Contexto sin ninguna autoridad cargada: lo que ve la app empaquetada en un Mac."""

    def __init__(self):
        self.cargados = []

    def load_verify_locations(self, path):
        self.cargados.append(path)

    def cert_store_stats(self):
        return {'x509_ca': len(self.cargados)}


def _sin_certifi(monkeypatch):
    monkeypatch.setitem(sys.modules, 'certifi', None)   # `certifi.where()` dejará de existir


def test_system_bundle_when_certifi_is_missing(monkeypatch, tmp_path):
    """Si el paquete no viajara dentro de la app, aún queda el almacén del sistema."""
    bundle = tmp_path / 'cert.pem'
    bundle.write_bytes(b'')
    monkeypatch.setattr(net, 'SYSTEM_BUNDLES', (str(tmp_path / 'no-existe.pem'), str(bundle)))
    _sin_certifi(monkeypatch)
    context = _SinCA()
    assert net._load(context) == str(bundle)
    assert context.cargados == [str(bundle)]


def test_without_any_bundle_the_app_says_so(monkeypatch, tmp_path):
    """Sin certificados, Ajustes → Motor tiene que avisar en lugar de fallar en silencio."""
    monkeypatch.setattr(net, 'SYSTEM_BUNDLES', (str(tmp_path / 'no-existe.pem'),))
    _sin_certifi(monkeypatch)
    assert net._load(_SinCA()) == ''

    monkeypatch.setattr(net, 'source', lambda: '')
    issues = components.Components.status(_ComponentesFalsos())['issues']
    assert any('certificados' in i for i in issues), issues


class _ComponentesFalsos:
    ffmpeg = ffprobe = deno = 'x'
    node = None
    ffmpeg_source = deno_source = node_source = 'incluido'
    versions = {'ffmpeg': '8.1.1', 'deno': '2.0'}
    update = {'state': 'idle'}


def test_update_check_goes_through_net(monkeypatch):
    """Era el fallo real: updates.py usaba urllib directamente y en macOS no conectaba nunca."""
    visto = {}

    class _Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"tag_name": "v9.9.9"}'

    def fake_urlopen(request, timeout=30):
        visto['url'] = request.full_url
        visto['timeout'] = timeout
        return _Respuesta()

    monkeypatch.setattr(net, 'urlopen', fake_urlopen)
    monkeypatch.setattr(updates.json, 'load', lambda response: {'tag_name': 'v9.9.9'})
    assert updates.fetch_latest()['tag_name'] == 'v9.9.9'
    assert visto['url'] == updates.LATEST_API and visto['timeout'] == updates.TIMEOUT
