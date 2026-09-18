"""Descarga FFmpeg, FFprobe y Deno oficiales para incluirlos en la app, verificando su SHA-256.

Uso: python packaging/fetch_components.py [--platform windows|macos] [--arch x64|arm64]
Resultado: packaging/bin/<plataforma>-<arquitectura>/
"""
import argparse
import fnmatch
import hashlib
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {'User-Agent': 'NactionX-Downloader-build'}
YTDLP_FFMPEG = 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest'
DENO = 'https://github.com/denoland/deno/releases/latest/download'
RIEDL = 'https://ffmpeg.martin-riedl.de/redirect/latest/macos/{arch}/release/{tool}.zip'

SOURCES = {
    ('windows', 'x64'): [
        {'name': 'FFmpeg (compilación de yt-dlp, GPL, librerías compartidas)',
         'url': f'{YTDLP_FFMPEG}/ffmpeg-master-latest-win64-gpl-shared.zip',
         'checksums': f'{YTDLP_FFMPEG}/checksums.sha256',
         'extract': ['*/bin/ffmpeg.exe', '*/bin/ffprobe.exe', '*/bin/*.dll']},
        {'name': 'Deno', 'url': f'{DENO}/deno-x86_64-pc-windows-msvc.zip', 'sha_url_suffix': '.sha256sum',
         'extract': ['deno.exe']},
    ],
    ('macos', 'arm64'): [
        {'name': 'FFmpeg', 'url': RIEDL.format(arch='arm64', tool='ffmpeg'), 'sha_url_suffix': '.sha256', 'extract': ['ffmpeg']},
        {'name': 'FFprobe', 'url': RIEDL.format(arch='arm64', tool='ffprobe'), 'sha_url_suffix': '.sha256', 'extract': ['ffprobe']},
        {'name': 'Deno', 'url': f'{DENO}/deno-aarch64-apple-darwin.zip', 'sha_url_suffix': '.sha256sum', 'extract': ['deno']},
    ],
    ('macos', 'x64'): [
        {'name': 'FFmpeg', 'url': RIEDL.format(arch='amd64', tool='ffmpeg'), 'sha_url_suffix': '.sha256', 'extract': ['ffmpeg']},
        {'name': 'FFprobe', 'url': RIEDL.format(arch='amd64', tool='ffprobe'), 'sha_url_suffix': '.sha256', 'extract': ['ffprobe']},
        {'name': 'Deno', 'url': f'{DENO}/deno-x86_64-apple-darwin.zip', 'sha_url_suffix': '.sha256sum', 'extract': ['deno']},
    ],
}


def current_target():
    plat = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower(), 'x64')
    return plat, arch


def download(url, dest):
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=120) as response, open(dest, 'wb') as out:
        final_url = response.geturl()
        total = int(response.headers.get('Content-Length') or 0)
        done = 0
        digest = hashlib.sha256()
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                print(f'\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB', end='', flush=True)
        print()
    return final_url, digest.hexdigest()


def fetch_text(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as response:
        return response.read().decode('utf-8', 'replace')


def expected_hash(source, final_url):
    filename = source['url'].rsplit('/', 1)[-1]
    if source.get('checksums'):
        for line in fetch_text(source['checksums']).splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip('*') == filename:
                return parts[0].lower()
        raise SystemExit(f'No se encontró el hash de {filename}')
    if source.get('sha_url_suffix'):
        base = source['url'] if 'github.com' in source['url'] else final_url
        match = re.search(r'\b[0-9a-fA-F]{64}\b', fetch_text(base + source['sha_url_suffix']))
        if not match:
            raise SystemExit(f'No se pudo leer el hash publicado de {filename}')
        return match.group(0).lower()
    return None


def main():
    parser = argparse.ArgumentParser()
    default_plat, default_arch = current_target()
    parser.add_argument('--platform', default=default_plat, choices=['windows', 'macos'])
    parser.add_argument('--arch', default=default_arch, choices=['x64', 'arm64'])
    parser.add_argument('--dest-root', default=os.environ.get('NACTIONX_BIN_ROOT') or str(ROOT / 'packaging' / 'bin'),
                        help='Carpeta base de salida (por defecto packaging/bin o NACTIONX_BIN_ROOT)')
    args = parser.parse_args()
    key = (args.platform, args.arch)
    if key not in SOURCES:
        raise SystemExit(f'Plataforma no soportada: {key}')
    dest = Path(args.dest_root) / f'{args.platform}-{args.arch}'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        for source in SOURCES[key]:
            print(f'Descargando {source["name"]}…')
            archive = Path(tmp) / source['url'].rsplit('/', 1)[-1]
            final_url, digest = download(source['url'], archive)
            expected = expected_hash(source, final_url)
            if expected and expected != digest:
                raise SystemExit(f'SHA-256 no coincide para {source["name"]}: {digest} != {expected}')
            print(f'  SHA-256 verificado: {digest}' if expected else '  (el proveedor no publica SHA-256)')
            with zipfile.ZipFile(archive) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    if any(fnmatch.fnmatch(member.filename, pattern) for pattern in source['extract']):
                        target = dest / Path(member.filename).name
                        with zf.open(member) as src, open(target, 'wb') as out:
                            shutil.copyfileobj(src, out)
                        if args.platform != 'windows':
                            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    files = sorted(p.name for p in dest.iterdir())
    size = sum(p.stat().st_size for p in dest.iterdir()) / 1e6
    print(f'Listo: {len(files)} archivos, {size:.0f} MB en {dest}')
    print('  ' + ', '.join(files[:12]) + (' …' if len(files) > 12 else ''))


if __name__ == '__main__':
    main()
