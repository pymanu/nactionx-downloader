"""Publica los instaladores en el repositorio público de descargas.

El código vive en un repositorio privado; los instaladores, en uno público, para que la propia app
pueda preguntar «¿hay una versión nueva?» sin llevar ninguna credencial dentro.

Uso (con la sesión de GitHub ya iniciada en `gh auth login`):
    python packaging/publish_release.py                 # comprueba y publica lo que haya en releases/
    python packaging/publish_release.py --dry-run       # solo comprueba
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nactionx import __version__  # noqa: E402

REPO = 'pymanu/nactionx-downloader-releases'
# Lo que la app busca al comprobar si hay versión nueva: si falta alguno, ese sistema se queda sin aviso.
EXPECTED = [
    'NactionX-Downloader-{v}-Windows-x64-Setup.exe',
    'NactionX-Downloader-{v}-macOS-arm64.dmg',
    'NactionX-Downloader-{v}-macOS-x64.dmg',
]
OPTIONAL = ['NactionX-Downloader-{v}-Windows-x64-Portable.zip']


def changelog_notes(version):
    """La sección del CHANGELOG de esta versión, que se usa como notas de la publicación."""
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## {re.escape(version)}\b.*?(?=^## |\Z)', text, re.M | re.S)
    return match.group(0).strip() if match else f'NactionX Downloader {version}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=__version__)
    parser.add_argument('--dir', default=str(ROOT / 'releases'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--gh', default='gh', help='Ruta al ejecutable de GitHub CLI')
    args = parser.parse_args()

    folder, version = Path(args.dir), args.version
    required = [folder / name.format(v=version) for name in EXPECTED]
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        raise SystemExit(f'Faltan archivos de la versión {version} en {folder}:\n  ' + '\n  '.join(missing))
    files = required + [p for p in (folder / n.format(v=version) for n in OPTIONAL) if p.is_file()]
    for path in files:
        print(f'  {path.name}  ({path.stat().st_size / 1e6:.0f} MB)')

    notes = changelog_notes(version)
    if args.dry_run:
        print(f'\n(dry-run) Se publicaría v{version} en {REPO} con estas notas:\n\n{notes}')
        return 0

    notes_file = folder / f'.notas-{version}.md'
    notes_file.write_text(notes, encoding='utf-8')
    try:
        subprocess.run([args.gh, 'release', 'create', f'v{version}', '--repo', REPO,
                        '--title', f'NactionX Downloader {version}', '--notes-file', str(notes_file),
                        *[str(p) for p in files]], check=True)
    finally:
        notes_file.unlink(missing_ok=True)
    print(f'\nPublicado: https://github.com/{REPO}/releases/tag/v{version}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
