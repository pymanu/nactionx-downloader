"""Reconstrucción de píxeles: el trabajo fino del borrado de marcas de agua.

Aquí no hay FFmpeg ni archivos, solo matrices. Lo que entra son fotogramas ya decodificados y lo que
sale son fotogramas reparados, para que cada pieza se pueda probar sola y medir con números.

Hay tres formas de saber qué hay debajo de una marca, de mejor a peor:

1. **Traerlo de otro fotograma** (`plan_motion` + `recover_by_motion`). La marca está siempre en el
   mismo sitio de la pantalla, pero la imagen no: si la cámara se mueve, lo que ahora tapa la marca
   estuvo a la vista unos fotogramas antes o después, en otra posición. Se calcula ese
   desplazamiento y se trae. Son los píxeles de verdad, con su textura y su grano.
2. **Deshacer la mezcla** (`estimate_blend` + `unblend`). Si la marca es semitransparente, lo que se
   ve es `observado = a · fondo + b`, con `a` y `b` fijos para cada píxel. Con suficientes fotogramas
   de fondos distintos se estiman los dos y se invierte la cuenta. También son los píxeles de verdad.
3. **Reconstruirlo** (`find_exemplar` + `fill_region`). Cuando la marca es opaca y nada se mueve, los
   píxeles no existen en ninguna parte y hay que inventarlos: estructura por difusión (Laplace
   multiescala) y textura trasplantada del parche más parecido que haya alrededor.

Encima de cualquiera de las tres va `blend_seam`, que iguala el parche al fotograma en dominio de
gradiente. Sin eso no sirve de nada acertar el contenido: un parche perfecto con un escalón de brillo
de un solo nivel se ve igual, porque el ojo caza el borde, no el relleno.
"""
import numpy as np

EPS = 1e-6


# ------------------------------------------------------------------ utilidades
def to_float(frame):
    """Fotograma uint8 -> float32 en 0..255. Todo el módulo trabaja en float."""
    return np.asarray(frame, dtype=np.float32)


def to_bytes(frame):
    return np.clip(frame, 0.0, 255.0).astype(np.uint8)


def gray(frame):
    """Luminancia Rec.709. Las marcas se ven en luminancia; el croma solo añade ruido."""
    frame = np.asarray(frame, np.float32)
    if frame.ndim == 2:
        return frame
    return frame[..., 0] * 0.2126 + frame[..., 1] * 0.7152 + frame[..., 2] * 0.0722


def box_blur(values, radius):
    """Media en ventana cuadrada en tiempo constante por píxel (sumas acumuladas), separable."""
    out = np.asarray(values, np.float32)
    if radius < 1:
        return out.copy()
    out = out.copy()
    for axis in (0, 1):
        length = out.shape[axis]
        pad = [(0, 0)] * out.ndim
        pad[axis] = (radius, radius)
        cumulative = np.cumsum(np.pad(out, pad, mode='edge'), axis=axis, dtype=np.float32)
        head = list(cumulative.shape)
        head[axis] = 1
        cumulative = np.concatenate([np.zeros(head, np.float32), cumulative], axis=axis)
        high = np.take(cumulative, np.arange(2 * radius + 1, 2 * radius + 1 + length), axis=axis)
        low = np.take(cumulative, np.arange(0, length), axis=axis)
        out = (high - low) / np.float32(2 * radius + 1)
    return out


def dilate(mask, radius):
    """Engorda la máscara. Los bordes de una marca se difuminan con la compresión: sin este margen
    queda un halo del ancho de un píxel que se ve perfectamente en el vídeo final."""
    if radius < 1:
        return np.asarray(mask, bool).copy()
    return box_blur(np.asarray(mask, np.float32), radius) > 0.5 / (2 * radius + 1) ** 2


def erode(mask, radius):
    if radius < 1:
        return np.asarray(mask, bool).copy()
    return box_blur(np.asarray(mask, np.float32), radius) > 1.0 - 0.5 / (2 * radius + 1) ** 2


def gradients(image):
    """Gradiente por diferencias centrales, con el borde repetido. -> (gy, gx)."""
    image = np.asarray(image, np.float32)
    pad = ((1, 1), (1, 1)) + ((0, 0),) * (image.ndim - 2)
    p = np.pad(image, pad, mode='edge')
    return (p[2:, 1:-1] - p[:-2, 1:-1]) * 0.5, (p[1:-1, 2:] - p[1:-1, :-2]) * 0.5


