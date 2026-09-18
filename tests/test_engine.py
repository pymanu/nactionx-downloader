import os

import yt_dlp

from nactionx import engine, settings


class FakeComponents:
    def ffmpeg_location(self):
        return None

    def js_runtimes(self):
        return {}


class FakeContext:
    components = FakeComponents()

    def __init__(self, folder):
        self.snapshot = {**settings.defaults(), 'folder': str(folder)}

    def settings_snapshot(self):
        return dict(self.snapshot)

    def flag(self, job_id):
        return None

    def reserve_name(self, job, folder, name):
        return name

    def log(self, *args):
        pass

    def touch(self):
        pass

    def bump_progress(self):
        pass


def make_job(folder, **options):
    return {'id': 'j1', 'url': 'https://example.com/v', 'title': 't', 'uploader': '', 'duration': None, 'thumbnail': '',
            'status': 'starting', 'phase': '', 'progress': 0.0, 'speed': 0, 'eta': None, 'downloaded': 0, 'total': 0,
            'filepath': '', 'note': '', 'format_label': '', 'subfolder': '', 'custom_name': options.pop('custom_name', ''),
            'outname': '', 'outname_for': '', 'outdir': '',
            'options': {**settings.job_options({}, {**settings.defaults(), 'folder': str(folder)}), **options}}


def filename_for(tmp_path, folder_depth=3, **options):
    folder = tmp_path.joinpath(*(['carpeta-con-un-nombre-bastante-largo'] * folder_depth))
    folder.mkdir(parents=True)
    job = make_job(folder, **options)
    download = engine.Download(job, FakeContext(folder))
    opts, _pps, *_ = download.build(str(folder))
    info = {'id': 'abc', 'title': 'Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film', 'ext': 'mp4'}
    with yt_dlp.YoutubeDL({**opts, 'logger': None, 'quiet': True}) as ydl:
        return folder, ydl.prepare_filename(info)


def test_long_destination_folder_does_not_truncate_name(tmp_path):
    """El límite de longitud se aplicaba a la ruta completa y cortaba el título y el sufijo de recorte."""
    folder, path = filename_for(tmp_path, start='0:00', end='0:03')
    assert len(str(folder)) + len(os.path.basename(path)) > 180, 'la ruta debe superar el límite antiguo'
    assert os.path.dirname(path) == str(folder)
    assert os.path.basename(path) == 'Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film (recorte 00m00s-00m03s).mp4'


def test_custom_name_is_used_as_is(tmp_path):
    _, path = filename_for(tmp_path, folder_depth=2, custom_name='Mi 100% vídeo')
    assert os.path.basename(path) == 'Mi 100% vídeo.mp4'


def test_very_long_titles_are_limited(tmp_path):
    folder = tmp_path / 'dl'
    folder.mkdir()
    job = make_job(folder)
    opts, *_ = engine.Download(job, FakeContext(folder)).build(str(folder))
    with yt_dlp.YoutubeDL({**opts, 'logger': None, 'quiet': True}) as ydl:
        path = ydl.prepare_filename({'id': 'x', 'title': 'T' * 400, 'ext': 'mp4'})
    assert len(os.path.splitext(os.path.basename(path))[0]) <= 150
