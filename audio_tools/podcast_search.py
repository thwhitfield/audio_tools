"""Functions for searching podcasts and episodes via the iTunes Search API."""

import requests
import feedparser
from pathlib import Path
from typing import Callable


def search_podcasts(query: str, limit: int = 25) -> list[dict]:
    """Search for podcasts by name using the iTunes Search API.

    Args:
        query: Search term for podcast name
        limit: Maximum number of results to return (default: 25)

    Returns:
        List of podcast dictionaries with keys: id, name, author, artwork_url, feed_url
    """
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "media": "podcast",
        "entity": "podcast",
        "limit": limit,
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    podcasts = []
    for result in data.get("results", []):
        podcasts.append({
            "id": result.get("collectionId"),
            "name": result.get("collectionName"),
            "author": result.get("artistName"),
            "artwork_url": result.get("artworkUrl100"),
            "feed_url": result.get("feedUrl"),
        })

    return podcasts


def search_episodes(query: str, limit: int = 25) -> list[dict]:
    """Search for podcast episodes by keyword using the iTunes Search API.

    Args:
        query: Search term for episode name/content
        limit: Maximum number of results to return (default: 25)

    Returns:
        List of episode dictionaries with keys: id, title, podcast_name, audio_url,
        duration_ms, artwork_url, release_date
    """
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "media": "podcast",
        "entity": "podcastEpisode",
        "limit": limit,
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    episodes = []
    for result in data.get("results", []):
        episodes.append({
            "id": result.get("trackId"),
            "title": result.get("trackName"),
            "podcast_name": result.get("collectionName"),
            "audio_url": result.get("episodeUrl"),
            "duration_ms": result.get("trackTimeMillis"),
            "artwork_url": result.get("artworkUrl160") or result.get("artworkUrl100"),
            "release_date": result.get("releaseDate"),
        })

    return episodes


def get_podcast_episodes(feed_url: str, limit: int | None = None) -> list[dict]:
    """Fetch episodes from a podcast RSS feed.

    Args:
        feed_url: URL of the podcast RSS feed
        limit: Maximum number of episodes to return (default: None = all episodes)

    Returns:
        List of episode dictionaries with keys: title, audio_url, duration,
        release_date, description
    """
    feed = feedparser.parse(feed_url)

    entries = feed.entries[:limit] if limit else feed.entries
    episodes = []
    for entry in entries:
        audio_url = None
        duration = None

        # Find the audio enclosure
        for enclosure in entry.get("enclosures", []):
            if "audio" in enclosure.get("type", ""):
                audio_url = enclosure.get("href")
                break

        # Try to get duration from itunes namespace
        duration = entry.get("itunes_duration")

        episodes.append({
            "title": entry.get("title"),
            "audio_url": audio_url,
            "duration": duration,
            "release_date": entry.get("published"),
            "description": entry.get("summary", ""),
        })

    return episodes


def download_episode(
    audio_url: str,
    output_path: str,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Download a podcast episode to a file.

    Args:
        audio_url: URL of the audio file to download
        output_path: Path where the file should be saved
        progress_callback: Optional callback function(bytes_downloaded, total_bytes)
            for progress updates

    Returns:
        Path to the downloaded file
    """
    response = requests.get(audio_url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0

    output_path = Path(output_path)

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)

    return output_path


def format_duration(duration_ms: int | None) -> str:
    """Format duration in milliseconds to human-readable string.

    Args:
        duration_ms: Duration in milliseconds

    Returns:
        Formatted string like "1h 23m" or "45m"
    """
    if not duration_ms:
        return ""

    total_seconds = duration_ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_duration_str(duration_str: str | None) -> str:
    """Format iTunes duration string (HH:MM:SS or MM:SS) to human-readable string.

    Args:
        duration_str: Duration string from RSS feed

    Returns:
        Formatted string like "1h 23m" or "45m"
    """
    if not duration_str:
        return ""

    parts = duration_str.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, _ = map(int, parts)
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        elif len(parts) == 2:
            minutes, _ = map(int, parts)
            return f"{minutes}m"
    except ValueError:
        pass

    return duration_str
