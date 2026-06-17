from pathlib import Path

from vinylsplit.audio import read_audio
from vinylsplit.detection import TrackBoundary, TrackDetector
from vinylsplit.fingerprint import Fingerprinter
from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.models import AudioInfo
from vinylsplit.splitter import SplitTrack, TrackSplitter


class Pipeline:
    """Coordinates VinylSplit operations."""

    def __init__(self) -> None:
        self.fingerprinter = Fingerprinter()
        self.lookup = AlbumLookup()
        self.detector = TrackDetector()
        self.splitter = TrackSplitter()

    def inspect(self, filename: str) -> AudioInfo:
        """Read information about an audio file."""

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        """Identify an album."""

        fingerprint = self.fingerprinter.fingerprint(filename)

        return self.lookup.identify(fingerprint)

    def analyze(self, filename: str) -> list[TrackBoundary]:
        """Analyze an audio file for track boundaries."""

        return self.detector.detect(filename)

    def split(
        self,
        filename: str,
        output_directory: str,
    ) -> list[SplitTrack]:
        """Analyze and split an audio recording."""

        boundaries = self.analyze(filename)

        return self.splitter.split(
            filename=filename,
            boundaries=boundaries,
            output_directory=output_directory,
        )