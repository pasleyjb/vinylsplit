"""Album identification engine."""

from dataclasses import dataclass

from vinylsplit.metadata import RecordingMetadata
from vinylsplit.services.metadata_reader import MetadataReader
from vinylsplit.services.musicbrainz import (
    MusicBrainzAlbum,
    MusicBrainzService,
)
from vinylsplit.smart_identifier import SmartIdentifier


@dataclass(slots=True)
class AlbumIdentification:
    """Result of album identification."""

    artist: str
    album: str
    year: str
    release_id: str
    track_count: int
    confidence: float


class AlbumIdentifier:
    """
    Identifies an album from a recording.

    Strategy:

    1. Read embedded metadata.
    2. Search MusicBrainz using Artist + Album.
    3. Fall back to SmartIdentifier if metadata is unavailable.
    """

    def __init__(self) -> None:
        self.metadata_reader = MetadataReader()
        self.musicbrainz = MusicBrainzService()
        self.smart_identifier = SmartIdentifier()

    def identify(
        self,
        filename: str,
    ) -> AlbumIdentification | None:
        """
        Identify the album represented by a recording.

        Returns None if no confident identification can be made.
        """

        metadata = self.metadata_reader.read(filename)

        if metadata.can_identify_album:
            album = self._identify_from_metadata(metadata)

            if album is not None:
                return album

        #
        # Fingerprint fallback.
        #
        # We don't implement it yet.
        # That will become Sprint 2.
        #

        return None

    def _identify_from_metadata(
        self,
        metadata: RecordingMetadata,
    ) -> AlbumIdentification | None:
        """Identify using embedded metadata."""

        result = self.musicbrainz.search_album(
            artist=metadata.artist,
            album=metadata.album,
        )

        if result is None:
            return None

        return AlbumIdentification(
            artist=result.artist,
            album=result.album,
            year=result.year,
            release_id=result.release_id,
            track_count=result.track_count,
            confidence=1.0,
        )