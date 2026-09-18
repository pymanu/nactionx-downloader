import yt_dlp
from yt_dlp.utils import FormatSorter

from nactionx import formats


def fmt(fid, ext, vcodec, height, width=None, fps=30, tbr=1000):
    return {'format_id': fid, 'ext': ext, 'vcodec': vcodec, 'acodec': 'none', 'height': height,
            'width': width or height * 16 // 9, 'fps': fps, 'tbr': tbr, 'protocol': 'https', 'url': 'x'}


def best(sort, fmts):
    sorter = FormatSorter(yt_dlp.YoutubeDL({'quiet': True}), sort)
    return sorted(fmts, key=sorter.calculate_preference)[-1]['format_id']


def test_maxima_prefers_resolution_over_container():
    """A01: con MP4, un 1080p MP4 le ganaba a un 2160p WEBM."""
    candidates = [fmt('mp4-1080', 'mp4', 'avc1.640028', 1080, fps=60, tbr=5000),
                  fmt('webm-2160', 'webm', 'vp9', 2160, fps=60, tbr=20000)]
    assert best(formats.video_selection('best', 'mp4', 'auto')['format_sort'], candidates) == 'webm-2160'


def test_container_breaks_ties_at_same_resolution():
    candidates = [fmt('webm-1080', 'webm', 'vp9', 1080, tbr=3000), fmt('mp4-1080', 'mp4', 'avc1', 1080, tbr=2500)]
    assert best(formats.video_selection('best', 'mp4', 'auto')['format_sort'], candidates) == 'mp4-1080'


def test_quality_cap_is_respected():
    candidates = [fmt('webm-2160', 'webm', 'vp9', 2160), fmt('mp4-1080', 'mp4', 'avc1', 1080)]
    assert best(formats.video_selection('1080', 'mp4', 'auto')['format_sort'], candidates) == 'mp4-1080'


def test_fps_beats_container():
    candidates = [fmt('mp4-1080-30', 'mp4', 'avc1', 1080, fps=30), fmt('webm-1080-60', 'webm', 'vp9', 1080, fps=60)]
    assert best(formats.video_selection('best', 'mp4', 'auto')['format_sort'], candidates) == 'webm-1080-60'


def test_h264_preference_at_same_resolution():
    candidates = [fmt('av1', 'mp4', 'av01.0.08M.08', 1080, tbr=2000), fmt('h264', 'mp4', 'avc1.640028', 1080, tbr=4000)]
    assert best(formats.video_selection('best', 'mp4', 'h264')['format_sort'], candidates) == 'h264'


def test_webm_with_h264_is_corrected():
    """A02: WEBM + H.264 hacía fallar ffmpeg."""
    selection = formats.video_selection('best', 'webm', 'h264')
    assert 'vcodec:vp9' in selection['format_sort']
    assert 'vp0?9' in selection['format'] and selection['merge_output_format'] == 'webm'


def test_vertical_video_uses_short_side_and_rounds_fps():
    """C01 y C02: Shorts mostraban «1920p» y 59,94 fps «p59»."""
    info = {'duration': 60, 'formats': [
        {'format_id': 'v', 'width': 1080, 'height': 1920, 'vcodec': 'avc1', 'acodec': 'none', 'fps': 59.94, 'tbr': 3000},
        {'format_id': 'a', 'vcodec': 'none', 'acodec': 'opus', 'abr': 128, 'tbr': 128},
    ]}
    qualities, audio = formats.summarize(info)
    assert qualities[0]['value'] == '1080' and qualities[0]['label'] == '1080p60'
    assert audio == 128 * 60 * 125


def test_audio_size_estimates():
    """C12: FLAC y WAV se estimaban con el tamaño del audio original."""
    assert formats.estimate_audio('mp3', '320', 60, 0) == 2_400_000
    assert formats.estimate_audio('wav', '320', 60, 0) == 11_520_000
    assert formats.estimate_audio('flac', '320', 60, 1000) > 1000 * 100
    assert formats.estimate_audio('original', '320', 60, 777) == 777