def bbox_of(mask):
    """(y0, y1, x0, x1) semiabierto, o None si la máscara está vacía."""
    rows = np.flatnonzero(np.any(mask, axis=1))
    cols = np.flatnonzero(np.any(mask, axis=0))
    if not rows.size or not cols.size:
        return None
    return int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1


def label_components(mask, max_passes=600):
    """Etiqueta las islas conectadas propagando el índice mayor. Un par de docenas de pasadas bastan
    para las manchas compactas que deja una marca; el bucle corta en cuanto deja de cambiar."""
    mask = np.asarray(mask, bool)
    height, width = mask.shape
    labels = np.where(mask, np.arange(1, height * width + 1, dtype=np.int32).reshape(height, width), 0)
    for _ in range(max_passes):
        p = np.pad(labels, 1)
        grown = np.maximum.reduce([labels, p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:],
                                   p[:-2, :-2], p[:-2, 2:], p[2:, :-2], p[2:, 2:]])
        grown = np.where(mask, grown, 0)
        if np.array_equal(grown, labels):
            break
        labels = grown
    return labels


def component_boxes(mask, min_pixels=12):
    """-> [(y0, y1, x0, x1, píxeles)] ordenado de mayor a menor."""
    labels = label_components(mask)
    found = []
    for value in np.unique(labels):
        if value == 0:
            continue
        island = labels == value
        count = int(island.sum())
        if count < min_pixels:
            continue
        box = bbox_of(island)
        found.append((box[0], box[1], box[2], box[3], count))
    return sorted(found, key=lambda item: -item[4])


# ------------------------------------------------------------------ difusión (Laplace multiescala)
def _half(values):
    """Suma bloques 2x2. Repite la última fila o columna si la dimensión es impar."""
    if values.shape[0] % 2:
        values = np.concatenate([values, values[-1:]], axis=0)
    if values.shape[1] % 2:
        values = np.concatenate([values, values[:, -1:]], axis=1)
    rows = values[0::2] + values[1::2]
    return rows[:, 0::2] + rows[:, 1::2]


def _double(values, shape):
    return np.repeat(np.repeat(values, 2, axis=0), 2, axis=1)[:shape[0], :shape[1]]


def _diffuse(values, known, sweeps):
    """values: (H, W, C). known: (H, W) con 1 donde el píxel es fiable."""
    unknown = known < 0.5
    if not unknown.any():
        return values
    out = values.copy()
    height, width = known.shape
    if min(height, width) > 4:
        weight = _half(known)
        coarse = _half(values * known[:, :, None])
        guess = _diffuse(coarse / np.maximum(weight, EPS)[:, :, None], (weight > 0).astype(np.float32), sweeps)
        out[unknown] = _double(guess, (height, width))[unknown]
    else:
        total = max(float(known.sum()), EPS)
        out[unknown] = (values * known[:, :, None]).sum((0, 1)) / total
    keep = known[:, :, None] > 0.5
    for _ in range(sweeps):
        p = np.pad(out, ((1, 1), (1, 1), (0, 0)), mode='edge')
        neighbours = 0.25 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:])
        out = np.where(keep, values, neighbours)
    return out


