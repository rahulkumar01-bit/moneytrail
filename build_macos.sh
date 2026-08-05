#!/bin/bash
# ============================================================
#  Build a standalone macOS .app for Money Trail Report Generator
#  Run this ON macOS from the project root folder:
#      chmod +x build_macos.sh && ./build_macos.sh
# ============================================================
set -e

echo "Creating virtual environment (if not already present)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Building .app with PyInstaller..."
pyinstaller --noconfirm --clean --onefile --windowed \
    --name "MoneyTrailReportGenerator" \
    --add-data "core/templates:core/templates" \
    main.py

echo ""
echo "============================================================"
echo " Build complete. Find the app at:"
echo "   dist/MoneyTrailReportGenerator.app"
echo "============================================================"
