#!/usr/bin/env bash
# Compila NactionX Downloader en un Mac y genera el .dmg.
# Uso: bash packaging/build_macos.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
case "$(uname -m)" in arm64) ARCH=arm64 ;; *) ARCH=x64 ;; esac
export NACTIONX_ARCH="$ARCH"

python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install --upgrade pip -q
python -m pip install -r requirements-build.txt -q
python packaging/fetch_components.py --platform macos --arch "$ARCH"
python packaging/make_icons.py
python -m pytest tests -q -p no:cacheprovider
python -m PyInstaller packaging/nactionx.spec --noconfirm --clean
bash packaging/make_dmg.sh "$ARCH"
