# Audio Tools Makefile

.PHONY: run build clean kill help icon dmg check-env

# Expected conda environment name
CONDA_ENV := audio_tools

# Check if the correct conda environment is active
check-env:
	@if [ "$$CONDA_DEFAULT_ENV" != "$(CONDA_ENV)" ]; then \
		echo "Error: Wrong conda environment active."; \
		echo "  Current: $${CONDA_DEFAULT_ENV:-none}"; \
		echo "  Expected: $(CONDA_ENV)"; \
		echo ""; \
		echo "Run: conda activate $(CONDA_ENV)"; \
		exit 1; \
	fi

# Run the Streamlit app (development mode)
# Prompts user if port 8501 is already in use
run: check-env
	@if lsof -ti:8501 >/dev/null 2>&1; then \
		echo "Port 8501 is already in use."; \
		echo ""; \
		echo "Options:"; \
		echo "  [k] Kill the existing process and use port 8501"; \
		echo "  [n] Use a different port (8502)"; \
		echo "  [q] Quit"; \
		echo ""; \
		read -p "Choice [k/n/q]: " choice; \
		case "$$choice" in \
			k|K) \
				echo "Killing existing process..."; \
				lsof -ti:8501 | xargs kill -9 2>/dev/null; \
				sleep 1; \
				streamlit run app/main.py; \
				;; \
			n|N) \
				echo "Starting on port 8502..."; \
				streamlit run app/main.py --server.port 8502; \
				;; \
			*) \
				echo "Cancelled."; \
				exit 0; \
				;; \
		esac; \
	else \
		streamlit run app/main.py; \
	fi

# Kill any process using port 8501 (Streamlit's default port)
kill:
	@lsof -ti:8501 | xargs kill -9 2>/dev/null || echo "No process running on port 8501"

# Build the standalone macOS app
build: check-env
	./build_app.sh

# Clean build artifacts
clean:
	rm -rf build_venv/
	rm -rf app/build/
	rm -rf app/dist/
	rm -rf app/binaries/

# Install dependencies for development
install: check-env
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
	@echo "  make run       - Run the Streamlit app in development mode"
	@echo "  make kill      - Kill any process using port 8501"
	@echo "  make build     - Build the standalone macOS app"
	@echo "  make clean     - Remove build artifacts"
	@echo "  make install   - Install dependencies for development"
	@echo "  make icon      - Convert app/icon.png to app/icon.icns"
	@echo "  make dmg       - Create a DMG file for distribution"
	@echo "  make check-env - Verify correct conda environment is active"
	@echo ""
	@echo "Note: Most commands require the '$(CONDA_ENV)' conda environment."
	@echo "      Run 'conda activate $(CONDA_ENV)' before using make."
