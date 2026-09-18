#!/usr/bin/env bash
# Compila NactionX Downloader en tu Mac y crea el .dmg. No instala nada en el sistema:
# todo el entorno va a ~/.nactionx-build y el resultado a la carpeta releases/ del proyecto.
#
# Cómo ejecutarlo:
#   1. Abre la app Terminal (Launchpad > Otras > Terminal).
#   2. Escribe:  bash     (con un espacio al final)
#   3. Arrastra este archivo a la ventana de Terminal y pulsa Intro.
set -euo pipefail
cd "$(dirname "$0")"

echo "== NactionX Downloader: compilación para macOS"
case "$(uname -m)" in
  arm64) ARCH=arm64 ;;
  *)     ARCH=x64 ;;
esac
echo "   Mac detectado: $ARCH"

PY=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0)"
    case "$version" in
      3.12|3.13|3.14) PY="$candidate"; break ;;
    esac
  fi
done
if [ -z "$PY" ]; then
  echo
  echo "Falta Python 3.12 o superior."
  echo "Descárgalo aquí (instalador oficial, doble clic) y vuelve a ejecutar este archivo:"
  echo "   https://www.python.org/downloads/macos/"
  exit 1
fi
echo "   Python: $($PY --version)"

BUILD="$HOME/.nactionx-build"
mkdir -p "$BUILD"
if [ ! -x "$BUILD/venv/bin/python" ]; then
  echo "== Creando entorno de compilación"
  "$PY" -m venv "$BUILD/venv"
fi
# shellcheck disable=SC1091
source "$BUILD/venv/bin/activate"
python -m pip install --upgrade pip --quiet
echo "== Instalando dependencias"
python -m pip install -r requirements-build.txt --quiet

export NACTIONX_ARCH="$ARCH"
export NACTIONX_BIN_ROOT="$BUILD/bin"
echo "== Descargando FFmpeg y Deno oficiales (se verifica su SHA-256)"
python packaging/fetch_components.py --platform macos --arch "$ARCH" --dest-root "$NACTIONX_BIN_ROOT"
echo "== Iconos"
python packaging/make_icons.py
echo "== Tests"
python -m pytest tests -q -p no:cacheprovider
echo "== Construyendo la app"
python -m PyInstaller packaging/nactionx.spec --noconfirm --clean --distpath "$BUILD/dist" --workpath "$BUILD/work"
echo "== Prueba automática de la app (descarga real y recorte)"
python packaging/smoke_test.py --app "$BUILD/dist/NactionX Downloader.app/Contents/MacOS/NactionX Downloader" --work "$BUILD/smoke"
echo "== Creando el DMG"
bash packaging/make_dmg.sh "$ARCH" "$BUILD/dist"

echo
echo "Listo. Tienes el DMG en la carpeta releases del proyecto."
open releases 2>/dev/null || true
