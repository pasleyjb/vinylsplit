from pathlib import Path

from vinylsplit.audio import read_audio
from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.models import AudioInfo


class Pipeline:
    """Coordinates VinylSplit operations."""

    def __init__(self) -> None:
        self.lookup = AlbumLookup()

    def inspect(self, filename: str) -> AudioInfo:
        """Read information about an audio file."""

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        """Identify an album."""

        return self.lookup.identify(filename)