"""Monta NactionX Downloader para Windows sobre el Python oficial firmado.

Por qué no un .exe propio: Smart App Control (activo por defecto en Windows 11) bloquea ejecutables
sin firma de pago. Esta distribución solo ejecuta binarios firmados o con reputación conocida:
  runtime/  Python embebible oficial (firmado por la Python Software Foundation)
  app/      código de NactionX, FFmpeg de Gyan (8.1.1) y Deno (firmado por Deno Land)

Uso (en Windows): python packaging/build_windows_portable.py [--work C:\\ruta] [--zip]
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nactionx import APP_NAME, __version__  # noqa: E402

PYTHON_VERSION = '3.13.13'
PYTHON_URL = f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip'
FFMPEG_URL = 'https://github.com/GyanD/codexffmpeg/releases/download/8.1.1/ffmpeg-8.1.1-essentials_build.zip'
FFMPEG_SHA256 = '6f58ce889f59c311410f7d2b18895b33c03456463486f3b1ebc93d97a0f54541'  # fijado: versión verificada con Smart App Control
DENO_URL = 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip'
UA = {'User-Agent': 'NactionX-Downloader-build'}


def run(cmd, **kwargs):
    print('>', ' '.join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def fetch(url, dest):
    if dest.exists():
        return dest
    print(f'Descargando {url}', flush=True)
    tmp = dest.with_name(dest.name + '.part')
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as response, open(tmp, 'wb') as out:
        shutil.copyfileobj(response, out, 1024 * 1024)
    tmp.replace(dest)
    return dest


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def authenticode(path, expected_subject):
    """Exige firma Authenticode válida del editor esperado."""
    script = f"$s = Get-AuthenticodeSignature -LiteralPath '{path}'; Write-Output ($s.Status.ToString() + '|' + $s.SignerCertificate.Subject)"
    out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, check=True).stdout.strip()
    status, _, subject = out.partition('|')
    if status != 'Valid' or expected_subject not in subject:
        raise SystemExit(f'Firma no válida en {path}: {out}')
    print(f'  firma válida: {Path(path).name} ({expected_subject})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', default=os.path.join(os.path.expanduser('~'), '.nactionx-dev'),
                        help='Carpeta de trabajo fuera de OneDrive')
    parser.add_argument('--zip', action='store_true', help='Generar también el ZIP portable en releases/')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('Este script genera la versión de Windows y debe ejecutarse en Windows')
    if sys.version_info[:2] != (3, 13) or sys.maxsize <= 2 ** 32:
        raise SystemExit('Usa Python 3.13 de 64 bits para compilar (los paquetes deben coincidir con el Python embebido)')

    work = Path(args.work)
    downloads = work / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    stage = work / 'portable' / APP_NAME
    if stage.exists():
        shutil.rmtree(stage)
    runtime, app = stage / 'runtime', stage / 'app'
    runtime.mkdir(parents=True)

    # 1. Python embebible oficial, con firma verificada
    embed = fetch(PYTHON_URL, downloads / f'python-{PYTHON_VERSION}-embed-amd64.zip')
    with zipfile.ZipFile(embed) as zf:
        zf.extractall(runtime)
    for exe in ('python.exe', 'pythonw.exe', 'python313.dll'):
        authenticode(runtime / exe, 'Python Software Foundation')
    (runtime / 'python313._pth').write_text('python313.zip\n.\nLib\\site-packages\n..\\app\nimport site\n', encoding='utf-8')

    # 2. Dependencias de PyPI. El Python que compila es el mismo que el embebido (3.13, 64 bits), así que
    #    los paquetes coinciden; algunos puros (proxy_tools) solo existen como código fuente.
    site_packages = runtime / 'Lib' / 'site-packages'
    run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-compile', '--target', str(site_packages),
         '-r', str(ROOT / 'requirements.txt')])
    shutil.rmtree(site_packages / 'bin', ignore_errors=True)
    for cache in site_packages.rglob('__pycache__'):
        shutil.rmtree(cache, ignore_errors=True)

    # 3. Código de la app
    shutil.copytree(ROOT / 'nactionx', app / 'nactionx', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', app / 'THIRD_PARTY_NOTICES.md')
    if not (app / 'nactionx' / 'web' / 'icon.ico').exists():
        raise SystemExit('Falta nactionx/web/icon.ico: ejecuta packaging/make_icons.py')

    # 4. Componentes: FFmpeg (hash fijado) y Deno (hash publicado + firma)
    binaries = app / 'bin'
    binaries.mkdir()
    ffmpeg_zip = fetch(FFMPEG_URL, downloads / 'ffmpeg-8.1.1-essentials_build.zip')
    if sha256(ffmpeg_zip) != FFMPEG_SHA256:
        raise SystemExit('El SHA-256 de FFmpeg no coincide con el fijado')
    with zipfile.ZipFile(ffmpeg_zip) as zf:
        for member in zf.infolist():
            name = Path(member.filename).name
            if name in ('ffmpeg.exe', 'ffprobe.exe'):
                with zf.open(member) as src, open(binaries / name, 'wb') as out:
                    shutil.copyfileobj(src, out)
    deno_zip = downloads / 'deno-x86_64-pc-windows-msvc.zip'
    deno_zip.unlink(missing_ok=True)
    fetch(DENO_URL, deno_zip)
    published = urllib.request.urlopen(urllib.request.Request(DENO_URL + '.sha256sum', headers=UA), timeout=60).read().decode()
    if sha256(deno_zip).lower() not in published.lower():
        raise SystemExit('El SHA-256 de Deno no coincide con el publicado')
    with zipfile.ZipFile(deno_zip) as zf:
        zf.extract('deno.exe', binaries)
    authenticode(binaries / 'deno.exe', 'Deno Land')

    # 5. Precompilar para arrancar más rápido y lanzador
    run([sys.executable, '-m', 'compileall', '-q', '-j', '0', str(site_packages), str(app / 'nactionx')])
    (stage / f'{APP_NAME}.cmd').write_text(f'@echo off\r\nstart "" "%~dp0runtime\\pythonw.exe" -m nactionx %*\r\n', encoding='ascii')
    (stage / 'LEEME.txt').write_text(
        f'{APP_NAME} {__version__}\r\n\r\n'
        f'Abre la app con "{APP_NAME}.cmd". Dentro de la app, en Ajustes > Comportamiento, puedes crear accesos directos\r\n'
        'en el escritorio y en el menú Inicio.\r\n\r\n'
        'Esta versión funciona con Smart App Control de Windows 11: solo usa el Python oficial firmado,\r\n'
        'FFmpeg y Deno.\r\n', encoding='utf-8')
    (stage / 'build.json').write_text(json.dumps({'app': __version__, 'python': PYTHON_VERSION, 'ffmpeg': '8.1.1'}), encoding='utf-8')

    size = sum(f.stat().st_size for f in stage.rglob('*') if f.is_file()) / 1e6
    print(f'Listo: {stage} ({size:.0f} MB)')

    if args.zip:
        releases = ROOT / 'releases'
        releases.mkdir(exist_ok=True)
        target = releases / f'NactionX-Downloader-{__version__}-Windows-x64-Portable'
        with tempfile.TemporaryDirectory() as tmp:
            archive = shutil.make_archive(os.path.join(tmp, 'portable'), 'zip', stage.parent, APP_NAME)
            shutil.move(archive, f'{target}.zip')
        print(f'ZIP: {target}.zip ({Path(str(target) + ".zip").stat().st_size / 1e6:.0f} MB)')


if __name__ == '__main__':
    main()
