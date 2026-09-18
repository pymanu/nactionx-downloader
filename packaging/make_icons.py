"""Genera los iconos de NactionX Downloader (PNG, ICO para Windows e ICNS para macOS) con Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'packaging' / 'icons'
TOP, BOTTOM = (139, 125, 255), (91, 73, 240)


def mark(size):
    """Cuadrado redondeado con degradado y flecha de descarga, dibujado a 2x para suavizar bordes."""
    scale = 2
    s = size * scale
    gradient = Image.new('RGB', (s, s))
    pixels = gradient.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * (s - 1))
            pixels[x, y] = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.225), fill=255)
    icon = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    icon.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    width = int(s * 0.088)
    white = (255, 255, 255, 255)
    radius = width / 2

    def dot(px, py):
        draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=white)

    def stroke(points):
        draw.line(points, fill=white, width=width, joint='curve')
        for px, py in points:
            dot(px, py)

    tip = (s * 0.5, s * 0.64)
    stroke([(s * 0.5, s * 0.22), tip])
    stroke([(s * 0.31, s * 0.45), tip])
    stroke([(s * 0.69, s * 0.45), tip])
    stroke([(s * 0.285, s * 0.785), (s * 0.715, s * 0.785)])
    return icon.resize((size, size), Image.LANCZOS)


def mac_canvas(size=1024):
    """macOS espera margen alrededor del icono (824 px de 1024) y una sombra suave."""
    inner = int(size * 824 / 1024)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    offset = (size - inner) // 2
    ImageDraw.Draw(shadow).rounded_rectangle((offset, offset + size * 0.012, offset + inner, offset + inner + size * 0.012),
                                             radius=int(inner * 0.225), fill=(0, 0, 0, 90))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(size * 0.012)))
    canvas.alpha_composite(mark(inner), (offset, offset))
    return canvas


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    master = mark(1024)
    master.save(OUT / 'icon.png')
    master.resize((256, 256), Image.LANCZOS).save(ROOT / 'nactionx' / 'web' / 'icon.png')
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    master.save(OUT / 'icon.ico', sizes=[(n, n) for n in sizes])
    master.save(ROOT / 'nactionx' / 'web' / 'icon.ico', sizes=[(n, n) for n in sizes])
    mac = mac_canvas(1024)
    mac.save(OUT / 'icon-macos.png')
    try:
        mac.save(OUT / 'icon.icns')
    except Exception as e:  # en CI de macOS se puede generar con iconutil
        print('ICNS no generado con Pillow:', e)
    print('Iconos generados en', OUT)


if __name__ == '__main__':
    main()
