"""Chapter extraction and splitting logic for podcast episodes."""

import html
import json
import math
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Literal

from gtts import gTTS
from pydub import AudioSegment


class SplitMode(Enum):
    """Mode for splitting audio."""
    FIXED = "fixed"
    CHAPTERS = "chapters"
    HYBRID = "hybrid"


@dataclass
class Chapter:
    """Represents a single chapter in a podcast episode."""
    title: str
    start_ms: int
    end_ms: int | None = None

    @property
    def duration_ms(self) -> int | None:
        """Duration in milliseconds, or None if end_ms is not set."""
        if self.end_ms is not None:
            return self.end_ms - self.start_ms
        return None

    def duration_str(self) -> str:
        """Human-readable duration string."""
        if self.duration_ms is None:
            return "unknown"
        total_seconds = self.duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def start_time_str(self) -> str:
        """Human-readable start time string (HH:MM:SS or MM:SS)."""
        total_seconds = self.start_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass
class ChapterInfo:
    """Container for chapter information from an episode."""
    chapters: list[Chapter] = field(default_factory=list)
    source: Literal["rss", "embedded", "none"] = "none"
    episode_title: str | None = None
    total_duration_ms: int | None = None

    @property
    def has_chapters(self) -> bool:
        """Check if any chapters are available."""
        return len(self.chapters) > 0

    def finalize_end_times(self, total_duration_ms: int) -> None:
        """Set end times for all chapters using next chapter's start or total duration."""
        self.total_duration_ms = total_duration_ms
        for i, chapter in enumerate(self.chapters):
            if chapter.end_ms is None:
                if i + 1 < len(self.chapters):
                    chapter.end_ms = self.chapters[i + 1].start_ms
                else:
                    chapter.end_ms = total_duration_ms


@dataclass
class SplitSegment:
    """Represents a segment of audio to be exported."""
    chapter_title: str
    chapter_index: int
    part_number: int  # Part number within the chapter (1-based)
    total_parts: int  # Total parts this chapter was split into
    start_ms: int
    end_ms: int
    global_part_number: int  # Global part number across all segments (1-based)

    @property
    def is_chapter_start(self) -> bool:
        """Returns True if this segment is the first part of a chapter."""
        return self.part_number == 1


def _parse_timestamp_to_ms(timestamp: str) -> int:
    """Parse timestamp like '00:02:30.000' or '2:30' to milliseconds.

    Supports formats:
    - HH:MM:SS.mmm
    - HH:MM:SS
    - MM:SS
    - SS
    """
    parts = timestamp.replace(',', '.').split(':')

    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        hours = minutes = 0
        seconds = parts[0]

    # Handle fractional seconds
    if '.' in str(seconds):
        sec_parts = str(seconds).split('.')
        seconds = int(sec_parts[0])
        ms = int(sec_parts[1].ljust(3, '0')[:3])
    else:
        seconds = int(float(seconds))
        ms = 0

    total_ms = (int(hours) * 3600 + int(minutes) * 60 + seconds) * 1000 + ms
    return total_ms


