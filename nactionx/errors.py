"""Traduce errores técnicos de yt-dlp, ffmpeg y el sistema a mensajes claros y accionables."""
import re

ANSI = re.compile(r'\x1b\[[0-9;]*m')

# kind: network / ratelimit / locked -> se reintentan solos
RULES = [
    (r"confirm you.?re not a bot|Sign in to confirm",
     'YouTube pide verificar que no eres un bot. En Ajustes → Cuenta, usa las cookies de Firefox o un archivo cookies.txt, o prueba más tarde.', 'auth'),
    (r"confirm your age|age.restricted|inappropriate for some users",
     'Vídeo con restricción de edad. Usa las cookies de un navegador donde tengas la sesión iniciada (Ajustes → Cuenta).', 'auth'),
    (r"members.only|Join this channel|available to this channel's members",
     'Contenido exclusivo para miembros del canal. Necesitas las cookies de una cuenta con acceso.', 'auth'),
    (r"Private video|This video is private", 'Es un vídeo privado.', 'unavailable'),
    (r"Premieres in|will begin in|This live event will begin|is_upcoming",
     'El estreno o directo todavía no ha empezado.', 'live'),
    (r"is a live stream in progress|__LIVE__",
     'Es un directo en curso. Podrás descargarlo cuando termine la emisión.', 'live'),
    (r"copyright|blocked it in your country|not available in your country|geo.restrict",
     'El vídeo está bloqueado en tu país o por derechos de autor.', 'unavailable'),
    (r"Video unavailable|This video is unavailable|has been removed|does not exist|404: Not Found|HTTP Error 404",
     'El vídeo no está disponible (eliminado, privado o bloqueado).', 'unavailable'),
    (r"HTTP Error 429|Too Many Requests|rate.limit",
     'YouTube está limitando las peticiones temporalmente. Se reintentará en unos minutos.', 'ratelimit'),
    (r"HTTP Error 403|403: Forbidden",
     'El servidor rechazó la descarga (403). Actualiza el motor en Ajustes → Motor y vuelve a intentarlo.', 'update'),
    (r"nsig extraction failed|Signature extraction failed|Unable to extract|n challenge|Some formats may be missing|jsc|JS runtime",
     'La plataforma cambió algo y el motor necesita actualizarse (Ajustes → Motor → Actualizar).', 'update'),
    (r"Requested format is not available|No video formats found",
     'La calidad o el formato pedido no está disponible para este vídeo. Prueba con otra calidad.', 'format'),
    (r"Unsupported URL", 'Este enlace no es compatible.', 'unsupported'),
    (r"is not a valid URL|No such file or directory: 'http", 'El enlace no es válido.', 'unsupported'),
    (r"ffmpeg not found|ffprobe.* not found|ffmpeg is not installed",
     'Falta FFmpeg. Reinstala la app o revisa Ajustes → Motor.', 'components'),
    (r"unable to obtain file audio codec|does not contain any stream|no audio stream",
     'Este archivo no tiene pista de audio, así que no se puede extraer el audio. Descárgalo como vídeo.', 'format'),
    (r"Conversion failed|Error opening output file|Invalid data found when processing input",
     'FFmpeg no pudo procesar el archivo. Prueba con otro formato (por ejemplo MKV).', 'format'),
    (r"No space left on device|WinError 112|disk full|__NOSPACE__",
     'No queda espacio suficiente en el disco de destino.', 'disk'),
    (r"WinError 32|being used by another process|Resource busy|Text file busy",
     'Un archivo está en uso por otro programa (¿OneDrive, antivirus o un reproductor?). Se reintentará.', 'locked'),
    (r"WinError 5\b|Permission denied|Access is denied|Operation not permitted|Read-only file system",
     'No hay permiso para escribir en la carpeta de destino. Elige otra carpeta.', 'permission'),
    (r"WinError 206|File name too long|filename is too long",
     'La ruta del archivo es demasiado larga. Usa una carpeta más corta o un nombre más breve.', 'permission'),
    (r"could not find .* cookies database|Failed to decrypt|cookies.*(?:locked|could not copy)|DPAPI",
     'No se pudieron leer las cookies del navegador. En Windows, Chrome y Edge las cifran: usa Firefox o un archivo cookies.txt.', 'auth'),
    (r"getaddrinfo failed|Name or service not known|Failed to resolve|timed out|Connection (?:reset|refused|aborted)|"
     r"Network is unreachable|No route to host|RemoteDisconnected|IncompleteRead|Temporary failure|"
     r"Unable to download (?:webpage|API page)|Remote end closed|SSL: |EOF occurred",
     'Problema de conexión. Se reintentará automáticamente.', 'network'),
]
COMPILED = [(re.compile(p, re.I), msg, kind) for p, msg, kind in RULES]
RETRYABLE = {'network', 'ratelimit', 'locked'}


class FriendlyError(Exception):
    """Error con un mensaje ya pensado para el usuario."""

    def __init__(self, message, kind='other', detail=''):
        super().__init__(message)
        self.message, self.kind, self.detail = message, kind, detail


def clean(text):
    text = ANSI.sub('', str(text or '')).strip()
    text = re.sub(r'^(?:ERROR:\s*)+', '', text)
    return text[:1500]


def explain(error):
    """-> (mensaje para el usuario, tipo, detalle técnico)."""
    if isinstance(error, FriendlyError):
        return error.message, error.kind, error.detail or error.message
    detail = clean(error)
    for rx, message, kind in COMPILED:
        if rx.search(detail):
            return message, kind, detail
    short = re.sub(r'^\[[\w:]+\]\s*[\w-]+:\s*', '', detail)
    return (short[:300] or 'Error desconocido'), 'other', detail
