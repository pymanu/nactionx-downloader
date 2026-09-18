"""Reconocimiento de plataformas.

yt-dlp sabe descargar de cientos de webs, pero el resto de la app necesita saber tres cosas antes
de llamarlo: de qué plataforma es un enlace, si apunta a un vídeo suelto o a una colección (perfil,
playlist, canal) y en qué forma canónica conviene dejarlo. Instagram y TikTok añaden parámetros de
seguimiento al compartir y sirven el vídeo y el audio ya unidos en un solo archivo, y las dos cosas
cambian cómo hay que pedirle el enlace a yt-dlp.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

YOUTUBE, INSTAGRAM, TIKTOK = 'youtube', 'instagram', 'tiktok'

LABELS = {YOUTUBE: 'YouTube', INSTAGRAM: 'Instagram', TIKTOK: 'TikTok'}

HOSTS = (
    (YOUTUBE, re.compile(r'(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$', re.I)),
    (INSTAGRAM, re.compile(r'(^|\.)(instagram\.com|instagr\.am|ig\.me)$', re.I)),
    (TIKTOK, re.compile(r'(^|\.)tiktok\.com$', re.I)),
)

# Los enlaces que se comparten desde las apps traen identificadores de sesión que no hacen falta
# para descargar y que ensucian la detección de duplicados en la cola.
TRACKING = re.compile(
    r'^(igsh|igshid|img_index|utm_[\w-]+|_r|_t|_d|is_from_webapp|sender_device|sender_web_id|web_id|'
    r'share_app_id|share_link_id|share_item_id|social_sharing|enter_from|enter_method|refer|referer_url|'
    r'referer_video_id|checksum|share_iid|user_id|region|si|pp|feature|ab_channel)$', re.I)

# Primer segmento de la ruta de Instagram que identifica una publicación concreta, no a una persona.
IG_ITEMS = {'p', 'reel', 'reels', 'tv', 'share', 's'}
IG_RESERVED = IG_ITEMS | {'explore', 'accounts', 'direct', 'about', 'developer', 'legal', 'api', 'challenge'}
# Pestañas dentro de un perfil de Instagram: siguen siendo una colección de ese perfil.
IG_TABS = {'reels', 'tagged', 'saved', 'channel', 'feed'}
TIKTOK_LISTS = {'tag', 'music', 'discover', 'explore', 'foryou'}


def _split(url):
    parts = urlsplit(str(url or '').strip())
    segments = [s for s in parts.path.split('/') if s]
    return parts, segments


def host_of(url):
    return (_split(url)[0].hostname or '').lower()


def platform_of(url):
    host = host_of(url)
    for name, pattern in HOSTS:
        if pattern.search(host):
            return name
    return ''


def label_of(url):
    return LABELS.get(platform_of(url), '')


def progressive(url):
    """Plataformas que sirven un único archivo con vídeo y audio ya unidos.

    Pedirles pistas separadas (`bv*+ba`) no encuentra nada y obliga a yt-dlp a un segundo intento.
    """
    return platform_of(url) in (INSTAGRAM, TIKTOK)


def strip_tracking(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.fullmatch(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def normalize_url(url):
    """Deja el enlace en la forma que mejor entiende yt-dlp."""
    url = str(url or '').strip()
    platform = platform_of(url)
    if platform == YOUTUBE:
        if re.match(r'^https?://(www\.|m\.)?youtube\.com/(@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+)/?$', url):
            url = url.rstrip('/') + '/videos'
        return url
    if platform in (INSTAGRAM, TIKTOK):
        return strip_tracking(url).rstrip('/') or url
    return url


def _youtube_collection(parts, segments):
    if re.search(r'youtube\.com/(playlist\?|@|channel/|c/|user/)', parts.geturl()):
        return True
    query = dict(parse_qsl(parts.query))
    return 'list' in query and 'v' not in query and 'youtu.be' not in (parts.hostname or '')


def _instagram_collection(segments):
    if not segments:
        return False
    head = segments[0].lower()
    if head == 'stories':
        # /stories/<usuario> es el carrete entero; /stories/<usuario>/<id> es una historia suelta.
        return len(segments) == 2
    if head == 'explore':
        return True
    if head in IG_RESERVED:
        return False
    return len(segments) == 1 or segments[1].lower() in IG_TABS


def _tiktok_collection(segments):
    if not segments:
        return False
    head = segments[0].lower()
    if head.startswith('@'):
        # /@usuario es el perfil; /@usuario/video/<id> y /@usuario/photo/<id> son publicaciones.
        return len(segments) == 1
    return head in TIKTOK_LISTS


def looks_like_collection(url):
    """¿El enlace apunta a varios vídeos (playlist, canal o perfil) en lugar de a uno solo?"""
    parts, segments = _split(url)
    platform = platform_of(url)
    if platform == YOUTUBE:
        return _youtube_collection(parts, segments)
    if platform == INSTAGRAM:
        return _instagram_collection(segments)
    if platform == TIKTOK:
        return _tiktok_collection(segments)
    return False


def needs_login(url):
    """Plataformas donde la sesión iniciada es casi obligatoria para ver el contenido."""
    return platform_of(url) == INSTAGRAM


# TikTok responde con una página de verificación a la cabecera por defecto de yt-dlp, y con la página
# normal a la de un navegador. Sin esto, ningún enlace de TikTok se puede ni analizar: falla con
# «Unexpected response from webpage request». Comprobado contra vídeos públicos reales.
BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/140.0.0.0 Safari/537.36')


def request_options(url):
    """Opciones de yt-dlp que dependen de la plataforma del enlace."""
    if platform_of(url) == TIKTOK:
        return {'http_headers': {'User-Agent': BROWSER_UA}}
    return {}
