from pathlib import Path

from vinylsplit.audio import read_audio
from vinylsplit.detection import TrackBoundary, TrackDetector
from vinylsplit.fingerprint import Fingerprinter
from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.models import AudioInfo
from vinylsplit.splitter import SplitTrack, TrackSplitter
from vinylsplit.utils import sanitize_filename
from vinylsplit.smart_identifier import SmartIdentifier


class Pipeline:
    """Coordinates VinylSplit operations."""

    def __init__(self) -> None:
        self.fingerprinter = Fingerprinter()
        self.identifier = SmartIdentifier()
        self.detector = TrackDetector()
        self.splitter = TrackSplitter()

    def inspect(self, filename: str) -> AudioInfo:
        """Read information about an audio file."""

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        """Identify an audio recording."""

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

    def process(
        self,
        filename: str,
        output_directory: str,
    ) -> list[tuple[SplitTrack, AlbumMatch]]:
        """
        Complete VinylSplit workflow.

        1. Detect track boundaries
        2. Split the recording
        3. Identify each exported track
        4. Rename identified tracks
        """

        tracks = self.split(
            filename=filename,
            output_directory=output_directory,
        )

        results: list[tuple[SplitTrack, AlbumMatch]] = []
        failed: list[SplitTrack] = []

        for track in tracks:

            print(f"Identifying {track.path.name}...")

            try:
                match = self.identifier.identify(
                    str(track.path)
                )

            except RuntimeError:
                print(
                    f"  Could not identify {track.path.name}"
                )
                failed.append(track)
                continue

            new_name = (
                f"{track.track_number:02d} - "
                f"{sanitize_filename(match.title)}.flac"
            )

            new_path = track.path.with_name(
                new_name
            )

            track.path.rename(new_path)
            track.path = new_path

            results.append(
                (
                    track,
                    match,
                )
            )

        print()

        print(
            f"Successfully identified "
            f"{len(results)} of {len(tracks)} tracks."
        )

        if failed:

            print()
            print("Tracks requiring manual review:")

            for track in failed:
                print(f"  {track.path.name}")

        return results