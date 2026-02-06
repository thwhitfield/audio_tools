"""
Audio Tools - Streamlit App

A simple GUI for processing podcast MP3 files:
- Add spoken intro (filename or custom text)
- Adjust volume
- Split long podcasts into chunks
"""

import sys
import tempfile
import time
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional


def setup_environment():
    """Setup paths and ffmpeg for both development and bundled modes."""
    # Determine if we're running as a bundled app
    if getattr(sys, "frozen", False):
        # Running as bundled executable
        bundle_dir = Path(sys._MEIPASS)
        # Add the bundled audio_tools to path
        sys.path.insert(0, str(bundle_dir))
    else:
        # Running in normal Python environment
        sys.path.insert(0, str(Path(__file__).parent.parent))

    # Setup ffmpeg using static-ffmpeg if available
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except ImportError:
        pass  # Assume ffmpeg is in PATH


setup_environment()

import streamlit as st

from audio_tools.archive import PodcastArchive, PodcastRecord
from audio_tools.chapters import (
    ChapterInfo,
    SplitMode,
    extract_chapters_from_audio,
    get_chapters,
)
from audio_tools.podcast_search import (
    download_episode,
    format_duration,
    format_duration_str,
    get_podcast_episodes,
    search_episodes,
    search_podcasts,
)
from audio_tools.process import (
    full_process_podcast_episode,
    process_pod,
    process_podcast_folder,
    split_podcast,
)
from audio_tools.youtube_download import download_audio as download_youtube_audio
from audio_tools.youtube_download import format_duration as format_youtube_duration
from audio_tools.youtube_download import get_video_info, is_valid_youtube_url

st.set_page_config(
    page_title="Audio Tools",
    page_icon="🎧",
    layout="centered",
)

st.title("Audio Tools")
st.markdown("Process podcast MP3 files for your Shokz OpenSwim player")

# Initialize session state for cancellation
if "cancel_requested" not in st.session_state:
    st.session_state.cancel_requested = False

# Initialize session state for file to process (from Search & Download)
if "file_for_processing" not in st.session_state:
    st.session_state.file_for_processing = None

# Initialize session state for chapter info
if "chapter_info" not in st.session_state:
    st.session_state.chapter_info = None

# Initialize session state for episode description
if "episode_description" not in st.session_state:
    st.session_state.episode_description = None


def request_cancel():
    """Callback to set the cancel flag."""
    st.session_state.cancel_requested = True


class ProcessingCancelled(Exception):
    """Exception raised when processing is cancelled by user."""

    pass


# Mode options - About first as landing page
ALL_MODES = [
    "About",
    "Process Podcast",
    "YouTube Audio",
    "Single File (No Split)",
    "Batch Process Folder",
    "Archive",
]

# Initialize the radio key if not present
if "mode_radio" not in st.session_state:
    st.session_state.mode_radio = "About"