def laplace_fill(image, unknown, sweeps=24, margin=None):
    """Rellena `unknown` resolviendo la ecuación de Laplace con el resto como frontera.

    Se resuelve en pirámide (primero en pequeño, luego se refina) porque iterando solo a tamaño real
    harían falta miles de pasadas para que la información del borde llegue al centro de la mancha.

    Y se resuelve solo alrededor del hueco, no en toda la imagen: lo que pasa a cien píxeles del
    borde no cambia el resultado de forma apreciable y sí multiplica el tiempo por fotograma.
    """
    image = np.asarray(image, np.float32)
    unknown = np.asarray(unknown, bool)
    if not unknown.any():
        return image.copy()
    out = image.copy()
    box = bbox_of(unknown)
    if margin is None:
        # Estrecho a propósito: la solución dentro del hueco la manda el borde inmediato, y ampliar el
        # recorte solo multiplica el tiempo por fotograma sin cambiar un nivel el resultado.
        margin = int(min(max(8, (box[1] - box[0] + box[3] - box[2]) // 10), 48))
    height, width = unknown.shape
    y0, y1 = max(0, box[0] - margin), min(height, box[1] + margin)
    x0, x1 = max(0, box[2] - margin), min(width, box[3] + margin)
    crop = out[y0:y1, x0:x1]
    filled = _diffuse(crop if crop.ndim == 3 else crop[:, :, None],
                      (~unknown[y0:y1, x0:x1]).astype(np.float32), sweeps)
    out[y0:y1, x0:x1] = filled if crop.ndim == 3 else filled[:, :, 0]
    return out


def blend_seam(frame, patch, mask, sweeps=24):
    """Mete `patch` en `frame` dentro de `mask` sin que se vea el borde.

    No se copia el parche tal cual: se le suma un campo de corrección que vale exactamente la
    diferencia entre ambos en la frontera y se difumina hacia dentro. Así el contenido es el del
    parche y el nivel es el del fotograma, que es lo que hace que la costura desaparezca.
    """
    frame = np.asarray(frame, np.float32)
    patch = np.asarray(patch, np.float32)
    mask = np.asarray(mask, bool)
    if not mask.any():
        return frame.copy()
    difference = np.where(mask[:, :, None] if frame.ndim == 3 else mask, 0.0, frame - patch)
    correction = laplace_fill(difference, mask, sweeps)
    out = frame.copy()
    out[mask] = (patch + correction)[mask]
    return out


# ------------------------------------------------------------------ cancelación de la parte fija
def subtract_static(frame, average, base, mask):
    """Quita de `frame`, dentro de `mask`, todo lo que no cambia nunca.

    Una marca de agua aporta **exactamente lo mismo** a todos los fotogramas, así que restar la media
    temporal la cancela entera. No hay nada que estimar y por tanto nada en lo que equivocarse, que
    es justo lo que sí pasa al intentar medir cuánta transparencia tiene: con una marca ancha, el
    amortiguamiento de cualquier estimación del fondo se confunde con la transparencia, y aplicar esa
    ganancia mal medida deja un parche con el contraste torcido, que se ve más que la marca.

    Lo que se conserva es la variación real del fondo, con su textura y su grano. Lo que era fijo se
    sustituye por `base`, el relleno de esa media, calculado una sola vez para todo el vídeo.

    Cuando por debajo no cambia nada, `frame == average` y el resultado es exactamente `base`: el
    mismo relleno que se haría de todos modos. Es decir, nunca empeora.
    """
    frame = np.asarray(frame, np.float32)
    out = frame.copy()
    out[mask] = (base + (frame - average))[mask]
    return out


# ------------------------------------------------------------------ movimiento
def _subpixel(correlation, index, axis):
    """Ajuste parabólico de tres puntos alrededor del pico: da el desplazamiento con decimales."""
    size = correlation.shape[axis]
    before = list(index)
    after = list(index)
    before[axis] = (index[axis] - 1) % size
    after[axis] = (index[axis] + 1) % size
    left, centre, right = correlation[tuple(before)], correlation[tuple(index)], correlation[tuple(after)]
    denominator = left - 2.0 * centre + right
    if abs(denominator) < EPS:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denominator, -1.0, 1.0))


def phase_shift(current, reference, weight=None):
    """Desplazamiento (dy, dx) tal que `warp(reference, dy, dx)` cae encima de `current`.

    Correlación de fase: se queda con la fase y tira la amplitud, así que un cambio de brillo o de
    contraste entre fotogramas no la despista, que es justo lo que pasa con el fundido de un vídeo.

    `weight` apaga zonas al medir. Hay que pasarle la marca apagada: la marca es lo único que NO se
    mueve entre fotogramas, así que si se deja puesta arrastra la correlación hacia cero y el
    movimiento medido sale siempre más pequeño de lo que es.
    """
    current = np.asarray(current, np.float32)
    reference = np.asarray(reference, np.float32)
    height, width = current.shape
    window = np.outer(np.hanning(height), np.hanning(width)).astype(np.float32)
    if weight is not None:
        window = window * np.asarray(weight, np.float32)
    first = np.fft.rfft2((current - current.mean()) * window)
    second = np.fft.rfft2((reference - reference.mean()) * window)
    cross = first * np.conj(second)
    cross /= np.maximum(np.abs(cross), EPS)
    correlation = np.fft.irfft2(cross, s=(height, width))
    peak = np.unravel_index(int(np.argmax(correlation)), correlation.shape)
    offset_y = peak[0] + _subpixel(correlation, peak, 0)
    offset_x = peak[1] + _subpixel(correlation, peak, 1)
    if offset_y > height / 2:
        offset_y -= height
    if offset_x > width / 2:
        offset_x -= width
    return float(offset_y), float(offset_x)


def warp(image, offset_y, offset_x):
    """Desplaza `image` (dy, dx) con interpolación bilineal, repitiendo el borde."""
    image = np.asarray(image, np.float32)
    height, width = image.shape[:2]
    if float(offset_y).is_integer() and float(offset_x).is_integer():
        # Atajo para desplazamientos enteros: ni interpola ni suaviza, y es el caso habitual.
        rows = np.clip(np.arange(height) - int(offset_y), 0, height - 1)
        cols = np.clip(np.arange(width) - int(offset_x), 0, width - 1)
        return image[rows][:, cols]
    rows = np.clip(np.arange(height, dtype=np.float32) - offset_y, 0, height - 1)
    cols = np.clip(np.arange(width, dtype=np.float32) - offset_x, 0, width - 1)
    row0 = np.floor(rows).astype(np.int32)
    col0 = np.floor(cols).astype(np.int32)
    row1 = np.minimum(row0 + 1, height - 1)
    col1 = np.minimum(col0 + 1, width - 1)
    weight_row = (rows - row0)[:, None]
    weight_col = (cols - col0)[None, :]
    if image.ndim == 3:
        weight_row = weight_row[:, :, None]
        weight_col = weight_col[:, :, None]
    top = image[row0][:, col0] * (1 - weight_col) + image[row0][:, col1] * weight_col
    bottom = image[row1][:, col0] * (1 - weight_col) + image[row1][:, col1] * weight_col
    return top * (1 - weight_row) + bottom * weight_row


def shift_mask(mask, offset_y, offset_x):
    """La máscara desplazada, redondeando hacia fuera: en la duda, un píxel se da por tapado."""
    moved = warp(np.asarray(mask, np.float32), offset_y, offset_x)
    return moved > 1e-3


def weighted_error(current, reference, weight):
    """Error cuadrático medio entre dos ventanas mirando solo donde `weight` > 0."""
    total = float(weight.sum())
    if total <= 0:
        return float('inf')
    difference = current - reference
    if difference.ndim == 3:
        difference = difference.mean(2)
    return float((weight * difference * difference).sum() / total)


def refine_shift(current, reference, weight, start=(0.0, 0.0), radius=2):
    """Afina el desplazamiento probando enteros alrededor de `start`. -> (dy, dx, error)."""
    best = (float(start[0]), float(start[1]), float('inf'))
    for delta_y in range(-radius, radius + 1):
        for delta_x in range(-radius, radius + 1):
            candidate_y = round(start[0]) + delta_y
            candidate_x = round(start[1]) + delta_x
            error = weighted_error(current, warp(reference, candidate_y, candidate_x), weight)
            if error < best[2]:
                best = (float(candidate_y), float(candidate_x), error)
    return best


# ------------------------------------------------------------------ reconstrucción espacial
def find_exemplar(image, mask, search=96, step=3):
    """Busca en `image` el trozo más parecido al contorno de `mask` que no esté tapado por ella.

    Devuelve (dy, dx, error) del mejor desplazamiento, o None si no hay ninguno limpio. Dos pasadas,
    gruesa y fina, y todo por rebanadas enteras: interpolar mil candidatos costaba medio segundo por
    fotograma, y el parche que se busca no necesita precisión de medio píxel.
    """
    image = np.asarray(image, np.float32)
    mask = np.asarray(mask, bool)
    box = bbox_of(mask)
    if box is None:
        return None
    ring = dilate(mask, 6) & ~mask
    if ring.sum() < 24:
        return None
    height, width = mask.shape
    box_height, box_width = box[1] - box[0], box[3] - box[2]
    y0, y1 = max(0, box[0] - 6), min(height, box[1] + 6)
    x0, x1 = max(0, box[2] - 6), min(width, box[3] + 6)
    grayscale = gray(image)
    template = grayscale[y0:y1, x0:x1]
    weight = ring[y0:y1, x0:x1].astype(np.float32)

    def cost(delta_y, delta_x, stride):
        if y0 - delta_y < 0 or y1 - delta_y > height or x0 - delta_x < 0 or x1 - delta_x > width:
            return float('inf')
        # Si las cajas no se solapan, las máscaras tampoco: comprobación barata y siempre segura.
        if abs(delta_y) < box_height and abs(delta_x) < box_width:
            return float('inf')
        candidate = grayscale[y0 - delta_y:y1 - delta_y, x0 - delta_x:x1 - delta_x]
        return weighted_error(template[::stride, ::stride], candidate[::stride, ::stride],
                              weight[::stride, ::stride])

    best = None
    for delta_y in range(-search, search + 1, step):
        for delta_x in range(-search, search + 1, step):
            error = cost(delta_y, delta_x, 2)
            if best is None or error < best[2]:
                best = (delta_y, delta_x, error)
    if best is None or best[2] == float('inf'):
        return None
    refined = None
    for delta_y in range(best[0] - step, best[0] + step + 1):
        for delta_x in range(best[1] - step, best[1] + step + 1):
            error = cost(delta_y, delta_x, 1)
            if refined is None or error < refined[2]:
                refined = (delta_y, delta_x, error)
    return refined if refined and refined[2] != float('inf') else None


def fill_region(frame, mask, exemplar=None, detail=6, sweeps=24):
    """Reconstruye lo que tapa `mask`: estructura por difusión y textura del parche de `exemplar`.

    La difusión sola deja un borrón liso que canta muchísimo en cuanto el fondo tiene grano o
    textura. Por eso la baja frecuencia sale de la difusión (que garantiza que el borde encaja) y la
    alta se trasplanta de un trozo real parecido, que es lo que devuelve el aspecto de vídeo.
    """
    frame = np.asarray(frame, np.float32)
    mask = np.asarray(mask, bool)
    if not mask.any():
        return frame.copy()
    structure = laplace_fill(frame, mask, sweeps)
    if exemplar is None:
        return structure
    height, width = mask.shape
    box = bbox_of(mask)
    pad = detail * 2 + 4
    y0, y1 = max(0, box[0] - pad), min(height, box[1] + pad)
    x0, x1 = max(0, box[2] - pad), min(width, box[3] + pad)
    delta_y, delta_x = int(exemplar[0]), int(exemplar[1])
    if y0 - delta_y < 0 or y1 - delta_y > height or x0 - delta_x < 0 or x1 - delta_x > width:
        return structure
    source = frame[y0 - delta_y:y1 - delta_y, x0 - delta_x:x1 - delta_x]
    local = structure[y0:y1, x0:x1]
    candidate = np.clip(box_blur(local, detail) + (source - box_blur(source, detail)), 0.0, 255.0)
    inside = mask[y0:y1, x0:x1]
    structure[y0:y1, x0:x1] = np.where(inside[:, :, None] if local.ndim == 3 else inside, candidate, local)
    return structure


# ------------------------------------------------------------------ grano
def noise_sigma(image, mask, radius=2):
    """Desviación típica del ruido alrededor de `mask`, medida con un paso alto."""
    image = np.asarray(image, np.float32)
    ring = dilate(mask, 10) & ~dilate(mask, 2)
    if ring.sum() < 24:
        return 0.0
    grayscale = gray(image)
    high_pass = grayscale - box_blur(grayscale, radius)
    return float(np.sqrt(np.mean(high_pass[ring] ** 2)))


def add_grain(image, mask, sigma, seed=0):
    """Añade ruido de la misma fuerza que el de alrededor.

    Un parche perfectamente limpio dentro de un vídeo con grano se ve como un agujero en calma: la
    marca desaparece y en su sitio queda un rectángulo demasiado liso.
    """
    if sigma <= 0.15:
        return image
    generator = np.random.default_rng(seed)
    noise = generator.normal(0.0, sigma, size=image.shape).astype(np.float32)
    out = image.copy()
    out[mask] = np.clip(image + noise, 0.0, 255.0)[mask]
    return out


# ------------------------------------------------------------------ medida
def psnr(first, second, mask=None):
    """Relación señal/ruido de pico en dB. Por encima de 40 dB la diferencia no se ve."""
    first = np.asarray(first, np.float32)
    second = np.asarray(second, np.float32)
    difference = (first - second) ** 2
    if mask is not None:
        selection = mask if difference.ndim == 2 else np.repeat(mask[:, :, None], difference.shape[2], 2)
        if not selection.any():
            return float('inf')
        error = float(difference[selection].mean())
    else:
        error = float(difference.mean())
    if error <= EPS:
        return float('inf')
    return float(10.0 * np.log10(255.0 * 255.0 / error))


def edge_energy(image, mask):
    """Fuerza media del gradiente dentro de `mask`. Sirve para comprobar que los bordes duros de una
    marca han desaparecido de verdad y no solo se han atenuado."""
    gradient_y, gradient_x = gradients(gray(image))
    magnitude = np.sqrt(gradient_y ** 2 + gradient_x ** 2)
    if not mask.any():
        return 0.0
    return float(magnitude[mask].mean())
