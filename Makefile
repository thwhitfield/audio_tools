# Audio Tools Makefile

.PHONY: run build clean kill help icon dmg

# Run the Streamlit app (development mode)
run:
	streamlit run app/main.py

# Kill any process using port 8501 (Streamlit's default port)
kill:
	@lsof -ti:8501 | xargs kill -9 2>/dev/null || echo "No process running on port 8501"

# Build the standalone macOS app
build:
	./build_app.sh

# Clean build artifacts
clean:
	rm -rf build_venv/
	rm -rf app/build/
	rm -rf app/dist/
	rm -rf app/binaries/

# Install dependencies for development
install:
	pip install -r app/requirements.txt

# Convert PNG icon to macOS .icns format
icon:
	@if [ ! -f "app/icon.png" ]; then \
		echo "Error: app/icon.png not found"; \
		exit 1; \
	fi
	@echo "Converting icon.png to icon.icns..."
	@mkdir -p app/icon.iconset
	@sips -z 16 16 app/icon.png --out app/icon.iconset/icon_16x16.png >/dev/null
	@sips -z 32 32 app/icon.png --out app/icon.iconset/icon_16x16@2x.png >/dev/null
	@sips -z 32 32 app/icon.png --out app/icon.iconset/icon_32x32.png >/dev/null
	@sips -z 64 64 app/icon.png --out app/icon.iconset/icon_32x32@2x.png >/dev/null
	@sips -z 128 128 app/icon.png --out app/icon.iconset/icon_128x128.png >/dev/null
	@sips -z 256 256 app/icon.png --out app/icon.iconset/icon_128x128@2x.png >/dev/null
	@sips -z 256 256 app/icon.png --out app/icon.iconset/icon_256x256.png >/dev/null
	@sips -z 512 512 app/icon.png --out app/icon.iconset/icon_256x256@2x.png >/dev/null
	@sips -z 512 512 app/icon.png --out app/icon.iconset/icon_512x512.png >/dev/null
	@sips -z 1024 1024 app/icon.png --out app/icon.iconset/icon_512x512@2x.png >/dev/null
	@iconutil -c icns app/icon.iconset -o app/icon.icns
	@rm -rf app/icon.iconset
	@echo "Created app/icon.icns"

# Create a DMG file for distribution (requires build first)
dmg:
	@if [ ! -d "app/dist/Audio Tools.app" ]; then \
		echo "Error: app/dist/Audio Tools.app not found. Run 'make build' first."; \
		exit 1; \
	fi
	@echo "Creating DMG file..."
	@rm -f "AudioTools.dmg"
	hdiutil create -volname "Audio Tools" -srcfolder "app/dist/Audio Tools.app" -ov -format UDZO AudioTools.dmg
	@echo "Created AudioTools.dmg"

help:
	@echo "Available commands:"
	@echo "  make run      - Run the Streamlit app in development mode"
	@echo "  make kill     - Kill any process using port 8501"
	@echo "  make build    - Build the standalone macOS app"
	@echo "  make clean    - Remove build artifacts"
	@echo "  make install  - Install dependencies for development"
	@echo "  make icon     - Convert app/icon.png to app/icon.icns"
	@echo "  make dmg      - Create a DMG file for distribution"
