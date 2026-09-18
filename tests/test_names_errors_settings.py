import json

import pytest

from nactionx import errors, names, settings
from nactionx.settings import SettingsError


# ------------------------------------------------------------------ nombres
def test_clean_filename_removes_extension_and_invalid_chars():
    assert names.clean_filename('  Mi video: del zoo?.mp4 ') == 'Mi video del zoo'
    assert names.clean_filename('CON') == '_CON'
    assert names.clean_filename('...') == ''


def test_unique_base_avoids_existing_files_and_reserved_names(tmp_path):
    (tmp_path / 'clip.mp4').write_text('x')
    assert names.unique_base(tmp_path, 'clip') == 'clip (2)'
    assert names.unique_base(tmp_path, 'nuevo', taken={'Nuevo'}) == 'nuevo (2)'


def test_unique_base_ignores_partial_downloads(tmp_path):
    (tmp_path / 'resume.f399.mp4.part').write_text('x')
    assert names.unique_base(tmp_path, 'resume') == 'resume'


def test_rename_never_overwrites(tmp_path):
    a, b = tmp_path / 'a.mp4', tmp_path / 'b.mp4'
    a.write_text('a')
    b.write_text('b')
    new_path = names.rename_file(str(a), 'b')
    assert new_path.endswith('b (2).mp4') and b.read_text() == 'b'
    assert names.rename_file(new_path, 'B (2)').endswith('B (2).mp4')


# ------------------------------------------------------------------ errores
@pytest.mark.parametrize('raw, kind', [
    ('ERROR: [youtube] abc: Sign in to confirm you’re not a bot. Use --cookies', 'auth'),
    ('ERROR: [youtube] aaaaaaaaaaa: This video is unavailable', 'unavailable'),
    ('ERROR: [youtube] x: Private video. Sign in if you have access', 'unavailable'),
    ('HTTP Error 429: Too Many Requests', 'ratelimit'),
    ('<urlopen error [Errno 11001] getaddrinfo failed>', 'network'),
    ('[WinError 32] El proceso no tiene acceso al archivo porque está siendo utilizado por otro proceso', 'locked'),
    ('ERROR: Postprocessing: Conversion failed!', 'format'),
    ('[Errno 28] No space left on device', 'disk'),
    ('Postprocessing: WARNING: unable to obtain file audio codec with ffprobe', 'format'),
])
def test_errors_are_explained(raw, kind):
    message, found, detail = errors.explain(raw)
    assert found == kind and message and detail


def test_unknown_errors_keep_original_text():
    message, kind, _ = errors.explain('ERROR: [generic] algo raro pasó')
    assert kind == 'other' and 'algo raro' in message


def test_retryable_kinds():
    assert {'network', 'ratelimit', 'locked'} == errors.RETRYABLE


# ------------------------------------------------------------------ ajustes
def test_concurrency_validation():
    """A05: un valor no numérico rompía el planificador."""
    with pytest.raises(SettingsError):
        settings.validate({'concurrency': 'abc'})
    assert settings.validate({'concurrency': 99}) == {'concurrency': 8}
    assert settings.validate({'concurrency': '3'}) == {'concurrency': 3}


def test_unknown_and_invalid_values():
    assert settings.validate({'hack': True}) == {}
    with pytest.raises(SettingsError):
        settings.validate({'container': 'exe'})
    with pytest.raises(SettingsError):
        settings.validate({'folder': 'relativa/carpeta'})
    with pytest.raises(SettingsError):
        settings.validate({'proxy': 'ftp://x'})


@pytest.mark.parametrize('template', ['%(title.%(ext)s', '%(title)s', '../%(title)s.%(ext)s', '/abs/%(title)s.%(ext)s'])
def test_invalid_templates_are_rejected(template):
    """B14: una plantilla rota hacía fallar todas las descargas."""
    with pytest.raises(SettingsError):
        settings.validate({'template': template})


def test_valid_template():
    assert settings.validate({'template': '%(uploader)s/%(title)s.%(ext)s'})


def test_corrupt_settings_file_is_sanitized(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'concurrency': 'abc', 'mode': 'audio', 'template': '%(title'}), encoding='utf-8')
    store = settings.Settings(path)
    assert store.get('concurrency') == 2 and store.get('mode') == 'audio'
    assert store.get('template') == '%(title)s.%(ext)s'


def test_trim_validation():
    current = settings.defaults()
    with pytest.raises(SettingsError):
        settings.job_options({'start': '1:30', 'end': '1:00'}, current)
    options = settings.job_options({'start': '0:10', 'end': '0:20', 'mode': 'audio'}, current)
    assert options['start'] == '0:10' and options['mode'] == 'audio'
