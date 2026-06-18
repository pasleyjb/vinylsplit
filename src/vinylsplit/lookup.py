from dataclasses import dataclass

from vinylsplit.fingerprint import Fingerprint, Fingerprinter
from vinylsplit.services.acoustid import AcoustIDService
from vinylsplit.services.musicbrainz import MusicBrainzService


@dataclass
class AlbumMatch:
    """Album identification result."""

    artist: str
    title: str
    album: str
    year: str
    release_id: str
    confidence: float


class AlbumLookup:
    """Identify albums from acoustic fingerprints."""

    def __init__(self) -> None:
        self.fingerprinter = Fingerprinter()
        self.acoustid = AcoustIDService()
        self.musicbrainz = MusicBrainzService()

    def identify_file(self, filename: str) -> AlbumMatch:
        """Fingerprint and identify a single audio file."""

        fingerprint = self.fingerprinter.fingerprint(filename)

        return self.identify(fingerprint)

    def identify(self, fingerprint: Fingerprint) -> AlbumMatch:
        """Identify an album from an existing fingerprint."""

        acoustid = self.acoustid.lookup(fingerprint)

        metadata = self.musicbrainz.lookup(acoustid.recording_id)

        return AlbumMatch(
            artist=metadata.artist,
            title=metadata.title,
            album=metadata.album,
            year=metadata.year,
            release_id=metadata.release_id,
            confidence=acoustid.score,
        )
