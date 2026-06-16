from dataclasses import dataclass

from vinylsplit.fingerprint import Fingerprinter


@dataclass
class AlbumMatch:
    artist: str
    album: str
    year: str
    confidence: float


class AlbumLookup:
    """Album identification service."""

    def __init__(self) -> None:
        self.fingerprinter = Fingerprinter()

    def identify(self, filename: str) -> AlbumMatch:
        fingerprint = self.fingerprinter.fingerprint(filename)

        # Prevent unused-variable warnings for now.
        _ = fingerprint

        return AlbumMatch(
            artist="Unknown Artist",
            album="Unknown Album",
            year="----",
            confidence=0.0,
        )