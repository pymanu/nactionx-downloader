"""Borrado de marcas de agua: sondeo del vídeo, detección, plan, ejecución y verificación.

Este módulo es el que habla con FFmpeg y con el disco. Las cuentas sobre los píxeles están en
`inpaint.py`, y el reparto es a propósito: así los algoritmos se prueban con matrices inventadas, sin
vídeos ni procesos, y aquí queda solo la fontanería.

El recorrido de un vídeo:

    sondear → muestrear → detectar → analizar cada región → (vista previa) → borrar → verificar

El borrado **no** vuelca el vídeo entero por una tubería de Python. FFmpeg recorta la ventana que
rodea a las marcas, solo esa ventana entra aquí, y al final se superpone sobre el vídeo original con
`overlay`. Para una marca de esquina en 1080p son medio megabyte por segundo en lugar de ciento
ochenta, y el resto del fotograma llega al archivo final sin que nadie lo haya tocado.

Lo que **no** puede hacer, dicho aquí para que no haya que descubrirlo usándolo: si la marca es
opaca, tapa detalle y nada se mueve nunca por debajo, esos píxeles no existen en ningún fotograma del
archivo. En ese caso todo lo que hay es una reconstrucción, y una reconstrucción es siempre una
suposición razonable. El informe final lo dice con números en lugar de con adjetivos.
"""
import base64
import collections
import glob
import json
import os
import subprocess
import threading
import time
import uuid

from . import log, names, platform_utils
from .errors import FriendlyError

try:  # Sin NumPy este módulo no puede trabajar, pero la app tiene que arrancar igual y explicarlo.
    import numpy as np

    from . import inpaint
except ImportError:  # pragma: no cover - solo en una instalación incompleta
    np = inpaint = None

logger = log.get('watermark')

VIDEO_EXT = ('.mp4', '.mkv', '.webm', '.mov', '.m4v', '.avi', '.ts', '.m2ts', '.mpg', '.mpeg', '.flv', '.wmv', '.3gp')

DETECT_FRAMES = 28           # fotogramas repartidos por el vídeo para encontrar lo que nunca se mueve
DETECT_WIDTH = 854           # a esta anchura un logotipo sigue teniendo bordes de sobra y cabe en memoria
ANALYSE_FRAMES = 40          # recortes a resolución real para afinar la máscara y medir la mezcla
BURST_FRAMES = 40            # fotogramas seguidos para medir cuánto se mueve la imagen
MOTION_STEPS = (2, 3, 5, 8, 12, 18, 26, 36)
EDGE_MARGIN = 2              # los bordes de una marca se difuminan al comprimir: sin margen queda halo
EXEMPLAR_EVERY = 12          # cada cuántos fotogramas se vuelve a buscar el parche de textura
WINDOW_BUDGET = 224 * 1024 * 1024

QUALITY = {
    'maxima': {'crf': 14, 'preset': 'slow', 'vp9': 24, 'label': 'Máxima'},
    'alta': {'crf': 18, 'preset': 'medium', 'vp9': 30, 'label': 'Alta'},
    'rapida': {'crf': 22, 'preset': 'veryfast', 'vp9': 34, 'label': 'Rápida'},
}
DEFAULT_OPTIONS = {'quality': 'alta', 'tight': True, 'motion': True, 'grain': True}

STRATEGY_LABEL = {
    'movimiento': 'Píxeles originales traídos de otros fotogramas',
    'diferencial': 'Cancelación de la parte fija de la marca',
    'reconstruido': 'Reconstrucción de estructura y textura',
}


def available():
    """(hay NumPy, motivo si no)."""
    if np is None:
        return False, ('Falta el componente NumPy, que es el que hace las cuentas sobre los píxeles. '
                       'Reinstala la app para recuperarlo.')
    return True, ''


def require():
    ok, reason = available()
    if not ok:
        raise FriendlyError(reason, 'components')


def opencv():
    """OpenCV si está instalado (se descarga aparte). Añade flujo óptico denso: movimiento que no es
    un simple desplazamiento, como un zoom o una mano temblando."""
    try:
        import cv2
        return cv2
    except Exception:
        return None


# ------------------------------------------------------------------ sondeo
def _run(args, timeout=120, stdin=None):
    try:
        done = subprocess.run(args, input=stdin, capture_output=True, timeout=timeout,
                              **platform_utils.popen_kwargs())
    except FileNotFoundError:
        raise FriendlyError('No se encontró FFmpeg. Revisa Ajustes → Motor y componentes.', 'components')
    except subprocess.TimeoutExpired:
        raise FriendlyError('FFmpeg tardó demasiado y se ha cancelado.', 'other')
    if done.returncode != 0:
        detail = (done.stderr or b'').decode('utf-8', 'replace').strip()[-600:]
        raise FriendlyError('FFmpeg no pudo leer el vídeo. Puede estar dañado o en un formato raro.',
                            'format', detail)
    return done.stdout


def _fraction(text, fallback=0.0):
    try:
        numerator, _, denominator = str(text or '').partition('/')
        divisor = float(denominator or 1)
        return float(numerator) / divisor if divisor else fallback
    except ValueError:
        return fallback


def _rotation(stream):
    for side in stream.get('side_data_list') or []:
        if 'rotation' in side:
            return int(round(float(side['rotation']))) % 360
    try:
        return int(float((stream.get('tags') or {}).get('rotate') or 0)) % 360
    except (TypeError, ValueError):
        return 0


def probe(path, ffprobe):
    """Todo lo que hay que saber del archivo antes de tocarlo."""
    if not os.path.isfile(path):
        raise FriendlyError('Ese archivo ya no existe en disco.', 'unavailable')
    if not ffprobe:
        raise FriendlyError('No se encontró FFprobe, que es el que lee las propiedades del vídeo. '
                            'Revisa Ajustes → Motor y componentes.', 'components')
    raw = _run([ffprobe, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path])
    try:
        data = json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        raise FriendlyError('No se pudo leer la información del vídeo.', 'format')
    streams = data.get('streams') or []
    video = next((s for s in streams
                  if s.get('codec_type') == 'video' and (s.get('disposition') or {}).get('attached_pic') != 1), None)
    if not video:
        raise FriendlyError('Ese archivo no tiene pista de vídeo, así que no hay ninguna marca que quitar.', 'format')

    rotation = _rotation(video)
    width, height = int(video.get('width') or 0), int(video.get('height') or 0)
    if rotation in (90, 270):
        # Lo que se ve está girado: FFmpeg gira los fotogramas antes de los filtros, así que todas las
        # coordenadas de este módulo (y las que dibuja el usuario) van en esas medidas, no en las del archivo.
        width, height = height, width
    if width < 32 or height < 32:
        raise FriendlyError('El vídeo es demasiado pequeño para trabajar con él.', 'format')

    average = _fraction(video.get('avg_frame_rate'))
    nominal = _fraction(video.get('r_frame_rate'))
    fps = average or nominal or 25.0
    duration = float(data.get('format', {}).get('duration') or video.get('duration') or 0.0)
    frames = int(video.get('nb_frames') or 0) or int(round(duration * fps))
    pixel_format = str(video.get('pix_fmt') or 'yuv420p')
    return {
        'path': path,
        'name': os.path.basename(path),
        'size': os.path.getsize(path),
        'container': os.path.splitext(path)[1].lstrip('.').lower(),
        'codec': str(video.get('codec_name') or ''),
        'profile': str(video.get('profile') or ''),
        'pix_fmt': pixel_format,
        'deep': any(tag in pixel_format for tag in ('10', '12', '16')),
        'width': width, 'height': height,
        'fps': fps,
        'fps_text': str(video.get('avg_frame_rate') or video.get('r_frame_rate') or '25/1'),
        'duration': duration,
        'frames': max(frames, 1),
        # Con fotogramas a intervalos desiguales, superponer por número de fotograma descuadraría el
        # vídeo: se reencoda a ritmo constante y el informe lo dice.
        'variable_fps': bool(nominal and average and abs(nominal - average) / max(nominal, average) > 0.01),
        'rotation': rotation,
        'color': {key: str(video.get(key) or '') for key in
                  ('color_space', 'color_primaries', 'color_transfer', 'color_range')},
        'audio': sum(1 for s in streams if s.get('codec_type') == 'audio'),
        'subtitles': sum(1 for s in streams if s.get('codec_type') == 'subtitle'),
    }