def _extract_chapters_from_description(text: str) -> list[Chapter]:
    """Extract chapters from description/show notes text.

    Many podcasts include chapters in their description in formats like:
    - "(00:00) Chapter Title"
    - "(01:23:45) Chapter Title"
    - "00:00 - Chapter Title"
    - "[00:00] Chapter Title"
    - "Chapter Title (00:00:00)" - timestamp after title

    Args:
        text: Description or show notes text that may contain chapters

    Returns:
        List of Chapter objects extracted from the text
    """
    chapters_ts_first = []
    chapters_ts_last = []

    # Pattern 1: Timestamp BEFORE title (at start of line or after brackets)
    # Matches: (00:00) Title, [00:00] Title, 00:00 - Title, etc.
    # The timestamp must be at or near the start, not at the end
    pattern_ts_first = r'(?:^|\n)\s*[\(\[]?(\d{1,2}:\d{2}(?::\d{2})?)\)?[\)\]]?\s*[-–—]?\s*(.+?)(?=\n|$|<)'

    # Pattern 2: Timestamp AFTER title (e.g., "Chapter Title (00:00:00)")
    # Matches: Title (00:00:00) or Title (00:00) at end of line or before </li>
    # Also handles HTML list items: <li>Title (00:00:00)</li>
    pattern_ts_last = r'(?:^|<li>)([^(<\n]+?)\s*\((\d{1,2}:\d{2}(?::\d{2})?)\)\s*(?:$|</li>)'

    # Try pattern 1 (timestamp before title)
    for match in re.finditer(pattern_ts_first, text, re.MULTILINE):
        timestamp_str = match.group(1)
        title = match.group(2).strip()

        # Skip if the "title" ends with a timestamp in parentheses - that's pattern 2
        if re.search(r'\(\d{1,2}:\d{2}(?::\d{2})?\)\s*$', title):
            continue

        # Clean up the title - remove HTML tags and extra whitespace
        title = re.sub(r'<[^>]+>', '', title)
        # Decode HTML entities (e.g., &#8211; -> –, &amp; -> &)
        title = html.unescape(title)
        # Remove leading dashes/hyphens that some podcasts use
        title = re.sub(r'^[-–—]\s*', '', title)
        title = title.strip()

        # Skip empty titles or very short ones
        if len(title) < 2:
            continue

        # Skip if title looks like a URL or contains only special chars
        if title.startswith('http') or not re.search(r'[a-zA-Z]', title):
            continue

        try:
            start_ms = _parse_timestamp_to_ms(timestamp_str)
            chapters_ts_first.append(Chapter(
                title=title,
                start_ms=start_ms,
            ))
        except (ValueError, IndexError):
            continue

    # Try pattern 2 (timestamp after title) - used by 80,000 Hours, etc.
    for match in re.finditer(pattern_ts_last, text, re.MULTILINE):
        title = match.group(1).strip()
        timestamp_str = match.group(2)

        # Clean up the title - remove HTML tags and extra whitespace
        title = re.sub(r'<[^>]+>', '', title)
        # Decode HTML entities
        title = html.unescape(title)
        title = title.strip()

        # Skip empty titles or very short ones
        if len(title) < 2:
            continue

        # Skip if title looks like a URL or contains only special chars
        if title.startswith('http') or not re.search(r'[a-zA-Z]', title):
            continue

        try:
            start_ms = _parse_timestamp_to_ms(timestamp_str)
            chapters_ts_last.append(Chapter(
                title=title,
                start_ms=start_ms,
            ))
        except (ValueError, IndexError):
            continue

    # Choose the pattern that found more chapters (they shouldn't overlap)
    # This avoids mixing formats from the same description
    if len(chapters_ts_last) > len(chapters_ts_first):
        chapters = chapters_ts_last
    else:
        chapters = chapters_ts_first

    # Sort and deduplicate by start time
    chapters.sort(key=lambda c: c.start_ms)

    # Remove duplicates (same start time within 1 second)
    deduplicated = []
    for ch in chapters:
        if not deduplicated or abs(ch.start_ms - deduplicated[-1].start_ms) > 1000:
            deduplicated.append(ch)

    return deduplicated


def extract_chapters_from_rss_entry(entry: dict) -> ChapterInfo:
    """Extract chapter information from a feedparser RSS entry.

    Looks for chapters in multiple formats:
    1. Podlove Simple Chapters (psc:chapters namespace)
    2. Chapters embedded in description/show notes text

    Args:
        entry: A feedparser entry dict from an RSS feed

    Returns:
        ChapterInfo with chapters extracted from RSS, or empty ChapterInfo if none found
    """
    chapters = []

    # feedparser parses PSC chapters into 'psc_chapters' attribute
    # The format is a dict with 'chapters' key containing list of chapter dicts
    psc_data = entry.get('psc_chapters', {})

    # Handle both possible structures
    if isinstance(psc_data, dict):
        # Try both 'chapters' (common) and 'chapter' (some feeds)
        psc_chapters = psc_data.get('chapters', []) or psc_data.get('chapter', [])
    elif isinstance(psc_data, list):
        psc_chapters = psc_data
    else:
        psc_chapters = []

    # Also check for top-level 'chapters' key (some feeds use this)
    if not psc_chapters:
        psc_chapters = entry.get('chapters', [])

    for psc in psc_chapters:
        start_str = psc.get('start', '00:00:00.000')
        start_ms = _parse_timestamp_to_ms(start_str)

        chapters.append(Chapter(
            title=psc.get('title', 'Untitled'),
            start_ms=start_ms,
        ))

    # If no PSC chapters found, try parsing from description/content
    if not chapters:
        # Try summary first, then content
        description_text = entry.get('summary', '')

        # Also check content (some feeds put chapters there)
        content_list = entry.get('content', [])
        if content_list and isinstance(content_list, list):
            for content_item in content_list:
                if isinstance(content_item, dict):
                    description_text += '\n' + content_item.get('value', '')

        if description_text:
            chapters = _extract_chapters_from_description(description_text)

    # Sort chapters by start time
    chapters.sort(key=lambda c: c.start_ms)

    source = "rss" if chapters else "none"
    return ChapterInfo(
        chapters=chapters,
        source=source,
        episode_title=entry.get('title'),
    )


