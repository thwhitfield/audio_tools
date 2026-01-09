"""
Entry point for PyInstaller bundled Streamlit app.

This wrapper script starts the Streamlit server and opens the browser.
"""

import os
import sys
from pathlib import Path


def get_app_path():
    """Get the path to main.py, works both in development and when bundled."""
    if getattr(sys, "frozen", False):
        # Running as bundled executable
        bundle_dir = Path(sys._MEIPASS)
    else:
        # Running in normal Python environment
        bundle_dir = Path(__file__).parent

    return str(bundle_dir / "main.py")


def setup_ffmpeg():
    """Ensure ffmpeg is available for pydub."""
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except ImportError:
        pass  # static_ffmpeg not installed, assume ffmpeg is in PATH


if __name__ == "__main__":
    # Setup ffmpeg before importing anything that needs it
    setup_ffmpeg()

    # Import streamlit CLI
    from streamlit.web import cli as stcli

    # Configure streamlit to run our app
    app_path = get_app_path()

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
    ]

    sys.exit(stcli.main())
