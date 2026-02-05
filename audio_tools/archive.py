"""
Podcast Archive - Track processed podcasts and their settings.

This module provides functionality to:
- Log processed podcasts with their settings
- View processing history
- Re-download previously processed podcasts
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict


@dataclass
class PodcastRecord:
    """A record of a processed podcast episode."""

    id: str  # Unique identifier (timestamp-based)
    title: str
    processed_date: str  # ISO format datetime string

    # Processing settings
    db_change: int
    speed: float
    split_length: Optional[int] = None  # None for unsplit files
    split_mode: Optional[str] = None
    use_part_numbers: bool = True
    generate_toc: bool = False

    # Source information
    source_type: str = "unknown"  # "podcast", "youtube", "upload"
    audio_url: Optional[str] = None
    podcast_name: Optional[str] = None
    episode_description: Optional[str] = None
    artwork_url: Optional[str] = None
    duration: Optional[str] = None

    # Processing results
    num_chunks: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PodcastRecord':
        """Create from dictionary."""
        return cls(**data)


class PodcastArchive:
    """Manages the podcast processing archive."""

    def __init__(self, archive_path: Optional[Path] = None):
        """Initialize the archive.

        Args:
            archive_path: Path to the archive JSON file. If None, uses default location
                         in user's home directory (~/.audio_tools/archive.json)
        """
        if archive_path is None:
            archive_dir = Path.home() / ".audio_tools"
            archive_dir.mkdir(exist_ok=True)
            archive_path = archive_dir / "archive.json"

        self.archive_path = Path(archive_path)
        self._ensure_archive_exists()

    def _ensure_archive_exists(self):
        """Create archive file if it doesn't exist."""
        if not self.archive_path.exists():
            self._save_records([])

    def _load_records(self) -> List[PodcastRecord]:
        """Load all records from the archive."""
        try:
            with open(self.archive_path, 'r') as f:
                data = json.load(f)
                return [PodcastRecord.from_dict(record) for record in data]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_records(self, records: List[PodcastRecord]):
        """Save all records to the archive."""
        with open(self.archive_path, 'w') as f:
            json.dump([record.to_dict() for record in records], f, indent=2)

    def add_record(self, record: PodcastRecord) -> str:
        """Add a new record to the archive.

        Args:
            record: The podcast record to add

        Returns:
            The ID of the added record
        """
        # Generate ID if not provided
        if not record.id:
            record.id = datetime.now().strftime("%Y%m%d_%H%M%S")

        records = self._load_records()
        records.insert(0, record)  # Add to beginning (most recent first)
        self._save_records(records)

        return record.id

    def get_records(self, limit: Optional[int] = None) -> List[PodcastRecord]:
        """Get all records from the archive.

        Args:
            limit: Maximum number of records to return (most recent first)

        Returns:
            List of podcast records
        """
        records = self._load_records()
        if limit:
            return records[:limit]
        return records

    def get_record(self, record_id: str) -> Optional[PodcastRecord]:
        """Get a specific record by ID.

        Args:
            record_id: The ID of the record to retrieve

        Returns:
            The podcast record, or None if not found
        """
        records = self._load_records()
        for record in records:
            if record.id == record_id:
                return record
        return None

    def search_records(self, query: str) -> List[PodcastRecord]:
        """Search records by title or podcast name.

        Args:
            query: Search query string

        Returns:
            List of matching podcast records
        """
        query_lower = query.lower()
        records = self._load_records()

        return [
            record for record in records
            if query_lower in record.title.lower()
            or (record.podcast_name and query_lower in record.podcast_name.lower())
        ]

    def delete_record(self, record_id: str) -> bool:
        """Delete a record from the archive.

        Args:
            record_id: The ID of the record to delete

        Returns:
            True if deleted, False if not found
        """
        records = self._load_records()
        original_length = len(records)
        records = [r for r in records if r.id != record_id]

        if len(records) < original_length:
            self._save_records(records)
            return True
        return False

    def clear_archive(self):
        """Clear all records from the archive."""
        self._save_records([])

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the archive.

        Returns:
            Dictionary with archive statistics
        """
        records = self._load_records()

        if not records:
            return {
                "total_records": 0,
                "source_types": {},
                "total_chunks_processed": 0,
            }

        source_types = {}
        total_chunks = 0

        for record in records:
            source_types[record.source_type] = source_types.get(record.source_type, 0) + 1
            total_chunks += record.num_chunks

        return {
            "total_records": len(records),
            "source_types": source_types,
            "total_chunks_processed": total_chunks,
        }