def extract_chapters_from_audio(filepath: str | Path) -> ChapterInfo:
    """Extract embedded chapter information from an audio file using ffprobe.

    Args:
        filepath: Path to the audio file (MP3, M4A, M4B, etc.)

    Returns:
        ChapterInfo with chapters extracted from audio metadata, or empty if none found
    """
    filepath = Path(filepath)

    try:
        result = subprocess.run(
            ['ffprobe', '-print_format', 'json', '-show_chapters', '-v', 'quiet', str(filepath)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return ChapterInfo(source="none")

        data = json.loads(result.stdout)
        raw_chapters = data.get('chapters', [])

        chapters = []
        for ch in raw_chapters:
            # Times can be in 'start_time' (seconds as string) or 'start' (timebase units)
            start_time = ch.get('start_time')
            end_time = ch.get('end_time')

            if start_time is not None:
                start_ms = int(float(start_time) * 1000)
            else:
                start_ms = 0

            if end_time is not None:
                end_ms = int(float(end_time) * 1000)
            else:
                end_ms = None

            tags = ch.get('tags', {})
            title = tags.get('title', f"Chapter {ch.get('id', len(chapters)) + 1}")

            chapters.append(Chapter(
                title=title,
                start_ms=start_ms,
                end_ms=end_ms,
            ))

        # Sort chapters by start time
        chapters.sort(key=lambda c: c.start_ms)

        source = "embedded" if chapters else "none"
        return ChapterInfo(chapters=chapters, source=source)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        return ChapterInfo(source="none")


def get_chapters(
    rss_entry: dict | None = None,
    audio_path: str | Path | None = None,
) -> ChapterInfo:
    """Get chapter information from available sources with fallback.

    Attempts to extract chapters from RSS first (preferred), then falls back
    to embedded audio chapters if no RSS chapters are found.

    Args:
        rss_entry: Optional feedparser entry dict
        audio_path: Optional path to downloaded audio file

    Returns:
        ChapterInfo from the first source that provides chapters, or empty ChapterInfo
    """
    # Try RSS first (preferred source)
    if rss_entry is not None:
        info = extract_chapters_from_rss_entry(rss_entry)
        if info.has_chapters:
            return info

    # Fall back to embedded chapters
    if audio_path is not None:
        info = extract_chapters_from_audio(audio_path)
        if info.has_chapters:
            return info

    return ChapterInfo(source="none")


def calculate_segments(
    chapter_info: ChapterInfo,
    total_duration_ms: int,
    mode: SplitMode,
    split_length_ms: int = 600000,  # 10 minutes default
) -> list[SplitSegment]:
    """Calculate the split segments based on chapter info and mode.

    Args:
        chapter_info: Chapter information (may be empty)
        total_duration_ms: Total audio duration in milliseconds
        mode: The splitting strategy to use
        split_length_ms: Length for fixed splits or max chapter length for hybrid (in ms)

    Returns:
        List of SplitSegment objects defining each output segment
    """
    if mode == SplitMode.FIXED:
        return _split_fixed(total_duration_ms, split_length_ms)

    # For chapter-aware modes, we need chapters
    if not chapter_info.has_chapters:
        # Fall back to fixed splitting if no chapters available
        return _split_fixed(total_duration_ms, split_length_ms)

    # Ensure end times are set
    chapter_info.finalize_end_times(total_duration_ms)

    if mode == SplitMode.CHAPTERS:
        return _split_by_chapters(chapter_info)
    elif mode == SplitMode.HYBRID:
        return _split_hybrid(chapter_info, split_length_ms)
    else:
        return _split_fixed(total_duration_ms, split_length_ms)


def _split_fixed(
    total_duration_ms: int,
    split_length_ms: int,
) -> list[SplitSegment]:
    """Generate fixed-interval split segments (current behavior)."""
    segments = []
    num_chunks = math.ceil(total_duration_ms / split_length_ms)

    for i in range(num_chunks):
        start_ms = i * split_length_ms
        end_ms = min((i + 1) * split_length_ms, total_duration_ms)

        segments.append(SplitSegment(
            chapter_title=f"Part {i + 1}",
            chapter_index=i,
            part_number=1,
            total_parts=1,
            start_ms=start_ms,
            end_ms=end_ms,
            global_part_number=i + 1,
        ))

    return segments


def _split_by_chapters(chapter_info: ChapterInfo) -> list[SplitSegment]:
    """Generate split segments at chapter boundaries."""
    segments = []

    for i, chapter in enumerate(chapter_info.chapters):
        segments.append(SplitSegment(
            chapter_title=chapter.title,
            chapter_index=i,
            part_number=1,
            total_parts=1,
            start_ms=chapter.start_ms,
            end_ms=chapter.end_ms,
            global_part_number=i + 1,
        ))

    return segments


def _split_hybrid(
    chapter_info: ChapterInfo,
    max_length_ms: int,
) -> list[SplitSegment]:
    """Generate hybrid split segments (chapters + split long chapters)."""
    segments = []
    global_part = 0

    for chapter_idx, chapter in enumerate(chapter_info.chapters):
        chapter_duration = chapter.end_ms - chapter.start_ms

        if chapter_duration <= max_length_ms:
            # Single segment for this chapter
            global_part += 1
            segments.append(SplitSegment(
                chapter_title=chapter.title,
                chapter_index=chapter_idx,
                part_number=1,
                total_parts=1,
                start_ms=chapter.start_ms,
                end_ms=chapter.end_ms,
                global_part_number=global_part,
            ))
        else:
            # Split chapter into multiple parts with even distribution
            num_parts = math.ceil(chapter_duration / max_length_ms)
            part_length = chapter_duration / num_parts

            for part_idx in range(num_parts):
                global_part += 1
                start = chapter.start_ms + int(part_idx * part_length)
                end = chapter.start_ms + int((part_idx + 1) * part_length)

                # Ensure last part ends exactly at chapter end
                if part_idx == num_parts - 1:
                    end = chapter.end_ms

                segments.append(SplitSegment(
                    chapter_title=chapter.title,
                    chapter_index=chapter_idx,
                    part_number=part_idx + 1,
                    total_parts=num_parts,
                    start_ms=start,
                    end_ms=end,
                    global_part_number=global_part,
                ))

    return segments


def generate_toc_entries(segments: list[SplitSegment]) -> list[tuple[str, int]]:
    """Generate table of contents entries (chapter_title, part_number).

    Only includes the first part of each chapter.

    Args:
        segments: List of SplitSegment objects

    Returns:
        List of (chapter_title, global_part_number) tuples
    """
    entries = []
    for segment in segments:
        if segment.is_chapter_start:
            entries.append((segment.chapter_title, segment.global_part_number))
    return entries


def generate_toc_text(segments: list[SplitSegment], episode_title: str | None = None) -> str:
    """Generate text representation of TOC for display in UI.

    Args:
        segments: List of SplitSegment objects
        episode_title: Optional episode title

    Returns:
        Formatted text string showing the TOC
    """
    entries = generate_toc_entries(segments)

    lines = []
    if episode_title:
        lines.append(f"Table of contents for: {episode_title}")
    else:
        lines.append("Table of contents")
    lines.append("")

    for title, part_num in entries:
        lines.append(f"  {title}, Part {part_num}")

    return "\n".join(lines)


def generate_toc_audio(
    segments: list[SplitSegment],
    episode_title: str | None = None,
) -> AudioSegment:
    """Generate a spoken Table of Contents audio segment.

    Creates TTS audio announcing each chapter with its starting part number.
    Example: "Table of contents. Introduction, Part 1. Main Topic, Part 3."

    Args:
        segments: List of SplitSegment objects
        episode_title: Optional episode title to include in intro

    Returns:
        AudioSegment containing the spoken TOC
    """
    entries = generate_toc_entries(segments)

    # Build the spoken text
    if episode_title:
        text = f"Table of contents for {episode_title}. "
    else:
        text = "Table of contents. "

    for title, part_num in entries:
        text += f"{title}, Part {part_num}. "

    # Generate TTS audio
    audio = gTTS(text=text)
    audio_file = BytesIO()
    audio.write_to_fp(audio_file)
    audio_file.seek(0)

    return AudioSegment.from_mp3(audio_file)
