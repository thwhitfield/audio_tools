# Audio Tools Makefile

.PHONY: run build clean kill help

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

help:
	@echo "Available commands:"
	@echo "  make run      - Run the Streamlit app in development mode"
	@echo "  make kill     - Kill any process using port 8501"
	@echo "  make build    - Build the standalone macOS app"
	@echo "  make clean    - Remove build artifacts"
	@echo "  make install  - Install dependencies for development"