# ------------------------------------------------------------------ lectura de fotogramas
def _even(value):
    return int(value) - (int(value) % 2)


def _chain(region, size, monochrome):
    parts = []
    if region:
        parts.append('crop=%d:%d:%d:%d' % region)
    if size:
        parts.append('scale=%d:%d:flags=bicubic' % size)
    parts.append('format=' + ('gray' if monochrome else 'rgb24'))
    return ','.join(parts)


class Frames:
    """Fotogramas de un vídeo como matrices.

    `region` recorta y `size` reescala, las dos cosas en coordenadas de lo que se ve: FFmpeg aplica
    la rotación del archivo antes que los filtros, así que aquí ya no hay que pensar en ella.
    """

    def __init__(self, path, ffmpeg, out, region=None, size=None, monochrome=False, start=None, count=None):
        self.path, self.ffmpeg = path, ffmpeg
        self.width, self.height = out
        self.channels = 1 if monochrome else 3
        self.stride = self.width * self.height * self.channels
        self.args = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin']
        if start:
            self.args += ['-ss', f'{max(0.0, float(start)):.3f}']
        self.args += ['-i', path]
        if count:
            self.args += ['-frames:v', str(int(count))]
        self.args += ['-an', '-sn', '-dn', '-map', '0:v:0', '-vf', _chain(region, size, monochrome),
                      '-fps_mode', 'passthrough', '-f', 'rawvideo',
                      '-pix_fmt', 'gray' if monochrome else 'rgb24', 'pipe:1']
        self.process = None
        self.errors = collections.deque(maxlen=20)

    def __enter__(self):
        if not self.ffmpeg:
            raise FriendlyError('No se encontró FFmpeg. Revisa Ajustes → Motor y componentes.', 'components')
        self.process = subprocess.Popen(self.args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        **platform_utils.popen_kwargs())
        threading.Thread(target=self._drain, daemon=True, name='wm-read-err').start()
        return self

    def __exit__(self, *_):
        self.close()

    def _drain(self):
        for line in iter(self.process.stderr.readline, b''):
            text = line.decode('utf-8', 'replace').strip()
            if text:
                self.errors.append(text)

    def shape(self):
        return (self.height, self.width) if self.channels == 1 else (self.height, self.width, 3)

    def read(self):
        """Un fotograma, o None cuando se acaba el vídeo."""
        chunks, missing = [], self.stride
        while missing > 0:
            chunk = self.process.stdout.read(missing)
            if not chunk:
                break
            chunks.append(chunk)
            missing -= len(chunk)
        if missing > 0:
            return None
        return np.frombuffer(b''.join(chunks), np.uint8).reshape(self.shape())

    def __iter__(self):
        while True:
            frame = self.read()
            if frame is None:
                return
            yield frame

    def close(self):
        if not self.process:
            return
        try:
            if self.process.poll() is None:
                self.process.kill()
            self.process.stdout.close()
            self.process.wait(timeout=5)
        except Exception:
            pass
        self.process = None

    def problem(self):
        return ' | '.join(self.errors)


def grab(path, ffmpeg, time_point, out, region=None, size=None, monochrome=False):
    """Un solo fotograma en el segundo `time_point`."""
    with Frames(path, ffmpeg, out, region, size, monochrome, start=time_point, count=1) as reader:
        frame = reader.read()
        if frame is None:
            raise FriendlyError('No se pudo leer ese punto del vídeo.', 'format', reader.problem())
        return frame.copy()


def sample_times(info, count):
    """Instantes repartidos por el vídeo, sin los extremos: la primera y la última décima suelen ser
    créditos, fundidos a negro o una carátula, y ahí no se ve nada de lo que hay que medir."""
    duration = max(float(info['duration']), 0.1)
    first, last = duration * 0.06, duration * 0.94
    if count <= 1 or last <= first:
        return [duration * 0.5]
    step = (last - first) / (count - 1)
    return [first + step * i for i in range(count)]


def encode_jpeg(frame, ffmpeg, quality=3):
    """Fotograma -> JPEG. Para la vista previa: la interfaz solo admite `data:` y un PNG de 1080p
    ocupa un megabyte y medio."""
    height, width = frame.shape[:2]
    return _run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'rawvideo',
                 '-pixel_format', 'rgb24', '-video_size', f'{width}x{height}', '-i', 'pipe:0',
                 '-frames:v', '1', '-q:v', str(quality), '-f', 'mjpeg', 'pipe:1'],
                stdin=np.ascontiguousarray(frame, np.uint8).tobytes())


def data_url(payload):
    return 'data:image/jpeg;base64,' + base64.b64encode(payload).decode('ascii')


# ------------------------------------------------------------------ detección
def _persistent_edges(stack):
    """El gradiente que sobrevive a la mediana de todos los fotogramas.

    Una marca de agua está siempre en el mismo sitio con la misma forma, así que sus bordes aparecen
    idénticos en los treinta fotogramas. Los del contenido cambian de sitio y de signo, y la mediana
    se los come. Lo que queda en pie es la marca.
    """
    height, width = stack.shape[1:]
    result = np.zeros((height, width), np.float32)
    for axis in (0, 1):
        per_frame = np.empty(stack.shape, np.float32)
        for index, frame in enumerate(stack):
            per_frame[index] = inpaint.gradients(frame)[axis]
        median = np.median(per_frame, axis=0)
        del per_frame
        result += median * median
    return np.sqrt(result)


def _content_bounds(stack, threshold=14.0):
    """Los límites de la imagen de verdad, sin las bandas negras.

    El borde de una banda negra es un gradiente fortísimo que no cambia nunca, es decir, exactamente
    lo que busca el detector. Sin este recorte, todos los vídeos con bandas salen con una «marca»
    perfecta a lo ancho de la pantalla.
    """
    brightest = stack.max(0)
    rows = np.flatnonzero(brightest.max(1) > threshold)
    cols = np.flatnonzero(brightest.max(0) > threshold)
    height, width = brightest.shape
    if not rows.size or not cols.size:
        return 0, height, 0, width
    return int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1


