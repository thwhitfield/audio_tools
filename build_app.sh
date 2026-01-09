#!/bin/bash
# Build script for Audio Tools macOS app
#
# This script creates a standalone .app bundle that can be distributed
# to users without requiring them to install Python or any dependencies.
#
# Prerequisites:
#   - Python 3.9+
#   - Run this from the project root directory
#
# Usage:
#   ./build_app.sh
#
# Output:
#   - app/dist/Audio Tools.app (the distributable application)

set -e  # Exit on error

echo "=== Audio Tools Build Script ==="
echo ""

# Check we're in the right directory
if [ ! -f "setup.py" ]; then
    echo "Error: Please run this script from the project root directory"
    exit 1
fi

# Create a virtual environment for building (to avoid polluting your main env)
echo "1. Creating build virtual environment..."
python3 -m venv build_venv
source build_venv/bin/activate

# Install dependencies
echo ""
echo "2. Installing dependencies..."
pip install --upgrade pip
pip install pyinstaller
pip install streamlit pydub gTTS static-ffmpeg

# Pre-download ffmpeg binaries so they're available
echo ""
echo "3. Pre-downloading ffmpeg binaries..."
python -c "import static_ffmpeg; static_ffmpeg.add_paths(); print('ffmpeg ready')"

# Build the app
echo ""
echo "4. Building the application..."
cd app
pyinstaller AudioTools.spec --clean --noconfirm

echo ""
echo "=== Build Complete ==="
echo ""
echo "The app is located at:"
echo "  app/dist/Audio Tools.app"
echo ""
echo "To test it, run:"
echo "  open 'app/dist/Audio Tools.app'"
echo ""
echo "To distribute, you can:"
echo "  1. Zip the .app: cd app/dist && zip -r 'Audio Tools.zip' 'Audio Tools.app'"
echo "  2. Create a DMG (optional): hdiutil create -volname 'Audio Tools' -srcfolder 'app/dist/Audio Tools.app' -ov -format UDZO AudioTools.dmg"
echo ""

# Deactivate virtual environment
deactivate

echo "Note: First launch on a new Mac may show a security warning."
echo "Right-click the app and select 'Open' to bypass it."
