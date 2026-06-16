from dataclasses import dataclass

from vinylsplit.fingerprint import Fingerprint
from vinylsplit.services.acoustid import AcoustIDService


@dataclass
class AlbumMatch:
    """Album identification result."""

    artist: str
    album: str
    year: str
    confidence: float


class AlbumLookup:
    """Identify albums from acoustic fingerprints."""

    def __init__(self) -> None:
        self.acoustid = AcoustIDService()

    def identify(self, fingerprint: Fingerprint) -> AlbumMatch:
        """Identify an album."""

        result = self.acoustid.lookup(fingerprint)

        return AlbumMatch(
            artist=result.artist,
            album=result.album,
            year=result.year,
            confidence=result.score,
        )