def _edge_prior(box, width, height):
    """Las marcas viven pegadas a un borde o en una esquina. Algo en mitad de la pantalla suele ser
    contenido: un cartel, un rótulo del propio vídeo, una farola que no se mueve."""
    centre_x = (box[2] + box[3]) / 2.0 / width
    centre_y = (box[0] + box[1]) / 2.0 / height
    distance = min(centre_x, 1 - centre_x, centre_y, 1 - centre_y)
    return 1.0 if distance < 0.2 else (0.8 if distance < 0.3 else 0.55)


def detect(stack, video_size):
    """Encuentra las marcas. `stack` son fotogramas en gris reducidos; devuelve rectángulos en
    coordenadas del vídeo con una confianza de 0 a 1."""
    height, width = stack.shape[1:]
    scale_x, scale_y = video_size[0] / width, video_size[1] / height
    persistent = _persistent_edges(stack)
    top, bottom, left, right = _content_bounds(stack)
    inside = np.zeros((height, width), bool)
    inside[top + 2:max(top + 3, bottom - 2), left + 2:max(left + 3, right - 2)] = True
    if not inside.any():
        return []

    # El suelo se mide sobre el propio vídeo: en un plano fijo casi todo el gradiente persiste y el
    # listón tiene que subir, o el detector marcaría la escena entera.
    floor = float(np.median(persistent[inside]))
    threshold = max(1.3, floor * 4.0 + 0.9)
    strong = (persistent > threshold) & inside
    if strong.sum() < 20:
        return []

    glue = max(2, int(round(width * 0.012)))  # une las letras sueltas de un logotipo en una sola región
    labels = inpaint.label_components(inpaint.dilate(strong, glue))
    area = float(width * height)
    found = []
    for value in np.unique(labels):
        if value == 0:
            continue
        core = strong & (labels == value)
        if core.sum() < 24:
            continue
        box = inpaint.bbox_of(core)
        box_height, box_width = box[1] - box[0], box[3] - box[2]
        if box_height < 6 or box_width < 6:
            continue
        if box_height * box_width > area * 0.34:
            continue
        # Una franja fina de lado a lado es una banda, un borde o un letterbox mal recortado.
        if box_width > width * 0.9 and box_height < height * 0.06:
            continue
        if box_height > height * 0.9 and box_width < width * 0.06:
            continue
        strength = float(persistent[core].mean()) / threshold
        confidence = min(1.0, max(0.0, (strength - 1.0) / 2.5)) * _edge_prior(box, width, height)
        found.append({
            'x': max(0, int(round((box[2] - 2) * scale_x))),
            'y': max(0, int(round((box[0] - 2) * scale_y))),
            'w': min(video_size[0], int(round((box_width + 4) * scale_x))),
            'h': min(video_size[1], int(round((box_height + 4) * scale_y))),
            'confidence': round(confidence, 3),
            'source': 'auto',
        })
    found.sort(key=lambda r: -r['confidence'])
    # El listón alto es deliberado. Una detección de más manda a reconstruir un trozo de imagen que
    # estaba perfecto, y eso se ve; una de menos solo obliga a dibujar el rectángulo a mano.
    return [r for r in found if r['confidence'] >= 0.32][:6]


# ------------------------------------------------------------------ análisis de una región
def clamp_box(region, width, height, minimum=8):
    """Rectángulo del usuario -> rectángulo válido dentro del vídeo."""
    x = max(0, min(int(region.get('x') or 0), width - minimum))
    y = max(0, min(int(region.get('y') or 0), height - minimum))
    w = max(minimum, min(int(region.get('w') or 0), width - x))
    h = max(minimum, min(int(region.get('h') or 0), height - y))
    return {'x': x, 'y': y, 'w': w, 'h': h,
            'confidence': float(region.get('confidence') or 0.0),
            'source': str(region.get('source') or 'manual')[:12]}


