#!/usr/bin/env bash
# Builds mhtml-cleaner.exe and SyncReviewExcel.exe for Windows using Wine + PyInstaller.
#
# Requires: wine (64-bit prefix), curl. Everything else (Python for Windows,
# pip, PyInstaller, project dependencies) is installed automatically into the
# default Wine prefix (~/.wine) on first run.
#
# Usage: ./Releases/scripts/build-windows.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$PROJECT_DIR/Releases/windows"

PYTHON_VERSION="3.12.6"
PYTHON_INSTALLER="python-${PYTHON_VERSION}-amd64.exe"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_INSTALLER}"
CACHE_DIR="$SCRIPT_DIR/.cache"

WINE_PYTHON_DIR='C:\Python312'
WINE_PYTHON_EXE="$HOME/.wine/drive_c/Python312/python.exe"

command -v wine >/dev/null || { echo "❌ wine is not installed" >&2; exit 1; }

mkdir -p "$CACHE_DIR" "$OUT_DIR"

# ── 1. Install Python for Windows into the Wine prefix (once) ────────────────
if [ ! -f "$WINE_PYTHON_EXE" ]; then
    echo "📥 Downloading Python ${PYTHON_VERSION} for Windows..."
    curl -fL -o "$CACHE_DIR/$PYTHON_INSTALLER" "$PYTHON_URL"

    echo "📦 Installing Python into the Wine prefix..."
    wine "$CACHE_DIR/$PYTHON_INSTALLER" /quiet InstallAllUsers=0 TargetDir="$WINE_PYTHON_DIR" \
        PrependPath=0 Include_launcher=0 Include_test=0
else
    echo "✅ Python already installed at $WINE_PYTHON_EXE"
fi

WINE_PY="wine $WINE_PYTHON_DIR\\python.exe"

# ── 2. Install / upgrade build dependencies ───────────────────────────────────
echo "📦 Installing PyInstaller and project dependencies..."
$WINE_PY -m pip install --quiet --upgrade pip
$WINE_PY -m pip install --quiet --upgrade pyinstaller xlrd xlwt xlutils openpyxl

# ── 3. Build mhtml-cleaner.exe ────────────────────────────────────────────────
echo "🔨 Building mhtml-cleaner.exe..."
cd "$PROJECT_DIR"
$WINE_PY -m PyInstaller --noconfirm --onefile --console \
    --name mhtml-cleaner \
    --distpath "$PROJECT_DIR/Releases/windows" \
    --workpath "$SCRIPT_DIR/.build/mhtml-cleaner" \
    --specpath "$SCRIPT_DIR/.build" \
    mhtml-cleaner.py

# ── 4. Build SyncReviewExcel.exe ──────────────────────────────────────────────
echo "🔨 Building SyncReviewExcel.exe..."
$WINE_PY -m PyInstaller --noconfirm --onefile --console \
    --name SyncReviewExcel \
    --distpath "$PROJECT_DIR/Releases/windows" \
    --workpath "$SCRIPT_DIR/.build/SyncReviewExcel" \
    --specpath "$SCRIPT_DIR/.build" \
    SyncReviewExcel.py

echo "✅ Done. Executables written to $OUT_DIR"
ls -la "$OUT_DIR"/*.exe
