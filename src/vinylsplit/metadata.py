"""Metadata models used by VinylSplit."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RecordingMetadata:
    """Metadata read directly from the source recording."""

    path: Path

    # Embedded tags
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    title: str = ""
    year: str = ""
    genre: str = ""
    comment: str = ""

    # Technical information
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bits_per_sample: int = 0

    # Album information
    track_total: int = 0
    disc_number: int = 1

    # Artwork
    has_artwork: bool = False

    @property
    def can_identify_album(self) -> bool:
        """Return True if enough metadata exists to identify the album."""
        return bool(self.artist and self.album)


@dataclass(slots=True)
class TrackMetadata:
    """Metadata for a single track."""

    number: int
    title: str
    recording_id: str
    duration: float = 0.0


@dataclass(slots=True)
class AlbumMetadata:
    """Metadata describing a MusicBrainz album release."""

    artist: str
    title: str
    year: str
    release_id: str

    cover_art_url: str = ""

    tracks: list[TrackMetadata] = field(default_factory=list)

    @property
    def track_count(self) -> int:
        """Return the number of tracks in the release."""
        return len(self.tracks)