def _pad_box(box, width, height, pad):
    x0 = max(0, box['x'] - pad)
    y0 = max(0, box['y'] - pad)
    x1 = min(width, box['x'] + box['w'] + pad)
    y1 = min(height, box['y'] + box['h'] + pad)
    return {'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0}


def refine_mask(crop_stack, inner, tight):
    """Máscara al píxel: el dibujo de la marca, no el rectángulo que la rodea.

    Importa más de lo que parece. Un rectángulo de 300x70 son 21.000 píxeles que hay que recuperar;
    el trazo real de un logotipo son dos mil. Todo lo que quede fuera del trazo es fondo auténtico que
    no hace falta tocar, y no tocarlo es siempre mejor que reconstruirlo bien.
    """
    height, width = crop_stack.shape[1:3]
    rectangle = np.zeros((height, width), bool)
    rectangle[inner[1]:inner[1] + inner[3], inner[0]:inner[0] + inner[2]] = True
    if not tight:
        return rectangle
    persistent = _persistent_edges(inpaint.gray(crop_stack))
    outside = ~inpaint.dilate(rectangle, 4)
    floor = float(np.median(persistent[outside])) if outside.sum() > 40 else float(np.median(persistent))
    strong = (persistent > max(1.3, floor * 4.0 + 0.9)) & rectangle
    mask = inpaint.dilate(strong, EDGE_MARGIN) & rectangle
    # Un trazo demasiado fino suele significar que el ajuste ha fallado (marca muy transparente o muy
    # comprimida). Ante la duda, el rectángulo entero: es más trabajo, no peor resultado.
    if mask.sum() < rectangle.sum() * 0.02:
        return rectangle
    return mask


def measure_motion(path, ffmpeg, window, mask, moment):
    """Cuánto se mueve la imagen alrededor de la marca, y si llega a despejarla.

    `window` y `mask` van en el mismo sistema: la ventana de análisis. Se leen fotogramas *seguidos*,
    no repartidos por el vídeo, porque lo que hay que medir es el movimiento entre vecinos.

    -> (desplazamiento típico por fotograma, fracción de la marca recuperable de 0 a 1).

    La fracción se cuenta **píxel a píxel**, que es como se recupera luego. Despejar del todo una
    marca de 180 px de ancho exigiría un barrido de 180 px y casi nunca pasa; despejar el trazo de
    una letra necesita diez, y eso pasa constantemente. Medirlo como «sí o no» daba siempre que no.
    """
    size = (window['w'], window['h'])
    region = (window['w'], window['h'], window['x'], window['y'])
    weight = (~inpaint.dilate(mask, 6)).astype(np.float32)
    frames = []
    with Frames(path, ffmpeg, size, region, None, True, start=moment, count=BURST_FRAMES) as reader:
        for frame in reader:
            frames.append(frame.astype(np.float32))
    if len(frames) < 6 or not mask.any():
        return 0.0, 0.0
    reference = frames[0]
    covered = np.zeros_like(mask)
    per_frame = 0.0
    for step in MOTION_STEPS:
        if step >= len(frames):
            break
        offset_y, offset_x = inpaint.phase_shift(reference, frames[step], weight)
        per_frame = max(per_frame, (abs(offset_y) + abs(offset_x)) / step)
        covered |= mask & ~inpaint.shift_mask(mask, offset_y, offset_x)
    return per_frame, float(covered.sum()) / float(mask.sum())


def analyse_region(crop_stack, box, window, tight):
    """Estudia una región y prepara lo que necesita el borrado.

    `crop_stack` son los recortes de `window` a resolución real en los instantes muestreados. De ahí
    salen dos cosas que se calculan **una sola vez para todo el vídeo**: la media temporal (donde
    vive la marca, porque es lo único que no cambia nunca) y su relleno.
    """
    inner = (box['x'] - window['x'], box['y'] - window['y'], box['w'], box['h'])
    mask = refine_mask(crop_stack, inner, tight)
    observed = crop_stack.astype(np.float32)
    average = observed.mean(0)
    deviation = observed.std(0)
    del observed
    ring = inpaint.dilate(mask, 10) & ~mask
    sigma = inpaint.noise_sigma(crop_stack[len(crop_stack) // 2].astype(np.float32), mask)
    variation = float(np.median(deviation[mask])) if mask.any() else 0.0
    return {
        'box': box, 'window': window, 'mask': mask,
        'average': average,
        # Más pasadas que de costumbre: esto se resuelve una vez y es la base de todo lo demás.
        'base': inpaint.laplace_fill(average, mask, sweeps=64),
        'variation': round(variation, 2),
        'ring_variation': round(float(np.median(deviation[ring])) if ring.any() else 0.0, 2),
        # Restar la media solo aporta algo si por debajo cambia algo más que el ruido de compresión.
        'differential': bool(variation > max(2.5 * sigma, 3.0)),
        'sigma': sigma,
        'coverage': round(float(mask.sum()) / max(1.0, float(box['w'] * box['h'])), 3),
    }


def plan_of(region, recoverable, motion_pixels):
    """El plan que se le enseña al usuario antes de tocar el archivo. Sin adjetivos de más: si algo
    va a ser una suposición, aquí lo pone."""
    percent = round(recoverable * 100)
    if recoverable >= 0.85:
        return {'strategy': 'movimiento', 'quality': 'excelente',
                'note': f'La imagen se mueve {motion_pixels:.1f} px por fotograma, así que el {percent} % de la '
                        f'marca estuvo a la vista en otros fotogramas. Se traen los píxeles originales.'}
    if recoverable >= 0.30:
        return {'strategy': 'movimiento', 'quality': 'buena',
                'note': f'El {percent} % de la marca se recupera de otros fotogramas con los píxeles originales; '
                        f'el resto se reconstruye.'}
    if region['differential']:
        return {'strategy': 'diferencial', 'quality': 'buena',
                'note': 'La cámara no se mueve, pero por debajo la imagen cambia. Se cancela la parte fija (la '
                        'marca lo es por completo) y se conserva toda la variación real del fondo.'}
    if region['coverage'] < 0.30:
        return {'strategy': 'reconstruido', 'quality': 'buena',
                'note': 'Nada se mueve por debajo. El trazo ocupa un %d %% del rectángulo, así que se reconstruye '
                        'con la estructura y la textura de alrededor.' % round(region['coverage'] * 100)}
    return {'strategy': 'reconstruido', 'quality': 'aceptable',
            'note': 'La marca cubre casi todo el rectángulo y por debajo no cambia nada en todo el vídeo. Esos '
                    'píxeles no existen en ningún fotograma del archivo: lo que salga será una reconstrucción, '
                    'no el original.'}


# ------------------------------------------------------------------ borrado
class Remover:
    """Ejecuta el borrado sobre un archivo. Un objeto por trabajo."""

    def __init__(self, analysis, options, ffmpeg, report=None, cancelled=None, note=None):
        self.info, self.options, self.ffmpeg = analysis['info'], options, ffmpeg
        self.report = report or (lambda *_: None)
        self.cancelled = cancelled or (lambda: False)
        self.note = note or (lambda *_: None)
        self.regions = analysis['regions']
        self.window = self._window(analysis['window'])
        self.tally = collections.Counter()
        self._prepare()

    # -- preparación
    def _window(self, analysed):
        """La ventana que se recorta del vídeo.

        Se parte de la ventana de análisis, **no** de los rectángulos: así las máscaras y los
        coeficientes de la mezcla, que están en coordenadas de aquella, caen siempre dentro de esta.
        Encima se añade sitio para que la búsqueda de movimiento y la de textura tengan de dónde tirar.
        """
        width, height = self.info['width'], self.info['height']
        margin = int(min(max(96, (analysed['w'] + analysed['h']) * 0.35), width * 0.4, height * 0.4))
        window = _pad_box(analysed, width, height, margin)
        # Par: con coordenadas impares, `overlay` sobre 4:2:0 desplaza el croma medio píxel.
        window['x'] -= window['x'] % 2
        window['y'] -= window['y'] % 2
        window['w'] = max(16, _even(min(window['w'] + 2, width - window['x'])))
        window['h'] = max(16, _even(min(window['h'] + 2, height - window['y'])))
        return window

    def _prepare(self):
        window = self.window
        for region in self.regions:
            mask = np.zeros((window['h'], window['w']), bool)
            source = region['mask']
            top = region['window']['y'] - window['y']
            left = region['window']['x'] - window['x']
            height = min(source.shape[0], window['h'] - top)
            width = min(source.shape[1], window['w'] - left)
            mask[top:top + height, left:left + width] = source[:height, :width]
            box = inpaint.bbox_of(mask)
            pad = int(min(max(24, max(box[1] - box[0], box[3] - box[2])), 140))
            region['local'] = (max(0, box[0] - pad), min(window['h'], box[1] + pad),
                               max(0, box[2] - pad), min(window['w'], box[3] + pad))
            y0, y1, x0, x1 = region['local']
            region['window_mask'] = mask
            region['local_mask'] = mask[y0:y1, x0:x1]
            region['ring'] = (inpaint.dilate(region['local_mask'], 10) & ~region['local_mask']).astype(np.float32)
            region['motion_weight'] = (~inpaint.dilate(mask, 8)).astype(np.float32)
            region['exemplar'] = None
            region['exemplar_age'] = 10 ** 9
            # La media y su relleno se midieron sobre la ventana de análisis: aquí se recortan a la
            # ventana de trabajo, que es más grande, para que las coordenadas cuadren fotograma a fotograma.
            offset_y = region['window']['y'] - window['y'] - y0
            offset_x = region['window']['x'] - window['x'] - x0
            region['local_average'] = _place(region['average'], region['local_mask'].shape, offset_y, offset_x, 0.0)
            region['local_base'] = _place(region['base'], region['local_mask'].shape, offset_y, offset_x, 0.0)
        self.sigma = max((region['sigma'] for region in self.regions), default=0.0)
        self.tolerance = max((2.6 * self.sigma) ** 2, 7.0)
        lookahead = max(MOTION_STEPS) if self.options.get('motion', True) else 0
        frame_bytes = window['w'] * window['h'] * 3
        self.lookahead = int(max(0, min(lookahead, WINDOW_BUDGET // max(frame_bytes * 2, 1))))
        self.steps = [s for s in MOTION_STEPS if s <= self.lookahead]
        self.small = max(1, int(round(min(window['w'], window['h']) / 180.0)))

    # -- reparación de un fotograma
    def _motion_fill(self, region, current, refs):
        """Trae de otros fotogramas los píxeles que allí sí estaban a la vista. -> (origen, tomados).

        Píxel a píxel y no todo o nada. La marca está siempre en el mismo sitio de la pantalla, pero
        la imagen no: al moverse, cada fotograma vecino deja al descubierto una parte distinta de lo
        que ahora tapa la marca. Exigir que un solo fotograma la despejara entera era pedir un
        barrido del ancho de la marca, que no ocurre casi nunca; pidiendo la parte que a cada uno le
        toca, basta con que el trazo se mueva su propio grosor.

        Cada fotograma candidato se acepta solo si el anillo de alrededor encaja: si no encaja, el
        movimiento medido es falso y traer de ahí pondría contenido equivocado.
        """
        mask = region['local_mask']
        y0, y1, x0, x1 = region['local']
        height, width = self.window['h'], self.window['w']
        current_small = current.small
        weight_small = region['motion_weight_small']
        current_local = current.gray[y0:y1, x0:x1]
        here = current.rgb[y0:y1, x0:x1].astype(np.float32)
        ring = region['ring']
        source = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
        missing, taken = mask.copy(), np.zeros_like(mask)

        for reference in refs:
            if not missing.any():
                break
            offset_y, offset_x = inpaint.phase_shift(current_small, reference.small, weight_small)
            base_y = int(round(offset_y * self.small))
            base_x = int(round(offset_x * self.small))
            best = None
            for delta_y in (-1, 0, 1):
                for delta_x in (-1, 0, 1):
                    shift_y, shift_x = base_y + delta_y, base_x + delta_x
                    # Recortado, no descartado: si el desplazamiento se sale de la ventana solo por un
                    # lado, la parte que sí cae dentro sirve igual. Exigir que cupiera entera era exigir
                    # que la ventana fuese mucho mayor que el desplazamiento, y entonces no se traía nada.
                    cut = self._overlap(shift_y, shift_x, region)
                    if cut is None:
                        continue
                    top, bottom, left, right = cut
                    candidate = reference.gray[y0 - shift_y + top:y0 - shift_y + bottom,
                                               x0 - shift_x + left:x0 - shift_x + right]
                    # Uno de cada dos píxeles: comprobar si el anillo encaja no necesita más, y esta
                    # comprobación se repite dieciséis veces por fotograma.
                    error = inpaint.weighted_error(current_local[top:bottom:2, left:right:2],
                                                   candidate[::2, ::2], ring[top:bottom:2, left:right:2])
                    if best is None or error < best[0]:
                        best = (error, shift_y, shift_x, cut)
            if best is None or best[0] > self.tolerance:
                continue
            _, shift_y, shift_x, (top, bottom, left, right) = best
            inside = np.zeros_like(mask)
            inside[top:bottom, left:right] = True
            # Lo que en el fotograma de referencia sigue tapado por su propia marca no sirve.
            usable = missing & inside & ~inpaint.shift_mask(mask, shift_y, shift_x)
            if not usable.any():
                continue
            # Desplazamiento entero a propósito: recortar sin interpolar conserva el grano y el
            # detalle exactos. Interpolar medio píxel suavizaría justo lo que hemos venido a salvar.
            patch = np.zeros_like(source)
            patch[top:bottom, left:right] = reference.rgb[y0 - shift_y + top:y0 - shift_y + bottom,
                                                          x0 - shift_x + left:x0 - shift_x + right]
            # Igualar el nivel: entre dos fotogramas separados la exposición cambia, y sin corregirlo
            # el trozo traído se nota como un parche más claro aunque el dibujo encaje perfecto.
            around = (ring > 0) & inside
            if around.sum() > 24:
                patch = patch + (here[around].mean(0) - patch[around].mean(0))
            source[usable] = patch[usable]
            missing &= ~usable
            taken |= usable
        return (source, taken) if taken.any() else (None, None)

    def _overlap(self, shift_y, shift_x, region):
        """Qué parte de la caja local sigue dentro de la ventana al traerla desplazada.

        -> (arriba, abajo, izquierda, derecha) en coordenadas de la caja local, o None si no queda
        nada aprovechable.
        """
        y0, y1, x0, x1 = region['local']
        height, width = self.window['h'], self.window['w']
        top = max(0, shift_y - y0)
        bottom = (y1 - y0) - max(0, (y1 - shift_y) - height)
        left = max(0, shift_x - x0)
        right = (x1 - x0) - max(0, (x1 - shift_x) - width)
        if bottom - top < 8 or right - left < 8:
            return None
        return top, bottom, left, right

    def repair(self, index, current, refs):
        """Un fotograma reparado. Los tres caminos se combinan: cada píxel se arregla con el mejor
        que tenga disponible, no la región entera con uno solo."""
        frame = inpaint.to_float(current)
        grain = self.options.get('grain', True)
        for region in self.regions:
            y0, y1, x0, x1 = region['local']
            local = frame[y0:y1, x0:x1]
            mask = region['local_mask']
            combined = local.copy()
            recovered = None
            if self.steps and refs:
                source, recovered = self._motion_fill(region, current, refs)
                if recovered is not None:
                    combined[recovered] = source[recovered]
                    self.tally['movimiento'] += int(recovered.sum())
            missing = mask if recovered is None else (mask & ~recovered)
            rebuilt = False
            if missing.any():
                if region['differential']:
                    combined = inpaint.subtract_static(combined, region['local_average'],
                                                       region['local_base'], missing)
                    self.tally['diferencial'] += int(missing.sum())
                else:
                    if region['exemplar_age'] >= EXEMPLAR_EVERY:
                        # No en cada fotograma: además de costar, un parche distinto cada vez parpadea.
                        region['exemplar'] = inpaint.find_exemplar(combined, missing)
                        region['exemplar_age'] = 0
                    region['exemplar_age'] += 1
                    combined = inpaint.fill_region(combined, missing, region['exemplar'])
                    self.tally['reconstruido'] += int(missing.sum())
                    rebuilt = True
            repaired = inpaint.blend_seam(local, combined, mask)
            if rebuilt and grain and region['sigma'] > 0.15:
                repaired = inpaint.add_grain(repaired, missing, region['sigma'], seed=index)
            frame[y0:y1, x0:x1] = repaired
        return inpaint.to_bytes(frame)

    # -- codificación
    def encoder_args(self, target, deep):
        info, quality = self.info, QUALITY[self.options.get('quality') or 'alta']
        extension = os.path.splitext(target)[1].lower()
        if extension == '.webm':
            video = ['-c:v', 'libvpx-vp9', '-crf', str(quality['vp9']), '-b:v', '0', '-row-mt', '1',
                     '-deadline', 'good', '-cpu-used', '2', '-pix_fmt', 'yuv420p']
        else:
            video = ['-c:v', 'libx264', '-preset', quality['preset'], '-crf', str(quality['crf']),
                     '-pix_fmt', 'yuv420p10le' if deep else 'yuv420p']
        colour = []
        for flag, key in (('-colorspace', 'color_space'), ('-color_primaries', 'color_primaries'),
                          ('-color_trc', 'color_transfer'), ('-color_range', 'color_range')):
            value = info['color'].get(key)
            if value and value not in ('unknown', 'reserved'):
                colour += [flag, value]
        rate = ['-fps_mode', 'cfr', '-r', info['fps_text']] if info['variable_fps'] else ['-fps_mode', 'passthrough']
        extra = ['-movflags', '+faststart'] if extension in ('.mp4', '.m4v', '.mov') else []
        if info['rotation']:
            # Los píxeles ya salen derechos del filtro: si además se copiara la etiqueta de rotación,
            # el reproductor los giraría una segunda vez.
            extra += ['-metadata:s:v:0', 'rotate=0']
        return video + colour + rate + extra

    def command(self, target, deep):
        window, info = self.window, self.info
        return ([self.ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-nostdin',
                 '-i', info['path'],
                 '-f', 'rawvideo', '-pixel_format', 'rgb24',
                 '-video_size', f'{window["w"]}x{window["h"]}', '-framerate', info['fps_text'], '-i', 'pipe:0',
                 '-filter_complex', f'[0:v][1:v]overlay={window["x"]}:{window["y"]}:format=auto[v]',
                 '-map', '[v]', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0', '-map_chapters', '0',
                 '-c:a', 'copy', '-c:s', 'copy']
                + self.encoder_args(target, deep) + [target])

    # -- ejecución
    def run(self, target):
        try:
            return self._encode(target, self.info['deep'])
        except FriendlyError as first:
            if not self.info['deep']:
                raise
            # No todos los FFmpeg traen x264 de 10 bits. Se reintenta a 8 y se avisa en el informe.
            self.note('El codificador no admitía 10 bits: el vídeo se ha guardado a 8 bits por color.')
            logger.info('Reintento a 8 bits tras fallar 10 bits: %s', first.detail[:200])
            return self._encode(target, False)

    def _encode(self, target, deep):
        window, info = self.window, self.info
        total = info['frames']
        produced, buffer, first = 0, [], 0
        started = time.time()
        writer = subprocess.Popen(self.command(target, deep), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, **platform_utils.popen_kwargs())
        failures = collections.deque(maxlen=30)

        def drain():
            for line in iter(writer.stderr.readline, b''):
                text = line.decode('utf-8', 'replace').strip()
                if text:
                    failures.append(text)

        threading.Thread(target=drain, daemon=True, name='wm-write-err').start()

        def emit(index):
            references = []
            for step in self.steps:
                for candidate in (index - step, index + step):
                    position = candidate - first
                    if 0 <= position < len(buffer):
                        references.append(buffer[position])
            frame = self.repair(index, buffer[index - first], references)
            writer.stdin.write(np.ascontiguousarray(frame, np.uint8).tobytes())

        try:
            with Frames(info['path'], self.ffmpeg, (window['w'], window['h']),
                        (window['w'], window['h'], window['x'], window['y'])) as reader:
                index = -1
                for index, frame in enumerate(reader):
                    if self.cancelled():
                        raise Stop()
                    buffer.append(frame)
                    if len(buffer) > 2 * self.lookahead + 1:
                        buffer.pop(0)
                        first += 1
                    while produced <= index - self.lookahead:
                        emit(produced)
                        produced += 1
                        if produced % 24 == 0:
                            self.report(produced, total, started)
                if index < 0:
                    raise FriendlyError('No se pudo decodificar ningún fotograma del vídeo.', 'format',
                                        reader.problem())
                while produced <= index:
                    emit(produced)
                    produced += 1
            writer.stdin.close()
            code = writer.wait()
            if code != 0:
                raise FriendlyError('FFmpeg no pudo guardar el vídeo final.', 'format', ' | '.join(failures))
        except Stop:
            _kill(writer)
            _remove(target)
            raise
        except BrokenPipeError:
            _kill(writer)
            _remove(target)
            raise FriendlyError('FFmpeg se cerró antes de tiempo al guardar el vídeo.', 'format',
                                ' | '.join(failures))
        except BaseException:
            _kill(writer)
            _remove(target)
            raise
        self.report(total, total, started)
        return produced


class Stop(Exception):
    """Cancelación pedida por el usuario."""


def _place(values, shape, offset_y, offset_x, fill):
    """Recorta/rellena `values` para que encaje en `shape` a partir de (offset_y, offset_x)."""
    out = np.full(shape + values.shape[2:], fill, np.float32)
    y0, x0 = max(0, -offset_y), max(0, -offset_x)
    height = min(values.shape[0] - y0, shape[0] - max(0, offset_y))
    width = min(values.shape[1] - x0, shape[1] - max(0, offset_x))
    if height > 0 and width > 0:
        target_y, target_x = max(0, offset_y), max(0, offset_x)
        out[target_y:target_y + height, target_x:target_x + width] = values[y0:y0 + height, x0:x0 + width]
    return out


def _kill(process):
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    except Exception:
        pass


def _remove(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


# ------------------------------------------------------------------ verificación
def verify(analysis, target, ffmpeg, samples=6):
    """Comprueba el resultado con números en vez de con adjetivos.

    Dos medidas, y las dos importan: cuánto ha bajado la fuerza de los bordes donde estaba la marca
    (si no baja, la marca sigue ahí) y cuánto se parece al original **fuera** de la marca (si baja,
    es que el reencodado ha estropeado el resto del vídeo, que es el error clásico de estas
    herramientas y el que nadie mide).
    """
    info, window = analysis['info'], analysis['window']
    region_args = (window['w'], window['h'], window['x'], window['y'])
    size = (window['w'], window['h'])
    mask = np.zeros((window['h'], window['w']), bool)
    for item in analysis['regions']:
        mask |= item['mask']
    outside = ~inpaint.dilate(mask, 6)

    before_energy, after_energy, fidelity = [], [], []
    for moment in sample_times(info, samples):
        try:
            original = inpaint.to_float(grab(info['path'], ffmpeg, moment, size, region_args))
            result = inpaint.to_float(grab(target, ffmpeg, moment, size, region_args))
        except FriendlyError:
            continue
        before_energy.append(inpaint.edge_energy(original, mask))
        after_energy.append(inpaint.edge_energy(result, mask))
        fidelity.append(inpaint.psnr(original, result, outside))
    if not before_energy:
        return {}
    before = sum(before_energy) / len(before_energy)
    residual = sum(after_energy) / len(after_energy)
    clean = [value for value in fidelity if value != float('inf')]
    return {
        'edge_before': round(before, 2),
        'edge_after': round(residual, 2),
        'edge_drop': round(max(0.0, 1.0 - residual / before) * 100, 1) if before > 0.01 else 0.0,
        'psnr_outside': round(sum(clean) / len(clean), 1) if clean else None,
        'samples': len(before_energy),
    }


# ------------------------------------------------------------------ trabajos
def output_path(source, folder=None):
    """Nunca se sobrescribe el vídeo del usuario: el resultado es un archivo nuevo al lado."""
    directory = folder or os.path.dirname(source)
    base, extension = os.path.splitext(os.path.basename(source))
    name = names.unique_base(directory, f'{base} (sin marca)', glob.escape(extension))
    return os.path.join(directory, name + extension)


def validate_options(raw):
    options = dict(DEFAULT_OPTIONS)
    raw = raw or {}
    quality = str(raw.get('quality') or options['quality'])
    if quality not in QUALITY:
        raise FriendlyError('Calidad de salida no válida.', 'validation')
    options['quality'] = quality
    for key in ('tight', 'motion', 'grain'):
        if key in raw:
            options[key] = bool(raw[key])
    return options


class Studio:
    """Un trabajo cada vez. El borrado exprime la CPU y lanzar dos a la vez solo alarga los dos.

    Guarda además el análisis en memoria: las máscaras y los coeficientes de la mezcla son matrices
    de varios megas que no caben (ni pintan nada) en una respuesta JSON.
    """

    def __init__(self, components, settings):
        self.components, self.settings = components, settings
        self.lock = threading.RLock()
        self.revision = 1
        self.task = None
        self.thread = None
        self.stop = False
        self.entries = collections.deque(maxlen=200)
        self.analysis = None      # {'path', 'mtime', 'regions', 'options', 'info'}
        self.crops = None         # caché de los recortes leídos: (path, mtime, ventana, instantes) -> matriz
        self.outputs = set()

    # -- utilidades
    @property
    def ffmpeg(self):
        return self.components.ffmpeg

    @property
    def ffprobe(self):
        return self.components.ffprobe

    def note(self, message):
        with self.lock:
            self.entries.append({'t': time.time(), 'msg': str(message)[:400]})
            self.revision += 1

    def touch(self, **fields):
        with self.lock:
            if self.task:
                self.task.update(fields)
            self.revision += 1

    def cancelled(self):
        return self.stop

    def state(self, revision=None):
        with self.lock:
            if revision == self.revision:
                return {'rev': self.revision, 'unchanged': True}
            task = dict(self.task) if self.task else None
            return {'rev': self.revision, 'task': task, 'log': list(self.entries)}

    def status(self):
        ok, reason = available()
        cv = opencv()
        return {
            'ready': bool(ok and self.ffmpeg and self.ffprobe),
            'numpy': getattr(np, '__version__', '') if ok else '',
            'opencv': getattr(cv, '__version__', '') if cv else '',
            'ffmpeg': bool(self.ffmpeg),
            'reason': reason or ('' if (self.ffmpeg and self.ffprobe) else
                                 'Falta FFmpeg o FFprobe. Revisa Ajustes → Motor y componentes.'),
            'busy': bool(self.task and self.task.get('status') == 'running'),
            'extensions': list(VIDEO_EXT),
            'qualities': [{'value': key, 'label': value['label']} for key, value in QUALITY.items()],
        }

    def known_paths(self):
        with self.lock:
            return set(self.outputs)

    # -- planificación de trabajos
    def submit(self, kind, worker, title):
        with self.lock:
            if self.task and self.task.get('status') == 'running':
                raise FriendlyError('Ya hay un trabajo en marcha. Espera a que termine o cancélalo.', 'busy')
            self.stop = False
            self.entries.clear()
            self.task = {'id': uuid.uuid4().hex[:10], 'kind': kind, 'status': 'running', 'phase': title,
                         'progress': 0.0, 'eta': None, 'result': None, 'error': '', 'error_detail': '',
                         'started': time.time(), 'finished': None}
            self.revision += 1
            task_id = self.task['id']
        self.thread = threading.Thread(target=self._run, args=(task_id, worker), daemon=True, name=f'wm-{kind}')
        self.thread.start()
        return {'id': task_id}

    def _run(self, task_id, worker):
        try:
            result = worker()
            with self.lock:
                if self.task and self.task['id'] == task_id:
                    self.task.update(status='done', progress=100.0, phase='Listo', result=result,
                                     finished=time.time(), eta=None)
        except Stop:
            with self.lock:
                if self.task and self.task['id'] == task_id:
                    self.task.update(status='canceled', phase='Cancelado', finished=time.time(), eta=None)
        except BaseException as exc:  # noqa: BLE001 - cualquier fallo tiene que llegar a la interfaz
            from . import errors
            message, kind, detail = errors.explain(exc)
            if kind == 'other':
                logger.exception('Fallo en el trabajo de marcas de agua')
            with self.lock:
                if self.task and self.task['id'] == task_id:
                    self.task.update(status='error', phase='Error', error=message, error_detail=detail,
                                     finished=time.time(), eta=None)
        finally:
            with self.lock:
                self.revision += 1

    def cancel(self):
        with self.lock:
            self.stop = True
            self.revision += 1
        return {'ok': True}

    def progress(self, done, total, started):
        if self.stop:
            raise Stop()
        fraction = min(0.999, done / max(1, total))
        elapsed = time.time() - started
        self.touch(progress=round(fraction * 100, 1),
                   eta=int(elapsed / fraction - elapsed) if fraction > 0.02 else None)

    # -- lectura con caché
    def _crop_stack(self, info, window, times):
        key = (info['path'], os.path.getmtime(info['path']), tuple(window.items()), tuple(round(t, 2) for t in times))
        if self.crops and self.crops[0] == key:
            return self.crops[1]
        region = (window['w'], window['h'], window['x'], window['y'])
        frames = np.empty((len(times), window['h'], window['w'], 3), np.uint8)
        for index, moment in enumerate(times):
            if self.stop:
                raise Stop()
            frames[index] = grab(info['path'], self.ffmpeg, moment, (window['w'], window['h']), region)
            self.touch(progress=round(20 + 55 * (index + 1) / len(times), 1))
        self.crops = (key, frames)
        return frames

    def _analysed(self, info, boxes, options):
        """Analiza las regiones pedidas y guarda el resultado con las matrices dentro."""
        window = {'x': min(b['x'] for b in boxes), 'y': min(b['y'] for b in boxes)}
        window['w'] = max(b['x'] + b['w'] for b in boxes) - window['x']
        window['h'] = max(b['y'] + b['h'] for b in boxes) - window['y']
        pad = int(min(max(28, (window['w'] + window['h']) * 0.12), 220))
        window = _pad_box(window, info['width'], info['height'], pad)
        # Con una ventana grande (una marca en mosaico que ocupa el fotograma entero) los fotogramas
        # de muestra se comen la memoria: se leen menos, que para medir una mezcla sigue bastando.
        count = ANALYSE_FRAMES
        while count > 16 and window['w'] * window['h'] * count > 48_000_000:
            count -= 4
        times = sample_times(info, count)
        stack = self._crop_stack(info, window, times)
        regions = [analyse_region(stack, box, window, options['tight']) for box in boxes]
        if self.stop:
            raise Stop()
        self.touch(progress=82.0, phase='Midiendo el movimiento')
        for region in regions:
            if self.stop:
                raise Stop()
            pixels, recoverable = (0.0, 0.0)
            if options['motion']:
                pixels, recoverable = measure_motion(info['path'], self.ffmpeg, window, region['mask'],
                                                     info['duration'] * 0.4)
            region['motion_pixels'] = round(pixels, 2)
            region['recoverable'] = round(recoverable, 3)
            region['plan'] = plan_of(region, recoverable, pixels)
        return {'path': info['path'], 'mtime': os.path.getmtime(info['path']), 'info': info,
                'window': window, 'regions': regions, 'options': options}

    @staticmethod
    def public_region(region):
        """Lo que sí cabe en una respuesta JSON: sin máscaras ni medias, que son matrices de megas."""
        return {**region['box'], 'plan': region['plan'], 'coverage': region['coverage'],
                'motion_pixels': region['motion_pixels'], 'recoverable': region['recoverable'],
                'variation': region['variation'], 'differential': region['differential'],
                'sigma': round(region['sigma'], 2)}

    # -- acciones públicas
    def open(self, path):
        """Sondea el archivo y devuelve el primer fotograma. Rápido: sin detección todavía."""
        require()
        path = os.path.abspath(str(path or ''))
        if os.path.splitext(path)[1].lower() not in VIDEO_EXT:
            raise FriendlyError('Ese archivo no parece un vídeo. Formatos admitidos: '
                                + ', '.join(e.lstrip('.').upper() for e in VIDEO_EXT[:8]) + '…', 'unsupported')
        info = probe(path, self.ffprobe)
        return {'info': info, 'frame': self.frame(path, info['duration'] * 0.35, info)}

    def frame(self, path, moment, info=None, width=1280):
        """Un fotograma como JPEG para la interfaz."""
        require()
        info = info or probe(path, self.ffprobe)
        target_width = min(width, info['width'])
        target_height = _even(round(info['height'] * target_width / info['width'])) or 2
        image = grab(path, self.ffmpeg, max(0.0, float(moment)), (target_width, target_height),
                     None, (target_width, target_height))
        return {'image': data_url(encode_jpeg(image, self.ffmpeg)),
                'width': target_width, 'height': target_height, 'time': round(float(moment), 3)}

    def analyse(self, path, regions, options):
        """Detecta (si no vienen regiones) y estudia cada una. Trabajo de fondo: son varios segundos."""
        require()
        options = validate_options(options)
        info = probe(path, self.ffprobe)

        def work():
            self.touch(phase='Buscando lo que no se mueve', progress=3.0)
            boxes = [clamp_box(r, info['width'], info['height']) for r in (regions or [])]
            if not boxes:
                boxes = self.detect_boxes(info)
            if not boxes:
                return {'info': info, 'regions': [], 'detected': 0,
                        'message': 'No se ha encontrado ninguna marca de agua fija. Si la ves, dibújala a mano '
                                   'sobre el fotograma: el borrado funciona igual.'}
            self.touch(phase='Midiendo la marca a resolución real', progress=18.0)
            analysis = self._analysed(info, boxes, options)
            with self.lock:
                self.analysis = analysis
            return {'info': info, 'detected': len(boxes),
                    'regions': [self.public_region(r) for r in analysis['regions']]}

        return self.submit('analyse', work, 'Analizando el vídeo')

    def detect_boxes(self, info):
        """Pasada de detección: fotogramas reducidos en gris repartidos por todo el vídeo."""
        width = min(DETECT_WIDTH, info['width'])
        height = _even(round(info['height'] * width / info['width'])) or 2
        times = sample_times(info, DETECT_FRAMES)
        stack = np.empty((len(times), height, width), np.float32)
        for index, moment in enumerate(times):
            if self.stop:
                raise Stop()
            stack[index] = grab(info['path'], self.ffmpeg, moment, (width, height), None, (width, height), True)
            self.touch(progress=round(3 + 12 * (index + 1) / len(times), 1))
        return [clamp_box(box, info['width'], info['height'])
                for box in detect(stack, (info['width'], info['height']))]

    def preview(self, path, regions, options, moments=None):
        """Procesa unos pocos fotogramas y devuelve antes y después. Ver es la única forma de decidir."""
        require()
        options = validate_options(options)
        info = probe(path, self.ffprobe)
        boxes = [clamp_box(r, info['width'], info['height']) for r in (regions or [])]
        if not boxes:
            raise FriendlyError('Marca al menos una zona antes de comparar.', 'validation')

        def work():
            self.touch(phase='Preparando la comparación', progress=5.0)
            analysis = self._analysed(info, boxes, options)
            with self.lock:
                self.analysis = analysis
            self.touch(phase='Reparando los fotogramas de muestra', progress=88.0)
            remover = Remover(analysis, options, self.ffmpeg, cancelled=self.cancelled, note=self.note)
            window = remover.window
            region_args = (window['w'], window['h'], window['x'], window['y'])
            shots = []
            for moment in (moments or sample_times(info, 3)):
                if self.stop:
                    raise Stop()
                original = grab(info['path'], self.ffmpeg, moment, (window['w'], window['h']), region_args)
                repaired = remover.repair(0, original, [])
                shots.append({
                    'time': round(moment, 2),
                    'before': data_url(encode_jpeg(original, self.ffmpeg, 2)),
                    'after': data_url(encode_jpeg(repaired, self.ffmpeg, 2)),
                })
            return {'window': window, 'shots': shots,
                    'regions': [self.public_region(r) for r in analysis['regions']],
                    'note': 'La comparación se hace sin mirar los fotogramas vecinos. Cuando la imagen se '
                            'mueve, el resultado final es mejor que esto, nunca peor.'}

        return self.submit('preview', work, 'Preparando la comparación')

    def remove(self, path, regions, options, folder=None):
        """El trabajo de verdad: recorre el vídeo entero y escribe el archivo nuevo."""
        require()
        options = validate_options(options)
        info = probe(path, self.ffprobe)
        boxes = [clamp_box(r, info['width'], info['height']) for r in (regions or [])]
        if not boxes:
            raise FriendlyError('Marca al menos una zona antes de borrar.', 'validation')
        if folder and not os.path.isdir(folder):
            raise FriendlyError('La carpeta de destino no existe.', 'validation')
        target = output_path(path, folder)

        def work():
            self.touch(phase='Midiendo la marca', progress=3.0)
            analysis = self._analysed(info, boxes, options)
            with self.lock:
                self.analysis = analysis
            plans = {region['plan']['strategy'] for region in analysis['regions']}
            self.note('Plan: ' + ', '.join(sorted(STRATEGY_LABEL[p] for p in plans)))
            self.touch(phase='Borrando la marca de todo el vídeo', progress=0.0)
            remover = Remover(analysis, options, self.ffmpeg,
                              report=self.progress, cancelled=self.cancelled, note=self.note)
            if info['variable_fps']:
                self.note(f'El vídeo tenía fotogramas a intervalos desiguales: se ha guardado a '
                          f'{info["fps"]:.3f} fps constantes.')
            frames = remover.run(target)
            self.touch(phase='Comprobando el resultado', progress=99.0, eta=None)
            measurements = verify(analysis, target, self.ffmpeg)
            total = sum(remover.tally.values()) or 1
            with self.lock:
                self.outputs.add(target)
            return {
                'output': target,
                'name': os.path.basename(target),
                'size': os.path.getsize(target) if os.path.isfile(target) else 0,
                'frames': frames,
                'seconds': round(time.time() - (self.task or {}).get('started', time.time()), 1),
                'mix': {STRATEGY_LABEL.get(key, key): round(value * 100 / total) for key, value in remover.tally.items()},
                'checks': measurements,
                'regions': [self.public_region(r) for r in analysis['regions']],
            }

        return self.submit('remove', work, 'Borrando la marca')
