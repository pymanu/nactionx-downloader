import json
import urllib.error

import pytest

from nactionx import engine, formats, sites, updates
from nactionx.errors import FriendlyError


# ------------------------------------------------------------------ plataformas
@pytest.mark.parametrize('url, expected', [
    ('https://www.youtube.com/watch?v=abc', 'youtube'),
    ('https://youtu.be/abc', 'youtube'),
    ('https://music.youtube.com/watch?v=abc', 'youtube'),
    ('https://www.instagram.com/reel/Cx1/', 'instagram'),
    ('https://instagram.com/p/Cx1/', 'instagram'),
    ('https://www.tiktok.com/@user/video/123', 'tiktok'),
    ('https://vm.tiktok.com/ZM8abc/', 'tiktok'),
    ('https://vimeo.com/123', ''),
    ('https://notinstagram.com.evil.example/p/1', ''),
])
def test_platform_detection(url, expected):
    assert sites.platform_of(url) == expected


@pytest.mark.parametrize('url', [
    'https://www.instagram.com/reel/Cx1/',
    'https://www.instagram.com/p/Cx1/',
    'https://www.instagram.com/stories/alguien/3212/',
    'https://www.tiktok.com/@user/video/123',
    'https://www.tiktok.com/@user/photo/123',
    'https://vm.tiktok.com/ZM8abc/',
    'https://www.youtube.com/watch?v=abc',
])
def test_single_items_are_not_collections(url):
    assert not sites.looks_like_collection(url)


@pytest.mark.parametrize('url', [
    'https://www.instagram.com/usuario/',
    'https://www.instagram.com/usuario/reels/',
    'https://www.instagram.com/stories/usuario/',
    'https://www.instagram.com/explore/tags/gatos/',
    'https://www.tiktok.com/@usuario',
    'https://www.tiktok.com/tag/gatos',
    'https://www.youtube.com/playlist?list=PL123',
    'https://www.youtube.com/@canal',
])
def test_profiles_and_lists_are_collections(url):
    assert sites.looks_like_collection(url)


def test_share_links_lose_their_tracking_parameters():
    """Los mismos vídeos compartidos desde la app traían identificadores distintos y se colaban
    duplicados en la cola."""
    a = sites.normalize_url('https://www.instagram.com/reel/Cx1/?igsh=ABC123&utm_source=ig_web_copy_link')
    b = sites.normalize_url('https://www.instagram.com/reel/Cx1/?igsh=OTRA99')
    assert a == b == 'https://www.instagram.com/reel/Cx1'
    tiktok = sites.normalize_url('https://www.tiktok.com/@u/video/7?is_from_webapp=1&sender_device=pc&_r=1')
    assert tiktok == 'https://www.tiktok.com/@u/video/7'


def test_youtube_channel_gets_its_videos_tab():
    assert sites.normalize_url('https://www.youtube.com/@canal') == 'https://www.youtube.com/@canal/videos'


def test_progressive_platforms():
    assert sites.progressive('https://www.tiktok.com/@u/video/7')
    assert sites.progressive('https://www.instagram.com/reel/Cx1/')
    assert not sites.progressive('https://www.youtube.com/watch?v=abc')


def test_progressive_selection_asks_for_the_whole_file_first():
    """Instagram y TikTok no publican pistas separadas: pedir «bv*+ba» primero solo gasta un intento."""
    selection = formats.video_selection('best', 'mp4', 'h264', progressive=True)
    assert selection['format'].startswith('b/')
    assert formats.video_selection('best', 'mp4', 'h264')['format'] == 'bv*+ba/b'


def test_tiktok_gets_a_browser_user_agent():
    """Con la cabecera por defecto de yt-dlp, TikTok devuelve una página de verificación y no se puede
    analizar ni un solo vídeo. Comprobado contra vídeos públicos reales."""
    headers = sites.request_options('https://www.tiktok.com/@u/video/7')['http_headers']
    assert 'Chrome/' in headers['User-Agent'] and 'Mozilla/5.0' in headers['User-Agent']
    assert sites.request_options('https://www.youtube.com/watch?v=abc') == {}
    assert sites.request_options('https://www.instagram.com/reel/Cx1/') == {}


class _FailingYdl:
    def __init__(self, error):
        self.error = error

    def extract_info(self, url, download=False):
        raise self.error


