"""Functions for downloading audio from YouTube videos using yt-dlp."""

import tempfile
from pathlib import Path
from typing import Callable


def get_video_info(url: str) -> dict:
    """Get metadata for a YouTube video.

    Args:
        url: YouTube video URL

    Returns:
        Dictionary with keys: title, duration, thumbnail, uploader
    """
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader", "Unknown"),
    }


def download_audio(
    url: str,
    output_path: str | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> Path:
    """Download audio from a YouTube video as MP3.

    Args:
        url: YouTube video URL
        output_path: Optional path where the file should be saved.
            If not provided, a temporary file will be created.
        progress_callback: Optional callback function(progress_percent, status)
            for progress updates

    Returns:
        Path to the downloaded MP3 file
    """
    import yt_dlp

    # Create output path if not provided
    if output_path is None:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp_file.name
        tmp_file.close()

    output_path = Path(output_path)

    # Remove extension since yt-dlp adds it
    output_template = str(output_path.with_suffix(""))

    def progress_hook(d):
        if progress_callback and d["status"] == "downloading":
            # Calculate percentage
            if d.get("total_bytes"):
                percent = (d.get("downloaded_bytes", 0) / d["total_bytes"]) * 100
            elif d.get("total_bytes_estimate"):
                percent = (d.get("downloaded_bytes", 0) / d["total_bytes_estimate"]) * 100
            else:
                percent = 0
            progress_callback(percent, "Downloading...")
        elif progress_callback and d["status"] == "finished":
            progress_callback(100, "Converting to MP3...")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # yt-dlp adds .mp3 extension
    final_path = Path(output_template + ".mp3")

    return final_path


def format_duration(seconds: int | None) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "1h 23m" or "45m 30s"
    """
    if not seconds:
        return ""

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def is_valid_youtube_url(url: str) -> bool:
    """Check if a URL is a valid YouTube video URL.

    Args:
        url: URL to validate

    Returns:
        True if the URL appears to be a valid YouTube video URL
    """
    import re

    # Common YouTube URL patterns
    patterns = [
        r"^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+",
        r"^https?://youtu\.be/[\w-]+",
        r"^https?://(?:www\.)?youtube\.com/shorts/[\w-]+",
        r"^https?://(?:www\.)?youtube\.com/embed/[\w-]+",
    ]

    for pattern in patterns:
        if re.match(pattern, url):
            return True

    return False
