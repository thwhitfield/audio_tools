#!/bin/bash
# Collect rubberband and all its dependencies for bundling with PyInstaller
# Run this script before building the app

set -e

BINARIES_DIR="$(dirname "$0")/binaries"

# Remove existing binaries directory to avoid permission issues with read-only files
if [ -d "$BINARIES_DIR" ]; then
    rm -rf "$BINARIES_DIR"
fi
mkdir -p "$BINARIES_DIR"

echo "Collecting rubberband and dependencies..."

# Main binary
cp /opt/homebrew/bin/rubberband "$BINARIES_DIR/"

# Direct dependencies
cp /opt/homebrew/opt/libsamplerate/lib/libsamplerate.0.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/libsndfile/lib/libsndfile.1.dylib "$BINARIES_DIR/"

# Transitive dependencies from libsndfile
cp /opt/homebrew/opt/libogg/lib/libogg.0.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/libvorbis/lib/libvorbisenc.2.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/libvorbis/lib/libvorbis.0.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/flac/lib/libFLAC.14.dylib "$BINARIES_DIR/" 2>/dev/null || cp /opt/homebrew/opt/flac/lib/libFLAC.*.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/opus/lib/libopus.0.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/mpg123/lib/libmpg123.0.dylib "$BINARIES_DIR/"
cp /opt/homebrew/opt/lame/lib/libmp3lame.0.dylib "$BINARIES_DIR/"

echo "Fixing library paths with install_name_tool..."

# Fix the rubberband binary to look for libraries in the same directory
install_name_tool -change /opt/homebrew/opt/libsamplerate/lib/libsamplerate.0.dylib @executable_path/libsamplerate.0.dylib "$BINARIES_DIR/rubberband"
install_name_tool -change /opt/homebrew/opt/libsndfile/lib/libsndfile.1.dylib @executable_path/libsndfile.1.dylib "$BINARIES_DIR/rubberband"

# Fix libsndfile to look for its dependencies in the same directory
install_name_tool -change /opt/homebrew/opt/libogg/lib/libogg.0.dylib @loader_path/libogg.0.dylib "$BINARIES_DIR/libsndfile.1.dylib"
install_name_tool -change /opt/homebrew/opt/libvorbis/lib/libvorbisenc.2.dylib @loader_path/libvorbisenc.2.dylib "$BINARIES_DIR/libsndfile.1.dylib"
install_name_tool -change /opt/homebrew/opt/libvorbis/lib/libvorbis.0.dylib @loader_path/libvorbis.0.dylib "$BINARIES_DIR/libsndfile.1.dylib"
install_name_tool -change /opt/homebrew/opt/flac/lib/libFLAC.14.dylib @loader_path/libFLAC.14.dylib "$BINARIES_DIR/libsndfile.1.dylib" 2>/dev/null || true
install_name_tool -change /opt/homebrew/opt/opus/lib/libopus.0.dylib @loader_path/libopus.0.dylib "$BINARIES_DIR/libsndfile.1.dylib"
install_name_tool -change /opt/homebrew/opt/mpg123/lib/libmpg123.0.dylib @loader_path/libmpg123.0.dylib "$BINARIES_DIR/libsndfile.1.dylib"
install_name_tool -change /opt/homebrew/opt/lame/lib/libmp3lame.0.dylib @loader_path/libmp3lame.0.dylib "$BINARIES_DIR/libsndfile.1.dylib"

# Fix libvorbisenc to find libvorbis and libogg
install_name_tool -change /opt/homebrew/opt/libvorbis/lib/libvorbis.0.dylib @loader_path/libvorbis.0.dylib "$BINARIES_DIR/libvorbisenc.2.dylib"
install_name_tool -change /opt/homebrew/opt/libogg/lib/libogg.0.dylib @loader_path/libogg.0.dylib "$BINARIES_DIR/libvorbisenc.2.dylib"

# Fix libvorbis to find libogg
install_name_tool -change /opt/homebrew/opt/libogg/lib/libogg.0.dylib @loader_path/libogg.0.dylib "$BINARIES_DIR/libvorbis.0.dylib"

# Make rubberband executable
chmod +x "$BINARIES_DIR/rubberband"

echo "Done! Binaries collected in $BINARIES_DIR"
ls -la "$BINARIES_DIR"