@pytest.mark.parametrize('url, esperado', [
    ('https://www.tiktok.com/@nasa', 'TikTok no deja listar'),
    ('https://www.instagram.com/nasa/', 'Instagram no deja listar'),
])
def test_profile_links_explain_themselves(url, esperado):
    """Pegar el perfil en lugar de la publicación daba «please report this issue on github»."""
    ydl = _FailingYdl(ValueError('Failed to parse JSON; please report this issue on https://github.com/...'))
    with pytest.raises(FriendlyError) as caught:
        engine.extract(ydl, url, collection=True)
    assert esperado in caught.value.message and caught.value.kind == 'unsupported'


def test_other_failures_keep_their_original_error():
    ydl = _FailingYdl(ValueError('HTTP Error 429: Too Many Requests'))
    for url, collection in [('https://www.youtube.com/@canal', True),
                            ('https://www.tiktok.com/@u/video/7', False)]:
        with pytest.raises(ValueError) as caught:
            engine.extract(ydl, url, collection=collection)
        assert not isinstance(caught.value, FriendlyError)


# ------------------------------------------------------------------ aviso de versión
@pytest.mark.parametrize('candidate, current, newer', [
    ('1.1.0', '1.0.0', True),
    ('v1.1.0', '1.1.0', False),
    ('1.10.0', '1.9.0', True),
    ('1.0.0', '1.1.0', False),
    ('2.0', '1.9.9', True),
])
def test_version_comparison(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_release_notes_become_plain_text():
    notes = updates.trim_notes('## Novedades\n- Instagram y [TikTok](https://x)\n\n<!-- oculto -->\n')
    assert notes == 'Novedades\n- Instagram y TikTok'


def test_asset_for_this_platform(monkeypatch):
    monkeypatch.setattr(updates.sys, 'platform', 'win32')
    assets = [{'name': 'NactionX-Downloader-1.1.0-macOS-arm64.dmg', 'browser_download_url': 'u1', 'size': 1},
              {'name': 'NactionX-Downloader-1.1.0-Windows-x64-Setup.exe', 'browser_download_url': 'u2', 'size': 2}]
    assert updates.pick_asset(assets)['url'] == 'u2'
    monkeypatch.setattr(updates.sys, 'platform', 'darwin')
    monkeypatch.setattr(updates.paths, 'arch_tag', lambda: 'arm64')
    assert updates.pick_asset(assets)['url'] == 'u1'
    assert updates.pick_asset([{'name': 'codigo.zip', 'browser_download_url': 'u3'}]) is None


def _updates_in(tmp_path, monkeypatch, release=None, error=None):
    def fake_fetch():
        if error:
            raise error
        return release
    monkeypatch.setattr(updates, 'fetch_latest', fake_fetch)
    return updates.AppUpdates(tmp_path / 'app_update.json')


def test_newer_release_is_reported_and_remembered(tmp_path, monkeypatch):
    release = {'tag_name': 'v9.9.9', 'name': 'NactionX 9.9.9', 'body': '- Algo nuevo',
               'html_url': 'https://example/9', 'assets': []}
    store = _updates_in(tmp_path, monkeypatch, release=release)
    result = store.check()
    assert result['state'] == 'available' and result['version'] == '9.9.9'
    assert '9.9.9' in result['message']
    # El aviso sobrevive a cerrar la app, sin volver a preguntar a GitHub.
    again = updates.AppUpdates(tmp_path / 'app_update.json')
    assert again.status()['state'] == 'available'


def test_same_version_is_reported_as_current(tmp_path, monkeypatch):
    store = _updates_in(tmp_path, monkeypatch, release={'tag_name': f'v{updates.__version__}'})
    assert store.check()['state'] == 'current'
    assert json.loads((tmp_path / 'app_update.json').read_text(encoding='utf-8'))['found'] == {}


def test_missing_release_is_not_an_alarm(tmp_path, monkeypatch):
    error = urllib.error.HTTPError('u', 404, 'Not Found', {}, None)
    store = _updates_in(tmp_path, monkeypatch, error=error)
    result = store.check()
    assert result['state'] == 'error' and 'Todavía no hay' in result['message']


def test_network_failure_keeps_a_known_update_visible(tmp_path, monkeypatch):
    path = tmp_path / 'app_update.json'
    path.write_text(json.dumps({'checked_at': 0, 'found': {'version': '9.9.9', 'url': 'https://example/9'}}),
                    encoding='utf-8')
    monkeypatch.setattr(updates, 'fetch_latest', lambda: (_ for _ in ()).throw(OSError('sin red')))
    store = updates.AppUpdates(path)
    assert store.check()['state'] == 'available'
