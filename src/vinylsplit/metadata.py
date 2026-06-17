from dataclasses import dataclass, field


@dataclass
class TrackMetadata:
    """Metadata for a single track."""

    number: int
    title: str
    recording_id: str


@dataclass
class AlbumMetadata:
    """Metadata for an album release."""

    artist: str
    title: str
    year: str
    release_id: str
    cover_art_url: str = ""

    tracks: list[TrackMetadata] = field(default_factory=list)