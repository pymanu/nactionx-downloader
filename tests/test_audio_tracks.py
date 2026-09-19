import pytest

from nactionx import engine, formats, manager as manager_mod, settings
from nactionx.settings import SettingsError


def audio(language, note, preference=-1, **extra):
    return {'acodec': 'opus', 'vcodec': 'none', 'language': language, 'format_note': note,
            'language_preference': preference, **extra}


# ------------------------------------------------------------------ etiquetas
@pytest.mark.parametrize('code, note, esperado', [
    ('en', 'English original (default), medium', 'Inglés'),
    ('es', 'Spanish, medium', 'Español'),
    ('es-419', 'Spanish (Latin America), medium', 'Español (Latinoamérica)'),
    ('es-ES', 'Spanish (Spain) original (default), medium', 'Español (España)'),
    ('pt-BR', 'Portuguese (Brazil), low', 'Portugués (Brasil)'),
    ('zh-Hant', 'Chinese (Traditional), medium', 'Chino (tradicional)'),
    ('fr', '', 'Francés'),
    ('tlh', 'Klingon, medium', 'Klingon'),   # idioma sin traducir: se usa lo que diga yt-dlp
    (None, '', 'Desconocido'),
])
def test_language_label(code, note, esperado):
    """El paréntesis de la región no se puede perder: distingue doblajes del mismo idioma."""
    assert formats.language_label(code, note) == esperado


# ------------------------------------------------------------------ detección de pistas
def test_tracks_are_listed_with_the_original_first():
    info = {'formats': [
        audio('es', 'Spanish, medium'),
        audio('en', 'English original (default), medium', preference=10),
        audio('de', 'German, low'),
        {'acodec': 'none', 'vcodec': 'avc1', 'language': 'en'},        # vídeo: no es una pista
    ]}
    tracks = formats.audio_tracks(info)
    assert [t['value'] for t in tracks] == ['en', 'de', 'es']
    assert tracks[0] == {'value': 'en', 'label': 'Inglés', 'original': True}
    assert [t['label'] for t in tracks] == ['Inglés', 'Alemán', 'Español']


def test_one_language_means_nothing_to_choose():
    """La interfaz usa la lista vacía para no enseñar el selector."""
    assert formats.audio_tracks({'formats': [audio('en', 'English, medium'), audio('en', 'English, low')]}) == []
    assert formats.audio_tracks({'formats': []}) == []


def test_formats_without_language_are_ignored():
    """La mayoría de plataformas no etiquetan el idioma: no hay nada que elegir."""
    info = {'formats': [audio(None, 'medium'), audio('', 'low'), {'acodec': 'aac', 'vcodec': 'avc1'}]}
    assert formats.audio_tracks(info) == []


# ------------------------------------------------------------------ selección de formato
def test_chosen_track_goes_first_and_keeps_a_fallback():
    """Si ese vídeo no tiene la pista, debe caer al selector de siempre en vez de fallar."""
    fmt = formats.video_selection('best', 'mp4', 'h264', audio_track='es')['format']
    assert fmt == 'bv*+ba[language=es]/bv*+ba/b'
    assert formats.video_selection('best', 'mp4', 'h264')['format'] == 'bv*+ba/b'


def test_webm_keeps_its_codec_filter_when_a_track_is_chosen():
    """WEBM no admite AAC: sin el filtro de códec, la unión falla con «Conversion failed!»."""
    fmt = formats.video_selection('best', 'webm', 'vp9', audio_track='es')['format']
    assert fmt.startswith('bv*[vcodec~="^(vp0?9|av0?1)"]+ba[language=es][acodec~="^(opus|vorbis)"]/')
    assert 'bv*+ba/b' in fmt


def test_audio_only_selection():
    assert formats.audio_only_selection('pt-BR') == 'ba[language=pt-BR]/ba/b'
    assert formats.audio_only_selection() == 'ba/b'


def test_progressive_platforms_ignore_the_track():
    """Instagram y TikTok sirven un archivo único: no hay pistas separadas que elegir."""
    assert formats.video_selection('best', 'mp4', 'h264', progressive=True, audio_track='es')['format'] == 'b/bv*+ba'


# ------------------------------------------------------------------ validación
def test_valid_track_codes():
    current = settings.defaults()
    for code in ('es', 'es-419', 'zh-Hant', 'pt-BR', 'fil'):
        assert settings.job_options({'audio_track': code}, current)['audio_track'] == code
    assert settings.job_options({}, current)['audio_track'] == ''
    assert settings.job_options({'audio_track': '  '}, current)['audio_track'] == ''


@pytest.mark.parametrize('malo', ['es;rm -rf', 'language=es]', '../es', 'e', 'x' * 40, 'es--419'])
def test_invalid_track_codes_are_rejected(malo):
    """El código entra tal cual en el selector de formato de yt-dlp: no puede ser texto libre."""
    with pytest.raises(SettingsError):
        settings.job_options({'audio_track': malo}, settings.defaults())


def test_label_without_note_still_reads_well():
    """Al construir el nombre del archivo solo se tiene el código guardado en el trabajo."""
    assert formats.language_label('es-419') == 'Español (Latinoamérica)'
    assert formats.language_label('zh-Hant') == 'Chino (tradicional)'
    assert formats.language_label('es') == 'Español'


# ------------------------------------------------------------------ cola y nombres
class _FakeComponents:
    def status(self):
        return {'ytdlp': 'test', 'issues': [], 'update': {}}


def test_two_languages_of_one_video_are_not_duplicates(tmp_path):
    """Se descargaba solo la primera: la clave de duplicados no miraba la pista."""
    store = settings.Settings(tmp_path / 'settings.json')
    store.update({'folder': str(tmp_path / 'dl')})
    queue = manager_mod.Manager(store, _FakeComponents(), data_dir=tmp_path, runner=lambda job, m: 0,
                                collection_check=lambda url: False, notifier=lambda t, b: None,
                                autostart=False)
    url = 'https://www.youtube.com/watch?v=Qtl8lJwbd4g'
    item = [{'url': url, 'title': 'Vídeo'}]
    assert queue.add(item, {'mode': 'audio', 'audio_track': 'es'})['added'] == 1
    assert queue.add(item, {'mode': 'audio', 'audio_track': 'de'})['added'] == 1
    repetido = queue.add(item, {'mode': 'audio', 'audio_track': 'de'})
    assert repetido == {'added': 0, 'duplicates': 1}
    assert len(queue.jobs) == 2


def _template(options, job_extra=None):
    job = {'options': options, 'custom_name': '', 'outname': '', **(job_extra or {})}
    download = engine.Download.__new__(engine.Download)
    download.job, download.ctx = job, None
    return download.output_template('/destino')


def test_filename_says_which_track_it_is():
    """Dos idiomas del mismo vídeo daban «Vídeo.mp4» y «Vídeo (2).mp4», imposibles de distinguir."""
    assert _template({'audio_track': 'es'}) == '%(title)s (Español).%(ext)s'
    assert _template({'audio_track': 'es-419'}) == '%(title)s (Español (Latinoamérica)).%(ext)s'
    assert _template({'audio_track': ''}) == '%(title)s.%(ext)s'


def test_track_and_trim_suffixes_live_together():
    template = _template({'audio_track': 'de', 'start': '0:30', 'end': '0:40'})
    assert template == '%(title)s (recorte 00m30s-00m40s) (Alemán).%(ext)s'


def test_a_custom_name_wins_over_both_suffixes():
    assert _template({'audio_track': 'es', 'start': '0:30'}, {'outname': 'Mi nombre'}) == 'Mi nombre.%(ext)s'
