"""Recording metadata model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RecordingMetadata:
    """Metadata describing the source recording."""

    path: Path

    # Music metadata
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    title: str | None = None
    year: str | None = None
    genre: str | None = None
    comment: str | None = None

    # Technical information
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bits_per_sample: int | None = None

    # Album information
    track_total: int | None = None
    disc_number: int | None = None

    # Embedded artwork
    has_artwork: bool = False

    @property
    def has_album_metadata(self) -> bool:
        """Return True if enough metadata exists to identify an album."""
        return bool(self.artist and self.album)

    @property
    def display_name(self) -> str:
        """Return a friendly display name."""
        if self.artist and self.album:
            return f"{self.artist} - {self.album}"
        return self.path.stem