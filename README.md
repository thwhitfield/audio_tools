# Audio Tools

Tools to process audio data to make it easier to listen to on Shokz OpenSwim MP3 players.

## Features

- **Podcast Search & Download**: Search for podcasts and episodes using the iTunes API, then download episodes directly in the app
- **Spoken Intros**: Automatically adds text-to-speech audio of the filename at the beginning of each file
- **Volume Adjustment**: Increase or decrease audio volume by a specified number of decibels
- **Speed Adjustment**: Change playback speed while preserving pitch (requires rubberband)
- **File Splitting**: Split long podcasts into smaller chunks for easier navigation
- **Batch Processing**: Process multiple files at once

## Installation

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/audio_tools.git
cd audio_tools

# Install dependencies
pip install -r app/requirements.txt

# For speed adjustment feature, install rubberband
brew install rubberband  # macOS
```

### Running the App

```bash
# Run the Streamlit GUI
make run

# Or directly with streamlit
streamlit run app/main.py
```

## Building a Standalone macOS App

Build a distributable `.app` bundle that doesn't require Python:

```bash
# Optional: Add a custom icon (place a 1024x1024 PNG at app/icon.png)
make icon

# Build the app
make build
```

The built app will be at `app/dist/Audio Tools.app`.

## Usage

### GUI (Streamlit App)

The app has four modes:

1. **Process Podcast**: Search for podcasts online or upload a local MP3 file. Split long episodes into chunks with spoken intros, adjust volume, and change speed.

2. **Single File (No Split)**: Process a single MP3 file without splitting - add a spoken intro, adjust volume, and change speed.

3. **Batch Process Folder**: Upload multiple MP3 files and process them all at once.

4. **About**: Welcome page with documentation and quick access to all modes.

### Python API

```python
from audio_tools.process import process_pod, full_process_podcast_episode

# Process a single file
processed = process_pod(
    filepath="podcast.mp3",
    db_change=10,           # Increase volume by 10dB
    speed=1.25,             # 25% faster
    start_audio_text="My Podcast"  # Custom intro text
)
processed.export("output.mp3")

# Full processing with splitting
output_folder = full_process_podcast_episode(
    filepath="long_podcast.mp3",
    db_change=10,
    split_length=10,        # Split into 10-minute chunks
    speed=1.0
)
```

## Make Commands

| Command | Description |
|---------|-------------|
| `make run` | Run the Streamlit app in development mode |
| `make build` | Build the standalone macOS app |
| `make clean` | Remove build artifacts |
| `make install` | Install dependencies for development |
| `make icon` | Convert app/icon.png to app/icon.icns |
| `make kill` | Kill any process using port 8501 |

## Requirements

- Python 3.9+
- ffmpeg (automatically handled by static-ffmpeg)
- rubberband (for speed adjustment): `brew install rubberband`
