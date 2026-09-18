import hashlib
import io
import json
import subprocess
import sys
import textwrap
import zipfile

from nactionx import components, paths


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_wheel(package, version_text):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(f'{package}/__init__.py', f'__version__ = "{version_text}"\n')
    return buffer.getvalue()


def test_install_update_downloads_and_verifies(tmp_path, monkeypatch):
    """A07: la carpeta de paquetes no existía y la actualización fallaba."""
    monkeypatch.setattr(paths, '_data_dir', tmp_path)
    ytdlp, ejs = fake_wheel('yt_dlp', '2099.1.1'), fake_wheel('yt_dlp_ejs', '9.9.9')
    releases = {
        'https://pypi.org/pypi/yt-dlp/json': {'info': {'version': '2099.1.1', 'requires_dist': ['yt-dlp-ejs==9.9.9; extra == "default"']},
                                               'urls': [{'packagetype': 'bdist_wheel', 'filename': 'yt_dlp-2099.1.1-py3-none-any.whl', 'url': 'w1', 'digests': {'sha256': hashlib.sha256(ytdlp).hexdigest()}}]},
        'https://pypi.org/pypi/yt-dlp-ejs/9.9.9/json': {'info': {'version': '9.9.9'},
                                                         'urls': [{'packagetype': 'bdist_wheel', 'filename': 'yt_dlp_ejs-9.9.9-py3-none-any.whl', 'url': 'w2', 'digests': {'sha256': hashlib.sha256(ejs).hexdigest()}}]},
    }
    blobs = {'w1': ytdlp, 'w2': ejs}

    def fake_open(self, url, timeout=30):
        return FakeResponse(json.dumps(releases[url]).encode() if url in releases else blobs[url])

    monkeypatch.setattr(components.Components, '_open', fake_open)
    comp = components.Components.__new__(components.Components)
    comp.update = {'state': 'idle'}
    import threading
    comp._lock = threading.Lock()
    result = comp.install_update()
    assert result['state'] == 'restart', result
    meta = json.loads((tmp_path / 'components' / 'ytdlp.json').read_text(encoding='utf-8'))
    assert meta['version'] == '2099.1.1' and len(meta['wheels']) == 2

    blobs['w1'] = b'manipulado'
    assert comp.install_update()['state'] == 'error', 'un hash que no coincide se rechaza'


def test_overlay_is_imported_before_bundled_version(tmp_path):
    """Un proceso nuevo importa yt_dlp desde el paquete actualizado."""
    folder = tmp_path / 'components' / 'python'
    folder.mkdir(parents=True)
    (folder / 'yt_dlp-2099.1.1-py3-none-any.whl').write_bytes(fake_wheel('yt_dlp', '2099.1.1'))
    (tmp_path / 'components' / 'ytdlp.json').write_text(json.dumps({'version': '2099.1.1', 'wheels': ['yt_dlp-2099.1.1-py3-none-any.whl']}))
    script = textwrap.dedent('''
        from nactionx import components
        print(components.apply_overlay())
        import yt_dlp
        print(yt_dlp.__version__, yt_dlp.__file__)
    ''')
    env = {**__import__('os').environ, 'NACTIONX_DATA_DIR': str(tmp_path)}
    out = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env, cwd=str(paths.PROJECT_DIR), timeout=60)
    lines = out.stdout.strip().splitlines()
    assert lines[0] == '2099.1.1', out.stderr
    assert lines[1].startswith('2099.1.1') and '.whl' in lines[1]
