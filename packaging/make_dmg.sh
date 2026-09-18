#!/usr/bin/env bash
# Firma ad-hoc la .app y crea el .dmg con acceso directo a Aplicaciones.
# Uso: bash packaging/make_dmg.sh <arm64|x64> [ruta de dist]
set -euo pipefail
ARCH="${1:?arquitectura: arm64 o x64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${2:-$ROOT/dist}"
APP="$DIST/NactionX Downloader.app"
VERSION="$(cd "$ROOT" && python -c 'import nactionx; print(nactionx.__version__)')"
OUT="$ROOT/releases"
mkdir -p "$OUT"

# Apple Silicon no ejecuta binarios sin firmar: firma ad-hoc de todo el paquete
chmod +x "$APP/Contents/MacOS/"* || true
find "$APP" -type f \( -name ffmpeg -o -name ffprobe -o -name deno \) -exec chmod +x {} \;
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="$OUT/NactionX-Downloader-$VERSION-macOS-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "NactionX Downloader" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"
echo "Listo: $DMG"