# Sidebar for mode selection - key binds directly to session state
mode = st.sidebar.radio(
    "Mode",
    ALL_MODES,
    captions=[
        "Welcome & help",
        "Search or upload podcasts",
        "Download from YouTube",
        None,
        None,
        "View processing history",
    ],
    key="mode_radio",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
*Optimized for [Shokz OpenSwim](https://shokz.com/products/openswim) MP3 players*
"""
)


def export_audio_to_bytes(audio_segment) -> bytes:
    """Export an AudioSegment to bytes for download."""
    buffer = BytesIO()
    audio_segment.export(buffer, format="mp3")
    buffer.seek(0)
    return buffer.getvalue()


def estimate_processing_time(file_size_mb, speed=1.0, num_chunks=1):
    """Estimate processing time based on file size and settings.

    Based on empirical testing (14.5MB file, 2 chunks, speed 1.3x = 12.9 seconds):
    - Base processing: ~0.5 seconds per MB for loading, volume, splitting, exporting
    - Speed adjustment adds time: ~0.3 seconds per MB (pyrubberband)
    - Per-chunk overhead: ~2 seconds per chunk for gTTS intro generation

    Args:
        file_size_mb: Size of the input file in megabytes
        speed: Playback speed setting (1.0 = no speed change)
        num_chunks: Number of chunks the file will be split into

    Returns:
        Estimated processing time in seconds
    """
    # Base time for loading, processing, and exporting
    base_time = file_size_mb * 0.5

    # Speed adjustment adds some overhead
    if speed != 1.0:
        base_time += file_size_mb * 0.3

    # Per-chunk overhead for gTTS intro generation (requires network call)
    chunk_overhead = num_chunks * 2

    return base_time + chunk_overhead


def format_time(seconds, prefix="~"):
    """Format seconds into a human-readable string with units.

    Args:
        seconds: Time in seconds
        prefix: Optional prefix (default "~" for estimates, "" for elapsed)

    Returns:
        Formatted string like "~15s", "~1m 30s", or "1m 05s"
    """
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if minutes == 0:
        return f"{prefix}{remaining_seconds}s"
    return f"{prefix}{minutes}m {remaining_seconds:02d}s"


def save_to_archive(
    title: str,
    source_type: str,
    settings: dict,
    num_chunks: int,
    output_folder: Path,
    podcast_name: str = None,
) -> Optional[PodcastRecord]:
    """Save processed files to archive and create a record.

    Args:
        title: Title of the episode
        source_type: Type of source ("podcast", "youtube", "upload", "batch")
        settings: Processing settings dict
        num_chunks: Number of chunks created
        output_folder: Path to folder containing processed files
        podcast_name: Optional podcast name

    Returns:
        The created PodcastRecord or None if archiving failed
    """
    try:
        archive = PodcastArchive()

        # Create record first to get ID
        record = archive.add_record(
            title=title,
            source_type=source_type,
            settings=settings,
            num_chunks=num_chunks,
            podcast_name=podcast_name,
            processed_files_dir=None,  # Will update after copying files
        )

        # Create storage directory for this record
        storage_dir = archive.create_record_storage_dir(record.id)

        # Copy all processed files to archive storage
        import shutil

        processed_files = list(output_folder.glob("louder_*.mp3"))
        for mp3_file in processed_files:
            shutil.copy2(mp3_file, storage_dir / mp3_file.name)

        # Update record with storage directory path
        record.processed_files_dir = str(storage_dir)
        archive._save()

        return record
    except Exception as e:
        print(f"Warning: Could not save to archive: {e}")
        return None


# =============================================================================
# About (Landing Page)
# =============================================================================
if mode == "About":
    st.header("Welcome to Audio Tools")

    # Callback functions for mode switching
    def switch_to_process_podcast():
        st.session_state.mode_radio = "Process Podcast"

    def switch_to_youtube_audio():
        st.session_state.mode_radio = "YouTube Audio"

    def switch_to_single_file():
        st.session_state.mode_radio = "Single File (No Split)"

    def switch_to_batch_process():
        st.session_state.mode_radio = "Batch Process Folder"

    # Mode selection at top
    st.markdown("### Choose a Mode")

    col1, col2 = st.columns([1, 3])
    with col1:
        st.button(
            "Process Podcast",
            type="primary",
            use_container_width=True,
            on_click=switch_to_process_podcast,
        )
    with col2:
        st.markdown(
            "Search for podcasts online or upload local MP3 files. Split long episodes into chunks with spoken intros."
        )

    col1, col2 = st.columns([1, 3])
    with col1:
        st.button(
            "YouTube Audio", use_container_width=True, on_click=switch_to_youtube_audio
        )
    with col2:
        st.markdown(
            "Download audio from YouTube videos. Just paste a link and process the audio."
        )

    col1, col2 = st.columns([1, 3])
    with col1:
        st.button(
            "Single File", use_container_width=True, on_click=switch_to_single_file
        )
    with col2:
        st.markdown(
            "Process a single file without splitting. Add intro and adjust volume."
        )

    col1, col2 = st.columns([1, 3])
    with col1:
        st.button(
            "Batch Process", use_container_width=True, on_click=switch_to_batch_process
        )
    with col2:
        st.markdown("Process multiple files at once with the same settings.")

    st.markdown("---")

    st.markdown(
        """
## What is Audio Tools?

Audio Tools is designed to make podcast episodes easier to listen to on **Shokz OpenSwim**
bone conduction MP3 players (and similar devices). These players are great for swimming
and workouts, but they have limitations:

- **No screen** to see track names or progress
- **Limited controls** make navigation difficult
- **Lower volume** compared to regular headphones

This tool solves these problems by processing your audio files.

---

## Key Features

### Spoken Intros
Each audio chunk gets a **text-to-speech intro** announcing which part you're listening to
(e.g., "Part 1", "Part 2"). This way you always know where you are in a long episode
without needing to look at a screen.

### Volume Boost
Increase the volume of your audio files by up to **+30 dB** for better clarity during
workouts or in noisy environments like pools.

### Smart Splitting
Long podcasts (1-3+ hours) are split into **smaller chunks** (default: 10 minutes each).
This makes it easier to:
- Resume where you left off
- Skip forward/backward by track
- Manage your listening sessions

### Speed Adjustment
Speed up or slow down playback from **0.5x to 2.0x**. Great for:
- Getting through content faster (1.25x - 1.5x is popular)
- Slowing down dense educational content

---

## Tips

- **Start with default settings** and adjust based on your experience
- **10 dB volume boost** works well for most podcasts
- **1.25x speed** is a good starting point if you want to listen faster
- **10-minute chunks** balance convenience with not having too many files
    """
    )


# =============================================================================
# Process Podcast (Combined Landing Page)
# =============================================================================
elif mode == "Process Podcast":
    st.header("Process Podcast")
    st.markdown(
        """
    Search for a podcast online or upload a local file to process it.
    """
    )

    # Initialize session state for podcast search
    if "selected_podcast" not in st.session_state:
        st.session_state.selected_podcast = None
    if "podcast_episodes" not in st.session_state:
        st.session_state.podcast_episodes = None
    if "episodes_per_page" not in st.session_state:
        st.session_state.episodes_per_page = 25
    if "feed_episode_page" not in st.session_state:
        st.session_state.feed_episode_page = 0
    if "search_episode_page" not in st.session_state:
        st.session_state.search_episode_page = 0
    if "cached_episode_search" not in st.session_state:
        st.session_state.cached_episode_search = {"query": None, "results": []}

    def download_and_store_episode(
        audio_url: str,
        title: str,
        chapter_info: ChapterInfo | None = None,
        description: str | None = None,
    ):
        """Download an episode and store it in session state for processing."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            download_episode(audio_url, tmp_file.name)
            audio_bytes = Path(tmp_file.name).read_bytes()
            Path(tmp_file.name).unlink()

        # Create safe filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[
            :50
        ]
        filename = f"{safe_title}.mp3"

        st.session_state.file_for_processing = {
            "bytes": audio_bytes,
            "filename": filename,
        }
        # Store chapter info if available
        st.session_state.chapter_info = chapter_info
        # Store episode description if available
        st.session_state.episode_description = description
        # Clear search state
        st.session_state.selected_podcast = None
        st.session_state.podcast_episodes = None

    # Check if we already have a file to process
    if st.session_state.file_for_processing:
        # Show the file info
        st.success(
            f"Ready to process: {st.session_state.file_for_processing['filename']}"
        )
        if st.button("Choose different file"):
            st.session_state.file_for_processing = None
            st.session_state.chapter_info = None
            st.session_state.episode_description = None
            st.rerun()
    else:
        # Show file source options using tabs
        search_tab, upload_tab = st.tabs(["Search Online", "Upload Local File"])

        with search_tab:
            # Search type toggle
            search_type = st.radio(
                "Search for",
                ["Podcasts", "Episodes"],
                horizontal=True,
                help="Search by podcast name or search for specific episodes",
            )

            # Search input
            search_query = st.text_input(
                "Search",
                placeholder="Enter podcast or episode name...",
                key="podcast_search_query",
            )

            # Only show search results if no podcast is selected
            if search_query and not st.session_state.selected_podcast:
                if search_type == "Podcasts":
                    # Search for podcasts
                    with st.spinner("Searching podcasts..."):
                        try:
                            podcasts = search_podcasts(search_query)
                        except Exception as e:
                            st.error(f"Error searching podcasts: {e}")
                            podcasts = []

                    if podcasts:
                        st.markdown(f"**Found {len(podcasts)} podcasts:**")

                        for podcast in podcasts:
                            col1, col2 = st.columns([1, 4])

                            with col1:
                                if podcast.get("artwork_url"):
                                    st.image(podcast["artwork_url"], width=80)

                            with col2:
                                st.markdown(f"**{podcast['name']}**")
                                st.caption(f"by {podcast.get('author', 'Unknown')}")

                                if podcast.get("feed_url"):
                                    if st.button(
                                        "View Episodes", key=f"view_{podcast['id']}"
                                    ):
                                        st.session_state.selected_podcast = podcast
                                        st.session_state.podcast_episodes = None
                                        st.rerun()

                            st.markdown("---")
                    else:
                        st.info("No podcasts found. Try a different search term.")

                else:  # Episodes
                    # Search for episodes directly (cache results for pagination)
                    if st.session_state.cached_episode_search["query"] != search_query:
                        with st.spinner("Searching episodes..."):
                            try:
                                # Fetch more results for pagination (iTunes allows up to 200)
                                episodes = search_episodes(search_query, limit=200)
                                st.session_state.cached_episode_search = {
                                    "query": search_query,
                                    "results": episodes,
                                }
                                st.session_state.search_episode_page = 0
                            except Exception as e:
                                st.error(f"Error searching episodes: {e}")
                                st.session_state.cached_episode_search = {
                                    "query": search_query,
                                    "results": [],
                                }

                    episodes = st.session_state.cached_episode_search["results"]

                    if episodes:
                        total_episodes = len(episodes)
                        per_page = st.session_state.episodes_per_page
                        total_pages = (total_episodes + per_page - 1) // per_page
                        current_page = st.session_state.search_episode_page

                        # Page size selector and page info
                        ctrl_col1, ctrl_col2 = st.columns([1, 2])
                        with ctrl_col1:
                            new_per_page = st.selectbox(
                                "Results per page",
                                options=[10, 25, 50],
                                index=[10, 25, 50].index(per_page),
                                key="search_per_page_select",
                            )
                            if new_per_page != per_page:
                                st.session_state.episodes_per_page = new_per_page
                                st.session_state.search_episode_page = 0
                                st.rerun()
                        with ctrl_col2:
                            start_idx = current_page * per_page + 1
                            end_idx = min((current_page + 1) * per_page, total_episodes)
                            st.markdown(
                                f"**Showing {start_idx}-{end_idx} of {total_episodes} episodes**"
                            )

                        # Get current page of episodes
                        page_start = current_page * per_page
                        page_end = page_start + per_page
                        page_episodes = episodes[page_start:page_end]

                        for episode in page_episodes:
                            col1, col2, col3 = st.columns([1, 3, 1])

                            with col1:
                                if episode.get("artwork_url"):
                                    st.image(episode["artwork_url"], width=80)

                            with col2:
                                st.markdown(f"**{episode['title']}**")
                                st.caption(
                                    f"from {episode.get('podcast_name', 'Unknown')}"
                                )
                                duration = format_duration(episode.get("duration_ms"))
                                if duration:
                                    st.caption(f"Duration: {duration}")

                            with col3:
                                if episode.get("audio_url"):
                                    if st.button(
                                        "Select",
                                        key=f"sel_ep_{episode['id']}",
                                        type="primary",
                                    ):
                                        with st.spinner("Downloading..."):
                                            try:
                                                download_and_store_episode(
                                                    episode["audio_url"],
                                                    episode["title"],
                                                    description=episode.get(
                                                        "description"
                                                    ),
                                                )
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Download failed: {e}")

                            # Show description expander if available
                            ep_description = episode.get("description")
                            if ep_description:
                                with st.expander("📝 Description", expanded=False):
                                    st.html(ep_description)

                            st.markdown("---")

                        # Previous/Next navigation buttons
                        if total_pages > 1:
                            nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                            with nav_col1:
                                if current_page > 0:
                                    if st.button("← Previous", key="search_prev"):
                                        st.session_state.search_episode_page -= 1
                                        st.rerun()
                            with nav_col2:
                                st.markdown(
                                    f"<div style='text-align: center'>Page {current_page + 1} of {total_pages}</div>",
                                    unsafe_allow_html=True,
                                )
                            with nav_col3:
                                if current_page < total_pages - 1:
                                    if st.button("Next →", key="search_next"):
                                        st.session_state.search_episode_page += 1
                                        st.rerun()
                    else:
                        st.info("No episodes found. Try a different search term.")

            # Show selected podcast's episodes
            if st.session_state.selected_podcast:
                podcast = st.session_state.selected_podcast

                st.markdown("---")
                col1, col2 = st.columns([1, 4])
                with col1:
                    if podcast.get("artwork_url"):
                        st.image(podcast["artwork_url"], width=100)
                with col2:
                    st.subheader(podcast["name"])
                    st.caption(f"by {podcast.get('author', 'Unknown')}")

                if st.button("Back to search results"):
                    st.session_state.selected_podcast = None
                    st.session_state.podcast_episodes = None
                    st.session_state.feed_episode_page = 0
                    st.rerun()

                # Fetch episodes if not already loaded
                if st.session_state.podcast_episodes is None:
                    with st.spinner("Loading episodes..."):
                        try:
                            st.session_state.podcast_episodes = get_podcast_episodes(
                                podcast["feed_url"],
                                extract_chapters=True,  # Extract chapters from RSS
                            )
                            st.session_state.feed_episode_page = 0
                        except Exception as e:
                            st.error(f"Error loading episodes: {e}")
                            st.session_state.podcast_episodes = []

                all_episodes = st.session_state.podcast_episodes
                if all_episodes:
                    # Search within podcast episodes
                    episode_filter = st.text_input(
                        "Search within this podcast",
                        placeholder="Filter episodes by title...",
                        key="feed_episode_filter",
                    )

                    # Filter episodes if search term provided
                    if episode_filter:
                        filter_lower = episode_filter.lower()
                        episodes = [
                            ep
                            for ep in all_episodes
                            if filter_lower in ep.get("title", "").lower()
                        ]
                        # Reset to first page when filter changes
                        if (
                            "last_feed_filter" not in st.session_state
                            or st.session_state.last_feed_filter != episode_filter
                        ):
                            st.session_state.feed_episode_page = 0
                            st.session_state.last_feed_filter = episode_filter
                    else:
                        episodes = all_episodes
                        st.session_state.last_feed_filter = ""

                    total_episodes = len(episodes)
                    per_page = st.session_state.episodes_per_page
                    total_pages = max(1, (total_episodes + per_page - 1) // per_page)
                    current_page = min(
                        st.session_state.feed_episode_page, total_pages - 1
                    )

                    if total_episodes > 0:
                        # Page size selector and page info
                        ctrl_col1, ctrl_col2 = st.columns([1, 2])
                        with ctrl_col1:
                            new_per_page = st.selectbox(
                                "Results per page",
                                options=[10, 25, 50],
                                index=[10, 25, 50].index(per_page),
                                key="feed_per_page_select",
                            )
                            if new_per_page != per_page:
                                st.session_state.episodes_per_page = new_per_page
                                st.session_state.feed_episode_page = 0
                                st.rerun()
                        with ctrl_col2:
                            start_idx = current_page * per_page + 1
                            end_idx = min((current_page + 1) * per_page, total_episodes)
                            st.markdown(
                                f"**Showing {start_idx}-{end_idx} of {total_episodes} episodes**"
                            )

                        # Get current page of episodes
                        page_start = current_page * per_page
                        page_end = page_start + per_page
                        page_episodes = episodes[page_start:page_end]

                        for i, episode in enumerate(page_episodes):
                            col1, col2 = st.columns([4, 1])

                            with col1:
                                st.markdown(f"**{episode['title']}**")
                                duration = format_duration_str(episode.get("duration"))
                                if duration:
                                    st.caption(f"Duration: {duration}")
                                if episode.get("release_date"):
                                    st.caption(
                                        f"Released: {episode['release_date'][:10]}"
                                    )

                            with col2:
                                if episode.get("audio_url"):
                                    # Show chapter indicator if available
                                    ep_chapters = episode.get("chapters")
                                    if ep_chapters and ep_chapters.has_chapters:
                                        st.caption(
                                            f"📑 {len(ep_chapters.chapters)} chapters"
                                        )
                                    if st.button(
                                        "Select",
                                        key=f"sel_feed_{page_start + i}",
                                        type="primary",
                                    ):
                                        with st.spinner("Downloading..."):
                                            try:
                                                download_and_store_episode(
                                                    episode["audio_url"],
                                                    episode["title"],
                                                    chapter_info=episode.get(
                                                        "chapters"
                                                    ),
                                                    description=episode.get(
                                                        "description"
                                                    ),
                                                )
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Download failed: {e}")

                            # Show description expander if available
                            ep_description = episode.get("description")
                            if ep_description:
                                with st.expander("📝 Description", expanded=False):
                                    st.html(ep_description)

                            st.markdown("---")

                        # Previous/Next navigation buttons
                        if total_pages > 1:
                            nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                            with nav_col1:
                                if current_page > 0:
                                    if st.button("← Previous", key="feed_prev"):
                                        st.session_state.feed_episode_page -= 1
                                        st.rerun()
                            with nav_col2:
                                st.markdown(
                                    f"<div style='text-align: center'>Page {current_page + 1} of {total_pages}</div>",
                                    unsafe_allow_html=True,
                                )
                            with nav_col3:
                                if current_page < total_pages - 1:
                                    if st.button("Next →", key="feed_next"):
                                        st.session_state.feed_episode_page += 1
                                        st.rerun()
                    else:
                        st.info("No episodes match your search.")

        with upload_tab:
            uploaded_file = st.file_uploader(
                "Upload MP3 file", type=["mp3"], key="upload_local"
            )
            if uploaded_file is not None:
                # Store uploaded file in session state
                st.session_state.file_for_processing = {
                    "bytes": uploaded_file.getvalue(),
                    "filename": uploaded_file.name,
                }
                # For uploaded files, we'll try to extract chapters from the audio during processing
                # Clear any existing chapter info and description (no RSS data for uploads)
                st.session_state.chapter_info = None
                st.session_state.episode_description = None
                st.rerun()

    # Only show processing options if we have a file
    if st.session_state.file_for_processing:
        file_bytes = st.session_state.file_for_processing["bytes"]
        file_name = st.session_state.file_for_processing["filename"]

        st.markdown("---")
        st.subheader("Processing Options")

        col1, col2, col3 = st.columns(3)

        with col1:
            split_length = st.slider(
                "Chunk Length (minutes)",
                min_value=1,
                max_value=60,
                value=10,
                help="How long each split chunk should be",
            )

        with col2:
            db_change = st.slider(
                "Volume Adjustment (dB)",
                min_value=-20,
                max_value=30,
                value=10,
                key="full_process_db",
                help="Positive values increase volume",
            )

        with col3:
            speed = st.slider(
                "Playback Speed",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                key="full_process_speed",
                help="1.0 = normal, 1.5 = 50% faster, 0.75 = 25% slower",
            )

        # Chapter-aware splitting options
        chapter_info = st.session_state.chapter_info
        has_chapters = chapter_info is not None and chapter_info.has_chapters

        # Split mode selector
        split_mode_options = ["Fixed Intervals", "By Chapters", "Hybrid"]
        split_mode_help = {
            "Fixed Intervals": "Split every N minutes (current behavior)",
            "By Chapters": "Split at chapter boundaries only",
            "Hybrid": "Split at chapters, but also split long chapters",
        }

        # Default to "By Chapters" if chapters are available, else "Fixed Intervals"
        default_mode_index = 1 if has_chapters else 0

        split_mode_label = st.radio(
            "Split Mode",
            split_mode_options,
            index=default_mode_index,
            horizontal=True,
            help="How to split the audio into parts",
        )

        # Map label to SplitMode enum
        split_mode_map = {
            "Fixed Intervals": SplitMode.FIXED,
            "By Chapters": SplitMode.CHAPTERS,
            "Hybrid": SplitMode.HYBRID,
        }
        split_mode = split_mode_map[split_mode_label]

        # Show warning if chapter mode selected but no chapters
        if split_mode != SplitMode.FIXED and not has_chapters:
            st.warning("No chapters detected. Will use fixed intervals instead.")

        # Chapter preview if available
        if has_chapters:
            with st.expander(
                f"📑 Preview Chapters ({len(chapter_info.chapters)} chapters)",
                expanded=False,
            ):
                for i, ch in enumerate(chapter_info.chapters):
                    st.markdown(f"**{i + 1}. {ch.title}** — {ch.start_time_str()}")

        # Episode description if available
        episode_description = st.session_state.episode_description
        if episode_description:
            with st.expander("📝 Episode Description", expanded=False):
                # Use unsafe_allow_html to render HTML content properly
                st.html(episode_description)

        # TOC option (only show if chapters available)
        generate_toc = False
        if has_chapters:
            generate_toc = st.checkbox(
                "Generate Table of Contents",
                value=True,
                help="Create a spoken TOC as the first file, listing chapters and their part numbers",
            )

        use_part_numbers = st.checkbox(
            "Use simple part numbers",
            value=True,
            help="If checked, intro will be 'Part 1', 'Part 2', etc. Otherwise uses full filename.",
        )
        st.audio(file_bytes, format="audio/mp3")

        # Estimate processing time based on file size and settings
        file_size_mb = len(file_bytes) / (1024 * 1024)
        # Estimate audio duration: ~1 MB per minute for typical MP3 at 128kbps
        estimated_duration_min = file_size_mb * 1.0
        # After speed adjustment, duration changes
        adjusted_duration_min = (
            estimated_duration_min / speed if speed != 1.0 else estimated_duration_min
        )
        estimated_chunks = max(1, int(adjusted_duration_min / split_length) + 1)
        estimated_time = estimate_processing_time(file_size_mb, speed, estimated_chunks)
        st.info(
            f"Estimated processing time: {format_time(estimated_time)} ({estimated_chunks} chunks)"
        )

        if st.button("Process File", type="primary", key="full_process_btn"):
            # Reset cancel flag at start of processing
            st.session_state.cancel_requested = False

            start_time = time.time()
            chunk_times = []  # Track time per chunk for estimation

            # Create progress bar, status text, and cancel button
            progress_bar = st.progress(0)
            status_text = st.empty()
            cancel_container = st.empty()
            cancel_container.button(
                "Cancel", key="cancel_full_process", on_click=request_cancel
            )

            # Create temp directory for processing
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_dir = Path(tmp_dir)

                # Save file to temp directory
                input_path = tmp_dir / file_name
                input_path.write_bytes(file_bytes)

                last_chunk_time = [
                    start_time
                ]  # Use list to allow mutation in nested function

                def update_progress(current, total, message):
                    # Check for cancellation
                    if st.session_state.cancel_requested:
                        raise ProcessingCancelled("Processing cancelled by user")

                    now = time.time()
                    elapsed = now - start_time

                    # Track chunk processing times
                    if current > 0 and total > 1:
                        chunk_time = now - last_chunk_time[0]
                        chunk_times.append(chunk_time)
                        last_chunk_time[0] = now

                    # Calculate ETA
                    if current > 0 and total > 0 and chunk_times:
                        avg_chunk_time = sum(chunk_times) / len(chunk_times)
                        remaining_chunks = total - current
                        eta_seconds = remaining_chunks * avg_chunk_time
                        eta_str = f" | ETA: {format_time(eta_seconds, prefix='')}"
                    else:
                        eta_str = ""

                    # Format elapsed time
                    elapsed_str = f"Elapsed: {format_time(elapsed, prefix='')}"

                    if total > 0:
                        progress_bar.progress(current / total)
                    status_text.text(f"{message} | {elapsed_str}{eta_str}")

                try:
                    # Run full processing with progress callback
                    output_folder = full_process_podcast_episode(
                        filepath=input_path,
                        db_change=db_change,
                        split_length=split_length,
                        use_part_numbers_only=use_part_numbers,
                        progress_callback=update_progress,
                        speed=speed,
                        split_mode=split_mode,
                        chapter_info=chapter_info,
                        generate_toc=generate_toc,
                    )

                    # Update progress for zip creation
                    elapsed = time.time() - start_time
                    status_text.text(
                        f"Creating ZIP file... | Elapsed: {format_time(elapsed, prefix='')}"
                    )

                    # Create zip file of all processed chunks
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(
                        zip_buffer, "w", zipfile.ZIP_DEFLATED
                    ) as zip_file:
                        for mp3_file in output_folder.glob("louder_*.mp3"):
                            zip_file.write(mp3_file, mp3_file.name)

                    zip_buffer.seek(0)

                    # Clear progress indicators and cancel button
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()

                    # Count files
                    processed_files = sorted(output_folder.glob("louder_*.mp3"))
                    num_files = len(processed_files)
                    elapsed_time = time.time() - start_time
                    st.success(
                        f"Processing complete! Created {num_files} chunks in {format_time(elapsed_time, prefix='')}."
                    )

                    # Save to archive
                    archive_settings = {
                        "volume_db": db_change,
                        "speed": speed,
                        "split_length": split_length,
                        "split_mode": split_mode_label,
                        "use_part_numbers": use_part_numbers,
                        "generate_toc": generate_toc if has_chapters else False,
                    }
                    save_to_archive(
                        title=Path(file_name).stem,
                        source_type="podcast",
                        settings=archive_settings,
                        num_chunks=num_files,
                        output_folder=output_folder,
                    )

                    # Clear the file_for_processing, chapter_info, and description after successful processing
                    if st.session_state.file_for_processing:
                        st.session_state.file_for_processing = None
                    st.session_state.chapter_info = None
                    st.session_state.episode_description = None

                    # Preview first chunk
                    if processed_files:
                        st.markdown("**Preview first chunk:**")
                        first_chunk_bytes = processed_files[0].read_bytes()
                        st.audio(first_chunk_bytes, format="audio/mp3")

                    # Download button for zip
                    zip_filename = f"{Path(file_name).stem}_processed.zip"
                    st.download_button(
                        label="Download All Processed Files (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name=zip_filename,
                        mime="application/zip",
                    )

                except ProcessingCancelled:
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()
                    st.warning("Processing cancelled.")
                    st.session_state.cancel_requested = False

                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()
                    st.error(f"Error processing file: {e}")


# =============================================================================
# YouTube Audio Download
# =============================================================================
elif mode == "YouTube Audio":
    st.header("YouTube Audio")
    st.markdown(
        """
    Download audio from a YouTube video. Just paste the video URL below.
    """
    )

    # Initialize session state for YouTube
    if "youtube_file_for_processing" not in st.session_state:
        st.session_state.youtube_file_for_processing = None

    def download_and_store_youtube(url: str, title: str):
        """Download YouTube audio and store it in session state for processing."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        # Download the audio
        downloaded_path = download_youtube_audio(url, tmp_path)
        audio_bytes = downloaded_path.read_bytes()
        downloaded_path.unlink(missing_ok=True)

        # Create safe filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[
            :50
        ]
        filename = f"{safe_title}.mp3"

        st.session_state.youtube_file_for_processing = {
            "bytes": audio_bytes,
            "filename": filename,
        }

    # Check if we already have a file to process
    if st.session_state.youtube_file_for_processing:
        # Show the file info
        st.success(
            f"Ready to process: {st.session_state.youtube_file_for_processing['filename']}"
        )
        if st.button("Download different video", key="youtube_choose_different"):
            st.session_state.youtube_file_for_processing = None
            st.rerun()
    else:
        # URL input
        youtube_url = st.text_input(
            "YouTube URL",
            placeholder="https://www.youtube.com/watch?v=...",
            key="youtube_url_input",
        )

        if youtube_url:
            # Validate URL
            if not is_valid_youtube_url(youtube_url):
                st.error("Please enter a valid YouTube URL")
            else:
                # Fetch video info
                with st.spinner("Fetching video info..."):
                    try:
                        video_info = get_video_info(youtube_url)

                        col1, col2 = st.columns([1, 3])
                        with col1:
                            if video_info.get("thumbnail"):
                                st.image(video_info["thumbnail"], width=160)
                        with col2:
                            st.markdown(f"**{video_info['title']}**")
                            st.caption(f"by {video_info.get('uploader', 'Unknown')}")
                            duration = format_youtube_duration(
                                video_info.get("duration")
                            )
                            if duration:
                                st.caption(f"Duration: {duration}")

                        if st.button(
                            "Download Audio", type="primary", key="youtube_download_btn"
                        ):
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            def update_progress(percent, status):
                                progress_bar.progress(min(percent / 100, 1.0))
                                status_text.text(status)

                            try:
                                with st.spinner("Downloading and converting..."):
                                    download_and_store_youtube(
                                        youtube_url, video_info["title"]
                                    )
                                progress_bar.empty()
                                status_text.empty()
                                st.rerun()
                            except Exception as e:
                                progress_bar.empty()
                                status_text.empty()
                                st.error(f"Download failed: {e}")

                    except Exception as e:
                        st.error(f"Error fetching video info: {e}")

    # Only show processing options if we have a file
    if st.session_state.youtube_file_for_processing:
        file_bytes = st.session_state.youtube_file_for_processing["bytes"]
        file_name = st.session_state.youtube_file_for_processing["filename"]

        st.markdown("---")
        st.subheader("Processing Options")

        col1, col2, col3 = st.columns(3)

        with col1:
            split_length = st.slider(
                "Chunk Length (minutes)",
                min_value=1,
                max_value=60,
                value=10,
                key="youtube_split_length",
                help="How long each split chunk should be",
            )

        with col2:
            db_change = st.slider(
                "Volume Adjustment (dB)",
                min_value=-20,
                max_value=30,
                value=10,
                key="youtube_db",
                help="Positive values increase volume",
            )

        with col3:
            speed = st.slider(
                "Playback Speed",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                key="youtube_speed",
                help="1.0 = normal, 1.5 = 50% faster, 0.75 = 25% slower",
            )

        use_part_numbers = st.checkbox(
            "Use simple part numbers",
            value=True,
            key="youtube_part_numbers",
            help="If checked, intro will be 'Part 1', 'Part 2', etc. Otherwise uses full filename.",
        )
        st.audio(file_bytes, format="audio/mp3")

        # Estimate processing time based on file size and settings
        file_size_mb = len(file_bytes) / (1024 * 1024)
        # Estimate audio duration: ~1 MB per minute for typical MP3 at 128kbps
        estimated_duration_min = file_size_mb * 1.0
        # After speed adjustment, duration changes
        adjusted_duration_min = (
            estimated_duration_min / speed if speed != 1.0 else estimated_duration_min
        )
        estimated_chunks = max(1, int(adjusted_duration_min / split_length) + 1)
        estimated_time = estimate_processing_time(file_size_mb, speed, estimated_chunks)
        st.info(
            f"Estimated processing time: {format_time(estimated_time)} ({estimated_chunks} chunks)"
        )

        if st.button("Process File", type="primary", key="youtube_process_btn"):
            # Reset cancel flag at start of processing
            st.session_state.cancel_requested = False

            start_time = time.time()
            chunk_times = []  # Track time per chunk for estimation

            # Create progress bar, status text, and cancel button
            progress_bar = st.progress(0)
            status_text = st.empty()
            cancel_container = st.empty()
            cancel_container.button(
                "Cancel", key="cancel_youtube_process", on_click=request_cancel
            )

            # Create temp directory for processing
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_dir = Path(tmp_dir)

                # Save file to temp directory
                input_path = tmp_dir / file_name
                input_path.write_bytes(file_bytes)

                last_chunk_time = [
                    start_time
                ]  # Use list to allow mutation in nested function

                def update_progress(current, total, message):
                    # Check for cancellation
                    if st.session_state.cancel_requested:
                        raise ProcessingCancelled("Processing cancelled by user")

                    now = time.time()
                    elapsed = now - start_time

                    # Track chunk processing times
                    if current > 0 and total > 1:
                        chunk_time = now - last_chunk_time[0]
                        chunk_times.append(chunk_time)
                        last_chunk_time[0] = now

                    # Calculate ETA
                    if current > 0 and total > 0 and chunk_times:
                        avg_chunk_time = sum(chunk_times) / len(chunk_times)
                        remaining_chunks = total - current
                        eta_seconds = remaining_chunks * avg_chunk_time
                        eta_str = f" | ETA: {format_time(eta_seconds, prefix='')}"
                    else:
                        eta_str = ""

                    # Format elapsed time
                    elapsed_str = f"Elapsed: {format_time(elapsed, prefix='')}"

                    if total > 0:
                        progress_bar.progress(current / total)
                    status_text.text(f"{message} | {elapsed_str}{eta_str}")

                try:
                    # Run full processing with progress callback
                    output_folder = full_process_podcast_episode(
                        filepath=input_path,
                        db_change=db_change,
                        split_length=split_length,
                        use_part_numbers_only=use_part_numbers,
                        progress_callback=update_progress,
                        speed=speed,
                    )

                    # Update progress for zip creation
                    elapsed = time.time() - start_time
                    status_text.text(
                        f"Creating ZIP file... | Elapsed: {format_time(elapsed, prefix='')}"
                    )

                    # Create zip file of all processed chunks
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(
                        zip_buffer, "w", zipfile.ZIP_DEFLATED
                    ) as zip_file:
                        for mp3_file in output_folder.glob("louder_*.mp3"):
                            zip_file.write(mp3_file, mp3_file.name)

                    zip_buffer.seek(0)

                    # Clear progress indicators and cancel button
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()

                    # Count files
                    processed_files = sorted(output_folder.glob("louder_*.mp3"))
                    num_files = len(processed_files)
                    elapsed_time = time.time() - start_time
                    st.success(
                        f"Processing complete! Created {num_files} chunks in {format_time(elapsed_time, prefix='')}."
                    )

                    # Save to archive
                    archive_settings = {
                        "volume_db": db_change,
                        "speed": speed,
                        "split_length": split_length,
                        "use_part_numbers": use_part_numbers,
                    }
                    save_to_archive(
                        title=Path(file_name).stem,
                        source_type="youtube",
                        settings=archive_settings,
                        num_chunks=num_files,
                        output_folder=output_folder,
                    )

                    # Clear the file after successful processing
                    if st.session_state.youtube_file_for_processing:
                        st.session_state.youtube_file_for_processing = None

                    # Preview first chunk
                    if processed_files:
                        st.markdown("**Preview first chunk:**")
                        first_chunk_bytes = processed_files[0].read_bytes()
                        st.audio(first_chunk_bytes, format="audio/mp3")

                    # Download button for zip
                    zip_filename = f"{Path(file_name).stem}_processed.zip"
                    st.download_button(
                        label="Download All Processed Files (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name=zip_filename,
                        mime="application/zip",
                    )

                except ProcessingCancelled:
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()
                    st.warning("Processing cancelled.")
                    st.session_state.cancel_requested = False

                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()
                    st.error(f"Error processing file: {e}")


# =============================================================================
# Single File Processing (No Split)
# =============================================================================
elif mode == "Single File (No Split)":
    st.header("Process Single File")
    st.markdown("Upload an MP3 file to add a spoken intro and adjust volume.")

    uploaded_file = st.file_uploader(
        "Upload MP3 file", type=["mp3"], key="single_file_uploader"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        db_change = st.slider(
            "Volume Adjustment (dB)",
            min_value=-20,
            max_value=30,
            value=10,
            help="Positive values increase volume, negative decrease",
        )

    with col2:
        speed = st.slider(
            "Playback Speed",
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.1,
            key="single_file_speed",
            help="1.0 = normal, 1.5 = 50% faster, 0.75 = 25% slower",
        )

    with col3:
        use_custom_intro = st.checkbox("Use custom intro text")
        if use_custom_intro:
            custom_intro = st.text_input(
                "Custom intro text",
                placeholder="e.g., 'Episode 1 - Introduction'",
            )
        else:
            custom_intro = None

    if uploaded_file is not None:
        st.audio(uploaded_file, format="audio/mp3")

        # Estimate processing time based on file size and settings
        file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        estimated_time = estimate_processing_time(file_size_mb, speed, num_chunks=1)
        st.info(f"Estimated processing time: {format_time(estimated_time)}")

        if st.button("Process File", type="primary"):
            # Reset cancel flag at start of processing
            st.session_state.cancel_requested = False

            start_time = time.time()

            # Create status text and cancel button
            status_text = st.empty()
            status_text.text("Processing audio...")
            cancel_container = st.empty()
            cancel_container.button(
                "Cancel", key="cancel_single_file", on_click=request_cancel
            )

            # Save uploaded file to temp location
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name

            try:
                # Check for cancellation before processing
                if st.session_state.cancel_requested:
                    raise ProcessingCancelled("Processing cancelled by user")

                # Process the file
                # Use custom intro if specified, otherwise use the original filename
                if use_custom_intro and custom_intro:
                    intro_text = custom_intro
                else:
                    # Convert filename to spoken text (remove extension, replace underscores)
                    intro_text = Path(uploaded_file.name).stem.replace("_", " ")

                processed_audio = process_pod(
                    filepath=tmp_path,
                    db_change=db_change if db_change != 0 else None,
                    start_audio_text=intro_text,
                    speed=speed,
                )

                # Check for cancellation after processing
                if st.session_state.cancel_requested:
                    raise ProcessingCancelled("Processing cancelled by user")

                # Convert to bytes for download
                audio_bytes = export_audio_to_bytes(processed_audio)

                status_text.empty()
                cancel_container.empty()

                elapsed_time = time.time() - start_time
                st.success(
                    f"Processing complete! Took {format_time(elapsed_time, prefix='')}."
                )

                # Preview processed audio
                st.markdown("**Preview processed audio:**")
                st.audio(audio_bytes, format="audio/mp3")

                # Create download button
                output_filename = f"processed_{uploaded_file.name}"
                st.download_button(
                    label="Download Processed File",
                    data=audio_bytes,
                    file_name=output_filename,
                    mime="audio/mpeg",
                )

            except ProcessingCancelled:
                status_text.empty()
                cancel_container.empty()
                st.warning("Processing cancelled.")
                st.session_state.cancel_requested = False

            except Exception as e:
                status_text.empty()
                cancel_container.empty()
                st.error(f"Error processing file: {e}")

            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)


# =============================================================================
# Batch Process Folder
# =============================================================================
elif mode == "Batch Process Folder":
    st.header("Batch Process Multiple Files")
    st.markdown(
        """
    Upload multiple MP3 files to process them all at once.
    Each file will get a spoken intro (the filename) and volume adjustment.
    """
    )

    uploaded_files = st.file_uploader(
        "Upload MP3 files", type=["mp3"], accept_multiple_files=True
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        db_change = st.slider(
            "Volume Adjustment (dB)",
            min_value=-20,
            max_value=30,
            value=10,
            key="batch_db",
            help="Positive values increase volume",
        )

    with col2:
        speed = st.slider(
            "Playback Speed",
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.1,
            key="batch_speed",
            help="1.0 = normal, 1.5 = 50% faster, 0.75 = 25% slower",
        )

    with col3:
        prefix = st.text_input(
            "Output filename prefix",
            value="louder_",
            help="Text to add before each filename",
        )

    if uploaded_files:
        st.markdown(f"**{len(uploaded_files)} files selected:**")
        for f in uploaded_files:
            st.markdown(f"- {f.name}")

        # Estimate processing time based on total file size and settings
        total_size_mb = sum(len(f.getvalue()) for f in uploaded_files) / (1024 * 1024)
        estimated_time = estimate_processing_time(
            total_size_mb, speed, num_chunks=len(uploaded_files)
        )
        st.info(f"Estimated processing time: {format_time(estimated_time)}")

        if st.button("Process All Files", type="primary", key="batch_btn"):
            # Reset cancel flag at start of processing
            st.session_state.cancel_requested = False

            start_time = time.time()
            total_files = len(uploaded_files)

            # Create progress bar, status text, and cancel button
            progress_bar = st.progress(0)
            status_text = st.empty()
            cancel_container = st.empty()
            cancel_container.button(
                "Cancel", key="cancel_batch", on_click=request_cancel
            )

            # Create temp directory for processing
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_dir = Path(tmp_dir)
                output_dir = tmp_dir / "output"
                output_dir.mkdir()

                # Save all uploaded files
                for uploaded_file in uploaded_files:
                    input_path = tmp_dir / uploaded_file.name
                    input_path.write_bytes(uploaded_file.getvalue())

                try:
                    # Process files one by one so we can check for cancellation
                    processed_count = 0
                    for i, uploaded_file in enumerate(uploaded_files):
                        # Check for cancellation
                        if st.session_state.cancel_requested:
                            raise ProcessingCancelled("Processing cancelled by user")

                        # Update progress
                        elapsed = time.time() - start_time
                        status_text.text(
                            f"Processing {uploaded_file.name} ({i+1}/{total_files})... | Elapsed: {format_time(elapsed, prefix='')}"
                        )
                        progress_bar.progress((i) / total_files)

                        # Process the file
                        input_path = tmp_dir / uploaded_file.name
                        processed_audio = process_pod(
                            filepath=input_path,
                            db_change=db_change,
                            speed=speed,
                        )

                        # Save processed file
                        output_filename = f"{prefix}{Path(uploaded_file.name).stem}.mp3"
                        output_path = output_dir / output_filename
                        processed_audio.export(output_path)
                        processed_count += 1

                    # Final progress update
                    progress_bar.progress(1.0)

                    # Create zip of all processed files
                    elapsed = time.time() - start_time
                    status_text.text(
                        f"Creating ZIP file... | Elapsed: {format_time(elapsed, prefix='')}"
                    )

                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(
                        zip_buffer, "w", zipfile.ZIP_DEFLATED
                    ) as zip_file:
                        for mp3_file in output_dir.glob("*.mp3"):
                            zip_file.write(mp3_file, mp3_file.name)

                    zip_buffer.seek(0)

                    # Clear progress indicators and cancel button
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()

                    num_processed = len(list(output_dir.glob("*.mp3")))
                    elapsed_time = time.time() - start_time
                    st.success(
                        f"Processing complete! Processed {num_processed} files in {format_time(elapsed_time, prefix='')}."
                    )

                    st.download_button(
                        label="Download All Processed Files (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="processed_podcasts.zip",
                        mime="application/zip",
                    )

                except ProcessingCancelled:
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()
                    st.warning(
                        f"Processing cancelled. {processed_count} of {total_files} files were processed."
                    )
                    st.session_state.cancel_requested = False

                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    cancel_container.empty()
                    st.error(f"Error processing files: {e}")


# =============================================================================
# Archive Mode
# =============================================================================
elif mode == "Archive":
    st.header("Processing Archive")
    st.markdown("View and download previously processed podcasts.")

    # Initialize archive
    archive = PodcastArchive()

    # Initialize session state for archive view
    if "archive_view" not in st.session_state:
        st.session_state.archive_view = "list"  # "list" or "info"

    # View selector
    view_tabs = st.tabs(["Archive", "Info"])

    with view_tabs[0]:
        if not archive.records:
            st.info(
                "No processed podcasts in archive yet. Process some podcasts to see them here!"
            )
        else:
            # Statistics
            stats = archive.get_statistics()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Processed", stats["total_records"])
            with col2:
                st.metric("Total Chunks", stats["total_chunks"])
            with col3:
                top_source_name, top_source_count = stats["top_source"]
                st.metric("Top Source", f"{top_source_name} ({top_source_count})")

            st.markdown("---")

            # Search box
            search_query = st.text_input(
                "Search archive",
                placeholder="Search by title or podcast name...",
                key="archive_search",
            )

            # Filter records based on search
            if search_query:
                display_records = archive.search(search_query)
                if not display_records:
                    st.info("No records match your search.")
            else:
                display_records = archive.records

            # Display records in reverse chronological order (newest first)
            display_records = sorted(
                display_records, key=lambda r: r.date, reverse=True
            )

            for record in display_records:
                with st.container():
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**{record.title}**")
                        # Parse and format date
                        try:
                            date_obj = datetime.fromisoformat(record.date)
                            date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                        except:
                            date_str = record.date
                        st.caption(
                            f"Processed: {date_str} | Source: {record.source_type} | Chunks: {record.num_chunks}"
                        )

                    with col2:
                        # Download button for processed files
                        if record.processed_files_dir:
                            processed_dir = Path(record.processed_files_dir)
                            if processed_dir.exists():
                                # Create zip of processed files on-the-fly
                                zip_buffer = BytesIO()
                                with zipfile.ZipFile(
                                    zip_buffer, "w", zipfile.ZIP_DEFLATED
                                ) as zip_file:
                                    for mp3_file in sorted(
                                        processed_dir.glob("louder_*.mp3")
                                    ):
                                        zip_file.write(mp3_file, mp3_file.name)
                                zip_buffer.seek(0)

                                st.download_button(
                                    label="Download",
                                    data=zip_buffer.getvalue(),
                                    file_name=f"{record.title[:30]}_processed.zip",
                                    mime="application/zip",
                                    key=f"download_{record.id}",
                                    use_container_width=True,
                                )
                            else:
                                st.caption("Files not found")
                        else:
                            st.caption("No files")

                    # Settings expander
                    with st.expander("Settings & Details"):
                        st.json(record.settings)

                        # Delete button
                        if st.button(
                            "Delete Record", key=f"delete_{record.id}", type="secondary"
                        ):
                            if archive.delete_record(record.id):
                                st.success("Record deleted!")
                                st.rerun()
                            else:
                                st.error("Failed to delete record")

                    st.markdown("---")

            # Clear all button
            st.markdown("### Archive Management")
            if st.button("Clear Entire Archive", type="secondary"):
                if st.button(
                    "Confirm Clear All", type="secondary", key="confirm_clear"
                ):
                    archive.clear_all()
                    st.success("Archive cleared!")
                    st.rerun()

    with view_tabs[1]:
        st.markdown(
            """
### About the Archive

The archive automatically saves processed podcasts so you can:
- **Download them again** without reprocessing
- **Review processing settings** you used previously
- **Track your listening history**

### What Gets Archived

Every time you process a podcast, the following information is saved:
- **Title and source information**
- **Processing settings** (volume, speed, split length, etc.)
- **Processed audio files** (stored in `~/.audio_tools/archive/`)
- **Processing date and time**
- **Number of chunks created**

### Storage Location

- Archive metadata: `~/.audio_tools/archive/archive.json`
- Processed files: `~/.audio_tools/archive/processed_files/`

### Managing Storage

Each processed podcast takes up disk space. To free up space:
1. Delete individual records from the Archive view
2. Or clear the entire archive using the "Clear Entire Archive" button

Deleting a record removes both the metadata and the associated audio files.
        """
        )
