"""
Archive module for tracking processed podcasts and their settings.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PodcastRecord:
    """A record of a processed podcast episode."""

    id: str  # Timestamp-based ID
    title: str
    source_type: str  # "podcast", "youtube", "upload", "batch"
    date: str  # ISO format timestamp
    settings: dict  # Processing settings (volume, speed, split_length, etc.)
    num_chunks: int
    processed_files_dir: Optional[str] = None  # Directory where processed files are stored
    podcast_name: Optional[str] = None
    audio_url: Optional[str] = None


class PodcastArchive:
    """Manages the archive of processed podcasts."""

    def __init__(self, archive_path: Optional[Path] = None):
        """Initialize archive with optional custom path."""
        if archive_path is None:
            # Default to ~/.audio_tools/archive directory
            self.archive_dir = Path.home() / ".audio_tools" / "archive"
            self.archive_file = self.archive_dir / "archive.json"
        else:
            self.archive_dir = archive_path.parent
            self.archive_file = archive_path

        # Create directory if it doesn't exist
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Create processed files storage directory
        self.processed_files_dir = self.archive_dir / "processed_files"
        self.processed_files_dir.mkdir(exist_ok=True)

        self.records: list[PodcastRecord] = []
        self._load()

    def _load(self):
        """Load archive from JSON file."""
        if self.archive_file.exists():
            try:
                with open(self.archive_file, "r") as f:
                    data = json.load(f)
                    self.records = [
                        PodcastRecord(**record) for record in data.get("records", [])
                    ]
            except (json.JSONDecodeError, TypeError) as e:
                # If file is corrupted, start fresh
                print(f"Warning: Could not load archive: {e}")
                self.records = []

    def _save(self):
        """Save archive to JSON file."""
        try:
            data = {"records": [asdict(record) for record in self.records]}
            with open(self.archive_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save archive: {e}")

    def add_record(
        self,
        title: str,
        source_type: str,
        settings: dict,
        num_chunks: int,
        processed_files_dir: Optional[str] = None,
        podcast_name: Optional[str] = None,
        audio_url: Optional[str] = None,
    ) -> PodcastRecord:
        """Add a new record to the archive."""
        # Generate timestamp-based ID
        record_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Ensure unique ID
        existing_ids = {r.id for r in self.records}
        counter = 1
        original_id = record_id
        while record_id in existing_ids:
            record_id = f"{original_id}_{counter}"
            counter += 1

        record = PodcastRecord(
            id=record_id,
            title=title,
            source_type=source_type,
            date=datetime.now().isoformat(),
            settings=settings,
            num_chunks=num_chunks,
            processed_files_dir=processed_files_dir,
            podcast_name=podcast_name,
            audio_url=audio_url,
        )

        self.records.append(record)
        self._save()
        return record

    def get_record(self, record_id: str) -> Optional[PodcastRecord]:
        """Get a record by ID."""
        for record in self.records:
            if record.id == record_id:
                return record
        return None

    def delete_record(self, record_id: str) -> bool:
        """Delete a record by ID. Also deletes associated processed files."""
        record = self.get_record(record_id)
        if record:
            # Delete processed files if they exist
            if record.processed_files_dir:
                processed_dir = Path(record.processed_files_dir)
                if processed_dir.exists():
                    try:
                        # Delete all files in the directory
                        for file in processed_dir.iterdir():
                            file.unlink()
                        # Delete the directory
                        processed_dir.rmdir()
                    except Exception as e:
                        print(f"Warning: Could not delete processed files: {e}")

            # Remove record from list
            self.records = [r for r in self.records if r.id != record_id]
            self._save()
            return True
        return False

    def clear_all(self):
        """Clear all records. Also deletes all processed files."""
        # Delete all processed files
        if self.processed_files_dir.exists():
            try:
                for record in self.records:
                    if record.processed_files_dir:
                        processed_dir = Path(record.processed_files_dir)
                        if processed_dir.exists():
                            for file in processed_dir.iterdir():
                                file.unlink()
                            processed_dir.rmdir()
            except Exception as e:
                print(f"Warning: Could not delete all processed files: {e}")

        self.records = []
        self._save()

    def search(self, query: str) -> list[PodcastRecord]:
        """Search records by title or podcast name."""
        query_lower = query.lower()
        return [
            r
            for r in self.records
            if query_lower in r.title.lower()
            or (r.podcast_name and query_lower in r.podcast_name.lower())
        ]

    def get_statistics(self) -> dict:
        """Get statistics about the archive."""
        total_records = len(self.records)
        total_chunks = sum(r.num_chunks for r in self.records)

        # Count by source type
        source_counts = {}
        for record in self.records:
            source_type = record.source_type
            source_counts[source_type] = source_counts.get(source_type, 0) + 1

        # Find most common source
        top_source = max(source_counts.items(), key=lambda x: x[1]) if source_counts else ("None", 0)

        return {
            "total_records": total_records,
            "total_chunks": total_chunks,
            "source_counts": source_counts,
            "top_source": top_source,
        }

    def get_processed_files_path(self, record_id: str) -> Optional[Path]:
        """Get the path to processed files for a record."""
        record = self.get_record(record_id)
        if record and record.processed_files_dir:
            path = Path(record.processed_files_dir)
            if path.exists():
                return path
        return None

    def create_record_storage_dir(self, record_id: str) -> Path:
        """Create and return a directory for storing processed files for a record."""
        storage_dir = self.processed_files_dir / record_id
        storage_dir.mkdir(exist_ok=True)
        return storage_dir
